"""Map the complete controls trace's release state to its enumerated physical port.

Saved evidence only. Hub cookies and child cookies are schema-specific: a
shared hub cookie alone is never sufficient to select a child state context.
"""
from collections import defaultdict
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'scripts'/name)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


timeline=module('export-reopen-usb-timeline.py')
clock=module('validate-usb-state-capture.py').filetime
require,sha,read=timeline.require,timeline.digest,timeline.read
number=timeline.number


def correlate(rows,worker,completed,states,events):
    information=[r for r in rows if r['eventId']==6 and r['data'].get('fid_DeviceDescription')=='Rane SL3']
    require(len(information)==1,'Initial SL3 port is absent or ambiguous')
    initial=information[0];data=initial['data']
    hub,port,old_child=number(data['fid_HubDevice']),number(data['fid_PortNumber']),number(data['fid_UsbDevice'])
    require(hub>0 and old_child>0 and port>0,'Invalid initial port identity')

    def explicit_port(row):
        d=row['data']
        return number(d.get('fid_HubDevice','0'))==hub and number(d.get('fid_PortNumber','0'))==port

    enums=[r for r in rows if r['eventId']==61 and explicit_port(r)]
    require(len(enums)==2 and all(number(r['data']['fid_NtStatus'])==0 for r in enums),
            'Expected two successful enumerations on the exact SL3 port')
    enums.sort(key=lambda r:clock(r['time']))
    children=[old_child]+[number(r['data']['fid_UsbDevice']) for r in enums]
    require(all(child>0 for child in children) and len(set(children+[hub]))==4,'Hub/child identity was reused, null or ambiguous')
    cycles=[r for r in rows if r['eventId']==179 and r['pid']==worker and
            number(r['data'].get('fid_UsbDevice','0'))==hub and
            number(r['data'].get('fid_IoctlCode','0'))==timeline.CYCLE and
            number(r['data'].get('fid_idVendor','0'))==0x1cc5 and number(r['data'].get('fid_idProduct','0'))==1]
    cycles.sort(key=lambda r:clock(r['time']))
    require(len(cycles)==2 and clock(initial['time'])<clock(cycles[0]['time'])<clock(enums[0]['time'])<
            clock(cycles[1]['time'])<clock(enums[1]['time']), 'Worker/VID/PID cycle and port enumeration ordering differs')
    starts=[r for r in rows if r['eventId']==60 and number(r['data'].get('fid_UsbDevice','0'))==hub]
    starts.sort(key=lambda r:clock(r['time']))
    require(len(starts)==2 and all(number(r['data']['fid_PortNumber'])==port and
            clock(cycles[n]['time'])<=clock(r['time'])<=clock(enums[n]['time']) for n,r in enumerate(starts)),
            'Hub enumeration starts do not uniquely corroborate the SL3 port')
    redirected=[r for r in rows if r['eventId']==43 and explicit_port(r) and
                number(r['data']['fid_UsbDevice'])==children[1] and r['data'].get('fid_DeviceDescription')=='UsbDk device']
    require(len(redirected)==1 and clock(enums[0]['time'])<=clock(redirected[0]['time'])<clock(cycles[1]['time']),
            'Temporary redirect child is not tied to this port')
    groups=defaultdict(list)
    for row in rows:
        d=row['data']
        if row['eventId']!=110 or number(d['fid_StartIndex'])!=4000:continue
        state,event=number(d['fid_State']),number(d['fid_Event'])
        require(state in states and event in events,'Unknown state/event namespace')
        groups[number(d['fid_Context'])].append({'time':clock(row['time']),'device':number(d['fid_UsbDevice']),
            'pid':row['pid'],'state':states[state],'event':events[event],'depth':number(d['fid_Depth'])})
    selected=[]
    for child in children:
        matches=[(context,group) for context,group in groups.items() if any(r['device']==child for r in group)]
        require(len(matches)==1,'Enumerated child maps to absent or ambiguous DSM context')
        context,group=matches[0];group.sort(key=lambda r:r['time'])
        require({r['device'] for r in group}<={hub,child},'DSM context carries an unrelated child identity')
        selected.append((context,group))
    require(len({context for context,_ in selected})==3,'Distinct children share a DSM context')
    require(any(r['pid']==worker for r in selected[1][1]),'Redirect context lacks worker execution evidence')
    post=selected[2][1];done=clock(completed)
    require(selected[1][1][-1]['state']=='DsmStateEtwWaitingToBeDeleted' and selected[1][1][-1]['time']<done,
            'Redirect context did not retire before probe completion')
    require(clock(cycles[1]['time'])<=post[0]['time']<=clock(enums[1]['time'])<=post[-1]['time'],
            'Post-release context does not bracket its port enumeration')
    timers=[r for r in post if r['state']=='DsmStateEtwCheckIfDeviceCanBeDisabledOnDriverNotFound' and r['event']=='DsmEventTimerFired']
    require(len(timers)==1,'Timeout observation absent or ambiguous')
    timer=timers[0]
    entries=[r for r in post if r['state']=='DsmStateEtwStoppedEnumerated' and r['event']=='DsmEventOperationSuccess' and
             r['depth']==0 and clock(enums[1]['time'])<=r['time']<timer['time']]
    require(entries and done<timer['time'],'No successful stopped-enumerated window after probe completion')
    first_after_probe=next((r['time']-done for r in entries if r['time']>done),None)
    tail=[r for r in post if r['time']>=timer['time']]
    require([r['state'] for r in tail]==['DsmStateEtwCheckIfDeviceCanBeDisabledOnDriverNotFound',
            'DsmStateEtwDisablingDeviceInControllerOnStartTimeout','DsmStateEtwDisablingPortOnStartTimeout','DsmStateEtwStopped'] and
            tail[-1]['event']=='DsmEventPortDisabled','Unexpected post-release timeout/port-disable tail')
    project=lambda r:{'timestampFileTime':str(r['time']),'state':r['state'],'event':r['event'],'depth':r['depth']}
    return {'scope':'Trace-local exact-port/child correlation; no readiness decision',
            'port':port,'workerVidPidCycles':2,'successfulPortEnumerations':2,'distinctTargetDsmContexts':3,
            'contextRows':{'initial':len(selected[0][1]),'redirect':len(selected[1][1]),'postRelease':len(post)},
            'postReleaseContextMappedToSl3Port':True,
            'firstStoppedEnumeratedAfterProbeTicks':str(first_after_probe) if first_after_probe is not None else None,
            'postProbePendingStartFileTime':str(max(done,entries[-1]['time'])),
            'lastSuccessfulEntryToTimerTicks':str(timer['time']-entries[-1]['time']),
            'stoppedAfterProbeTicks':str(tail[-1]['time']-done),'timeoutTail':[project(r) for r in tail],
            'readinessAdmission':False,'successiveAcquisitionVerified':False,'normalUserReadinessObservationVerified':False}


