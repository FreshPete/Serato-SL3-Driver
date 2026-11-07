"""Compare dispatch and device replacement in three pinned saved SL3 traces."""

import hashlib
import json
from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]
INPUTS = (
    ('failed-reopen', 'inspect-reopen-staged-20261030-02',
     '8d3f834be39c188be2625cd2cbf568e30f95caa5378f9567e4d37d632cffaccc', 14368, (25532, 25532, 32156)),
    ('control-release', 'logging-batch-controls-image-20261101-launch-recheck-controls',
     'fe6fe7ebbafc41435440fcce94fd5c6da4f71ccf68e007a639b028a7395c48a2', 6536, (19936, 19936)),
    ('audio-release', 'native-activation-release-df1a615d163247d4b2c7553cdec308f3',
     '54d930b440299ada740dc14ce687978558cacc49395b1604e1fdbb61ef518f4b', 147471, (23900, 23900)),
)
SYMBOL_SHA = 'aec5bcc3254c582cbb6e71771e69a08cbc6af1b2dd88bd42dd63f2ee1c9ef55d'


def compare(rows, pids, state_names, event_names, api, clock):
    require, number = api['require'], api['number']

    def field(row, name):
        return number(row['data'].get('fid_'+name,'0'))

    def time(row):
        return clock(row['time'])

    initial = [r for r in rows if r['eventId']==6 and r['data'].get('fid_DeviceDescription')=='Rane SL3']
    require(len(initial)==1,'Initial SL3 port is absent or ambiguous')
    hub, port, child = (field(initial[0],name) for name in ('HubDevice','PortNumber','UsbDevice'))
    require(min(hub,port,child)>0 and hub!=child,'Invalid hub and child correlation')
    cycles = sorted((r for r in rows if r['eventId']==179 and field(r,'UsbDevice')==hub and
                     field(r,'IoctlCode')==api['CYCLE'] and
                     (field(r,'idVendor'),field(r,'idProduct'))==(0x1cc5,1)),key=time)
    require(tuple(r['pid'] for r in cycles)==pids and time(initial[0])<time(cycles[0]),'Unexpected SL3 cycle sequence')
    results = []
    children = {hub,child}
    for index, cycle in enumerate(cycles):
        start = time(cycle)
        stop = time(cycles[index+1]) if index+1<len(cycles) else max(map(time,rows))+1
        window = [r for r in rows if start<=time(r)<stop]
        child_rows = [r for r in window if field(r,'UsbDevice')==child and r['pid']==cycle['pid']]
        io = [r for r in child_rows if r['eventId'] in (90,91) and field(r,'IoctlCode')==api['CYCLE']]
        require([r['eventId'] for r in io]==[90,91] and time(io[0])<=time(io[1]) and field(io[1],'NtStatus')==0,
                'Expected one zero-status dispatch on the same child')
        dsm = [r for r in child_rows if r['eventId'] in (110,111) and field(r,'StartIndex')==4000]
        detach = [r for r in dsm if r['eventId']==110 and event_names[field(r,'Event')]=='DsmEventPortDetachDevice']
        unhandled = [r for r in dsm if r['eventId']==111 and event_names[field(r,'Event')]=='DsmEventClientRequestCycle']
        replacement = [r for r in window if r['eventId']==61 and
                       field(r,'HubDevice')==hub and field(r,'PortNumber')==port]
        success = index<2
        result = {'role':('acquire','release','reacquire')[index],'dispatchStatus':field(io[1],'NtStatus'),
                  'dispatchStartAfterRequestTicks':time(io[0])-start,
                  'dispatchCompleteAfterRequestTicks':time(io[1])-start}
        if success:
            require(len(detach)==len(replacement)==1 and not unhandled and field(replacement[0],'NtStatus')==0 and
                    time(detach[0])<time(replacement[0]),'Missing detach or successful replacement on the exact port')
            child = field(replacement[0],'UsbDevice')
            require(child>0 and child not in children,'Replacement child is absent or reused')
            children.add(child)
            result.update(detachAfterRequestTicks=time(detach[0])-start,
                          detachState=state_names[field(detach[0],'State')],
                          replacementAfterRequestTicks=time(replacement[0])-start)
        else:
            require(len(unhandled)==1 and not detach and not replacement and field(unhandled[0],'State')==0x1080 and
                    time(unhandled[0])<time(io[0]),'Failed reopen state differs')
            result.update(unhandledAfterRequestTicks=time(unhandled[0])-start,
                          unhandledState=state_names[field(unhandled[0],'State')],
                          replacementAfterRequestTicks=None)
        results.append(result)
    return {'port':port,'cycles':results}


def main():
    api = runpy.run_path(str(ROOT/'scripts/export-reopen-usb-timeline.py'))
    clock = runpy.run_path(str(ROOT/'scripts/validate-usb-state-capture.py'))['filetime']
    read, require, digest = (api[name] for name in ('read','require','digest'))
    symbols_path = ROOT/'analysis/attended-state-symbols.json'
    require(digest(symbols_path)==SYMBOL_SHA,'Reviewed state names differ')
    symbols = read(symbols_path)
    states = {item['value']:item['name'] for item in symbols['enums']['_DSM_STATE_ETW']['members']}
    events = {item['value']:item['name'] for item in symbols['enums']['_DSM_EVENT']['members']}
    reports = {}
    for label, folder, expected, count, pids in INPUTS:
        xml = ROOT/'tests/results/local'/folder/'events.xml'
        require(digest(xml)==expected,'Reviewed trace hash differs')
        rows, total = api['parse'](xml)
        require(total==count,'Decoded event count differs')
        reports[label] = {'xmlSha256':expected,'decodedEvents':total,**compare(rows,pids,states,events,api,clock)}
    print(json.dumps({'schema':'sl3.saved-cycle-outcomes.v1','timeUnitNanoseconds':100,
                      'exporterSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      'symbolReportSha256':SYMBOL_SHA,'symbolicLabelsAreVersionQualified':True,
                      'captures':reports,'readinessEstablished':False,'newHardwareOperation':False},indent=2))


if __name__=='__main__':
    main()
