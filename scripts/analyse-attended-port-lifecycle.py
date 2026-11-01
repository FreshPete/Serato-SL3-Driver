"""Decode the preserved 16:40Z failed experiment offline; never open USB.

Use the captured checked decoder plus three invariant formats from its pinned
MSI TMF. Keep this separate from the original failed runtime records.
"""
import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import uuid

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'scripts'/name)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


source=module('prepare-usbdk-lifecycle-trace.py')
release=module('analyse-sl3-release.py')
require=source.require
sha=release.sha
EXTRA={('64c95281-4f46-32d3-c872-5a725a3deb03','WdfDevice.cpp'):{17,21},
       ('b5e6b989-2f0e-e5db-a780-e327b8ea6fff','ControlDevice.cpp'):{65}}


def supplement(raw,image):
    require(source.sha(raw)==source.TMF_SHA,'Bundled TMF identity differs')
    records=defaultdict(set);current=None;lines=raw.decode('utf-8').splitlines();index=0
    while index<len(lines):
        header=re.fullmatch(r'([0-9a-f-]{36}) UsbDk // SRC=(\w+\.cpp) MJ= MN=',lines[index])
        if header:current=(header[1],header[2])
        entry=re.match(r'#typev \S+ (\d+) ',lines[index])
        if entry:
            start=index;index+=1
            while index<len(lines) and lines[index]!='}':index+=1
            require(index<len(lines),'Truncated bundled TMF')
            if current in EXTRA and int(entry[1]) in EXTRA[current]:
                records[(*current,int(entry[1]))].add('\n'.join(lines[start:index+1]))
        index+=1
    expected={(guid,file,n) for (guid,file),ids in EXTRA.items() for n in ids}
    require(set(records)==expected and all(len(v)==1 for v in records.values()),
            'Additional message inventory is missing or architecture-dependent')
    output=[]
    for (guid,file),ids in EXTRA.items():
        require(uuid.UUID(guid).bytes_le in image,'Additional message GUID absent from pinned driver')
        output.append(f'{guid} UsbDk // SRC={file} MJ= MN=')
        output.extend(next(iter(records[(guid,file,n)])) for n in sorted(ids))
    return ('\n'.join(output)+'\n').encode('utf-8')


