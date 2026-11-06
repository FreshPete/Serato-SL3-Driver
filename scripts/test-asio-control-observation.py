"""Validate control-log interpretation, then capture only an owned simulated ASIO fixture."""
import copy
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
API=runpy.run_path(str(ROOT/'scripts/inspect-asio-control-trace.py'))
require=API['require'];sha=lambda path:API['sha'](path.read_bytes())


def synthetic():
    marker={'schema':'sl3.asio-owned-session.v1','pid':123,'stopStatus':0,'eventsLost':0,'buffersLost':0,'complete':True,'hardwareStateAssessed':False}
    cases=[]
    def events(op,obj,call,result,tid=7):
        payload={'schema':'sl3.asio-call.v1','build':'session_fixture','op':op,'object':obj,'call':call,'result':0,'a0':0,'a1':0,'qpc':100+call,'frequency':10000000,'elapsedQpc':0,'phase':'begin'}
        begin={'schema':'sl3.asio-etw-record.v1','pid':123,'tid':tid,'timestampFileTime':str(1000+10*call),'payload':payload}
        end=copy.deepcopy(begin);end['timestampFileTime']=str(1001+10*call);end['payload'].update(phase='end',result=result,elapsedQpc=1)
        return [begin,end]
    rows=events(1,0,1,0)+events(2,1,2,1)+events(16,1,3,0)+events(6,1,4,0)+events(7,1,5,0)
    def summary(value=None,m=None):
        selected=rows if value is None else value
        decoder={'schema':'sl3.asio-etl-decode.v1','pid':123,'decodedEvents':len(selected),'readerReportedLosses':0,'traceControllerStarted':False,'deviceAccess':False,'seratoExecuted':False}
        return API['summarize'](selected,123,m or marker,decoder)
    def good(name,operation):
        operation();cases.append({'name':name,'passed':True})
    def refused(name,operation):
        try:operation()
        except ValueError:cases.append({'name':name,'passed':True})
        else:raise AssertionError('Unexpected admission: '+name)
    s=summary();good('successful-control-stages-not-physical-audio',lambda:require(s['objects'][0]['startReturnSuccessObserved'] and not s['physicalAudioVerified'] and not s['callbackProgressRecorded'],'Control result scope'))
    one=summary(events(2,1,2,0)+events(2,2,3,1,9)+events(6,2,4,0,9))
    good('objects-remain-separate',lambda:require(one['objects'][0]['initRejectionObserved'] and not one['objects'][0]['startReturnSuccessObserved'] and one['objects'][1]['startReturnSuccessObserved'],'Object separation'))
    a=events(2,1,2,1);b=events(2,2,3,1,9)
    good('interleaved-control-threads',lambda:require(summary([a[0],b[0],b[1],a[1]])['completeCallPairs']==2,'Pair interleaved threads by call identity'))
    s=summary(events(2,1,2,1)[:1]);good('begin-does-not-prove-init-success',lambda:require(not s['objects'] and s['unpairedCalls'][0]['operation']=='init' and not s['controlMetadataComplete'],'Missing init terminal'))
    a=events(2,1,2,1);a[1]['payload'].update(phase='abandoned',result=0);s=summary(a)
    good('abandoned-call-remains-incomplete',lambda:require(s['abandonedCalls']==[2] and not s['controlMetadataComplete'] and not s['objects'],'Abandoned is not success'))
    s=summary(events(2,1,2,1)[1:]);good('orphan-terminal-not-promoted',lambda:require(s['orphanTerminals']==[2] and not s['objects'],'Orphan result needs begin'))
    lossy={**marker,'complete':False,'eventsLost':1};good('reported-loss-prevents-completeness',lambda:require(not summary(m=lossy)['controlMetadataComplete'],'Lossy logger'))
    good('budget-limit-prevents-completeness',lambda:require(not summary(events(1,0,4096,0))['controlMetadataComplete'],'Saturated budget'))
    s=summary([]);good('empty-capture-not-selection-proof',lambda:require(not s['absenceOfCallsProvesDriverNotSelected'] and not s['objects'],'No false absence proof'))
    a=events(6,1,4,0);a[1]['payload']['elapsedQpc']=0;s=summary(a)
    good('indeterminate-timing-keeps-return-but-not-completeness',lambda:require(s['objects'][0]['startReturnSuccessObserved'] and not s['controlClockConsistent'],'Zero timing is indeterminate'))
    a=events(6,1,4,0x3f4847a0);good('future-success-code-is-not-start-success',lambda:require(summary(a)['objects'][0]['startFailureObserved'],'ASE_SUCCESS is for ASIOFuture, not start'))
    for name,mutate in [
        ('mixed-pid',lambda a:a[1].update(pid=124)),('mixed-build',lambda a:a[1]['payload'].update(build='production')),
        ('different-thread-terminal',lambda a:a[1].update(tid=10)),('different-pair-clock',lambda a:a[1]['payload'].update(qpc=999)),
        ('boolean-operation',lambda a:a[0]['payload'].update(op=True)),('unknown-operation',lambda a:a[0]['payload'].update(op=19)),
        ('begin-success-claim',lambda a:a[0]['payload'].update(result=1)),('extra-user-string',lambda a:a[0]['payload'].update(track='never include titles'))]:
        a=events(2,1,2,1);mutate(a);refused(name,lambda a=a:summary(a))
    refused('duplicate-begin',lambda:summary([rows[0],rows[0]]));refused('duplicate-terminal',lambda:summary(rows+[rows[-1]]))
    refused('contradictory-stop-marker',lambda:summary(m={**marker,'eventsLost':1}))
    refused('nonfinite-json',lambda:API['parse'](b'{"x":NaN}'));refused('duplicate-json-key',lambda:API['parse'](b'{"x":1,"x":2}'))
    return cases


