"""Validate split-role controls evidence; saved records only, no USB access."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('controls_user_base', ROOT/'scripts/validate-controls-host-probe.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
read, digest, require = base.read, base.digest, base.require
utc = base.physical.capture_validator.utc


def process(value, image=None, token=False):
    require(type(value['pid']) is int and 0 < value['pid'] < 2**32 and value['alive'] is True,
            'Process was not observed alive')
    require(type(value['creationFileTimeUtc']) is str and re.fullmatch(r'[1-9][0-9]{16,17}', value['creationFileTimeUtc']),
            'Invalid process creation time')
    require(type(value['imagePath']) is str and value['imagePath'], 'Missing process image')
    if image is not None:
        require(value['imagePath'].casefold() == str(image).casefold(), 'Unexpected process image')
    if token:
        require(value['tokenQueried'] is True and value['elevated'] is False and
                type(value['elevationType']) is int and value['elevationType'] in (1, 3),
                'Process token was not queried as non-elevated')
    else:
        require(value['tokenQueried'] is False and value['elevated'] is None and value['elevationType'] is None,
                'Collector query must not require elevated token access')


def admission_values(trace, context, before, observed, checked):
    process(observed, trace['collectorImagePath'])
    require(observed['pid'] == trace['collectorPid'] and
            observed['creationFileTimeUtc'] == trace['collectorCreationFileTimeUtc'],
            'Collector exited or process identity was reused')
    duration = context.get('traceSeconds', 60)
    require(type(duration) is int and 20 <= duration <= 60, 'Invalid explicit trace duration')
    require(type(trace['plan']['durationSeconds']) is int and trace['plan']['durationSeconds'] == duration and
            trace['status'] == 'recording' and
            trace['plan']['withUsbDkLifecycle'] is True, 'Trace not ready in required mode')
    require(re.fullmatch(r'SL3Startup-[0-9a-f]{32}', trace['session']), 'Unexpected trace session')
    require(0 <= (utc(checked)-utc(trace['startedUtc'])).total_seconds() <= min(10, duration-15),
            'Trace admission window expired')
    require(context['schema'] == 'sl3.controls-user.context.v1' and context['completed'] is False and
            context['error'] is None and context['administratorToken'] is True and
            context['probeLaunched'] is False and context['securityChanges'] is False,
            'Collector context is not ready')
    require(utc(context['startedUtc']) <= utc(before['collectedUtc']) <= utc(trace['startedUtc']),
            'Baseline outside collector window')
    require(before['secureBoot'] is True and len(before['devices']) == 1 and
            before['devices'][0]['device']['InstanceId'].upper() == r'USB\VID_1CC5&PID_0001\SL3.01.00',
            'Missing enabled-security resting SL3 baseline')
    require(context['testProcessesBefore'] == [], 'A previous test process remains')
    requested=trace['plan'].get('withStateObserver',False)
    require(type(requested) is bool and context.get('withStateObserver',False) is requested,'State observer selection differs')
    if requested:
        require(trace['plan']['realTimeDelivery'] is True and trace['stateObserver']['consumerAttemptVerified'] is True and
                trace['stateObserver']['readinessAdmission'] is False,'State consumer attempt was not prepared')
    update = ['update', 'trace', '-n', trace['session'], '-p',
              '{88e1661f-48b6-410f-b096-ba84e9f0656f}', '0x650', '4']
    configured = [n for n, row in enumerate(trace['commands']) if row['arguments'] == update and
                  type(row['exitCode']) is int and row['exitCode'] == 0]
    started = [n for n, row in enumerate(trace['commands']) if row['arguments'] == ['start', '-n', trace['session']] and
               type(row['exitCode']) is int and row['exitCode'] == 0]
    require(len(configured) == len(started) == 1 and configured[0] < started[0], 'WPP provider not configured before start')


def admission(folder):
    trace, context = read(folder/'admitted-trace.json'), read(folder/'admitted-context.json')
    observed = read(folder/'collector-process.json')
    checked = observed['checkedUtc']
    admission_values(trace, context, read(folder/'before-state.json'), observed['process'], checked)
    for obj, name in ((trace, 'capture-usb-startup.ps1'), (context, 'capture-controls-user-context.ps1')):
        require(obj['producerSha256'].lower() == digest(ROOT/'scripts'/name).lower(), 'Collector source changed')
    require(context['beforeStateSha256'].lower() == digest(folder/'before-state.json').lower(), 'Baseline hash differs')
    return {'valid': True, 'checkedUtc': checked, 'collectorPid': observed['process']['pid'],
            'collectorCreationFileTimeUtc': observed['process']['creationFileTimeUtc'], 'session': trace['session']}


def tokens(record, native_pid):
    values = record['userProcesses']
    require(set(values) == {'parent', 'probe', 'worker'}, 'Missing process token evidence')
    for role, value in values.items():
        process(value['process'], record[role+'ImagePath'], True)
        at = utc(value['checkedUtc'])
        if role != 'parent':
            require(utc(record['probeStartedUtc']) <= at <= utc(record['probeCompletedUtc']), 'Token query outside probe window')
            created = int(value['process']['creationFileTimeUtc'])
            start = int((utc(record['probeStartedUtc'])-datetime(1601, 1, 1, tzinfo=timezone.utc)).total_seconds()*10**7)
            queried = int((at-datetime(1601, 1, 1, tzinfo=timezone.utc)).total_seconds()*10**7)
            require(start-10_000 <= created <= queried, 'Process creation is outside the launch/query window')
    require(len({value['process']['pid'] for value in values.values()}) == 3, 'Process roles share a PID')
    require(values['probe']['process']['pid'] == record['probePid'] and
            values['worker']['process']['pid'] == native_pid, 'Probe/worker token PID differs')


def state_observer(folder,trace):
    requested=trace['plan'].get('withStateObserver',False)
    require(type(requested) is bool,'Invalid observer option')
    if not requested:
        require('stateObserver' not in trace,'Unexpected observer evidence');return None
    spec=importlib.util.spec_from_file_location('live_capture_validator',ROOT/'scripts/validate-usb-state-capture.py')
    validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
    saved=folder/'trace/state-observer-validation.json'
    require(digest(saved).lower()==trace['stateObserver']['validationSha256'].lower() and
            read(saved)==validator.validate(folder/'trace'),'Saved live consumer validation differs')
    return validator.validate(folder/'trace',folder/'events.xml')


def validate(folder, worker_sha, probe_sha, scope=False, broker_scope=False, input_record=False):
    require(sum(bool(x) for x in (scope, broker_scope, input_record)) <= 1, 'Conflicting trace scenarios')
    admitted = admission(folder)
    record, context, trace = read(folder/'run.json'), read(folder/'context.json'), read(folder/'trace/capture.json')
    if input_record:require(record.get('scenario')=='InputRecord' and record['traceSeconds']==60,'Input recording scenario/duration differs')
    if broker_scope:require(record.get('scenario')=='BrokerScope' and record['traceSeconds']==60,'Broker scope scenario/duration differs')
    if scope:require(record.get('scenario')=='Scope' and record['traceSeconds']==60,'Scope scenario/duration differs')
    require(record['splitUserContext'] is True and context['completed'] is True and context['error'] is None and
            context['probeLaunched'] is False and context['securityChanges'] is False and
            context['testProcessesAfter'] == [], 'Collector context did not complete cleanly')
    require(not record.get('probeTimedOut', False) and not record.get('probeContainmentRequested', False) and
            not record.get('tokenQueryError'), 'Probe token query or bounded retirement failed')
    old_context = read(folder/'admitted-context.json')
    require(context.get('traceSeconds',60) == old_context.get('traceSeconds',60) ==
            record.get('traceSeconds',60) == trace['plan']['durationSeconds'], 'Trace duration changed after admission')
    if 'traceSeconds' in old_context:
        require((utc(trace['stoppedUtc'])-utc(record['probeCompletedUtc'])).total_seconds() >= 12,
                'Trace did not retain twelve seconds after probe retirement')
    for key in ('schema', 'startedUtc', 'administratorToken', 'producerSha256', 'testProcessesBefore', 'beforeStateSha256'):
        require(context[key] == old_context[key], 'Collector context changed identity')
    require(context.get('withStateObserver',False) is old_context.get('withStateObserver',False),'Observer selection changed after admission')
    require(utc(record['probeCompletedUtc']) <= utc(read(folder/'after-state.json')['collectedUtc']) <= utc(context['completedUtc']),
            'After snapshot precedes probe retirement')
    for name, key in (('context.json', 'contextSha256'), ('admitted-trace.json', 'admittedTraceSha256'),
                      ('admitted-context.json', 'admittedContextSha256'), ('collector-process.json', 'collectorProcessSha256')):
        require(digest(folder/name).lower() == record[key].lower(), 'Split-role record binding differs: '+name)
    prefix = read(folder/'admitted-trace.json')
    for key in ('collectorPid', 'collectorCreationFileTimeUtc', 'collectorImagePath', 'producerSha256', 'session', 'startedUtc'):
        require(trace[key] == prefix[key], 'Collector identity changed after admission')
    launch_checked = admitted['checkedUtc']
    if 'launchAdmissionSha256' in record:
        launch_path=folder/'launch-admission.json'
        require(digest(launch_path).lower()==record['launchAdmissionSha256'].lower(),'Launch observation binding differs')
        launch=read(launch_path)
        admission_values(launch['trace'],old_context,read(folder/'before-state.json'),launch['process'],launch['checkedUtc'])
        for key in ('collectorPid','collectorCreationFileTimeUtc','collectorImagePath','producerSha256','session','startedUtc'):
            require(launch['trace'][key]==prefix[key],'Collector changed at launch observation')
        require(utc(admitted['checkedUtc'])<=utc(launch['checkedUtc']),'Launch observation precedes initial admission')
        launch_checked=launch['checkedUtc']
    require(utc(launch_checked) <= utc(record['probeStartedUtc']) and
            (utc(record['probeStartedUtc'])-utc(launch_checked)).total_seconds() <= 2,
            'Admission was not fresh at probe launch')
    for key, filename in (('beforeStateSha256', 'before-state.json'), ('afterStateSha256', 'after-state.json'),
                          ('traceRecordSha256', 'trace/capture.json')):
        require(context[key].lower() == digest(folder/filename).lower() == record[key].lower(), 'Collector snapshot binding differs')
    result = base.traced(folder, worker_sha, probe_sha, input_record=True) if input_record else base.traced(folder, worker_sha, probe_sha, broker_scope=True) if broker_scope else (base.traced(folder, worker_sha, probe_sha, scope=True) if scope else base.traced(folder, worker_sha, probe_sha))
    result['stateObserver']=state_observer(folder,trace)
    tokens(record, result['probe']['nativeJournal']['workerPid'])
    if broker_scope:
        session=(folder/'probe/broker-session.txt').read_text(encoding='ascii').splitlines()
        observed=record['userProcesses']['probe']['process']
        require(session[2]=='server_pid='+str(observed['pid']) and session[3]=='server_created='+observed['creationFileTimeUtc'],
                'Broker session does not belong to observed probe process')
    build = read(ROOT/'artifacts/build/native/native-build-Release.json')
    require(record['buildManifestSha256'].lower() == digest(ROOT/'artifacts/build/native/native-build-Release.json').lower(),
            'Build manifest changed')
    tested=build['inputRecordProbe'] if input_record else build['brokerScopeProbe'] if broker_scope else (build['scopeProbe'] if scope else build['hostProbe']['controls'])
    require(record['runnerInputs'] == tested['scriptInputs'], 'Tested script set differs')
    require(build['usbdk']['executableSha256'].lower() == worker_sha.lower() and
            (build['inputRecordProbe'] if input_record else build['brokerScopeProbe'] if broker_scope else (build['scopeProbe'] if scope else build['hostProbe']))['executableSha256'].lower() == probe_sha.lower(), 'Tested native build differs')
    for role, expected in (('worker', worker_sha), ('probe', probe_sha)):
        require(digest(Path(record[role+'ImagePath'])).lower() == expected.lower(), 'Native image changed')
    result.update(nonElevatedParentProbeAndWorker=True, collectorAdmission=admitted,
                  scope=('Normal-token three-second input prefix with silent output, shared trace and selected recovery; no analogue, timing or Serato/DVS claim' if input_record else 'Normal-token broker metadata, three client processes, shared trace and selected recovery only; no streaming, COM or Serato/DVS claim' if broker_scope else 'Normal-token facade scope/clock, shared trace and selected recovery only; no COM, streaming or Serato/DVS claim' if scope else
                         'Normal-token controls/ownership, shared trace and selected recovery only; no streaming or Serato/DVS claim'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--admission', type=Path)
    mode.add_argument('--run', type=Path)
    parser.add_argument('--worker-sha256')
    parser.add_argument('--probe-sha256')
    scenario=parser.add_mutually_exclusive_group()
    scenario.add_argument('--scope',action='store_true')
    scenario.add_argument('--broker-scope',action='store_true')
    scenario.add_argument('--input-record',action='store_true')
    args = parser.parse_args()
    require(args.admission or (args.worker_sha256 and args.probe_sha256), 'Native executable hashes required')
    if args.admission:result=admission(args.admission)
    else:result=validate(args.run,args.worker_sha256,args.probe_sha256,scope=args.scope,broker_scope=args.broker_scope,input_record=args.input_record)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        print(json.dumps({'valid': False, 'error': str(error)}))
        raise SystemExit(1)
