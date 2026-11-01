"""Check original SL3 descriptor/remapping initialization without vendor execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    controls = load('sl3_through', ROOT / 'scripts/export-serato-sl3-through-contract.py')
    controls.main()
    clock, require = controls.clock, controls.require
    image = clock.Image('artifacts/extracted/Serato DJ Pro 2.5.5/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe', clock.OLD_SHA)
    legacy = load('sl3_descriptor', ROOT / 'scripts/export-serato-legacy-descriptors.py')
    descriptor, _, _, xml = legacy.inspect(legacy.TARGETS[0])
    require(hashlib.sha256(xml).hexdigest() == '314e81ffb5d052e53280903d543107c8223e99ff1f4e200311a2b3d90e49154c',
            'Recovered original SL3 XML differs')
    device = ET.fromstring(xml).find('native_pro_device')
    require(device is not None and device.find('num_decks').get('value') == '3' and
            device.find('allow_channel_setup') is None, 'Original SL3 descriptor fields differ')
    checks = []

    def at(address, op, operands):
        row = image.at(address, op, operands)
        checks.append({'va': hex(address), 'instruction': f'{row.mnemonic} {row.op_str}'})

    require(image.text(image.rip(image.at(0x1403590ad, 'lea'))) == 'num_decks', 'Deck-count tag differs')
    require(image.text(image.rip(image.at(0x14035af05, 'lea'))) == 'allow_channel_setup', 'Setup tag differs')
    image.pe.parse_data_directories(directories=[1])
    atoi_slot = image.rip(image.at(0x1403590d6, 'call'))
    require(any(item.address == atoi_slot and item.name == b'atoi'
                for library in image.pe.DIRECTORY_ENTRY_IMPORT for item in library.imports), 'Count conversion differs')
    for address, op, operands in [
        # Parsed count is preserved, then loaded for the initial map/vector.
        (0x1403590dc, 'mov', 'ebx, eax'), (0x1403590de, 'mov', 'dword ptr [rbp - 0x30], eax'),
        (0x1403590c4, 'lea', 'rdx, [rip + 0x43e9d1d]'),
        (0x1403590ce, 'call', '0x1408bdee0'), (0x1403590d3, 'mov', 'rcx, rax'),
        (0x14035b480, 'mov', 'r13d, dword ptr [rbp - 0x30]'),
        (0x14035b1fe, 'lea', 'rcx, [rbp + 0x700]'), (0x14035b205, 'call', '0x14035bc30'),
        (0x14035b868, 'xor', 'r15d, r15d'), (0x14035b8ad, 'cmp', 'r13d, 4'),
        (0x14035b8b1, 'jne', '0x14035b8cc'),
        (0x14035b8cc, 'mov', 'rbx, r15'), (0x14035b8cf, 'test', 'r13d, r13d'),
        (0x14035b8d2, 'je', '0x14035b8fd'),
        (0x14035b8e0, 'mov', 'dword ptr [rbp - 0x80], ebx'),
        (0x14035b8e3, 'lea', 'rdx, [rbp - 0x80]'), (0x14035b8e7, 'lea', 'rcx, [rbp + 0xa78]'),
        (0x14035b8ee, 'call', '0x1400b42b0'), (0x14035b8f3, 'mov', 'dword ptr [rax], ebx'),
        (0x14035b8f5, 'inc', 'rbx'), (0x14035b8f8, 'cmp', 'rbx, r13'),
        (0x14035b8fb, 'jb', '0x14035b8e0'),
        (0x14035b914, 'lea', 'r8, [rbp - 0x80]'), (0x14035b918, 'mov', 'rdx, r13'),
        (0x14035b91b, 'lea', 'rcx, [rbp + 0xa98]'), (0x14035b922, 'call', '0x14035d7b0'),
        (0x14035b952, 'movsxd', 'r8, dword ptr [rax + 0x20]'),
        (0x14035b956, 'mov', 'rdx, qword ptr [rbp + 0xa98]'),
        (0x14035b95d, 'mov', 'ecx, dword ptr [rax + 0x1c]'),
        (0x14035b960, 'mov', 'dword ptr [rdx + r8*4], ecx'),
        # Missing allow_channel_setup keeps zero; the parsed byte reaches +3f8.
        (0x14035aef2, 'mov', 'byte ptr [rsp + 0x5f], 0'),
        (0x14035af17, 'test', 'rax, rax'), (0x14035af1a, 'je', '0x14035b00e'),
        (0x14035af2f, 'mov', 'byte ptr [rsp + 0x5f], al'),
        (0x14035b7da, 'movzx', 'eax, byte ptr [rsp + 0x5f]'),
        (0x14035b7df, 'mov', 'byte ptr [rbp + 0xaf8], al'),
        (0x1400f7134, 'cmp', 'byte ptr [rbx + 0x3f8], 0'),
        (0x1400f713b, 'je', '0x1400f71a3'), (0x1400f7143, 'mov', 'edx, eax'),
        (0x1400f7145, 'mov', 'rcx, rbx'), (0x1400f7148, 'call', '0x140356850'),
        (0x140356873, 'test', 'edx, edx'), (0x140356875, 'je', '0x1403568c0'),
        (0x140356877, 'sub', 'edx, 1'), (0x14035687a, 'je', '0x1403568ae'),
        (0x14035687c, 'sub', 'edx, 1'), (0x14035687f, 'je', '0x14035689c'),
        (0x140356881, 'cmp', 'edx, 1'), (0x140356884, 'jne', '0x140356984'),
        # The alternate builder also stores the inverse map, not its forward map.
        (0x140356910, 'mov', 'ecx, dword ptr [rax + 0x1c]'),
        (0x140356913, 'movsxd', 'r8, dword ptr [rax + 0x20]'),
        (0x140356917, 'mov', 'rdx, qword ptr [rdi + 0x398]'),
        (0x14035691e, 'mov', 'dword ptr [rdx + r8*4], ecx')]:
        at(address, op, operands)
    require(image.rip(image.at(0x1400f7128, 'mov')) == 0x144e39ef8, 'Global receiver differs')
    require(image.text(image.rip(image.at(0x1403590c4, 'lea'))) == 'value', 'Count attribute differs')
    require(0xa78 - 0x700 == 0x378 and 0xa98 - 0x700 == 0x398 and 0xaf8 - 0x700 == 0x3f8,
            'Stack descriptor coordinates differ')
    # Verify each branch's actual SIMD sources, then decode original table data.
    layouts = []
    for kind, first, second, sources in [
        (0, 0x1403568c0, 0x1403568c8, (0x1447d4d00, 0x1447d4e60)),
        (1, 0x1403568ae, 0x1403568b6, (0x1447d4ad0, 0x1447d4e50)),
        (2, 0x14035689c, 0x1403568a4, (0x1447d4d30, 0x1447d4e80)),
        (3, 0x14035688a, 0x140356892, (0x1447d4ae0, 0x1447d4e70))]:
        require(tuple(image.rip(image.at(address, 'movdqa')) for address in (first, second)) == sources,
                'Layout constant source differs')
        values = struct.unpack('<8i', b''.join(image.data(address, 16) for address in sources))
        pairs = list(zip(values[::2], values[1::2]))
        inverse = [None] * 4
        for key, value in pairs:
            require(0 <= value < 4 and inverse[value] is None, 'Layout inverse is ambiguous')
            inverse[value] = key
        layouts.append({'kind': kind, 'mapEntries': pairs, 'inverseVector': inverse})
    require([x['inverseVector'] for x in layouts] == [[0, 1, 2, 3], [1, 2, 0, 3], [0, 2, 3, 5], [2, 3, 0, 5]],
            'Alternate layout constants differ')
    report_paths = ['analysis/serato255-descriptor-parser-08.json', 'analysis/serato255-remap-fields.json',
                    'analysis/serato255-remap-events.json']
    for name in report_paths:
        report = json.loads((ROOT / name).read_text(encoding='utf-8-sig'))
        require(report['binary_sha256'] == image.sha and all(f.get('complete') for f in report['functions']),
                'Focused report identity/completion differs')
    result = {'scope': 'Original 2.5.5 SL3 descriptor initial remapping; static successful-parse consequence, not captured runtime state',
              'seratoSha256': image.sha, 'exporterSha256': sha(Path(__file__)),
              'sourceHelpers': {name: sha(ROOT / name) for name in ['scripts/export-serato-sl3-through-contract.py',
                  'scripts/export-serato-clock-handshake-evidence.py', 'scripts/export-serato-legacy-descriptors.py']},
              'descriptorXmlSha256': hashlib.sha256(xml).hexdigest(),
              'descriptorDecks': 3, 'allowChannelSetupPresent': False, 'allowChannelSetupDefault': False,
              'initialInverseVector': [0, 1, 2], 'initialApiSlotToControlGroup': [1, 2, 0],
              'descriptorOffsets': {'map': '0x378', 'inverseVector': '0x398', 'allowChannelSetup': '0x3f8'},
              'alternateLayouts': layouts, 'instructionChecks': checks,
              'focusedReports': [{'path': name, 'sha256': sha(ROOT / name)} for name in report_paths],
              'throughContractSha256': sha(ROOT / 'docs/evidence/serato255-sl3-through-contract.json'),
              'runtimeVectorCaptured': False, 'physicalMappingVerified': False, 'currentSeratoAdmissionVerified': False,
              'limits': ['Initial vector follows the original three-deck descriptor and successful parser/allocation path.',
                        'The inspected layout event cannot call its builder with a zero allow-channel-setup flag; other writers are not exhaustively excluded.',
                        'Alternate layout constants are not configurations to apply to the SL3.',
                        'No application execution, USB request, setting, resource patch, registration, account or firmware operation occurred.',
                        'API slot order does not establish physical jack order or an actual current Serato session.']}
    (ROOT / 'docs/evidence/serato255-sl3-initial-remap.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Verified SL3 initial inverse map [0,1,2], absent/default-false channel setup and guarded alternate builder')


if __name__ == '__main__':
    main()