def main():
    reference=Path(sys.argv[1]).absolute();expected_reference=sys.argv[2];decoder=Path(sys.argv[3]).absolute();decoder_sha=sys.argv[4]
    require(sha(reference)==expected_reference,'Reviewed fixture reference identity required');prior=json.loads(reference.read_bytes())
    require(prior['schema']=='sl3.activation-asio-run.v1' and prior['nativeDeviceAccess'] is False,'Owned simulated ASIO reference required')
    require(all(sha(ROOT/name)==value for name,value in prior['sourceSha256'].items()),'Referenced fixture source changed')
    images={Path(name).name:Path(name) for name in prior['imageSha256']}
    names=('sl3_activation_asio_tests.exe','sl3_activation_session_fixture.dll','sl3_broker_controller_unmeasured_simulated.exe','sl3_device_session_fixture.exe','UsbDkHelper.dll10')
    require(set(images)==set(names) and all(sha(Path(name))==value for name,value in prior['imageSha256'].items()),'Exact simulated fixture image contract required')
    source_pins={'scripts/inspect-asio-control-trace.py':sha(ROOT/'scripts/inspect-asio-control-trace.py'),Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__))}
    cases=synthetic();identity=uuid.uuid4().hex;folder=ROOT/'analysis'/('asio-observation-fixture-'+identity);folder.mkdir()
    profile=folder/'profile';profile.mkdir();device_output=folder/'simulated-owners'
    env={**os.environ,'SL3_ASIO_PRIVATE_TRACE':'1','LOCALAPPDATA':str(profile)}
    child=subprocess.Popen([str(images[name]) for name in names]+[str(device_output)],env=env,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    timeout=False
    try:stdout,stderr=child.communicate(timeout=45)
    except subprocess.TimeoutExpired:
        timeout=True;child.kill();stdout,stderr=child.communicate(timeout=5)
    (folder/'fixture-stdout.json').write_bytes(stdout);(folder/'fixture-stderr.txt').write_bytes(stderr)
    require(not timeout and child.returncode==0,'Owned simulated fixture did not retire normally')
    fixture=json.loads(stdout);require(fixture['passed'] and fixture['simulatedSessions']==5 and fixture['nativeDeviceAccess'] is False,'Expected actual fixture scope')
    retirements=[]
    for ordinal in range(1,6):
        path=device_output/('session-'+str(ordinal))/'result.json';record=json.loads(path.read_bytes())
        require(record['kind']=='simulated' and record['nativeDeviceAcquired'] is False and record['helperLoadedInController'] is False and
            all(record[k] is True for k in ('ioRetiredVerified','deviceReleasedVerified','processExited','jobEmpty')) and record['terminationRequested'] is False,'Simulated owner retirement required')
        require(record['successful']==(ordinal<5) and record['ownerFailureCode']==('none' if ordinal<5 else 'client_control_abandoned'),'Preserve destructive-callback failure')
        retirements.append({'owner':ordinal,'resultSha256':sha(path),'successful':record['successful']})
    directories=sorted((profile/'SL3Rebuild/AsioTraces').iterdir(),key=lambda p:p.stat().st_mtime)
    require(len(directories)==4,'Four explicitly bounded private logger lifetimes expected')
    observations=[]
    for ordinal,directory in enumerate(directories,1):
        marker=API['parse']((directory/'session.json').read_bytes());require(marker['pid']==child.pid,'Exact owned fixture process required')
        result=API['inspect'](directory,decoder,decoder_sha,ROOT/'analysis'/('asio-observation-decoded-'+identity+'-'+str(ordinal)))
        summary=result['summary'];require(summary['buildKind']=='session_fixture' and summary['controlMetadataComplete'],'Complete simulated fixture metadata required')
        require(any(obj['startReturnSuccessObserved'] for obj in summary['objects']) if ordinal<4 else
                any(obj['initRejectionObserved'] for obj in summary['objects']),'Expected successful starts and rejected initialization remain distinct')
        observations.append(result)
    collector_cases=[]
    def refused(name,operation,output):
        try:operation()
        except ValueError:collector_cases.append({'name':name,'passed':True})
        else:raise AssertionError('Unexpected collector admission: '+name)
        require(not output.exists(),'Collector refusal must precede new output creation')
    for ordinal,flag in enumerate(([],['--plan'])):
        plan=subprocess.run([sys.executable,'-I','-B',str(ROOT/'scripts/inspect-asio-control-trace.py'),*flag],capture_output=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
        result=json.loads(plan.stdout);require(plan.returncode==0 and all(result[name] is False for name in ('filesWritten','traceControllerStarted','applicationLaunched','deviceOpened')),'Default observer is inert')
        collector_cases.append({'name':'inert-plan-'+str(ordinal),'passed':True})
    first_output=ROOT/'analysis'/('asio-observation-decoded-'+identity+'-1');original_report=sha(first_output/'observation.json')
    try:API['inspect'](directories[0],decoder,decoder_sha,first_output)
    except ValueError:collector_cases.append({'name':'existing-output-preserved','passed':True})
    else:raise AssertionError('Existing observation overwritten')
    require(sha(first_output/'observation.json')==original_report,'Existing observation changed')
    for name,changes in [('open-logger',{'stopStatus':1,'complete':False}),('contradictory-marker',{'eventsLost':1})]:
        fault=folder/name;shutil.copytree(directories[0],fault);marker=json.loads((fault/'session.json').read_bytes());marker.update(changes);(fault/'session.json').write_text(json.dumps(marker),encoding='utf-8')
        output=ROOT/'analysis'/('asio-observation-refused-'+identity+'-'+name)
        refused(name,lambda fault=fault,output=output:API['inspect'](fault,decoder,decoder_sha,output),output)
    output=ROOT/'analysis'/('asio-observation-refused-'+identity+'-build')
    refused('wrong-decoder-build-identity',lambda:API['inspect'](directories[0],decoder,'0'*64,output),output)
    fault_decoder=folder/'fault-decoder';(fault_decoder/'Release').mkdir(parents=True)
    shutil.copyfile(decoder,fault_decoder/decoder.name)
    image=decoder.parent/'Release/sl3_asio_decode_trace.exe'
    (fault_decoder/'Release/sl3_asio_decode_trace.exe').write_bytes(image.read_bytes()+b'changed-but-never-executed')
    output=ROOT/'analysis'/('asio-observation-refused-'+identity+'-image')
    refused('changed-decoder-image-refused-before-execution',lambda:API['inspect'](directories[0],fault_decoder/decoder.name,decoder_sha,output),output)
    require(all(sha(ROOT/name)==value for name,value in source_pins.items()) and
            all(sha(Path(name))==value for name,value in prior['imageSha256'].items()),'Observer/fixture inputs changed during test')
    result={'schema':'sl3.asio-control-observation-tests.v1','passed':True,'syntheticCases':cases,'collectorCases':collector_cases,'sourceSha256':source_pins,
        'referenceRunSha256':expected_reference,'fixturePid':child.pid,'fixture':fixture,'retirements':retirements,
        'observations':observations,'ownedChildExited':True,'timedOut':False,'processOnlyEnvironmentOptIn':True,
        'persistentEnvironmentModified':False,'seratoLaunched':False,'nativeDeviceAccess':False,'registryModified':False}
    path=folder/'result.json';path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'syntheticCases':len(cases),'collectorCases':len(collector_cases),'completedRealFixtureLogs':len(observations),'report':str(path)},indent=2))


if __name__=='__main__':main()
