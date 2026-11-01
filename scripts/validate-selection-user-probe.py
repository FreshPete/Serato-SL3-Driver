"""Offline admission and final evidence checks for one normal-token setting test."""
import argparse
import importlib.util
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


user=module('selection_user_controls',ROOT/'scripts/validate-controls-user-probe.py')
selected=module('selection_user_operation',ROOT/'scripts/validate-selection-host-probe.py')
base=user.base
read,digest,require,utc=user.read,user.digest,user.require,user.utc
RUNNER_INPUTS=(*base.RUNNER_INPUTS,'test-selection-host-probe.py','validate-selection-host-probe.py',
               'test-selection-user-probe.ps1','validate-selection-user-probe.py')
BUILD=ROOT/'artifacts/build/native/native-build-Release.json'


def local(folder):
    require(folder.is_absolute() and not str(folder).startswith('\\\\') and not any(c in str(folder) for c in '\"\r\n'),
            'Absolute local evidence path required')
    return folder.resolve()


def target(text):
    require(type(text) is str and re.fullmatch(r'(sensitivity:[0-2]:(?:[0-9]|1[0-5])|through:[0-2]:[01])',text),
            'One canonical sensitivity/through target required')
    setting,group,value=text.split(':');return {'setting':setting,'group':int(group),'value':int(value)}


def build_contract(worker_sha,probe_sha):
    build=read(BUILD)
    require(type(worker_sha) is str and type(probe_sha) is str and
            re.fullmatch('[0-9a-fA-F]{64}',worker_sha) and re.fullmatch('[0-9a-fA-F]{64}',probe_sha),'Invalid executable hashes')
    require(build['usbdk']['executableSha256'].lower()==worker_sha.lower() and
            build['hostProbe']['executableSha256'].lower()==probe_sha.lower(),'Current native build differs')
    feature=build['hostProbe']['selection']
    require(feature['simulatedLifecyclePassed'] is True and feature['nativeSettingRunDuringBuild'] is False and
            feature['supervisedLauncherPrepared'] is True,'Setting launcher build gate missing')
    pins=feature['traceScriptInputs']
    require(set(pins)==set(RUNNER_INPUTS),'Setting trace dependency inventory differs')
    for name,expected in pins.items():require(digest(ROOT/'scripts'/name).lower()==expected.lower(),'Setting dependency changed: '+name)
    require(digest(ROOT/'scripts/build-native.ps1').lower()==build['buildScriptSha256'].lower(),'Build runner changed')
    for name,expected in build['inputs'].items():require(digest(ROOT/name).lower()==expected.lower(),'Native input changed: '+name)
    for name,expected in (('sl3_usbdk.exe',worker_sha),('sl3_host_probe.exe',probe_sha)):
        require(digest(ROOT/'artifacts/build/native/Release'/name).lower()==expected.lower(),'Native image changed: '+name)
    return {'buildManifestSha256':digest(BUILD),'runnerInputs':pins}


def prerequisite(folder,requested,worker_sha,probe_sha):
    folder=local(folder);selected.target(requested)
    build=build_contract(worker_sha,probe_sha)
    run=read(folder/'run.json')
    require(run.get('schema')=='sl3.controls-host.traced-run.v1' and run.get('splitUserContext') is True and
            run.get('completed') is True,'Completed split-role read-only controls run required')
    checked=user.validate(folder,worker_sha,probe_sha)
    require(checked['valid'] is True and checked['nonElevatedParentProbeAndWorker'] is True and
            checked['probe']['simulated'] is False,'Actual normal-token read-only prerequisite required')
    require(utc(read(folder/'after-state.json')['collectedUtc'])<=utc(read(folder/'context.json')['completedUtc'])<=utc(run['completedUtc']),
            'Read-only prerequisite was not finished after recovery')
    return {'schema':'sl3.selection-user.intent.v1','valid':True,
            'scope':'Validated current-build read-only prerequisite and exact intended target; not a setting result',
            'target':requested,'workerSha256':worker_sha.lower(),'probeSha256':probe_sha.lower(),**build,
            'baselineDirectory':str(folder),'baselineCompletedUtc':run['completedUtc'],
            'baselineFiles':{name:digest(folder/name) for name in ('run.json','probe/probe.json','before-state.json','after-state.json')},
            'reviewedRawControls':checked['probe']['rawControls'],'reviewedRateHz':checked['probe']['rateHz']}


