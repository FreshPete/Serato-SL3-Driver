"""Recheck the unstarted/cancelled 1 November phase-observation attempt."""
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    spec=importlib.util.spec_from_file_location('observer_abort',ROOT/'scripts/observe-sl3-hub-port.py')
    observer=importlib.util.module_from_spec(spec);spec.loader.exec_module(observer)
    require,read,sha=observer.require,observer.read,observer.sha
    job=ROOT/'analysis/hub-port-observer-release-20261101'
    capture=ROOT/'analysis/logging-batch-port-observe-20261101'
    require(sha(job/'plan.json')=='4f2199566fb7f395e783964dd3088a60fdac247b8ffaa461b316e213843e19df' and
            sha(capture/'controls-image.json')=='10f81f4ef37975be6c3e29098a8572cf5b2ce3a9263a212744c6b9371996cc0e',
            'Original plans changed')
    settings=observer.validate(job);supervision=read(job/'supervision.json')
    require(supervision['successful'] is False and supervision['exitCode']==1 and supervision['timedOut'] is False and
            supervision['directProducerRetired'] is True and supervision['pid']==37588 and
            supervision['workerError']=='No fresh collector window; no hub queries started' and
            supervision['observationsSha256']==sha(job/'observations.ndjson'),'Observer wait result differs')
    rows=[json.loads(line) for line in (job/'observations.ndjson').read_text().splitlines()]
    require(len(rows)==2 and rows[0]['record']=='header' and rows[0]['producerToken']['pid']==supervision['pid'] and
            rows[0]['producerToken']['elevated'] is False and rows[1]['record']=='summary' and
            rows[1]['successful'] is False,'Unexpected observation/sample lifecycle')
    launch=read(capture/'controls-image-launch-result.json')
    require(launch['status']=='launch_failed' and launch['collectorWrapperPid'] is None and launch['normalProbePid']==34116,
            'Unexpected administrator launch result')
    normal_error=(capture/'controls-normal-bdc658b14d4345bb995a819ed367d9e9.err').read_text(encoding='utf-8-sig')
    require('Collector did not become ready; no device test launched' in normal_error,'Normal device admission refusal differs')
    require(sha(capture/'controls-image-started.json')=='d8b4e9c26942e9286166f94c502d6a331aadea561a1b00ac6ad69ade021a13a7',
            'Abort marker differs')
    abort=read(capture/'controls-image-started.json')
    require(abort['schema']=='sl3.controls-image.aborted-before-start.v1' and abort['startedUtc'] is None and
            abort['sourceStarted'] is False and abort['deviceOpened'] is False and
            abort['planSha256']==sha(capture/'controls-image.json'),'Attempt was not explicitly disarmed')
    combined=observer.module('collect-controls-with-images.py')
    try:combined.validate(capture/'controls-image.json')
    except ValueError as error:require(str(error)=='Collector plan already attempted','Unexpected late-launch refusal')
    else:raise ValueError('Aborted attempt is still executable')
    plan=read(capture/'controls-image.json');batch=read(capture/'batch.json')
    require(not Path(plan['contextDirectory']).exists() and not Path(batch['jobs'][0]['contextDirectory']).exists() and
            not Path(batch['jobs'][0]['captureRoot']).exists(),'An unstarted capture created runtime state')
    retired=read(ROOT/'analysis/hub-port-observer-release-20261101-retirement.json')
    require({p['pid'] for p in retired['processes']}=={37588,34116} and all(p['present'] is False for p in retired['processes']) and
            retired['consentProcesses']==[] and retired['nativeDeviceProcesses']==[],'Pending owner or device process remains')
    phases=observer.module('analyse-hub-port-phases.py')
    try:phases.analyse(job,capture/'controls-image.json',ROOT/'analysis/nonexistent-aborted-window.json')
    except ValueError as error:require(str(error)=='Observer did not retire successfully','Unexpected failed-run analysis refusal')
    else:raise ValueError('Failed observer was admitted as a live phase comparison')
    result={'scope':'Cancelled administrator launch and expired observer admission; no physical phase experiment',
            'livePhaseComparisonPassed':False,'observerNormalTokenVerified':True,'baseWorkerPidMatchesDirectChild':True,
            'observerAdmissionExpired':True,'observerProcessTimedOut':False,'observerDirectProducerRetired':True,
            'samples':0,'nativeDeviceProbeLaunched':False,'traceStarted':False,'administratorLaunchStatus':launch['status'],
            'administratorWrapperCreated':False,'lateLaunchDisarmedAndRefused':True,'failedPhaseAnalysisRefused':True,
            'knownNormalProcessesObservedRetired':True,'consentPromptObservedAbsent':True,
            'readinessAdmission':False,'normalUserReadinessDiscriminatorVerified':False,
            'observerPlanSha256':sha(job/'plan.json'),'collectorPlanSha256':sha(capture/'controls-image.json'),
            'observationsSha256':sha(job/'observations.ndjson'),'supervisionSha256':sha(job/'supervision.json'),
            'abortMarkerSha256':sha(capture/'controls-image-started.json')}
    (ROOT/'docs/evidence/hub-port-observer-aborted-20261101.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Verified cancelled/unstarted phase attempt, zero samples, late-launch disarm and failed-analysis rejection')


if __name__=='__main__':main()
