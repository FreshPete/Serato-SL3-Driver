"""Reinspect an image ETL and bind its metadata window to a completed controls capture.

No live device or trace source access. A matching window is version evidence,
never physical USB port identity, loaded-memory identity or readiness admission.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'scripts'/name)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


controls=module('validate-controls-user-probe.py')
images=module('inspect-kernel-image-rundown.py')
clock=module('validate-usb-state-capture.py')
require,sha=controls.require,images.digest


def read(path):
    require(0<path.stat().st_size<=2*1024*1024,'JSON exceeds evidence bound')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def qualify(report,trace,run):
    require(report['sourceReportsNoLoss'] is True and len(report['headers'])==1,'Image source loss or ambiguous header')
    comparison=report['comparison']
    require(comparison['targetPresent'] is True and comparison['matchingRundownMetadata'] is True,
            'USBHUB3 rundown metadata does not match disk')
    expected=comparison['expected']
    require(expected['kernelPath'].casefold()==r'\SystemRoot\System32\drivers\UsbHub3.sys'.casefold(),
            'Expected USBHUB3 image comparison')
    rows=[r for r in report['kernelImages'] if r['canonicalKernelPath']==expected['kernelPath'].casefold()]
    require(len(rows)==1 and rows[0]['consistentRundownPair'] is True,'Ambiguous USBHUB3 image lifetime')
    observations=rows[0]['observations']
    require(len(observations)==2 and [r['operation'] for r in observations]==['DCStart','DCEnd'],
            'USBHUB3 reload or missing rundown boundary')
    require(all(all(row[k]==expected[k] for k in ('sizeOfImage','timeDateStamp','imageChecksum'))
                for row in observations),'USBHUB3 metadata changed')
    header=report['headers'][0]
    require(all(type(header[k]) is int for k in ('StartTime','EndTime','EventsLost','BuffersLost')) and
            header['EventsLost']==header['BuffersLost']==0,'Invalid image header or reported loss')
    start,end=clock.filetime(trace['startedUtc']),clock.filetime(trace['stoppedUtc'])
    probe_start,probe_end=clock.filetime(run['probeStartedUtc']),clock.filetime(run['probeCompletedUtc'])
    require(trace['status']=='window completed' and
            header['StartTime']<=clock.filetime(observations[0]['time'])<=start<=probe_start<=probe_end<=end<=
            clock.filetime(observations[1]['time'])<=header['EndTime'],
            'Image rundown does not encompass the actual USB/probe window')
    require(end-probe_end>=120_000_000,'Missing twelve-second post-release observation interval')
    return {'imageMetadataCoversUsbWindow':True,'diskImageSha256':expected['diskSha256'],
            'usbWindowStartFileTime':str(start),'usbWindowEndFileTime':str(end),
            'postReleaseTicks':str(end-probe_end),'loadedMemoryIdentityVerified':False,
            'physicalDeviceIdentityVerified':False,'readinessAdmission':False,
            'scope':'USBHUB3 version metadata agrees across this USB trace window; no audio or Serato claim'}


def validate(plan_path,output):
    combined=module('collect-controls-with-images.py')
    plan=read(plan_path);directory=plan_path.parent
    require(plan['schema'] in ('sl3.controls-image-collector.v1','sl3.scope-image-collector.v1'),'Unknown collector schema')
    scope=plan['schema']=='sl3.scope-image-collector.v1'
    require(plan['traceSeconds']==(60 if scope else 20) and
            (plan.get('scenario')=='Scope' if scope else 'scenario' not in plan),'Collector scenario/duration differs')
    require(plan['runtime']==(combined.runtime(scope=True) if scope else combined.runtime()),
            'Collector plan/runtime changed')
    started=read(directory/'controls-image-started.json')
    result=read(directory/'controls-image-result.json')
    require(result['schema']==('sl3.scope-image-collection.v1' if scope else 'sl3.controls-image-collection.v1'),
            'Collection result scenario differs')
    require(started['planSha256']==result['planSha256']==sha(plan_path) and
            result['collectionCompleted'] is True and result['error'] is None and
            not result.get('imageCleanupError') and result['imageControllerExitCode']==result['usbCollectorExitCode']==0,
            'Combined collection did not retire cleanly')
    batch_path=Path(plan['imageBatch'])
    require(batch_path==directory/'batch.json' and sha(batch_path)==plan['imageBatchSha256'],'Image batch binding differs')
    batch=read(batch_path);require(len(batch['jobs'])==1,'Unexpected image job count')
    job=batch['jobs'][0]
    require(job['durationSeconds']==(120 if scope else 60) and batch['nativeIdentityPolicy']=='observed-rechecked',
            'Image source scenario/window differs')
    source_path=Path(job['contextDirectory'])/'run.json'
    source=read(source_path);batch_result=read(directory/'batch-result.json')
    require(batch_result['successful'] is True and len(batch_result['jobs'])==1 and
            batch_result['planSha256']==sha(batch_path) and batch_result['jobs'][0]['sourceRunSha256']==sha(source_path),
            'Image controller result binding differs')
    require(source['successful'] is True and source['sourceDisappearanceObserved'] is True and
            source['sampledLossCountersZero'] is True and source['cleanup']['successful'] is True and
            source['cleanup']['stopRequested'] is False and source['cleanup']['collectorDeleted'] is True and
            source['after']['sourceActive'] is False and len(source['etlFiles'])==1,'Image cleanup or completeness failed')
    etl=Path(job['captureRoot'])/'images.etl';artifact=source['etlFiles'][0]
    require(Path(artifact['path'])==etl and sha(etl)==artifact['sha256'] and etl.stat().st_size==artifact['bytes'],
            'Image ETL binding differs')
    context=Path(plan['contextDirectory']);build=read(ROOT/'artifacts/build/native/native-build-Release.json')
    validated=controls.validate(context,build['usbdk']['executableSha256'],build['scopeProbe']['executableSha256'],scope=True) if scope else \
        controls.validate(context,build['usbdk']['executableSha256'],build['hostProbe']['executableSha256'])
    require(validated['valid'] is True,'Normal-user controls/trace/recovery validation failed')
    require(not output.exists() and output.parent.is_dir(),'Choose a fresh output file')
    rundown=output.with_name(output.stem+'-rundown.json')
    require(not rundown.exists(),'Choose a fresh rundown output file')
    image=Path(os.environ['SystemRoot'])/'System32/drivers/UsbHub3.sys'
    subprocess.run([sys.executable,str(ROOT/'scripts/inspect-kernel-image-rundown.py'),'--etl',str(etl),
                    '--output',str(rundown),'--image',str(image),'--kernel-path',r'\SystemRoot\System32\drivers\UsbHub3.sys'],
                   check=True,capture_output=True,timeout=75,creationflags=subprocess.CREATE_NO_WINDOW)
    report=read(rundown)
    require(report['sourceEtlSha256']==sha(etl) and report['inspectorSha256']==sha(ROOT/'scripts/inspect-kernel-image-rundown.py') and
            report['comparison']['expected']==images.image_metadata(image,r'\SystemRoot\System32\drivers\UsbHub3.sys'),
            'Recomputed image provenance differs')
    qualified=qualify(report,read(context/'trace/capture.json'),read(context/'run.json'))
    if scope:qualified['scenario']='Scope'
    qualified.update(planSha256=sha(plan_path),controlsRunSha256=sha(context/'run.json'),
                     sourceRunSha256=sha(source_path),rundownSha256=sha(rundown),
                     decoderWarningPresent='Warning:' in report.get('decoderOutput',''),
                     decoderOutput=report.get('decoderOutput',''))
    with output.open('x',encoding='utf-8') as stream:json.dump(qualified,stream,indent=2);stream.write('\n')
    return qualified


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(validate(args.plan.resolve(),args.output.resolve()),indent=2))