def admission(folder):
    folder=local(folder);intent=read(folder/'intent.json')
    require(intent['schema']=='sl3.selection-user.intent.v1' and intent['valid'] is True,'Missing validated selection intent')
    selected.target(intent['target'])
    require(build_contract(intent['workerSha256'],intent['probeSha256'])==
            {key:intent[key] for key in ('buildManifestSha256','runnerInputs')},'Build changed after prerequisite validation')
    baseline=local(Path(intent['baselineDirectory']))
    require(baseline!=folder and not baseline.is_relative_to(folder) and not folder.is_relative_to(baseline),'Evidence directories overlap')
    require(set(intent['baselineFiles'])=={'run.json','probe/probe.json','before-state.json','after-state.json'},'Baseline binding inventory differs')
    for name,expected in intent['baselineFiles'].items():require(digest(baseline/name)==expected,'Read-only baseline changed: '+name)
    raw=read(baseline/'probe/probe.json')
    require(raw['schema']=='sl3.controls-host-probe.v1' and raw['simulated'] is False and raw['successful'] is True and
            raw['raw_controls']==intent['reviewedRawControls'] and raw['acquisition']['rate_hz']==intent['reviewedRateHz'],
            'Reviewed table/rate differs from native read-only prerequisite')
    require(type(intent['reviewedRawControls']) is list and len(intent['reviewedRawControls'])==22 and
            all(base.uint(x,256) for x in intent['reviewedRawControls']),'Invalid reviewed table')
    before=read(folder/'before-state.json');prior=read(baseline/'after-state.json')
    require(base.physical.state_contract(prior)==base.physical.state_contract(before),'Resting state differs from reviewed baseline recovery')
    require(utc(read(baseline/'run.json')['completedUtc'])==utc(intent['baselineCompletedUtc'])<=utc(before['collectedUtc']),
            'Baseline completion is outside prerequisite order')
    return user.admission(folder)


