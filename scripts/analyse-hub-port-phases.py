"""Compare complete normal-user snapshot intervals with mapped USB release phases.

A repeated fingerprint across phases rules out that stateless distinction in
this capture. A difference is only a candidate; neither outcome admits USB.
"""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'scripts'/name)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


release=module('analyse-sl3-release.py')
clock,require,sha,read=release.clock,release.require,release.sha,release.read


def compare(samples,pending_start,timer,stopped,source_start,source_end):
    require(source_start<=pending_start<timer<=stopped<source_end,'Invalid phase boundaries')
    require(1<len(samples)<=128,'Snapshot count outside bound')
    phases={'pending':[],'stopped':[]};previous=None;excluded=0
    for sequence,sample in enumerate(samples,1):
        require(sample['record']=='sample' and sample['sequence']==sequence,'Missing or reordered snapshot')
        entry,end=clock(sample['entryUtc']),clock(sample['completedUtc']);query=sample['query'];node=sample['devnode']
        require(previous is None or previous<=entry,'Snapshot intervals overlap or clock regressed')
        previous=end
        require(entry<=clock(query['queryStartedUtc'])<=clock(query['queryFinishedUtc'])<=clock(query['completedUtc'])<=end,
                'Query/combined snapshot bounds differ')
        require(query['successful'] is True and query['error'] is None and query['handleClosed'] is True and
                node['complete'] is True,'Incomplete snapshot cannot classify a phase')
        require(query['readinessAdmission'] is False and query['connection']['readinessAdmission'] is False,
                'Snapshot overclaims readiness')
        values={'connection.'+k:v for k,v in query['connection'].items() if k!='readinessAdmission'}
        values.update({'devnode.'+k:v for k,v in node.items()})
        require(all(type(v) in (int,str,bool,type(None)) for v in values.values()),'Unexpected composite field')
        fingerprint=json.dumps(values,sort_keys=True,separators=(',',':'))
        phase=None
        if pending_start<=entry<=end<timer:phase='pending'
        if stopped<=entry<=end<=source_end:phase='stopped'
        if phase:phases[phase].append((entry,end,fingerprint,values))
        else:excluded+=1
    for name,cohort in phases.items():
        require(len(cohort)>=4 and cohort[-1][1]-cohort[0][0]>=7_500_000,
                'Insufficient complete snapshots in '+name+' phase')
    fingerprints={name:{row[2] for row in cohort} for name,cohort in phases.items()}
    common=fingerprints['pending']&fingerprints['stopped']
    keys=set(phases['pending'][0][3]);require(all(set(row[3])==keys for cohort in phases.values() for row in cohort),
                                           'Observed field inventory changed')
    candidates=[];values_by_phase={}
    for name,cohort in phases.items():
        values_by_phase[name]={key:sorted({json.dumps(row[3][key]) for row in cohort}) for key in sorted(keys)}
    for key in sorted(keys):
        if not set(values_by_phase['pending'][key])&set(values_by_phase['stopped'][key]):candidates.append(key)
    return {'scope':'Observed fields during startup-pending and port-stopped phases; no production readiness decision',
            'phaseSamples':{name:len(cohort) for name,cohort in phases.items()},'excludedBoundaryOrOtherPhaseSamples':excluded,
            'phaseSpansTicks':{name:str(cohort[-1][1]-cohort[0][0]) for name,cohort in phases.items()},
            'commonCompleteFingerprints':len(common),'ambiguousCompleteFingerprintObserved':bool(common),
            'candidateDisjointFields':candidates,
            'valuesByPhase':{phase:{key:[json.loads(value) for value in values] for key,values in fields.items()}
                             for phase,fields in values_by_phase.items()},
            'statelessReadinessFromTheseFieldsSupported':False,'readinessAdmission':False,
            'successiveAcquisitionVerified':False,'timingUsedAsReadinessRule':False}


