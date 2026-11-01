"""Recheck the real combined controls capture of 1 November; saved evidence only."""
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    spec=importlib.util.spec_from_file_location('window',ROOT/'scripts/validate-controls-image-window.py')
    window=importlib.util.module_from_spec(spec);spec.loader.exec_module(window)
    require,sha,read=window.require,window.sha,window.read
    directory=ROOT/'analysis/logging-batch-controls-image-20261101-launch-recheck'
    plan_path=directory/'controls-image.json';plan=read(plan_path)
    require(sha(plan_path)=='950a07d59f49db1485924a7a5642e6c412481ce81aa43e4e2f8495ff2889def4','Attended plan changed')
    context=Path(plan['contextDirectory']);run_path=context/'run.json'
    require(sha(run_path)=='e191c95ed262e9432a37db5c919f24edbe9f22e93b2fb6ac96c1562854d20724','Attended controls run changed')
    run=read(run_path);trace=read(context/'trace/capture.json');batch=read(directory/'batch.json');job=batch['jobs'][0]
    source_path=Path(job['contextDirectory'])/'run.json'
    require(sha(source_path)=='b9f827d5796ea1fcaac313711dfefd218498986df2bd6c7158069f0496111a28','Attended image run changed')
    combined=window.module('collect-controls-with-images.py')
    # Live admission still checks the current build. Historical assessment uses
    # the exact archived native build, without executing its binaries.
    archived=ROOT/'artifacts/build/checkpoints/native-controls-build-20261101'
    old_manifest=archived/'native-build-Release.json'
    require(sha(old_manifest)=='0d875f3d3e438e1f296cfc3b73e9f14c80b656df1e78bd0a8825a341461ab3da',
            'Archived physical-capture manifest changed')
    old_build=read(old_manifest)
    for name,expected in old_build['inputs'].items():
        require(sha(archived/'inputs'/name)==expected.lower(),'Archived native source changed: '+name)
    historical=combined.runtime()
    historical['buildManifestSha256']=sha(old_manifest)
    historical['nativeImages']={}
    for name,expected in (('sl3_host_probe.exe',old_build['hostProbe']['executableSha256']),
                          ('sl3_usbdk.exe',old_build['usbdk']['executableSha256'])):
        require(sha(archived/'Release'/name)==expected.lower(),'Archived native executable changed: '+name)
        historical['nativeImages'][name]=expected.lower()
    require(plan['runtime']==historical,'Attended runtime differs from archived build and current reviewed scripts')
    require(run['workerSha256'].lower()==historical['nativeImages']['sl3_usbdk.exe'] and
            run['probeSha256'].lower()==historical['nativeImages']['sl3_host_probe.exe'],
            'Physical run does not bind the archived native executables')
    # The saved live-consumer record binds the same old host manifest. Reuse
    # the unchanged validator with that explicitly verified offline input;
    # never relax the live validator's current-build preflight.
    def archived_state_observer(folder,trace):
        require(trace['plan']['withStateObserver'] is True,'Expected the actual state observer')
        validator=window.module('validate-usb-state-capture.py')
        validator.BUILD=old_manifest
        saved=folder/'trace/state-observer-validation.json'
        require(sha(saved)==trace['stateObserver']['validationSha256'].lower() and
                read(saved)==validator.validate(folder/'trace'),'Archived live consumer validation differs')
        return validator.validate(folder/'trace',folder/'events.xml')
    window.controls.state_observer=archived_state_observer
    # Redirect only these three saved-artifact reads to their byte-verified
    # archive locations. Process image-path evidence keeps its original paths.
    archived_paths={ROOT/'artifacts/build/native/native-build-Release.json':old_manifest,
                    ROOT/'artifacts/build/native/Release/sl3_usbdk.exe':archived/'Release/sl3_usbdk.exe',
                    ROOT/'artifacts/build/native/Release/sl3_host_probe.exe':archived/'Release/sl3_host_probe.exe'}
    original_read,original_digest=window.controls.read,window.controls.digest
    window.controls.read=lambda path:original_read(archived_paths.get(Path(path),Path(path)))
    window.controls.digest=lambda path:original_digest(archived_paths.get(Path(path),Path(path)))
    checked=window.controls.validate(context,run['workerSha256'],run['probeSha256'])
    require(checked==read(context/'run-validation.json'),'Saved controls validation differs from fresh recheck')
    saved=read(ROOT/'analysis/controls-image-window-20261101-pass.json')
    report_path=ROOT/'analysis/controls-image-window-20261101-pass-rundown.json';report=read(report_path)
    require(sha(report_path)==saved['rundownSha256']=='f804163760c766ddfa518c5dc4d9f5f078fcd2242ab71ee58aba265b03fa3022' and
            saved['planSha256']==sha(plan_path) and saved['controlsRunSha256']==sha(run_path) and
            saved['sourceRunSha256']==sha(source_path),'Image window result binding differs')
    source=read(source_path);image_etl=Path(job['captureRoot'])/'images.etl'
    require(source['successful'] is True and source['cleanup']['collectorDeleted'] is True and
            source['cleanup']['stopRequested'] is False and source['after']['sourceActive'] is False and
            report['sourceEtlSha256']==sha(image_etl)==source['etlFiles'][0]['sha256'] and
            report['inspectorSha256']==plan['runtime']['imageInspectorSha256'],'Image source/ETL/cleanup differs')
    qualified=window.qualify(report,trace,run)
    require(all(saved[k]==v for k,v in qualified.items()),'Recomputed overlap differs')
    collection=read(directory/'controls-image-result.json')
    require(collection['collectionCompleted'] is True and collection['error'] is None and
            not collection.get('imageCleanupError') and collection['imageControllerExitCode']==collection['usbCollectorExitCode']==0,
            'Collectors did not exit cleanly')
    observer=checked['stateObserver']
    require(observer['coverage']['allSourceStateRowsObserved'] is True and observer['stateRows']==493 and
            checked['traceStats']['eventCount']==6536,'Full source/live-row evidence differs')
    retired=read(ROOT/'analysis/combined-controls-20261101-pass-retirement.json')
    require({r['pid'] for r in retired['processes']}=={10024,16228,19936,9996,24460,40700,39612,42300,35596} and
            all(r['present'] is False for r in retired['processes']) and retired['nativeDeviceProcesses']==[],
            'Known owner processes not observed retired')
    result={'scope':'One normal-user acquisition/getters/release with complete USB state capture and matching image-version window',
            'combinedControlsCapturePassed':True,'administratorLaunchesForThisAttempt':1,
            'normalParentProbeWorkerTokensVerified':checked['nonElevatedParentProbeAndWorker'],
            'rateHz':checked['probe']['rateHz'],'rawControls':checked['probe']['rawControls'],
            'acquisitions':1,'redirectCloses':1,'audioStartAttempts':0,'probeStartedUtc':run['probeStartedUtc'],
            'probeCompletedUtc':run['probeCompletedUtc'],'postReleaseTicks':qualified['postReleaseTicks'],
            'usbTraceEvents':checked['traceStats']['eventCount'],'liveAndFileStateRows':493,'allFileStateRowsObservedLive':True,
            'usbReportedEventsLost':0,'usbReportedBuffersLost':0,'usbEtlBytes':trace['files'][0]['bytes'],
            'imageEtlBytes':report['sourceEtlBytes'],'imageMetadataCoversUsbWindow':True,
            'imageDiskSha256':qualified['diskImageSha256'],'imageDecodeWarningPresent':saved['decoderWarningPresent'],
            'secureBootBeforeAfter':True,'selectedRecoveryMatches':True,'knownOwnersObservedRetired':True,
            'loadedMemoryIdentityVerified':False,'physicalDeviceIdentityVerified':False,'readinessAdmission':False,
            'currentWorkerAudioTested':False,'safeSuccessiveAcquisitionVerified':False,'currentSeratoIntegrationVerified':False,
            'planSha256':sha(plan_path),'controlsRunSha256':sha(run_path),'sourceRunSha256':sha(source_path),
            'usbEtlSha256':trace['files'][0]['sha256'].lower(),'imageEtlSha256':sha(image_etl),
            'windowReportSha256':sha(ROOT/'analysis/controls-image-window-20261101-pass.json')}
    result['workerSha256']=run['workerSha256'].lower()
    result['probeSha256']=run['probeSha256'].lower()
    result['nativeBuildArchive']=str(archived.relative_to(ROOT))
    (ROOT/'docs/evidence/combined-controls-pass-20261101.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Verified real combined normal-user controls pass, all 493 state rows, image overlap and selected recovery; no reopen/audio/Serato claim')


if __name__=='__main__':main()
