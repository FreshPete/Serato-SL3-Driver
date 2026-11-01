"""Export payload-free evidence from the completed SL3 audio-alternate test.

Reads local recordings only. USB pointer correlation is performed locally; raw
transfer data, instance paths and kernel pointers are omitted from the export.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
folder = root / 'tests/results/local/winusb-audio-alternates-01'
ns = {'e': 'http://schemas.microsoft.com/win/2004/08/events/event'}
providers = {'{ac52ad17-cc01-4f85-8df5-4dce4333c99b}': 'USBHUB3',
             '{36da592d-e43a-4e28-af6f-4bc57c5a11e8}': 'UCX',
             '{30e1d284-5d88-459c-83fd-6345b39b19ec}': 'USBXHCI'}


def read(name):
    return json.loads((folder / name).read_text(encoding='utf-8-sig'))


rows = []
for index, event in enumerate(ET.parse(folder / 'events.xml').getroot()):
    system = event.find('e:System', ns)
    rows.append(dict(xml_event_index=index,
                     utc=system.find('e:TimeCreated', ns).get('SystemTime'),
                     provider=providers.get(system.find('e:Provider', ns).get('Guid'), 'Other'),
                     event_id=int(system.findtext('e:EventID', namespaces=ns)),
                     data={d.get('Name'): (d.text or '').strip() for d in event.findall('e:EventData/e:Data', ns)}))
identity = {r['data']['fid_UsbDevice'] for r in rows
            if 'vid_1cc5&pid_0001' in r['data'].get('fid_DeviceInterfacePath', '').lower()}
assert len(identity) == 1
device = identity.pop()
target = [r for r in rows if r['data'].get('fid_UsbDevice') == device]
fields = {'fid_UrbFunction', 'fid_UsbdStatus', 'fid_NtStatus', 'fid_IRP_NtStatus',
          'fid_ConfigurationValue', 'fid_InterfaceNumber', 'fid_AlternateSetting', 'fid_LastConfigureEndpointStatus'}
selected = [{**{k: v for k, v in r.items() if k != 'data'},
             'data': {k: v for k, v in r['data'].items() if k in fields}}
            for r in target if ((r['provider'] == 'USBXHCI' and r['event_id'] == 48) or
                                (r['provider'] == 'USBHUB3' and r['event_id'] == 93))]
configuration = [r for r in selected if r['provider'] == 'USBXHCI']
observed = [(int(r['data']['fid_InterfaceNumber'], 0), int(r['data']['fid_AlternateSetting'], 0)) for r in configuration]
assert observed[-4:] == [(1, 1), (2, 1), (2, 0), (1, 0)]
assert all(r['data']['fid_LastConfigureEndpointStatus'] == '0x0' for r in configuration)
head = rows[0]['data']
assert (int(head['EventsLost']), int(head['BuffersLost'])) == (0, 0)
experiment = read('audio-alternates.json')
assert experiment['activation_succeeded'] and experiment['restoration_succeeded'] and not experiment['error']
assert all(o['succeeded'] for o in experiment['operations'])
assert [r['alternate'] for r in experiment['after_interface_2']] == [0, 1, 1, 0]
assert [r['alternate'] for r in experiment['after_restore']] == [0, 0, 0, 0]
run = read('run.json')
final = read('final-state.json')
assert run['cleanup'] == 'completed' and run['secureBootBefore'] and run['secureBootAfter']
assert final['device']['Problem'] == 39 and final['originalInfPresent'] and not final['experimentalInfPresent']
assert not final['projectInterfaceGuidPresent'] and not any(c['present'] for c in final['certificates'])
baseline = json.loads((root / 'docs/evidence/sl3-descriptors-2026-10-26.json').read_text())['devices'][0]
after = read('after-cleanup-descriptors.json')['devices'][0]
assert all(after[k] == baseline[k] for k in ['device_descriptor_hex', 'configuration_descriptor_hex'])
status_counts = Counter((k, v) for r in target for k, v in r['data'].items()
                        if k in {'fid_UsbdStatus', 'fid_NtStatus', 'fid_IRP_NtStatus'})
result = {
    'scope': 'One traced binding and audio-alternate activation/restoration. No audio data, interrupt transfers, vendor controls, resets or firmware operations.',
    'local_results': str(folder.relative_to(root)), 'experiment': experiment,
    'installation': read('winusb-development-test.json'),
    'trace': {'file': read('trace/capture.json')['files'][0],
              'xml_sha256': hashlib.sha256((folder / 'events.xml').read_bytes()).hexdigest(),
              'events': len(rows), 'events_lost': int(head['EventsLost']), 'buffers_lost': int(head['BuffersLost']),
              'target_events': len(target), 'correlation': 'VID/PID identity -> fid_UsbDevice; pointer/path/payload omitted',
              'target_status_counts': [dict(field=k, value=v, count=n) for (k, v), n in status_counts.items()],
              'target_bulk_interrupt_dispatch_events': sum(r['provider'] == 'UCX' and r['event_id'] == 26 for r in target),
              'target_isochronous_dispatch_events': sum(r['provider'] == 'UCX' and r['event_id'] == 30 for r in target),
              'selected_events': selected},
    'cleanup': read('winusb-development-cleanup.json'), 'final_state': final,
    'secure_boot_before': run['secureBootBefore'], 'secure_boot_after_cleanup': run['secureBootAfter'],
    'descriptors_match_baseline_after_cleanup': True, 'pnp_events': read('pnp-events.json'),
    'interpretation': 'WinUSB selected the original driver audio alternate topology and restored it successfully. This does not establish audio clocking, sample format, packet scheduling, control semantics, ASIO, Serato support or stability.'}
(root / 'docs/evidence/winusb-audio-alternates.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'events': len(rows), 'target_events': len(target), 'configuration_sequence': observed,
                  'activation_succeeded': True, 'restoration_succeeded': True, 'cleanup': run['cleanup']}))
