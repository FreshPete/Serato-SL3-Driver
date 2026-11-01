"""Compare allowlisted current device fields with exact component-count code."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/file)
    value = importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


h = load('component_image', 'export-serato-clock-handshake-evidence.py')
r = load('component_archive', 'inspect-serato-resource-archive.py')
FIELDS = ('vendor_id', 'product_id', 'bcd_device', 'midi_direction', 'has_hid', 'requires_usb',
          'handshake_type', 'win_audio_api', 'win_audio_device_name', 'num_decks', 'dvs_device', 'dvs_only_device')
SELECTED = ('audio/serato_virtual_audio.xml', 'midi/midi_denon_ds1.xml', 'midi/midi_reloop_flux.xml',
            'midi/midi_reloop_flux_go.xml', 'hid/hid_traktor_kontrol_z2.xml', 'hid/hid_mwm_phase.xml')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    app = h.Image(r.APP_RELATIVE, r.APP_SHA)
    h.require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe').read_bytes()) == app.sha, 'Installed image differs')
    evidence = []
    checks = [
        (0x1405c90f6, 'lea', 'rdx, [rip + 0x22545e3]'), (0x1405c9100, 'call', '0x141b17da0'),
        (0x1405c9105, 'test', 'rax, rax'), (0x1405c9108, 'je', '0x1405c912b'),
        (0x1405c911f, 'lea', 'rcx, [rsi + 0x3e0]'), (0x1405c9126, 'call', '0x1404a8080'),
        (0x1405c6f0a, 'lea', 'rbx, [rcx + 0x3d0]'), (0x1405c6f19, 'mov', 'edi, 3'),
        (0x1405c6f2a, 'mov', 'r15d, 2'), (0x1405c6f30, 'lea', 'rdx, [rip + 0x2256421]'),
        (0x1405c6f41, 'call', '0x1421201f0'), (0x1405c6f4a, 'cmp', 'rsi, r15'),
        (0x1405c6f46, 'test', 'eax, eax'), (0x1405c6f48, 'jne', '0x1405c6f56'),
        (0x1405c6f4d, 'jne', '0x1405c6f56'), (0x1405c6f54, 'jmp', '0x1405c6fc4'),
        (0x1405c6f4f, 'mov', 'eax, 1'), (0x1405c6f60, 'cmp', 'rsi, rdi'),
        (0x1405c6f63, 'lea', 'rdx, [rip + 0x22563f2]'), (0x1405c6f74, 'call', '0x1421201f0'),
        (0x1405c6f7d, 'cmp', 'rsi, rdi'), (0x1405c6f82, 'mov', 'eax, r15d'),
        (0x1405c6f79, 'test', 'eax, eax'), (0x1405c6f7b, 'jne', '0x1405c6f87'),
        (0x1405c6f80, 'jne', '0x1405c6f87'), (0x1405c6f85, 'jmp', '0x1405c6fc4'),
        (0x1405c6f9c, 'mov', 'eax, 4'), (0x1405c6fa1, 'lea', 'rdx, [rip + 0x223f138]'),
        (0x1405c6fb2, 'call', '0x1421201f0'), (0x1405c6fb7, 'test', 'eax, eax'),
        (0x1405c6fb9, 'jne', '0x1405c6fc2'), (0x1405c6fbb, 'cmp', 'rbx, 4'),
        (0x1405c6fbf, 'cmove', 'edi, eax'), (0x1405c6fc2, 'mov', 'eax, edi'),
        (0x1421db993, 'xor', 'r14d, r14d'),
        (0x1421db9dc, 'call', '0x140c00570'), (0x1421db9e8, 'call', 'qword ptr [rax + 0x10]'),
        (0x1421db9eb, 'mov', 'edi, r14d'), (0x1421db9ee, 'test', 'eax, eax'),
        (0x1421db9f0, 'setne', 'dil'),
        (0x1421dba37, 'call', '0x140c00570'), (0x1421dba43, 'call', 'qword ptr [rax + 0x18]'),
        (0x1421dba46, 'movzx', 'esi, al'),
        (0x1421dba8c, 'call', '0x140c00570'), (0x1421dba98, 'call', 'qword ptr [rax + 0x28]'),
        (0x1421dba9b, 'movzx', 'ecx, al'), (0x1421dba9e, 'add', 'ecx, edi'),
        (0x1421dbaa0, 'add', 'ecx, esi'), (0x1421dbaa2, 'mov', 'dword ptr [rsp + 0x98], ecx'),
    ]
    for va, op, operands in checks:
        row = app.at(va, op, operands)
        evidence.append({'va': hex(va), 'bytes': row.bytes.hex(), 'instruction': op+' '+operands})
    for va, literal in ((0x1405c90f6, 'midi_direction'), (0x1405c6f30, 'in'),
                        (0x1405c6f63, 'out'), (0x1405c6fa1, 'none')):
        h.require(app.text(app.rip(app.at(va))) == literal, 'Wrong field/direction literal')
    table = 0x14281caf0
    locator = struct.unpack('<Q', app.data(table-8, 8))[0]
    col = struct.unpack('<6I', app.data(locator, 24))
    h.require(col[0] == 1 and col[1] == 16 and col[5]+app.base == locator and
              app.text(app.base+col[3]+16) == '.?AVControllerDescriptor@dj@serato@@', 'Wrong descriptor interface RTTI')
    for offset, target in ((0x10, 0x1405c6ef0), (0x18, 0x1405c7da0), (0x28, 0x1405c7e30)):
        h.require(struct.unpack('<Q', app.data(table+offset, 8))[0] == target, 'Wrong capability getter slot')
    app.pe.parse_data_directories(directories=[1])
    imports = {e.address: (d.dll.decode(), e.name.decode() if e.name else '') for d in app.pe.DIRECTORY_ENTRY_IMPORT for e in d.imports}
    thunk = list(app.dis.disasm(app.data(0x1421201f0, 6), 0x1421201f0))
    h.require(len(thunk) == 1 and thunk[0].mnemonic == 'jmp' and
              imports[app.rip(thunk[0])] == ('VCRUNTIME140.dll', 'memcmp'), 'Comparison is not the actual bytewise import')
    archive = (ROOT/r.APP_RELATIVE).with_name('userio_resources.bin').read_bytes()
    h.require(sha(archive) == r.ARCHIVE_SHA and
              Path('C:/Program Files/Serato/Serato DJ Pro/userio_resources.bin').read_bytes() == archive, 'Archive differs')
    seed = app.data(0x142f2de98, 16)
    key = struct.unpack('<4I', bytes((((x ^ 0xcf) >> (n & 7)) | ((x ^ 0xcf) << ((8-(n & 7)) & 7))) & 255 for n, x in enumerate(seed)))
    size = struct.unpack_from('<Q', archive)[0]
    h.require(size <= len(archive)-8, 'Index exceeds archive')
    entries = r.parse_index(r.decode_block(archive[8:8+size], key), len(archive), 8+size)
    profiles, direction_counts, kinds = [], Counter(), Counter()
    for entry in entries:
        data, crc = r.unpack_member(archive[entry['offset']:entry['offset']+entry['size']], key, entry['name'])
        if entry['name'].endswith('.xsd'):
            continue
        h.require(entry['name'].endswith('.xml'), 'Unexpected resource type')
        safe = re.sub(rb'<!DOCTYPE\s+[A-Za-z_][A-Za-z0-9_.:-]*\s*>', b'', data, flags=re.I)
        h.require(b'<!DOCTYPE' not in safe.upper() and b'<!ENTITY' not in safe.upper(), 'Unsupported XML declarations')
        for node in ET.fromstring(safe).iter():
            if node.tag not in ('native_pro_device', 'native_intro_device', 'osa_device'):
                continue
            fields = {}
            for tag in FIELDS:
                values = node.findall(tag)
                h.require(len(values) <= 1, 'Ambiguous scalar field: '+tag)
                if values:
                    fields[tag] = values[0].get('value')
            declared = fields.get('midi_direction')
            projection = {'in': 1, 'out': 2, 'none': 0}.get(declared, 3)
            direction_counts['value:'+str(declared) if 'midi_direction' in fields else '<absent>'] += 1
            kinds[node.tag] += 1
            profiles.append({'resource': entry['name'], 'kind': node.tag, 'fields': fields,
                             'xmlSha256': sha(data), 'zipCrc32': crc,
                             'controllerDescriptorMidiGetterProjection': projection,
                             'midiContributionIfThisGetterAndBranchUsed': int(projection != 0)})
    h.require(len(entries) == 229 and len(profiles) == 197 and dict(direction_counts) ==
              {'value:none': 15, '<absent>': 179, 'value:duplex': 1, 'value:in': 2}, 'Profile inventory differs')
    no_midi = [p for p in profiles if p['fields'].get('midi_direction') == 'none']
    selected = [p for p in profiles if p['resource'] in SELECTED]
    h.require(len(selected) == 6 and Counter(p['kind'] for p in no_midi) ==
              {'native_pro_device': 1, 'native_intro_device': 3, 'osa_device': 11}, 'Selected component profiles differ')
    result = {'scope': 'Allowlisted descriptor data plus original MIDI getter/component-count branch; no device or application execution',
              'binarySha256': app.sha, 'archiveSha256': r.ARCHIVE_SHA, 'allMemberCrcsVerified': True,
              'recognizedProfiles': 197, 'kindCounts': dict(kinds), 'midiDeclarationHistogram': dict(direction_counts),
              'allProfilesMetadataSha256': sha(json.dumps(profiles, sort_keys=True, separators=(',', ':')).encode()),
              'selectedProfiles': selected, 'explicitNoMidiResources': [p['resource'] for p in no_midi],
              'explicitNoMidiKindCounts': dict(Counter(p['kind'] for p in no_midi)),
              'explicitNoMidiWithHasHidTrue': sum(p['fields'].get('has_hid') == 'true' for p in no_midi),
              'explicitNoMidiNativeProDeclaringDvsYes': sum(p['kind'] == 'native_pro_device' and p['fields'].get('dvs_device') == 'DVS_DEVICE_YES' for p in no_midi),
              'descriptorInterface': {'vtable': hex(table), 'locator': hex(locator), 'completeOffset': 16},
              'checkedInstructions': evidence, 'comparisonImport': 'VCRUNTIME140.dll!memcmp',
              'midiGetter': {'exactStrings': {'in': 1, 'out': 2, 'none': 0}, 'emptyOrOther': 3, 'caseSensitive': True},
              'limits': ['Missing fields remain absent in the report, not invented false/none values',
                         'Projection through the checked ControllerDescriptor getter does not prove each resource uses that concrete getter/constructor at runtime',
                         'Getter projections assume construction/parser state with no later mutation; no runtime support/connection prediction',
                         'Component sum applies only to the identified descriptor branch, not every device/connection path',
                         'Handshake/DVS labels do not expose authentication material or establish account entitlement',
                         'No resource writer, identity substitution, application/account change or admitted SL3 integration introduced']}
    (ROOT/'docs/evidence/serato500-component-profiles.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified 197 profiles, 15 explicit no-MIDI declarations, selected interface differences and exact MIDI getter/component contribution')


if __name__ == '__main__':
    main()
