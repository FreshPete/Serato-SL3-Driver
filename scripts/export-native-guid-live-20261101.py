"""Verify both real observed/rechecked logging jobs; never starts tracing or USB."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
BATCH=ROOT/'analysis/logging-batch-20261101-native-recheck'
CAPSULE=ROOT/'artifacts/build/checkpoints/observed-native-guid-live-20261101'
LAUNCH='3858e854169045ff87a7b0c9edecd327'
RUN_HASHES=('ae543bfb92640ce6f43d028c01de314b602bb6da6d272046a347093702b197c8',
            '251b61283e6e3014e6268537b01dc6f2cd9128a507cb91ea3c0c4518238ede78')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def require(ok,message):
    if not ok:raise ValueError(message)


def filetime(text):
    value=datetime.fromisoformat(text).astimezone(timezone.utc)-datetime(1601,1,1,tzinfo=timezone.utc)
    return ((value.days*86400+value.seconds)*1000000+value.microseconds)*10


def main():
    require(sha(BATCH/'batch.json')=='39e3dadd52c3355205bd0dae6ab97d8248c7708540d7a4695f4a3a3e8fea6112','Actual plan changed')
    plan,batch=read(BATCH/'batch.json'),read(BATCH/'batch-result.json')
    launch,child=read(BATCH/f'launch-{LAUNCH}.json'),read(BATCH/f'child-{LAUNCH}-exit.json')
    require(launch['status']=='launched' and launch['pid']==child['pid']==3908 and child['exitCode']==0
            and child['wrapperError'] is None and launch['launchId']==child['launchId']==LAUNCH
            and launch['planSha256']==child['planSha256']==batch['planSha256']==sha(BATCH/'batch.json'), 'Actual launch binding differs')
    require(batch['successful'] is True and batch['attemptedJobs']==2 and batch['remainingJobsSkipped']==0
            and len(batch['jobs'])==2 and batch['producerToken']['queried'] is True
            and batch['producerToken']['elevated'] is True and batch['producerToken']['elevationType']==2,
            'Actual elevated sequence did not pass')
    for name,digest in plan['runtime']['scripts'].items():
        require(sha(CAPSULE/'runtime/scripts'/name)==digest,'Frozen runtime differs: '+name)
    rows=[];dependencies=[Path(__file__),BATCH/'batch.json',BATCH/'batch-result.json',BATCH/f'launch-{LAUNCH}.json',
                         BATCH/f'child-{LAUNCH}-exit.json',BATCH/f'child-{LAUNCH}.log']
    for n,expected_hash in enumerate(RUN_HASHES,1):
        context=ROOT/f'tests/results/local/logging-batch-20261101-native-recheck-{n}'
        require(sha(context/'run.json')==expected_hash==batch['jobs'][n-1]['sourceRunSha256'],'Actual source result changed')
        run=read(context/'run.json');discovery=run['nativeGuidDiscovery'];native=run['nativeSessionGuid']
        require(run['successful'] is True and run['nativeIdentityPolicy']=='observed-rechecked'
                and run['inputs']==plan['jobs'][n-1]['inputs'] and run['durationSeconds']==(5 if n==1 else 10)
                and run['sourceStarted'] is True and run['sourceDisappearanceObserved'] is True
                and not run.get('error') and not run.get('cleanupError'), 'Source role/outcome differs')
        require(discovery['recheckAccepted'] is True and discovery['configuredGuid']==run['sessionGuid']!=native
                and discovery['candidateNativeGuid']==native and sha(context/discovery['file'])==discovery['sha256']
                and sha(context/discovery['recheckFile'])==discovery['recheckSha256'], 'Discovery/recheck binding differs')
        rejected=read(context/discovery['file']);checked=read(context/discovery['recheckFile'])
        require(rejected['diagnosticAccepted'] is False and rejected['win32Status']==0
                and checked['diagnosticAccepted'] is True and checked['sourceActive'] is True
                and checked['expectedSessionGuid']==native and len(run['queryRejections'])==1
                and rejected['sourceSha256']==checked['sourceSha256']==run['inputs']['inspect-image-source-session.py'],
                'Rejected discovery was not separated from strict recheck')
        committed=read(context/'start.json.committed.json')
        require(run['startAction']['committedConfiguration']['sha256']==sha(context/'start.json.committed.json')
                and committed['configurationMatchesExpected'] is True and committed['status']==0,
                'Committed configuration binding differs')
        active=[row for row in run['observations'] if row['sourceActive'] is True]
        require(active and run['observations'][-1]['sourceActive'] is False,'Disappearance not observed')
        for observation in run['observations']:
            require(observation['diagnosticAccepted'] is True and observation['expectedSessionGuid']==native
                    and observation['receivedWithinWatchDeadline'] is True
                    and observation['sourceSha256']==run['inputs']['inspect-image-source-session.py'],
                    'Accepted observation identity/deadline differs')
        for observation in active:
            p=observation['properties']
            require(p['sessionGuid']==native and p['sessionGuidMatchesExpected'] is True
                    and p['sessionName']==run['sessionName'] and p['sessionNameMatchesExpected'] is True
                    and Path(p['logFileName']).resolve()==(Path(run['captureRoot'])/'images.etl').resolve()
                    and p['clockType']==1 and p['enableFlags']==4 and p['logFileMode']==0x02800000
                    and all(p[k]==0 for k in ('eventsLost','logBuffersLost','realTimeBuffersLost')),
                    'Live native identity/properties changed')
        require(run['cleanup']['successful'] is True and run['cleanup']['stopRequested'] is False
                and run['cleanup']['collectorDeleted'] is True and run['after']['win32Status']==4201
                and run['after']['sourceActive'] is False and run['independentStopValidated'] is False
                and run['timedExpiryCauseVerified'] is False and run['readinessAdmission'] is False,
                'Cleanup or claim limits differ')
        require(len(run['etlFiles'])==1,'Expected one ETL')
        etl=run['etlFiles'][0];path=Path(etl['path'])
        require(path.stat().st_size==etl['bytes'] and 0<etl['bytes']<=64*1024*1024 and sha(path)==etl['sha256'], 'ETL changed')
        image_path=ROOT/f'analysis/native-guid-rundown-20261101-job{n}/rundown.json';image=read(image_path)
        require(image['sourceEtlSha256']==etl['sha256'] and image['sourceEtlBytes']==etl['bytes']
                and image['inspectorSha256']==sha(CAPSULE/'inputs/inspect-kernel-image-rundown.py')
                and image['decoderSha256']==sha(CAPSULE/'inputs/tracerpt.exe')
                and image['comparison']['expected']['diskSha256']==sha(CAPSULE/'inputs/UsbHub3.sys')==
                    'f93fa3a32037c597fd19ca9d65f59e53a1e337123582ed2479d5c16a4848df16'
                and image['comparison']['expected']['kernelPath'].lower()==r'\systemroot\system32\drivers\usbhub3.sys',
                'Image inspection input differs')
        require(image['sourceReportsNoLoss'] is True and image['comparison']['matchingRundownMetadata'] is True
                and image['kernelImageOperations']=={'DCStart':259,'DCEnd':259}
                and len(image['kernelImages'])==259 and all(i['consistentRundownPair'] for i in image['kernelImages'])
                and image['loadedMemoryIdentityVerified'] is False and image['usbWindowQualified'] is False,
                'Image result or its limits differ')
        header=image['headers'][0]
        for observation in [rejected,*active]:
            require(header['StartTime']<=filetime(observation['queryStartedUtc'])<=
                    filetime(observation['queryFinishedUtc'])<=header['EndTime'], 'Live query is outside its ETL window')
        require(filetime(run['observations'][-1]['queryStartedUtc'])>=header['EndTime'], 'Absence preceded saved trace end')
        rows.append({'job':n,'requestedDurationSeconds':run['durationSeconds'],'configuredGuid':run['sessionGuid'],
            'nativeGuid':native,'nativeGuidStrictlyRechecked':True,'acceptedLiveSamples':len(active),
            'firstAcceptedQueryUtc':active[0]['queryStartedUtc'],'firstAbsentQueryUtc':run['observations'][-1]['queryStartedUtc'],
            'cleanupStopRequested':False,'collectorDeleted':True,'afterQueryAbsent':True,
            'etlBytes':etl['bytes'],'etlSha256':etl['sha256'],'etlWindow100ns':header['EndTime']-header['StartTime'],
            'liveQueriesInsideOwnImageWindow':True,
            'nativeMaximumFileSizeMiB':active[0]['properties']['maximumFileSizeMiB'],
            'decodedEvents':image['events'],'consistentKernelRundownPairs':259,
            'hubImageMetadataMatches':True,'decoderSchemaWarningObserved':'Some events do not match the schema' in image['decoderOutput']})
        dependencies.extend([context/'run.json',context/'start.json.committed.json',context/discovery['file'],
                             context/discovery['recheckFile'],image_path])
    retirement_path=ROOT/'analysis/native-guid-live-process-retirement-20261101.json'
    reuse_path=ROOT/'analysis/native-guid-live-pid-reuse-20261101.json'
    retirement,reuse=read(retirement_path),read(reuse_path)
    original=read(ROOT/'tests/results/local/logging-batch-20261101-native-recheck-1/start.json')['producer']
    require(retirement['recordedPidCount']==31 and len(retirement['remainingListedProcesses'])==1
            and retirement['remainingListedProcesses'][0]['Id']==reuse['pid']==original['pid']
            and reuse['recordedCreationFileTimeUtc']==original['creationFileTimeUtc']
            and int(reuse['currentCreationFileTimeUtc'])>int(reuse['recordedCreationFileTimeUtc'])
            and reuse['sameRecordedInstance'] is False,'Recorded process retirement/reuse evidence differs')
    dependencies.extend([retirement_path,reuse_path])
    result={'scope':'Two actual elevated source-only logging diagnostics; no SL3/audio operation',
        'batchSuccessful':True,'administratorLaunches':1,'jobs':rows,'hubImageDiskSha256':sha(CAPSULE/'inputs/UsbHub3.sys'),
        'recordedRuntimeInstancesRetired':True,'reusedPidsExcludedByCreationTime':1,
        'independentTimedExpiryCauseVerified':False,'nativeHardFileCapVerified':False,'loadedMemoryIdentityVerified':False,
        'usbWindowQualified':False,'readinessAdmission':False,'physicalAudioVerified':False,
        'limits':['Observed disappearance before cleanup is consistent with configured duration; its cause is not proven.',
                  'The observed native file-size limit is zero, with no hard cap claimed.',
                  'Image metadata agreement applies to each source window, not an earlier/future USB operation or loaded-memory hash.',
                  'Tracerpt reported some schema mismatches; the strict known-image parser does not prove every event decoded.',
                  'No SL3 acquisition/reopen, analogue audio, current-Serato or DVS result follows.'],
        'dependencies':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in dependencies}}
    (ROOT/'docs/evidence/native-guid-live-20261101.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'batchSuccessful':True,'durations':[5,10],'nativeGuidsStable':True,'kernelPairsPerTrace':259,
                      'hubMetadataMatches':True,'readinessAdmission':False}))


if __name__=='__main__':main()
