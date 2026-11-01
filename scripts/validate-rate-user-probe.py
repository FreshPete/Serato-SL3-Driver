"""Validate a normal-token held-rate experiment and separate administrator trace; never launches a test."""
import argparse
import importlib.util
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
user=module('rate_trace_controls',ROOT/'scripts/validate-controls-user-probe.py')
selected=module('rate_trace_operation',ROOT/'scripts/validate-rate-host-probe.py')
base=user.base
read,digest,require,utc=user.read,user.digest,user.require,user.utc
RUNNER_INPUTS=(*base.RUNNER_INPUTS,'test-rate-host-probe.py','validate-rate-host-probe.py','validate-usbdk-rate.py',
    'test-rate-user-probe.ps1','validate-rate-user-probe.py')
BUILD=ROOT/'artifacts/build/native/native-build-Release.json'

def local(folder):
    require(folder.is_absolute() and not str(folder).startswith('\\\\') and not any(c in str(folder) for c in '\"\r\n'),'Absolute local path required')
    return folder.resolve()

def clock(value):
    if type(value) is int and value in (44100,48000):return value
    require(type(value) is str and value in ('44100','48000'),'Canonical clock required')
    return int(value)

def build_contract(worker_sha,probe_sha):
    build=read(BUILD)
    require(type(worker_sha) is str and type(probe_sha) is str and
            re.fullmatch('[0-9a-fA-F]{64}',worker_sha) and re.fullmatch('[0-9a-fA-F]{64}',probe_sha),'Invalid executable hashes')
    require(build['usbdk']['executableSha256'].lower()==worker_sha.lower() and
            build['hostProbe']['executableSha256'].lower()==probe_sha.lower(),'Current native build differs')
    feature=build['hostProbe']['rateSelection']
    require(feature['testsPassed'] is True and feature['physicalRateChangeTested'] is False and
            feature['traceRunnerPrepared'] is True,'Rate launcher build gate missing')
    pins=feature['traceScriptInputs']
    require(set(pins)==set(RUNNER_INPUTS),'Rate trace dependency inventory differs')
    for name,expected in pins.items():require(digest(ROOT/'scripts'/name).lower()==expected.lower(),'Rate dependency changed: '+name)
    require(digest(ROOT/'scripts/build-native.ps1').lower()==build['buildScriptSha256'].lower(),'Build runner changed')
    for name,expected in build['inputs'].items():require(digest(ROOT/name).lower()==expected.lower(),'Native input changed: '+name)
    for name,expected in (('sl3_usbdk.exe',worker_sha),('sl3_host_probe.exe',probe_sha)):
        require(digest(ROOT/'artifacts/build/native/Release'/name).lower()==expected.lower(),'Native image changed: '+name)
    return {'buildManifestSha256':digest(BUILD),'runnerInputs':pins}


def intent_value(target,initial,worker_sha,probe_sha):
    target,initial=clock(target),clock(initial)
    return {'schema':'sl3.rate-user.intent.v1','valid':True,'targetHz':target,'expectedInitialHz':initial,
        'workerSha256':worker_sha.lower(),'probeSha256':probe_sha.lower(),**build_contract(worker_sha,probe_sha)}

def admission(folder):
    folder=local(folder);intent=read(folder/'intent.json')
    require(type(intent['targetHz']) is int and type(intent['expectedInitialHz']) is int,'Intent clocks must be integers')
    require(intent==intent_value(intent['targetHz'],intent['expectedInitialHz'],intent['workerSha256'],intent['probeSha256']),
        'Rate intent or tested runtime changed')
    return user.admission(folder)

