"""Reproduce the failed 1 November combined attempt; offline saved evidence only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
JOB=ROOT/'analysis/logging-batch-controls-image-20261101-reviewed'
CAPSULE=ROOT/'artifacts/build/checkpoints/combined-controls-first-20261101'


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def module(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'scripts'/name)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def main():
    require(sha(JOB/'controls-image.json')=='721b61e5d081682e06839f3e395cae6d2bf9151fb039c01f28148bdaca4ba5d3','Original plan changed')
    plan=read(JOB/'controls-image.json');batch=read(JOB/'batch.json');job=batch['jobs'][0]
    context=Path(plan['contextDirectory']);source_path=Path(job['contextDirectory'])/'run.json'
    require(sha(context/'run.json')=='c12fe92f747815df845dccd1cb9ff24b0fd22f0ce6a8abda20d2458799a5935b' and
            sha(source_path)=='07e09e368c161b7ef0102640ed0ba85a91aa11b7784ec1276fe1354064b3388f','Original run changed')
    pins={**plan['runtime']['controlsInputs'],**plan['runtime']['loggingRuntime']['scripts'],
          'collect-controls-with-images.py':plan['runtime']['collectorSha256'],
          'start-controls-image-capture.ps1':plan['runtime']['launcherSha256'],
          'validate-controls-image-window.py':plan['runtime']['windowValidatorSha256'],
          'inspect-kernel-image-rundown.py':plan['runtime']['imageInspectorSha256']}
    for name,expected in pins.items():require(sha(CAPSULE/'runtime/scripts'/name)==expected.lower(),'Frozen runtime differs: '+name)
    require(sha(CAPSULE/'native-build-Release.json')==plan['runtime']['buildManifestSha256'],'Frozen build manifest differs')
    run=read(context/'run.json');trace=read(context/'trace/capture.json');source=read(source_path)
    require(run['completed'] is False and run['error']=='Collector admission expired before launch' and
            'probeStartedUtc' not in run and run['probeExitCode'] is None and
            set(run['userProcesses'])=={'parent'} and not (context/'probe').exists(),'Unexpected device-probe evidence')
    require(trace['status']=='failed' and trace['error']=='State-consumer consistency validation failed' and
            read(context/'trace/state-observer-validation.json')=={'valid':False,'error':'No actual live state rows'},'Failure was changed')
    require(source['successful'] is True and source['cleanup']['stopRequested'] is False and
            source['cleanup']['collectorDeleted'] is True and source['after']['sourceActive'] is False,'Image source cleanup failed')
    require(any(c['arguments']==['delete','-n',trace['session']] and c['exitCode']==0 for c in trace['commands']),
            'USB collector deletion missing')
    artifact=trace['files'][0];etl=context/'trace'/artifact['name']
    require(len(trace['files'])==1 and sha(etl)==artifact['sha256'].lower() and etl.stat().st_size==artifact['bytes'],
            'USB ETL binding differs')
    xml=ROOT/'analysis/combined-controls-20261101-first/usb-events.xml'
    stats=module('validate-usbdk-capture.py').trace_statistics(xml)
    require(stats['session']==trace['session'] and stats['eventCount']==5502 and
            stats['eventsLost']==stats['buffersLost']==0,'USB decode differs')
    ns='{http://schemas.microsoft.com/win/2004/08/events/event}';header=None;state_rows=0
    for _,event in ET.iterparse(xml,events=['end']):
        if event.tag!=ns+'Event':continue
        system=event.find(ns+'System')
        if header is None:header={d.get('Name'):(d.text or '').strip() for d in event.findall(ns+'EventData/'+ns+'Data')}
        if system.find(ns+'Provider').get('Guid','').lower()=='{ac52ad17-cc01-4f85-8df5-4dce4333c99b}' and system.findtext(ns+'EventID') in ('110','111'):
            state_rows+=1
        event.clear()
    require(int(header['LogFileMode'],0)==0 and state_rows==0 and etl.stat().st_size<64*1024*1024,'USB mode/state evidence differs')
    observer=[json.loads(line) for line in (context/'trace/state-observer.ndjson').read_text().splitlines()]
    require(len(observer)==2 and observer[-1]['successful'] is True and observer[-1]['eventsSeen']==5500 and
            observer[-1]['stateRecords']==0,'Live consumer evidence differs')
    image_report=read(ROOT/'analysis/combined-controls-20261101-first-images.json')
    image_etl=Path(job['captureRoot'])/'images.etl'
    require(image_report['sourceEtlSha256']==sha(image_etl)==source['etlFiles'][0]['sha256'] and
            image_report['inspectorSha256']==plan['runtime']['imageInspectorSha256'] and
            image_report['sourceReportsNoLoss'] is True and image_report['comparison']['matchingRundownMetadata'] is True,
            'Image report binding differs')
    target=[r for r in image_report['kernelImages'] if r['canonicalKernelPath']==r'\SystemRoot\System32\drivers\UsbHub3.sys'.casefold()]
    clock=module('validate-usb-state-capture.py').filetime
    require(len(target)==1 and target[0]['consistentRundownPair'] is True and
            clock(target[0]['observations'][0]['time'])<=clock(trace['startedUtc'])<=clock(trace['stoppedUtc'])<=
            clock(target[0]['observations'][1]['time']),'Image metadata does not bracket the USB-only window')
    checked=read(context/'collector-process.json')['checkedUtc']
    minimum_guard_age=clock(run['startedUtc'])-clock(checked)
    require(minimum_guard_age>20_000_000,'Cold-verifier expiry was not reproduced')
    physical=module('export-usbdk-physical-checkpoint.py')
    before,after=read(context/'before-state.json'),read(context/'after-state.json')
    recovery=physical.state_contract(before)==physical.state_contract(after)
    require(recovery and before['secureBoot'] is True and after['secureBoot'] is True,'Selected recovery differs')
    retired=read(ROOT/'analysis/combined-controls-20261101-first-retirement.json')
    require({r['pid'] for r in retired['processes']}=={6340,41888,3888,6284,20020,42476} and
            all(r['present'] is False for r in retired['processes']) and retired['nativeDeviceProcesses']==[],
            'Known owners were not observed retired')
    result={'scope':'Failed combined attempt; useful collector components only', 'combinedControlsPassed':False,
            'probeLaunched':False,'minimumGuardAgeTicks':str(minimum_guard_age),'imageControllerPassed':True,
            'usbSequentialBytes':etl.stat().st_size,'usbHeaderLogFileMode':header['LogFileMode'],
            'usbHeaderMaximumFileMiB':int(header['MaxFileSize']),'nativeHardFileCapProven':False,
            'usbEvents':stats['eventCount'],'usbReportedEventsLost':0,'usbReportedBuffersLost':0,
            'liveEventsSeen':5500,'liveStateRows':0,'fileStateRows':0,'liveStateCheckPassed':False,
            'imageVersionMetadataBracketsUsbOnlyWindow':True,'imageBytes':image_etl.stat().st_size,
            'imageDecoderWarningPresent':'Warning:' in image_report.get('decoderOutput',''),
            'selectedRecoveryMatches':True,'secureBootBeforeAfter':True,'knownOwnersObservedRetired':True,
            'physicalDeviceIdentityVerified':False,'readinessAdmission':False,'audioTested':False,
            'currentSeratoIntegrationVerified':False,'planSha256':sha(JOB/'controls-image.json'),
            'originalRunSha256':sha(context/'run.json'),'sourceRunSha256':sha(source_path),
            'usbEtlSha256':sha(etl),'imageEtlSha256':sha(image_etl),'usbXmlSha256':sha(xml)}
    output=ROOT/'docs/evidence/combined-controls-first-20261101.json'
    output.write_text(json.dumps(result,indent=2)+'\n')
    print('Verified original failure, no probe launch, collector components and selected recovery; no hardware controls pass')


if __name__=='__main__':main()
