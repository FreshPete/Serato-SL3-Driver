"""Check the real 1 November logging-only attempt; no source or device operations."""
import hashlib
import json
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT/'analysis/logging-batch-20261101-ready'
CONTEXT = ROOT/'tests/results/local/logging-batch-20261101-ready-1'
CAPSULE = ROOT/'artifacts/build/checkpoints/attended-logging-20261101'
LAUNCH = '28acdf4ac30b4f73b2a37a10a6be59a7'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    require(sha(BATCH/'batch.json') == 'b638ba75fb4df909599ace097bf0b8f4c3a523ba08b194239cc53faef20bf1fd', 'Actual batch plan changed')
    require(sha(CONTEXT/'run.json') == '71876b2ccfe4fdadc0a8cfe31df0a9752710c798558894e5e255b493504a9c8a', 'Actual source result changed')
    plan, batch, run = read(BATCH/'batch.json'), read(BATCH/'batch-result.json'), read(CONTEXT/'run.json')
    launch, child = read(BATCH/f'launch-{LAUNCH}.json'), read(BATCH/f'child-{LAUNCH}-exit.json')
    require(launch['status'] == 'launched' and launch['pid'] == child['pid'] == 19580
            and launch['launchId'] == child['launchId'] == LAUNCH
            and launch['planSha256'] == child['planSha256'] == batch['planSha256'] == sha(BATCH/'batch.json'), 'Launch binding differs')
    require(child['exitCode'] == 1 and child['wrapperError'] is None and child['executionMarkerPresent'] is True
            and child['batchResultPresent'] is True, 'Child outcome differs')
    require(batch['producerToken']['queried'] is True and batch['producerToken']['elevated'] is True
            and batch['producerToken']['elevationType'] == 2 and batch['successful'] is False
            and batch['attemptedJobs'] == 1 and len(batch['jobs']) == 1 and batch['remainingJobsSkipped'] == 0,
            'Batch admission/outcome differs')
    require(batch['jobs'][0]['sourceRunSha256'] == sha(CONTEXT/'run.json'), 'Source result binding differs')
    for name, digest in plan['runtime']['scripts'].items():
        require(sha(CAPSULE/'runtime/scripts'/name) == digest, 'Frozen actual script differs: '+name)
    require(run['inputs'] == plan['jobs'][0]['inputs'] and run['successful'] is False
            and run['sourceStarted'] is None and not run.get('cleanupError'),
            'Source result role differs')
    require(not run.get('cleanupError') and run['observations'] == [] and len(run['queryRejections']) == 1,
            'Rejected observation/cleanup handling differs')
    sample = read(CONTEXT/'sample-0.json')
    require(sha(CONTEXT/'sample-0.json') == '9e579f87d765a710d29edf1d9e650a925e9bf1d48cbaf36023294c4308dce486'
            == run['queryRejections'][0]['sha256'], 'Native rejected metadata changed')
    start, cleanup, after = read(CONTEXT/'start.json'), read(CONTEXT/'cleanup.json'), read(CONTEXT/'after.json')
    committed = read(CONTEXT/'start.json.committed.json')
    require(start['successful'] is True and start['sourceCommitted'] is True and start['startRequested'] is True
            and start['sourceSha256'] == plan['runtime']['scripts']['hub-image-source-action.ps1']
            and start['committedConfiguration']['sha256'] == sha(CONTEXT/'start.json.committed.json'), 'Start/readback binding differs')
    require(committed['querySucceeded'] is True and committed['status'] == 0
            and committed['configurationMatchesExpected'] is True and committed['mismatches'] == []
            and committed['error'] is None, 'Committed configuration not accepted')
    properties = sample['properties']
    xml = ET.fromstring(committed['xml'])
    configured = str(uuid.UUID(xml.findtext('TraceDataCollector/Guid')))
    native = str(uuid.UUID(properties['sessionGuid']))
    require(configured == sample['expectedSessionGuid'] == run['sessionGuid'] and configured != native
            and uuid.UUID(native).int != 0, 'Observed GUID distinction differs')
    require(sample['win32Status'] == 0 and sample['sourceActive'] is True and sample['diagnosticAccepted'] is False
            and properties['sessionNameMatchesExpected'] is True and properties['sessionGuidMatchesExpected'] is False
            and properties['sessionName'] == run['sessionName'] and sample['controlCode'] == 0
            and sample['sourceSha256'] == plan['runtime']['scripts']['inspect-image-source-session.py'], 'Native query role differs')
    require(Path(properties['logFileName']).resolve() == (Path(run['captureRoot'])/'images.etl').resolve(), 'Native output differs')
    require(properties['logFileMode'] == 0x02800000 and properties['clockType'] == 1
            and properties['maximumFileSizeMiB'] == 0 and properties['enableFlags'] == 4
            and all(properties[k] == 0 for k in ('eventsLost','logBuffersLost','realTimeBuffersLost')), 'Observed native properties differ')
    require(cleanup['successful'] is True and cleanup['stopRequested'] is True and cleanup['collectorDeleted'] is True
            and after['win32Status'] == 4201 and after['sourceActive'] is False and after['diagnosticAccepted'] is True,
            'Cleanup/independent absence differs')
    etls = []
    for file in run['etlFiles']:
        path = Path(file['path'])
        require(path.resolve().is_relative_to(Path(run['captureRoot']).resolve()) and path.stat().st_size == file['bytes']
                and 0 < file['bytes'] <= 64*1024*1024 and sha(path) == file['sha256'], 'Actual ETL differs')
        etls.append({'bytes':file['bytes'],'sha256':file['sha256']})
    require(len(etls) == 1, 'Expected one actual retained ETL')
    paths = [BATCH/'batch.json',BATCH/'batch-result.json',BATCH/f'launch-{LAUNCH}.json',BATCH/f'child-{LAUNCH}-exit.json',
             BATCH/f'child-{LAUNCH}.log',CONTEXT/'run.json',CONTEXT/'start.json',CONTEXT/'start.json.committed.json',
             CONTEXT/'sample-0.json',CONTEXT/'cleanup.json',CONTEXT/'after.json',Path(__file__)]
    result = {'scope':'Actual elevated source-only batch and rejected live query; no SL3/audio test',
              'batchLaunched':True,'batchProcessElevated':True,'batchSuccessful':False,'sourceDiagnosticSuccessful':False,
              'committedConfigurationAccepted':True,'configuredSessionGuid':configured,'observedNativeSessionGuid':native,
              'nativeGuidDiffersFromConfigured':True,'nativeNameAndPrivateOutputMatch':True,
              'nativeLogFileMode':'0x02800000','nativeMaximumFileSizeMiB':0,'nativeClockType':1,'sampledLossCountersZero':True,
              'supervisorStoppedSource':True,'collectorDeleted':True,'independentAfterQueryAbsent':True,
              'independentTimedExpiryVerified':False,'readinessAdmission':False,'physicalAudioVerified':False,'etls':etls,
              'finding':'Persisted PLA configuration retains the requested GUID; the named native session returned a different GUID. Cleanup and the new launcher records worked.',
              'limits':['Only one native live GUID observation was captured; stability and the generating call were not traced.',
                        'This is consistent with the inspected service GUID-generation path, not proof that UuidCreate executed.',
                        'The strict failed source result remains unchanged; no identity acceptance policy is relaxed here.',
                        'Zero native file limit is not a hard cap; supervisor stop does not prove timer expiry.',
                        'No kernel handoff, SL3 reopen, analogue audio, current-Serato or DVS result follows.'],
              'dependencies':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in paths}}
    output = ROOT/'docs/evidence/attended-logging-20261101.json'
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'configuredGuid':configured,'nativeGuid':native,'cleanupConfirmed':True,'etls':etls,'sourceDiagnosticSuccessful':False}))


if __name__ == '__main__':
    main()
