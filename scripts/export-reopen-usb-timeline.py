"""Reproduce USBHUB3 observations in the historical failed second redirect.

Offline only. A USB event's fid_UsbDevice can mean the hub or the child,
depending on the event schema. Correlate hub/port and child identities separately.
This is an observation report, not a successful-startup acceptance gate.
"""
import collections
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = {'e': 'http://schemas.microsoft.com/win/2004/08/events/event'}
PROVIDER = 'Microsoft-Windows-USB-USBHUB3'
GUID = '{ac52ad17-cc01-4f85-8df5-4dce4333c99b}'
# WDK usbioctl.h/usbiodef.h: CTL_CODE(FILE_DEVICE_UNKNOWN, 7,
# METHOD_NEITHER, FILE_ANY_ACCESS) = (0x22 << 16) | (7 << 2) | 3.
CYCLE = (0x22 << 16) | (7 << 2) | 3


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def number(value):
    return int(value.strip(), 0)


def parse(path):
    rows, total = [], 0
    for _, event in ET.iterparse(path, events=['end']):
        if event.tag != '{'+NS['e']+'}Event':
            continue
        total += 1
        system = event.find('e:System', NS)
        provider = system.find('e:Provider', NS)
        if provider.get('Name') == PROVIDER:
            require(provider.get('Guid').lower() == GUID, 'Unexpected provider GUID')
            rows.append({
                'time': system.find('e:TimeCreated', NS).get('SystemTime'),
                'pid': int(system.find('e:Execution', NS).get('ProcessID')),
                'eventId': int(system.findtext('e:EventID', namespaces=NS)),
                'task': int(system.findtext('e:Task', namespaces=NS)),
                'message': event.findtext('e:RenderingInfo/e:Message', default='', namespaces=NS).strip(),
                'data': {item.get('Name'): (item.text or '').strip()
                         for item in event.findall('e:EventData/e:Data', NS)},
            })
        event.clear()
    return rows, total


