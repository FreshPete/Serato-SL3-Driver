"""Verify current Serato stereo-input map consumers without executing vendor code."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
image = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image)
require = image.require


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    app = image.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', image.CURRENT_SHA)
    reports = {}
    code = {}
    for name in ('serato500-endpoint-consumers-01.json', 'serato500-endpoint-enum-02.json', 'serato500-endpoint-mixer-03.json'):
        path = ROOT/'analysis'/name
        report = json.loads(path.read_text(encoding='utf-8-sig'))
        require(report['binary_sha256'] == app.sha, 'Wrong focused image')
        for row in report['functions']:
            require(row['complete'] and (int(row['start'], 16), int(row['end_exclusive'], 16)) in app.spans,
                    'Incomplete or mismatched focused range')
            code[row['start']] = row['pseudocode'].replace('\r', '')
        reports[name] = digest(path)
    require('FUN_1405c6d50' in code['1421744a0'] and '0x46c' in code['1421744a0'], 'Deck input selection changed')
    require('FUN_1405c6d50' in code['142148010'] and 'FUN_1405c6d80' in code['142148010'], 'Mixer map setup changed')
    require('FUN_1421b9d30' in code['14214e370'] and 'FUN_142185b10' in code['14214e370'], 'Input attachment path changed')
    # Inline strings and stores in the actual enum-map initializer.
    enums = []
    for name, address, reference, store, value in (
        ('Deck1In', 0x14281d180, 0x1405c35e4, 0x1405c3607, 2),
        ('Deck2In', 0x14281d188, 0x1405c3709, 0x1405c372c, 3),
        ('Deck3In', 0x14281d190, 0x1405c37f8, 0x1405c381b, 4),
    ):
        require(app.text(address) == name and app.rip(app.at(reference)) == address, 'Endpoint enum string changed')
        app.at(store, 'mov', f'dword ptr [rbp + 0xf], {value}')
        enums.append({'name': name, 'value': value, 'assembly': app.window(reference, 0, 10)})
    checks = (
        (0x1405c6d59, 'lea', 'rdx, [rcx + 0x6b8]'),
        (0x1405c6d89, 'lea', 'rdx, [rcx + 0x6c8]'),
        (0x14214855b, 'call', '0x1405c6d50'),
        (0x142148563, 'lea', 'rsi, [rdi + 0xf0]'),
        (0x14214867f, 'call', '0x1405c6d80'),
        (0x142148687, 'lea', 'rsi, [rdi + 0x100]'),
        (0x1405cb034, 'mov', 'dword ptr [rsp + 0x38], r14d'),
        (0x1405cb055, 'call', '0x141b19d10'),
        (0x1405cb384, 'mov', 'dword ptr [rcx + 0x20], r14d'),
        (0x1405cb38d, 'inc', 'r14d'),
        (0x1421744f9, 'call', '0x1405c6d50'),
        (0x1421744ff, 'mov', 'esi, 2'),
        (0x142174504, 'mov', 'eax, dword ptr [r15 + 0x46c]'),
        (0x14214e4ba, 'mov', 'eax, dword ptr [rcx + 0x20]'),
        (0x14214e4bd, 'lea', 'ebx, [rax + rax]'),
        (0x14214e4c6, 'call', '0x1421b9d30'),
        (0x14214e4ce, 'lea', 'ecx, [rbx + 1]'),
        (0x14214e4d7, 'call', '0x1421b9d30'),
        (0x1421b9d57, 'imul', 'rbx, qword ptr [rdi]'),
        (0x1421b9d5f, 'lea', 'rax, [rax + rbx*4]'),
    )
    for address, mnemonic, operands in checks:
        app.at(address, mnemonic, operands)
    require(app.text(app.rip(app.at(0x1405cb039))) == 'hw_src', 'Wrong hardware source attribute')
    table = 0x1431c4aa8
    locator = struct.unpack('<Q', app.data(table-8, 8))[0]
    signature, offset, _, td, _, own = struct.unpack('<6I', app.data(locator, 24))
    require(signature == 1 and app.base+own == locator and offset == 0x88
            and app.text(app.base+td+16) == '.?AVCNativeMixer@@', 'Mixer interface RTTI changed')
    require(struct.unpack('<Q', app.data(table+0x80, 8))[0] == 0x142148010
            and struct.unpack('<Q', app.data(table+0x10, 8))[0] == 0x14214e370, 'Mixer interface slots changed')
    legacy_path = ROOT/'docs/evidence/serato-legacy-sl3-descriptors.json'
    legacy = json.loads(legacy_path.read_text(encoding='utf-8-sig'))
    # This is a declared-order inference from the separately verified historical
    # resource, not an injected current descriptor or a physical channel map.
    versions = legacy['targets']
    require(len(versions) == 2, 'Missing historical descriptor evidence')
    for version in versions:
        require(version['inputsInDeclaredOrder'] == ['Deck3In', 'Deck1In', 'Deck2In'], 'Historical input order differs')
    result = {
        'scope': 'Static current Serato input-map units and mixer consumers; no runtime integration or physical mapping',
        'binarySha256': app.sha, 'focusedReportSha256': reports,
        'inputEnum': enums,
        'mixerInterface': {'vtable': hex(table), 'completeObjectOffset': '0x88',
                           'setupSlot': '0x80', 'inputConsumerSlot': '0x10',
                           'inputMapInterfaceOffset': '0xF0', 'outputMapInterfaceOffset': '0x100'},
        'hardwareInputIndexUnits': 'stereo pairs: mono channels 2*hw_src and 2*hw_src+1',
        'inputAttachAssembly': app.window(0x14214e4ba, 0, 28),
        'planarAddressAssembly': app.window(0x1421b9d30, 0, 22),
        'parserIndexAssembly': app.window(0x1405cb384, 0, 6),
        'legacyEvidenceSha256': digest(legacy_path),
        'historicalOrderInference': [{'endpoint': name, 'pairIndex': index, 'zeroBasedMonoChannels': [2*index, 2*index+1]}
                                    for index, name in enumerate(['Deck3In', 'Deck1In', 'Deck2In'])],
        'limits': ['Original XML order is a conditional mapping when parsed, not current SL3 stub configuration',
                   'Physical sockets, through/routing state, channel polarity and DVS deck attachment are unverified',
                   'Output indices need their own final sample consumer verification',
                   'No executable, resource, account state, authentication predicate or registration is changed'],
    }
    output = ROOT/'docs/evidence/serato500-endpoint-consumers.json'
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified current stereo input-map consumers; exported bounded static evidence')


if __name__ == '__main__':
    main()