def main():
    context=ROOT/'tests/results/local/logging-batch-controls-image-20261101-launch-recheck-controls'
    proof=read(ROOT/'docs/evidence/combined-controls-pass-20261101.json')
    require(proof['combinedControlsCapturePassed'] is True and sha(context/'run.json')==proof['controlsRunSha256'],
            'Controls pass binding differs')
    controls=module('validate-controls-user-probe.py');run=read(context/'run.json')
    checked=controls.validate(context,run['workerSha256'],run['probeSha256'])
    require(checked['stateObserver']['coverage']['allSourceStateRowsObserved'] is True,'Incomplete state-file correlation')
    xml=context/'events.xml';require(sha(xml)==run['traceStats']['xmlSha256'],'USB XML changed')
    rows,total=timeline.parse(xml);require(total==checked['traceStats']['eventCount'],'Event count differs')
    symbols=read(ROOT/'analysis/attended-state-symbols.json');symbol_helper=module('export-usbhub3-state-symbols.py')
    require(symbols['exporterSha256']==sha(ROOT/'scripts/export-usbhub3-state-symbols.py') and
            symbols['imageSha256']==symbol_helper.IMAGE_SHA==sha(symbol_helper.REFERENCE/'USBHUB3.SYS') and
            symbols['pdbSha256']==symbol_helper.PDB_SHA==sha(symbol_helper.REFERENCE/'usbhub3.pdb') and
            symbols['imageSemantics']['stateFieldIsEntryEtwName'] is True,'Inspected enum source differs')
    require(symbols['rsds']['guid']==symbols['pdbIdentity']['guid'] and
            symbols['pdbIdentity']['infoAge']>=symbols['rsds']['age'] and
            symbols['pdbIdentity']['dbiAge']==symbols['rsds']['age'],'PDB/image identity differs')
    image=read(ROOT/'analysis/controls-image-window-20261101-pass-rundown.json')
    require(sha(ROOT/'analysis/controls-image-window-20261101-pass-rundown.json')==
            'f804163760c766ddfa518c5dc4d9f5f078fcd2242ab71ee58aba265b03fa3022' and
            image['comparison']['matchingRundownMetadata'] is True and
            image['comparison']['expected']['diskSha256']==symbols['imageSha256'],'Image version evidence differs')
    # Check the native USB ETL header as well as the collector's later recording
    # timestamp: provider rundown can precede the collector's ready notification.
    import xml.etree.ElementTree as ET
    ns='{http://schemas.microsoft.com/win/2004/08/events/event}';usb_header=None
    for _,event in ET.iterparse(xml,events=['end']):
        if event.tag==ns+'Event':
            usb_header={d.get('Name'):(d.text or '').strip() for d in event.findall(ns+'EventData/'+ns+'Data')};break
    target=[r for r in image['kernelImages'] if r['canonicalKernelPath']==r'\SystemRoot\System32\drivers\UsbHub3.sys'.casefold()]
    require(len(target)==1 and target[0]['consistentRundownPair'] is True and
            clock(target[0]['observations'][0]['time'])<=int(usb_header['StartTime'])<int(usb_header['EndTime'])<=
            clock(target[0]['observations'][1]['time']),'Image rundown does not bracket native USB header times')
    states={r['value']:r['name'] for r in symbols['enums']['_DSM_STATE_ETW']['members']}
    events={r['value']:r['name'] for r in symbols['enums']['_DSM_EVENT']['members']}
    result=correlate(rows,checked['probe']['nativeJournal']['workerPid'],run['probeCompletedUtc'],states,events)
    result.update(all493StateRowsCorroborated=True,imageVersionMetadataMatchesNativeUsbWindow=True,
                  loadedMemoryIdentityVerified=False,usbNativeStartFileTime=usb_header['StartTime'],
                  usbNativeEndFileTime=usb_header['EndTime'],runSha256=sha(context/'run.json'),xmlSha256=sha(xml),
                  symbolsImageSha256=symbols['imageSha256'],symbolsPdbSha256=symbols['pdbSha256'])
    output=ROOT/'docs/evidence/sl3-release-port-20261101.json'
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