def validate(folder,worker_sha,probe_sha):
    folder=local(folder);admitted=admission(folder)
    record,context,trace=read(folder/'run.json'),read(folder/'context.json'),read(folder/'trace/capture.json')
    intent=read(folder/'intent.json')
    require(intent==intent_value(intent['targetHz'],intent['expectedInitialHz'],worker_sha,probe_sha),'Reviewed intent/build no longer validates')
    require(record['schema']=='sl3.rate-user.traced-run.v1' and record['completed'] is True and record['error'] is None,
            'Incomplete rate run')
    base.flags(record,('splitUserContext','traceCleanupConfirmed','secureBootBefore','secureBootAfter','recoveryConfirmed','withUsbDkLifecycle'),
               ('withUsbIdentity','driverChanges','securityChanges','asioRegistration','automaticRetry'))
    require(not record.get('probeTimedOut',False) and not record.get('probeContainmentRequested',False) and not record.get('tokenQueryError')
            and not record.get('evidencePreservationError') and not record.get('recoveryError'),
            'Bounded probe/token contract failed')
    require(type(record['probeExitCode']) is int and type(record['traceExitCode']) is int and
            record['probeExitCode']==record['traceExitCode']==0,'Rate probe/trace failed')
    for key in ('workerSha256','probeSha256','buildManifestSha256','runnerInputs','targetHz','expectedInitialHz'):
        require(record[key]==intent[key],'Run differs from immutable intent: '+key)
    require(context['completed'] is True and context['error'] is None and context['probeLaunched'] is False and
            context['securityChanges'] is False and context['testProcessesAfter']==[],'Collector did not finish cleanly')
    old_context=read(folder/'admitted-context.json');prefix=read(folder/'admitted-trace.json')
    for key in ('schema','startedUtc','administratorToken','producerSha256','testProcessesBefore','beforeStateSha256'):
        require(context[key]==old_context[key],'Collector context changed identity')
    require(context.get('withStateObserver',False) is old_context.get('withStateObserver',False),'Observer selection changed after admission')
    for key in ('collectorPid','collectorCreationFileTimeUtc','collectorImagePath','producerSha256','session','startedUtc'):
        require(trace[key]==prefix[key],'Collector identity changed after admission')
    require(record['traceSeconds']==context['traceSeconds']==old_context['traceSeconds']==trace['plan']['durationSeconds']==60,
            'Rate scenario requires a fixed sixty-second window')
    require(all(type(x) is int for x in (record['traceSeconds'],context['traceSeconds'],old_context['traceSeconds'],trace['plan']['durationSeconds'])) and (utc(trace['stoppedUtc'])-utc(record['probeCompletedUtc'])).total_seconds()>=12,
            'Rate trace lacks twelve seconds after probe retirement')
    launch_path=folder/'launch-admission.json'
    require(digest(launch_path).lower()==record['launchAdmissionSha256'].lower(),'Launch observation binding differs')
    launch=read(launch_path)
    user.admission_values(launch['trace'],old_context,read(folder/'before-state.json'),launch['process'],launch['checkedUtc'])
    for key in ('collectorPid','collectorCreationFileTimeUtc','collectorImagePath','producerSha256','session','startedUtc'):
        require(launch['trace'][key]==prefix[key],'Collector changed at launch observation')
    require(utc(admitted['checkedUtc'])<=utc(launch['checkedUtc'])<=utc(record['probeStartedUtc']) and
        (utc(record['probeStartedUtc'])-utc(launch['checkedUtc'])).total_seconds()<=2,'Launch observation expired')
    require(utc(trace['startedUtc'])<=utc(record['probeStartedUtc'])<=utc(record['probeCompletedUtc'])<=utc(trace['stoppedUtc'])
            <=utc(read(folder/'after-state.json')['collectedUtc'])<=utc(context['completedUtc'])<=utc(record['completedUtc']),
            'Probe/recovery outside collector window/order')
    for name,key in (('intent.json','intentRecordSha256'),('context.json','contextSha256'),('admitted-trace.json','admittedTraceSha256'),
                     ('admitted-context.json','admittedContextSha256'),('collector-process.json','collectorProcessSha256'),
                     ('before-state.json','beforeStateSha256'),('after-state.json','afterStateSha256'),('trace/capture.json','traceRecordSha256'),
                     ('probe/request.json','requestRecordSha256'),('probe/probe.json','probeRecordSha256'),('probe-validation.json','probeValidationSha256'),('probe/worker-1.tsv.rate/rate.json','nativeRateRecordSha256')):
        require(digest(folder/name).lower()==record[key].lower(),'Rate file binding differs: '+name)
    for key in ('beforeStateSha256','afterStateSha256','traceRecordSha256'):require(context[key].lower()==record[key].lower(),'Collector snapshot binding differs')
    before,after=read(folder/'before-state.json'),read(folder/'after-state.json')
    require(before['secureBoot'] is True and after['secureBoot'] is True and
            base.physical.state_contract(before)==base.physical.state_contract(after),'Selected Windows/security recovery differs')
    stats=base.physical.capture_validator.trace_statistics(folder/'events.xml')
    require(stats==record['traceStats'] and stats['eventsLost']==stats['buffersLost']==0 and stats['session']==trace['session'],
            'Trace statistics/session/loss differs')
    lifecycle=base.lifecycle_trace(folder/'trace',trace,True)
    require(trace['status']=='window completed' and sum(row['arguments']==['delete','-n',trace['session']] and
            type(row['exitCode']) is int and row['exitCode']==0 for row in trace['commands'])==1,'Trace cleanup not confirmed')
    etls=list((folder/'trace').glob('*.etl'))
    require(len(etls)==1 and digest(etls[0]).lower()==record['etlSha256'].lower(),'ETL binding differs')
    native_rate=read(folder/'probe/worker-1.tsv.rate/rate.json')
    require(utc(record['probeStartedUtc'])<=utc(native_rate['utc'])<=utc(record['probeCompletedUtc']),'Native rate observation is outside probe lifetime')
    result=selected.probe(folder/'probe',worker_sha)
    data=read(folder/'probe/probe.json')
    require(result==read(folder/'probe-validation.json'),'Saved selection validation differs')
    require(result['targetRateHz']==intent['targetHz'] and data['expected_initial_rate_hz']==intent['expectedInitialHz'],
        'Rate selection differs from reviewed target/initial clock')
    require(record['rateRestorationVerified'] is False,'Windows recovery does not restore the prior device rate')
    user.tokens(record,result['nativeJournal']['workerPid'])
    require(admitted['collectorPid'] not in {v['process']['pid'] for v in record['userProcesses'].values()},'Collector shared a probe role')
    for role,expected in (('worker',worker_sha),('probe',probe_sha)):
        path=ROOT/'artifacts/build/native/Release'/('sl3_usbdk.exe' if role=='worker' else 'sl3_host_probe.exe')
        require(str(path).casefold()==record[role+'ImagePath'].casefold() and digest(path).lower()==expected.lower(),'Native image/path changed')
    return {'valid':True,'scope':'One normal-token held-rate result, shared loss-checked USB trace and selected Windows recovery; no payload correlation, rate restoration, audio or Serato acceptance',
            'probe':result,'runRecordSha256':digest(folder/'run.json'),'intentRecordSha256':digest(folder/'intent.json'),
            'traceStats':stats,'lifecycleTrace':lifecycle,'collectorAdmission':admitted,'stateObserver':user.state_observer(folder,trace),
            'nonElevatedParentProbeAndWorker':True,'secureBootBeforeAndAfter':True,'recoveryConfirmed':True,
            'rateRestorationVerified':False,'usbPayloadCorrelationVerified':False,'continuousUsbIdentityVerified':False,'analogueSignalVerified':False,'audioStreamingVerified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--intent',action='store_true');mode.add_argument('--admission',type=Path);mode.add_argument('--run',type=Path)
    parser.add_argument('--target');parser.add_argument('--expected-initial');parser.add_argument('--worker-sha256');parser.add_argument('--probe-sha256');args=parser.parse_args()
    if args.intent:
        require(args.worker_sha256 and args.probe_sha256,'Expected images required')
        result=intent_value(args.target,args.expected_initial,args.worker_sha256,args.probe_sha256)
    elif args.admission:result=admission(args.admission)
    else:result=validate(args.run,args.worker_sha256,args.probe_sha256)
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as error:
        print(json.dumps({'valid':False,'error':str(error)}));raise SystemExit(1)