def analyse(job,collector_plan,window_path):
    observer=module('observe-sl3-hub-port.py');settings=observer.validate(job)
    supervision=read(job/'supervision.json');plan_sha=sha(job/'plan.json')
    require(supervision['successful'] is True and supervision['exitCode']==0 and supervision['timedOut'] is False and
            supervision['directProducerRetired'] is True and supervision['planSha256']==plan_sha and
            supervision['observationsSha256']==sha(job/'observations.ndjson'),'Observer did not retire successfully')
    rows=[json.loads(line) for line in (job/'observations.ndjson').read_text().splitlines()]
    header,admitted,summary=rows[0],rows[1],rows[-1]
    require(header['record']=='header' and header['planSha256']==plan_sha and header['producerToken']['pid']==supervision['pid'] and
            header['producerToken']['queried'] is True and header['producerToken']['elevated'] is False and
            summary['record']=='summary' and summary['successful'] is True,'Observer token or lifecycle differs')
    plan=read(collector_plan);context=Path(settings['contextDirectory'])
    require(context==Path(plan['contextDirectory']),'Observer and controls contexts differ')
    run=read(context/'run.json');trace=read(context/'trace/capture.json');window=read(window_path)
    require(window['planSha256']==sha(collector_plan) and window['controlsRunSha256']==sha(context/'run.json'),
            'Image window does not bind this controls run')
    checked=module('validate-controls-user-probe.py').validate(context,run['workerSha256'],run['probeSha256'])
    require(checked['stateObserver']['coverage']['allSourceStateRowsObserved'] is True,'Incomplete USB state retention')
    observer.admit(admitted['trace'],admitted['collector'],settings,admitted['checkedUtc'])
    require(admitted['record']=='admission' and admitted['trace']['session']==trace['session'],'Observer source differs')
    for key in ('collectorPid','collectorCreationFileTimeUtc','collectorImagePath','producerSha256','startedUtc'):
        require(admitted['trace'][key]==trace[key],'Collector identity changed after observer admission')
    for sample in rows[2:-1]:
        token=sample['query']['producerToken']
        require(token['pid']==supervision['pid'] and token['queried'] is True and token['elevated'] is False and
                type(token['elevationType']) is int and token['elevationType'] in (1,3),'Snapshot producer/token differs')
        require(all(sample['query'][k]==v for k,v in settings['query'].items()),'Snapshot query contract differs')
    require(len(rows[2:-1])==summary['samples'],'Sample count differs')
    topology=read(job/'topology-before.json')
    require(topology['device']['InstanceId'].upper()==settings['devnodeInstance'] and
            topology['parent']==settings['query']['hubInstance'] and topology['port']==settings['query']['port'] and
            observer.utc(settings['createdUtc'])<=observer.utc(topology['collectedUtc'])<=observer.utc(admitted['checkedUtc']),
            'Selected root-hub/port topology observation differs')
    symbols=read(ROOT/'analysis/attended-state-symbols.json');helper=module('export-usbhub3-state-symbols.py')
    require(symbols['exporterSha256']==sha(ROOT/'scripts/export-usbhub3-state-symbols.py') and
            symbols['imageSha256']==helper.IMAGE_SHA==sha(helper.REFERENCE/'USBHUB3.SYS') and
            symbols['pdbSha256']==helper.PDB_SHA==sha(helper.REFERENCE/'usbhub3.pdb'),'Inspected symbol inputs changed')
    require(symbols['imageSemantics']['stateFieldIsEntryEtwName'] is True and
            symbols['rsds']['guid']==symbols['pdbIdentity']['guid'] and
            symbols['pdbIdentity']['infoAge']>=symbols['rsds']['age'] and
            symbols['pdbIdentity']['dbiAge']==symbols['rsds']['age'],'Symbol namespace/image identity differs')
    image_path=window_path.with_name(window_path.stem+'-rundown.json');image=read(image_path)
    require(sha(image_path)==window['rundownSha256'] and image['comparison']['matchingRundownMetadata'] is True and
            image['comparison']['expected']['diskSha256']==symbols['imageSha256'],'Same-window image metadata differs')
    batch=read(collector_plan.parent/'batch.json');image_job=batch['jobs'][0]
    source_path=Path(image_job['contextDirectory'])/'run.json';source=read(source_path)
    require(window['sourceRunSha256']==sha(source_path) and source['successful'] is True and
            image['inspectorSha256']==sha(ROOT/'scripts/inspect-kernel-image-rundown.py') and
            image['sourceEtlSha256']==sha(Path(image_job['captureRoot'])/'images.etl')==source['etlFiles'][0]['sha256'],
            'Image source/ETL/inspector binding differs')
    states={x['value']:x['name'] for x in symbols['enums']['_DSM_STATE_ETW']['members']}
    events={x['value']:x['name'] for x in symbols['enums']['_DSM_EVENT']['members']}
    xml=context/'events.xml';require(sha(xml)==run['traceStats']['xmlSha256'],'USB XML changed')
    events_rows,total=release.timeline.parse(xml);require(total==checked['traceStats']['eventCount'],'USB event count differs')
    mapped=release.correlate(events_rows,checked['probe']['nativeJournal']['workerPid'],run['probeCompletedUtc'],states,events)
    require(mapped['port']==settings['query']['port'],'Observed port differs from mapped SL3 port')
    import xml.etree.ElementTree as ET
    ns='{http://schemas.microsoft.com/win/2004/08/events/event}'
    for _,event in ET.iterparse(xml,events=['end']):
        if event.tag==ns+'Event':
            usb_header={d.get('Name'):(d.text or '').strip() for d in event.findall(ns+'EventData/'+ns+'Data')};break
    source_start,source_end=int(usb_header['StartTime']),int(usb_header['EndTime'])
    target=[r for r in image['kernelImages'] if r['canonicalKernelPath']==r'\SystemRoot\System32\drivers\UsbHub3.sys'.casefold()]
    require(len(target)==1 and target[0]['consistentRundownPair'] is True and
            clock(target[0]['observations'][0]['time'])<=source_start<source_end<=clock(target[0]['observations'][1]['time']),
            'Image does not bracket native USB source window')
    timer=int(mapped['timeoutTail'][0]['timestampFileTime']);stopped=int(mapped['timeoutTail'][-1]['timestampFileTime'])
    pending=timer-int(mapped['lastSuccessfulEntryToTimerTicks'])
    result=compare(rows[2:-1],pending,timer,stopped,source_start,source_end)
    result.update(port=mapped['port'],controlsRunSha256=sha(context/'run.json'),observerPlanSha256=plan_sha,
                  observationsSha256=sha(job/'observations.ndjson'),windowSha256=sha(window_path),
                  pendingStartFileTime=str(pending),timerFileTime=str(timer),stoppedFileTime=str(stopped))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,required=True);parser.add_argument('--collector-plan',type=Path,required=True)
    parser.add_argument('--window',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();require(not args.output.exists(),'Choose a fresh phase report')
    result=analyse(args.job.resolve(),args.collector_plan.resolve(),args.window.resolve())
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))
