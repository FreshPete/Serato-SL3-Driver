"""Export a payload-free summary of the completed traced SL3 binding test.

Reads local ETW XML and recorded test outputs; performs no device operations.
Correlates the USB device pointer from the VID/PID identity event and omits raw
USB payload, instance paths and kernel pointer values from the exported events.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
folder = root / 'tests/results/local/winusb-traced-03'
ns = {'e': 'http://schemas.microsoft.com/win/2004/08/events/event'}
providers = {
    '{ac52ad17-cc01-4f85-8df5-4dce4333c99b}': 'USBHUB3',
    '{36da592d-e43a-4e28-af6f-4bc57c5a11e8}': 'UCX',
    '{30e1d284-5d88-459c-83fd-6345b39b19ec}': 'USBXHCI',
}


def read(name):
    return json.loads((folder / name).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


rows = []
for index, event in enumerate(ET.parse(folder / 'events.xml').getroot()):
    system = event.find('e:System', ns)
    rows.append({
        'xml_event_index': index,
        'utc': system.find('e:TimeCreated', ns).get('SystemTime'),
        'provider': providers.get(system.find('e:Provider', ns).get('Guid'), 'Other'),
        'event_id': int(system.findtext('e:EventID', namespaces=ns)),
        'data': {d.get('Name'): (d.text or '').strip() for d in event.findall('e:EventData/e:Data', ns)},
    })
identity = [r for r in rows if r['provider'] == 'USBHUB3' and
            'vid_1cc5&pid_0001' in r['data'].get('fid_DeviceInterfacePath', '').lower()]
devices = {r['data']['fid_UsbDevice'] for r in identity}
assert len(devices) == 1, 'An unambiguous identity-to-device-pointer correlation is required'
device = devices.pop()
target = [r for r in rows if r['data'].get('fid_UsbDevice') == device]
status_names = {'fid_IRP_NtStatus', 'fid_NtStatus', 'fid_UsbdStatus'}
status_counts = Counter((k, v) for r in target for k, v in r['data'].items() if k in status_names)
fields = status_names | {'fid_UrbFunction', 'fid_TargetState', 'fid_PowerAction',
                        'fid_ConfigurationValue', 'fid_InterfaceNumber',
                        'fid_AlternateSetting', 'fid_LastConfigureEndpointStatus'}
selected = []
for r in target:
    if ((r['provider'] == 'USBHUB3' and r['event_id'] in [41, 42, 51, 52, 92, 93]) or
            (r['provider'] == 'USBXHCI' and r['event_id'] == 48)):
        selected.append({**{k: v for k, v in r.items() if k != 'data'},
                         'data': {k: v for k, v in r['data'].items() if k in fields}})
head = rows[0]['data']
capture = read('trace/capture.json')
run = read('run.json')
installation = read('winusb-development-test.json')
probe = read('active-settings-probe.json')
final = read('final-state.json')
while_usb = read('while-winusb-descriptors.json')['devices'][0]
after_usb = read('after-cleanup-descriptors.json')['devices'][0]
baseline = json.loads((root / 'docs/evidence/sl3-descriptors-2026-10-26.json').read_text())['devices'][0]
assert installation['startSucceeded'] and probe['initialized']
assert probe['active_settings'] == [{'number': i, 'alternate': 0} for i in range(4)]
assert run['cleanup'] == 'completed' and run['secureBootBefore'] and run['secureBootAfter']
assert not final['experimentalInfPresent'] and final['originalInfPresent']
assert not final['projectInterfaceGuidPresent'] and not any(x['present'] for x in final['certificates'])
assert final['device']['Problem'] == 39
assert all(after_usb[k] == while_usb[k] == baseline[k]
           for k in ['device_descriptor_hex', 'configuration_descriptor_hex'])
result = {
    'scope': 'One actual binding attempt after two readiness-only aborts; descriptor/pipe/current-setting queries only. No alternate selection, interrupt command, audio, firmware or boot-policy changes.',
    'local_results': str(folder.relative_to(root)),
    'historical_failure_reproduced': False,
    'installation': installation,
    'trace': {
        'file': capture['files'][0], 'xml_sha256': digest(folder / 'events.xml'),
        'event_count': len(rows), 'events_lost': int(head['EventsLost']), 'buffers_lost': int(head['BuffersLost']),
        'provider_event_counts': dict(Counter(r['provider'] for r in rows)),
        'correlation': 'SL3 VID/PID identity event -> fid_UsbDevice -> matching USBHUB3, UCX and USBXHCI events. Pointer and instance path omitted.',
        'target_event_count': len(target),
        'target_status_counts': [{'field': k, 'value': v, 'count': n} for (k, v), n in status_counts.items()],
        'selected_events': selected,
    },
    'active_settings_probe': probe,
    'configuration_while_winusb': while_usb['configuration'],
    'descriptors_match_baseline_after_cleanup': True,
    'final_state': final,
    'secure_boot_before': run['secureBootBefore'], 'secure_boot_after_cleanup': run['secureBootAfter'],
    'cleanup': read('winusb-development-cleanup.json'),
    'pnp_events': read('pnp-events.json'),
    'interpretation': 'WinUSB startup and read-only access succeeded with all interfaces at alternate 0. The previous power-start failure remains unexplained; missing audio alternate 1 is not an unconditional startup blocker. Alternate switching, streaming and device command semantics remain untested.',
}
out = root / 'docs/evidence/winusb-traced-binding.json'
out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'events': len(rows), 'target_events': len(target), 'selected_events': len(selected),
                  'events_lost': result['trace']['events_lost'], 'started': True, 'cleanup': run['cleanup']}))