def observations(text,worker):
    pattern=r'^\[\d+\]([0-9A-Fa-f]+)\.([0-9A-Fa-f]+)::(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{7}) \[UsbDk\](.*)$'
    rows=[]
    for line in text.splitlines():
        match=re.fullmatch(pattern,line)
        if match:
            rows.append({'pid':int(match[1],16),'tid':int(match[2],16),
                         'utc':match[3]+'Z','message':match[4]})
    require(rows,'No decoded UsbDk messages')
    stages={}
    for key,message in (
        ('powerQuery','CWdmUsbDeviceAccess::Reset device power state D3'),
        ('powerCompletion','PowerRequestCompletion -> D0'),
        ('redirectHandle',f'CUsbDkRedirection::CreateRedirectorHandle done for process 0x{worker:X}'),
        ('close','CUsbDkRedirectorStrategy::OnClose'),
        ('waitDetach',r'CUsbDkControlDevice::RemoveRedirect Waiting for detachment from USB\VID_1CC5&PID_0001:SL3.01.00'),
        ('detached',r'CUsbDkControlDevice::RemoveRedirect Detached from USB\VID_1CC5&PID_0001:SL3.01.00'),
        ('removalFinished','CUsbDkControlDevice::RemoveRedirect Finished successfully. New redirections list:')):
        matches=[row for row in rows if row['message'].casefold()==message.casefold()]
        require(len(matches)==1,'Missing or ambiguous lifecycle stage: '+key)
        stages[key]=matches[0]
        if key!='powerCompletion':require(matches[0]['pid']==worker,'Wrong lifecycle caller: '+key)
    ticks=[release.clock(row['utc']) for row in stages.values()]
    require(ticks==sorted(ticks) and len(set(ticks))==len(ticks),'Lifecycle stage order differs')
    return {'decodedUsbDkRecords':len(rows),'selectedStages':stages,
            'observedPowerLogSpacingTicks':str(ticks[1]-ticks[0]),
            'powerCallbackRequestIdentityVerified':False,
            'detachmentWaitTicks':str(ticks[5]-ticks[4]),
            'removalReportedSuccessful':True,'readinessAdmission':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    require(output.parent==(ROOT/'analysis').resolve() and not output.exists(),'Choose a fresh direct analysis directory')
    context=ROOT/'tests/results/local/logging-batch-port-attended-20261101-1640-controls'
    evidence=release.read(ROOT/'docs/evidence/attended-port-controls-20261101.json')
    for relative in ('run.json','probe/probe.json','probe/worker-1.tsv'):
        path=context/relative;key=path.relative_to(ROOT).as_posix()
        require(sha(path)==evidence['bindings'][key],'Original run binding differs: '+relative)
    run=release.read(context/'run.json')
    require(run['completed'] is False and run['probeExitCode']==0,'Expected preserved failed experiment with native exit zero')
    capture=release.read(context/'trace/capture.json')
    checked,selected=source.check()
    require((context/'trace/lifecycle-decoder/lifecycle.tmf').read_bytes()==selected and
            capture['plan']['lifecycle']['selectedTmfSha256']==checked['selectedTmfSha256'],
            'Captured lifecycle decoder differs')
    etl=context/'trace/usb-startup_000001.etl'
    require(sha(etl)==run['etlSha256'].lower(),'Original USB ETL differs')
    image=(ROOT/'artifacts/extracted/usbdk-msi/UsbDk.sys10').read_bytes()
    extra=supplement((ROOT/'artifacts/extracted/usbdk-msi/UsbDk_TMF').read_bytes(),image)
    output.mkdir();decoder=output/'lifecycle-complete-observed.tmf';decoder.write_bytes(selected+extra)
    tracefmt=Path('C:/Program Files (x86)/Windows Kits/10/bin/10.0.19041.0/x64/tracefmt.exe')
    arguments=[str(tracefmt),str(etl),'-tmf',str(decoder),'-o',str(output/'messages.txt'),
               '-utc','-hires','-sortableTime','-cp','utf8']
    with (output/'tracefmt.log').open('xb') as stream:
        code=subprocess.run(arguments,stdout=stream,stderr=subprocess.STDOUT,timeout=30,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),cwd=ROOT).returncode
    require(code==0,'Offline Tracefmt failed')
    summary=(output/'messages.txt.sum').read_text(encoding='utf-8-sig')
    counts={name:int(re.search(r'(?m)^'+re.escape(label)+r'\s+(\d+)\s*$',summary)[1])
            for name,label in (('events','Total Events  Processed'),('lost','Total Events  Lost'),
                               ('formatErrors','Total Format  Errors'),('unknown','Total Formats Unknown'))}
    require(counts['lost']==counts['formatErrors']==counts['unknown']==0,'Incomplete offline message decoding')
    worker=evidence['offlineNativeProbeReassessment']['nativeJournal']['workerPid']
    result=observations((output/'messages.txt').read_text(encoding='utf-8-sig'),worker)
    xml=context/'events.xml';require(sha(xml)==run['traceStats']['xmlSha256'].lower(),'Original decoded XML differs')
    rows,total=release.timeline.parse(xml);require(total==counts['events']==run['traceStats']['eventCount'],'Source event count differs')
    symbols=release.read(ROOT/'analysis/attended-state-symbols.json')
    symbols_helper=module('export-usbhub3-state-symbols.py')
    require(symbols['imageSha256']==symbols_helper.IMAGE_SHA==sha(symbols_helper.REFERENCE/'USBHUB3.SYS') and
            symbols['pdbSha256']==symbols_helper.PDB_SHA==sha(symbols_helper.REFERENCE/'usbhub3.pdb'),
            'Cached state symbol identity differs')
    states={r['value']:r['name'] for r in symbols['enums']['_DSM_STATE_ETW']['members']}
    events={r['value']:r['name'] for r in symbols['enums']['_DSM_EVENT']['members']}
    result.update(schema='sl3.attended-port-lifecycle.v1',tracefmtCounts=counts,
                  port=release.correlate(rows,worker,run['probeCompletedUtc'],states,events),
                  originalExperimentPassed=False,fullWindowImageMetadataVerified=False,
                  loadedMemoryIdentityVerified=False,physicalRetestPerformed=False,
                  symbolScope='Cached image/PDB interpretation; failed image logger does not qualify the full USB window',
                  bindings={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in
                            (etl,xml,context/'run.json',decoder,output/'messages.txt',output/'messages.txt.sum',
                             output/'tracefmt.log',ROOT/'scripts/analyse-attended-port-lifecycle.py')},
                  tracefmtSha256=sha(tracefmt))
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
