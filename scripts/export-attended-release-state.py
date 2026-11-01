"""Correlate preserved live-only state observations; never grant reopen readiness."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONTEXT=ROOT/'tests/results/local/user-controls-attended-20261031-120514'


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def utc(value):
    seconds,fraction=divmod(value,10_000_000)
    instant=datetime(1601,1,1,tzinfo=timezone.utc)+timedelta(seconds=seconds)
    return instant.strftime('%Y-%m-%dT%H:%M:%S')+f'.{fraction:07d}Z'


def main():
    helper=load('release_state_symbols','export-usbhub3-state-symbols.py')
    state=load('release_state_stream','validate-usb-state-capture.py')
    component=load('release_component','validate-controls-host-probe.py')
    tokens=load('release_tokens','validate-controls-user-probe.py')
    timeline=load('release_xml_rows','export-reopen-usb-timeline.py')
    require,sha=component.require,helper.sha
    report=read(ROOT/'docs/evidence/attended-controls-components-20261031.json')
    require(report['normalTokenControlComponentPassed'] is True and report['endToEndPassed'] is False
            and report['fullWindowVerified'] is False,'Component scope changed')
    run=read(CONTEXT/'run.json');capture=read(CONTEXT/'trace/capture.json')
    require(sha(CONTEXT/'run.json')==report['originalRunSha256'] and run['completed'] is False,'Failed run changed')
    native=component.probe(CONTEXT/'probe',run['workerSha256']);worker=native['nativeJournal']['workerPid']
    tokens.tokens(run,worker)
    require(sha(CONTEXT/'trace/capture.json')==run['traceRecordSha256'].lower() and
            sha(CONTEXT/'trace/state-observer.ndjson')==capture['stateObserver']['outputSha256'].lower(),'Source/stream changed')
    _,_,values=state.observations(CONTEXT/'trace/state-observer.ndjson',capture['session'],60,capture['stateObserver']['process']['pid'])
    require(len(values)==514,'Live row count differs')
    fields=('eventId','task','pid','time','device','context','startIndex','state','event','depth')
    rows=[dict(zip(fields,value)) for value in values]
    require(all(state.filetime(capture['startRequestedUtc'])<=r['time']<=state.filetime(capture['stoppedUtc']) for r in rows),
            'Live row is outside recorded source interval')
    symbols_path=ROOT/'analysis/attended-state-symbols.json';symbols=read(symbols_path)
    require(symbols['exporterSha256']==sha(ROOT/'scripts/export-usbhub3-state-symbols.py') and
            symbols['imageSha256']==helper.IMAGE_SHA==sha(helper.REFERENCE/'USBHUB3.SYS') and
            symbols['pdbSha256']==helper.PDB_SHA==sha(helper.REFERENCE/'usbhub3.pdb'),'Inspected symbol/image bytes changed')
    require(symbols['rsds']['guid']==symbols['pdbIdentity']['guid'] and
            symbols['pdbIdentity']['infoAge']>=symbols['rsds']['age'] and
            symbols['pdbIdentity']['dbiAge']==symbols['rsds']['age'],'PDB identity differs')
    require(symbols['imageSemantics']['stateFieldIsEntryEtwName'] is True,'ETW/internal state namespace semantics differ')
    states={x['value']:x['name'] for x in symbols['enums']['_DSM_STATE_ETW']['members']}
    events={x['value']:x['name'] for x in symbols['enums']['_DSM_EVENT']['members']}
    dsm=[r for r in rows if r['startIndex']==4000]
    require(len(dsm)==330 and all(r['state'] in states and r['event'] in events for r in dsm),'Unknown DSM namespace/value')
    for r in dsm:r.update(stateName=states[r['state']],eventName=events[r['event']])
    shared={r['device'] for r in rows if r['startIndex']==3000 and r['pid']==worker}
    require(len(shared)==1,'Ambiguous worker-associated shared tracking value')
    shared=next(iter(shared))
    groups=defaultdict(list)
    for r in dsm:groups[r['context']].append(r)
    for group in groups.values():group.sort(key=lambda r:r['time'])
    initial=[group for group in groups.values() if any(r['device']==shared and r['pid']==worker for r in group)]
    require(len(initial)==1 and len(initial[0])==158,'Worker-entered DSM context differs')
    initial=initial[0]
    completed=state.filetime(run['probeCompletedUtc'])
    candidates=[group for group in groups.values() if any(r['device']==shared for r in group) and
                any(r['time']>completed and r['stateName']=='DsmStateEtwCheckIfDeviceCanBeDisabledOnDriverNotFound'
                    and r['eventName']=='DsmEventTimerFired' for r in group)]
    require(len(candidates)==1 and len(candidates[0])==97,'Post-release candidate is absent/ambiguous')
    candidate=candidates[0]
    require(initial[-1]['stateName']=='DsmStateEtwWaitingToBeDeleted' and initial[-1]['time']<completed,
            'Initial context retirement observation differs')
    timer=next(r for r in candidate if r['stateName']=='DsmStateEtwCheckIfDeviceCanBeDisabledOnDriverNotFound')
    entries=[r for r in candidate if r['stateName']=='DsmStateEtwStoppedEnumerated' and
             r['eventName']=='DsmEventOperationSuccess' and r['depth']==0 and r['time']<timer['time']]
    require(entries and entries[0]['time']>completed,'Candidate enumeration is not after the completed probe')
    anchor=entries[-1]
    tail=[r for r in candidate if r['time']>=timer['time']]
    require([r['stateName'] for r in tail]==['DsmStateEtwCheckIfDeviceCanBeDisabledOnDriverNotFound',
            'DsmStateEtwDisablingDeviceInControllerOnStartTimeout','DsmStateEtwDisablingPortOnStartTimeout','DsmStateEtwStopped'],
            'Observed timeout tail differs')
    ticks=timer['time']-anchor['time']
    require(100_000_000<=ticks<=101_000_000,'Observed timer interval differs')
    require(0<(CONTEXT/'events.xml').stat().st_size<=512*1024*1024 and
            sha(CONTEXT/'events.xml')==run['traceStats']['xmlSha256'],'Retained XML changed or exceeds bound')
    xml_rows,total=timeline.parse(CONTEXT/'events.xml')
    source=[]
    for row in xml_rows:
        if row['eventId'] in (110,111):
            source.append((row['eventId'],row['task'],row['pid'],state.filetime(row['time']),
                           *[timeline.number(row['data'][key]) for key in
                             ('fid_UsbDevice','fid_Context','fid_StartIndex','fid_State','fid_Event','fid_Depth')]))
    candidate_values=[tuple(r[key] for key in fields) for r in candidate]
    require(total==report['traceEventsRetained'] and len(source)==21 and
            not Counter(candidate_values)&Counter(source),'Candidate has unexpected retained-file corroboration')
    image=read(ROOT/'docs/evidence/attended-hub-image-20261031.json')
    require(image['matchingHubRundownMetadata'] is True and image['hub']['diskSha256']==symbols['imageSha256']
            and image['usbWindowQualified'] is False,'Later image evidence differs')
    require(capture['stateObserver']['hubImageBefore']==capture['stateObserver']['hubImageAfter'] and
            capture['stateObserver']['hubImageBefore']['sha256'].lower()==symbols['imageSha256'],'Observed disk image changed')

    def projected(row):
        return {'timeUtc':utc(row['time']),'timestampFileTime':str(row['time']),'stateForInspectedImage':row['stateName'],
                'eventForInspectedImage':row['eventName'],'depth':row['depth']}

    output={'scope':'Saved live-only candidate state correlation; labels conditional on inspected image; no readiness admission',
            'probeCompletedUtc':run['probeCompletedUtc'],'initialWorkerEnteredContextRows':158,'postReleaseCandidateRows':97,
            'candidateFirstStoppedEnumerated':projected(entries[0]),'candidateLastObservedSuccessfulEntry':projected(anchor),
            'candidateTimeoutTail':[projected(r) for r in tail],
            'observedEntryToTimerSeconds':ticks/10_000_000,
            'candidateFirstStoppedEnumeratedAfterProbeMilliseconds':(entries[0]['time']-completed)/10_000,
            'candidateStoppedAfterProbeSeconds':(tail[-1]['time']-completed)/10_000_000,
            'namespaces':dict(Counter(str(r['startIndex']) for r in rows)),
            'inspectedImageSha256':symbols['imageSha256'],'symbolsGuid':symbols['rsds']['guid'],
            'liveStreamCompletenessVerified':False,'candidateVidPidPortIdentityVerified':False,
            'sourceXmlCorroboratesCandidate':False,'loadedImageUsbWindowAttested':False,'readinessAdmission':False,
            'limits':['The candidate shares a worker-associated opaque tracking value before identity assignment; no retained VID/PID/port record proves its physical identity.',
                      'A different DSM context on the same hub can be unrelated; opaque values are grouped without asserting a physical port.',
                      'These early rows were overwritten in the file and survive only in the pinned live-consumer output.',
                      'Later image metadata and unchanged disk snapshots are supporting version evidence, not a USB-window loaded-image attestation.',
                      'The observed timer interval is not a production delay or proof that another cycle would succeed.'],
            'sources':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [Path(__file__),symbols_path,
                ROOT/'scripts/export-usbhub3-state-symbols.py',ROOT/'scripts/validate-usb-state-capture.py',
                CONTEXT/'run.json',CONTEXT/'probe/probe.json',CONTEXT/'probe/worker-1.tsv',CONTEXT/'trace/capture.json',
                CONTEXT/'trace/state-observer.ndjson',ROOT/'docs/evidence/attended-controls-components-20261031.json',
                ROOT/'docs/evidence/attended-hub-image-20261031.json',ROOT/'scripts/export-reopen-usb-timeline.py',
                CONTEXT/'events.xml']}}
    (ROOT/'docs/evidence/attended-release-state-20261031.json').write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
    print(f'Verified live-only candidate: enumeration {output["candidateFirstStoppedEnumeratedAfterProbeMilliseconds"]:.4f}ms after probe; observed timer {output["observedEntryToTimerSeconds"]:.7f}s; no target/readiness claim')


if __name__=='__main__':main()