def validate(folder,worker_sha,probe_sha):
    folder=local(folder);admitted=admission(folder)
    record,context,trace=read(folder/'run.json'),read(folder/'context.json'),read(folder/'trace/capture.json')
    intent=read(folder/'intent.json')
    require(intent==prerequisite(Path(intent['baselineDirectory']),intent['target'],worker_sha,probe_sha),
            'Reviewed prerequisite no longer validates')
    require(record['schema']=='sl3.selection-user.traced-run.v1' and record['completed'] is True and record['error'] is None,
            'Incomplete setting run')
    base.flags(record,('splitUserContext','traceCleanupConfirmed','secureBootBefore','secureBootAfter','recoveryConfirmed','withUsbDkLifecycle'),
               ('withUsbIdentity','driverChanges','securityChanges','asioRegistration','automaticRetry'))
    require(not record.get('probeTimedOut',False) and not record.get('probeContainmentRequested',False) and not record.get('tokenQueryError')
            and not record.get('evidencePreservationError') and not record.get('recoveryError'),
            'Bounded probe/token contract failed')
    require(type(record['probeExitCode']) is int and type(record['traceExitCode']) is int and
            record['probeExitCode']==record['traceExitCode']==0,'Setting probe/trace failed')
    for key in ('workerSha256','probeSha256','buildManifestSha256','runnerInputs','target'):
        require(record[key]==intent[key],'Run differs from immutable intent: '+key)
    require(context['completed'] is True and context['error'] is None and context['probeLaunched'] is False and
            context['securityChanges'] is False and context['testProcessesAfter']==[],'Collector did not finish cleanly')
    old_context=read(folder/'admitted-context.json');prefix=read(folder/'admitted-trace.json')
    for key in ('schema','startedUtc','administratorToken','producerSha256','testProcessesBefore','beforeStateSha256'):
        require(context[key]==old_context[key],'Collector context changed identity')
    require(context.get('withStateObserver',False) is old_context.get('withStateObserver',False),'Observer selection changed after admission')
    for key in ('collectorPid','collectorCreationFileTimeUtc','collectorImagePath','producerSha256','session','startedUtc'):
        require(trace[key]==prefix[key],'Collector identity changed after admission')
    require(0<=(utc(record['probeStartedUtc'])-utc(admitted['checkedUtc'])).total_seconds()<=2,'Admission expired before launch')
    require(utc(trace['startedUtc'])<=utc(record['probeStartedUtc'])<=utc(record['probeCompletedUtc'])<=utc(trace['stoppedUtc'])
            <=utc(read(folder/'after-state.json')['collectedUtc'])<=utc(context['completedUtc'])<=utc(record['completedUtc']),
            'Probe/recovery outside collector window/order')
    for name,key in (('intent.json','intentRecordSha256'),('context.json','contextSha256'),('admitted-trace.json','admittedTraceSha256'),
                     ('admitted-context.json','admittedContextSha256'),('collector-process.json','collectorProcessSha256'),
                     ('before-state.json','beforeStateSha256'),('after-state.json','afterStateSha256'),('trace/capture.json','traceRecordSha256'),
                     ('probe/request.json','requestRecordSha256'),('probe/probe.json','probeRecordSha256'),('probe-validation.json','probeValidationSha256')):
        require(digest(folder/name).lower()==record[key].lower(),'Setting file binding differs: '+name)
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
    result=selected.probe(folder/'probe',worker_sha)
    data=read(folder/'probe/probe.json')
    require(result==read(folder/'probe-validation.json'),'Saved selection validation differs')
    require(result['target']==intent['target'] and data['reviewed_baseline_raw_controls']==intent['reviewedRawControls'] and
            data['acquisition']['rate_hz']==intent['reviewedRateHz'],'Selection differs from reviewed table/target/rate')
    user.tokens(record,result['nativeJournal']['workerPid'])
    require(admitted['collectorPid'] not in {v['process']['pid'] for v in record['userProcesses'].values()},'Collector shared a probe role')
    for role,expected in (('worker',worker_sha),('probe',probe_sha)):
        path=ROOT/'artifacts/build/native/Release'/('sl3_usbdk.exe' if role=='worker' else 'sl3_host_probe.exe')
        require(str(path).casefold()==record[role+'ImagePath'].casefold() and digest(path).lower()==expected.lower(),'Native image/path changed')
    return {'valid':True,'scope':'One normal-token setting result, shared USB trace and selected Windows recovery; no analogue/audio/Serato acceptance',
            'probe':result,'runRecordSha256':digest(folder/'run.json'),'intentRecordSha256':digest(folder/'intent.json'),
            'traceStats':stats,'lifecycleTrace':lifecycle,'collectorAdmission':admitted,'stateObserver':user.state_observer(folder,trace),
            'nonElevatedParentProbeAndWorker':True,'secureBootBeforeAndAfter':True,'recoveryConfirmed':True,
            'continuousUsbIdentityVerified':False,'analogueSignalVerified':False,'audioStreamingVerified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prerequisite',type=Path);mode.add_argument('--admission',type=Path);mode.add_argument('--run',type=Path)
    parser.add_argument('--target');parser.add_argument('--worker-sha256');parser.add_argument('--probe-sha256');args=parser.parse_args()
    if args.admission:result=admission(args.admission)
    else:
        require(args.worker_sha256 and args.probe_sha256,'Expected native hashes required')
        result=(prerequisite(args.prerequisite,target(args.target),args.worker_sha256,args.probe_sha256) if args.prerequisite
                else validate(args.run,args.worker_sha256,args.probe_sha256))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as error:
        print(json.dumps({'valid':False,'error':str(error)}));raise SystemExit(1)