def main():
    folder = ROOT/'tests/results/local/inspect-reopen-staged-20261030-02'
    previous = read(ROOT/'docs/evidence/inspect-reopen-after-power-cycle-20261030.json')
    require(digest(folder/'run.json') == previous['runRecordSha256'].lower(), 'Run identity differs')
    run = read(folder/'run.json')
    require(not run['completed'] and run['inspectionOnly'], 'Expected historical failed inspection')
    require(digest(folder/'probe/probe.json') == run['probeRecordSha256'].lower(), 'Probe identity differs')
    xml = folder/'events.xml'
    require(digest(xml) == run['traceStats']['xmlSha256'].lower(), 'Decoded trace identity differs')
    etls = list((folder/'trace').glob('*.etl'))
    require(len(etls) == 1 and digest(etls[0]) == run['etlSha256'].lower(), 'ETL identity differs')
    require(run['traceStats']['eventsLost'] == run['traceStats']['buffersLost'] == 0, 'Lossy trace')
    journals = []
    for item in run['startupJournals']:
        prefix = (folder/'probe'/item['name']).read_bytes()[:item['snapshotBytes']]
        require(hashlib.sha256(prefix).hexdigest() == item['snapshotSha256'].lower(), 'Journal prefix differs')
        records = [line.split('\t') for line in prefix.decode('utf-8').splitlines()]
        require(len(records) == item['completeRecords'] and all(len(r) == 3 for r in records), 'Journal shape differs')
        pids = {int(r[1]) for r in records}
        require(len(pids) == 1, 'Journal has mixed process identities')
        journals.append({'pid': pids.pop(), 'snapshotSha256': item['snapshotSha256'],
                         'markers': [r[2] for r in records]})
    require(len(journals) == 2 and journals[0]['markers'][-1] == 'helper_unload.return'
            and journals[1]['markers'][-1] == 'redirect_start.enter'
            and 'redirect_start.return' not in journals[1]['markers'], 'Unexpected observed lifecycle')
    rows, total = parse(xml)
    require(total == run['traceStats']['eventCount'], 'Trace event count differs')
    initial = [r for r in rows if r['eventId'] == 6 and r['data'].get('fid_DeviceDescription') == 'Rane SL3']
    require(len(initial) == 1, 'Ambiguous initial SL3 rundown')
    data = initial[0]['data']
    hub, port = data['fid_HubDevice'], number(data['fid_PortNumber'])
    def on_port(row):
        d = row['data']
        # Enumeration-start and port-status schemas name the hub fid_UsbDevice.
        return d.get('fid_HubDevice', d.get('fid_UsbDevice')) == hub and number(d.get('fid_PortNumber', '-1')) == port
    enumerations = [r for r in rows if r['eventId'] == 61 and on_port(r)]
    children = {data['fid_UsbDevice']} | {r['data']['fid_UsbDevice'] for r in enumerations}
    pids = {r['pid'] for r in journals}
    cycles = [r for r in rows if r['eventId'] == 179 and r['pid'] in pids
              and r['data'].get('fid_UsbDevice') == hub
              and number(r['data'].get('fid_IoctlCode', '0')) == CYCLE
              and number(r['data'].get('fid_idVendor', '0')) == 0x1cc5
              and number(r['data'].get('fid_idProduct', '0')) == 1]
    require([r['pid'] for r in cycles] == [journals[0]['pid'], journals[0]['pid'], journals[1]['pid']],
            'Expected acquire/release/reacquire recovery actions')
    timeline = [r for r in rows if r['time'] >= cycles[0]['time'] and r['eventId'] != 110
                and (on_port(r) or r['data'].get('fid_UsbDevice') in children
                     or r in cycles)]
    second = cycles[-1]
    after = [r for r in timeline if r['time'] >= second['time']]
    completions = [r for r in after if r['eventId'] == 91
                   and number(r['data'].get('fid_IoctlCode', '0')) == CYCLE]
    require(len(completions) == 1 and number(completions[0]['data']['fid_NtStatus']) == 0,
            'Second cycle dispatch completion observation differs')
    require(len(enumerations) == 2 and all(number(r['data']['fid_NtStatus']) == 0 for r in enumerations),
            'Expected two successful pre-reacquisition enumerations')
    require(not any(r['eventId'] in (60, 61) for r in after), 'Later enumeration now present')
    require(sum(r['eventId'] == 111 for r in after) == 1, 'Unhandled state event observation differs')
    counts = collections.Counter(r['eventId'] for r in after)
    result = {
        'scope': 'Offline USBHUB3 timeline of one historical failed second redirect; no new hardware operation',
        'runRecordSha256': digest(folder/'run.json'), 'xmlSha256': digest(xml),
        'etlSha256': digest(etls[0]), 'traceStats': run['traceStats'],
        'traceStoppedUtc': run['traceStoppedUtc'], 'provider': PROVIDER, 'providerGuid': GUID,
        'cycleIoctl': hex(CYCLE), 'hubObject': hub, 'port': port,
        'childObjects': sorted(children), 'journalPrefixes': journals,
        'secondCycleObservedUtc': second['time'],
        'secondCycleDispatchCompletion': completions[0],
        'targetNonStateEventCountsAfterSecondCycle': dict(sorted(counts.items())),
        'timeline': timeline,
        'limits': [
            'Object addresses are trace-local identities, not stable device identifiers.',
            'fid_UsbDevice denotes a hub in some schemas and a child in others; arbitrary pointer equality is insufficient.',
            'USBHUB3 reports successful cycle dispatch completion; this is not UsbDk StartRedirect completion or successful PnP reattachment.',
            'No further target-port enumeration is recorded in this trace; zero reported loss does not prove all internal execution was observable.',
            'Unhandled state numeric fields are preserved without assigning undocumented state-machine meanings.',
            'Cycle receipt shows this attempt progressed beyond a preceding startup power wait; the exact subsequent UsbDk wait remains unidentified.',
            'The old journal prefix stops at second redirect entry; later appended journal data is outside its bound evidence.',
            'No UsbDk WPP lifecycle messages were captured; no kernel timeout, arbitrary delay or cancellation fix is established.',
        ],
    }
    (ROOT/'docs/evidence/reopen-usb-timeline-20261030.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified historical second-cycle receipt/completion, unhandled state event and absent later target-port enumeration')


if __name__ == '__main__':
    main()
