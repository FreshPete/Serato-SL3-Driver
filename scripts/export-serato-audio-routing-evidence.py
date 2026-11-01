"""Export execution-free evidence for Serato 5.0.0's audio backend selector.

Reads the exact original PE and retained focused reports. Does not patch, load,
register or execute application/driver code. Decompiler omissions of forwarded
Windows ABI arguments are resolved using the exported instruction windows.
"""
import hashlib
import json
from pathlib import Path
import struct

import capstone
import pefile

ROOT = Path(__file__).resolve().parents[1]
SHA = '66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265'
BINARY = ROOT / 'artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe'


def main():
    raw = BINARY.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SHA, 'Original PE identity changed'
    pe = pefile.PE(data=raw, fast_load=True)
    pe.parse_data_directories(directories=[1, 3])
    base = pe.OPTIONAL_HEADER.ImageBase
    spans = {(base + entry.struct.BeginAddress, base + entry.struct.EndAddress)
             for entry in pe.DIRECTORY_ENTRY_EXCEPTION}
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def dis(start, end, leaf=False):
        assert leaf or any(lo <= start < end <= hi for lo, hi in spans), 'Not inside an unwind range'
        rows = list(decoder.disasm(pe.get_data(start - base, end - start), start))
        assert rows and rows[-1].address + rows[-1].size == end, 'Incomplete instruction window'
        return rows

    def at(address, mnemonic, operands, leaf=False):
        row = next(decoder.disasm(pe.get_data(address - base, 15), address))
        assert row.mnemonic == mnemonic and row.op_str == operands, hex(address)
        if not leaf:
            assert any(lo <= address < hi for lo, hi in spans)
        return row

    def rtti(vtable):
        locator = struct.unpack('<Q', pe.get_data(vtable - base - 8, 8))[0]
        signature, offset, _, td, _, self_rva = struct.unpack('<6I', pe.get_data(locator - base, 24))
        assert signature == 1 and base + self_rva == locator
        return {'vtable': hex(vtable), 'objectOffset': hex(offset),
                'type': pe.get_data(td + 16, 256).split(b'\0', 1)[0].decode('ascii')}

    reports = {}
    def focused(file, start):
        path = ROOT / 'analysis' / file
        report = json.loads(path.read_text(encoding='utf-8-sig'))
        assert report['binary_sha256'].lower() == SHA
        row = next(f for f in report['functions'] if f['start'] == start)
        assert row['complete']
        reports[file] = hashlib.sha256(path.read_bytes()).hexdigest()
        return row['pseudocode'].replace('\r', '')

    choice = focused('serato500-audio-backend-choice.json', '1421b8b80')
    named = focused('serato500-audio-backend-factories.json', '1421b8580')
    ids = focused('serato500-audio-backend-factories.json', '1421b80c0')
    legacy = focused('serato500-audio-legacy-factories.json', '1421c2f80')
    legacy_ids = focused('serato500-audio-legacy-id-factory.json', '1421c2df0')
    enumeration = focused('serato500-portaudio-enumerator.json', '1421c2840')
    for target in ['FUN_1421b8030', 'FUN_1421b80c0', 'FUN_1421b8580']:
        assert target in choice
    assert "if (param_3 != '\\0')" in named and 'FUN_1421c2f80' in named
    assert 'FUN_1421c2df0' in ids and 'FUN_1421eb160' in ids
    assert 'FUN_1421202b0' in legacy and 'puVar5 = puVar4;' in legacy
    assert '+ 0x68' in legacy_ids and '+ 0x70' in legacy_ids
    assert 'iStack_e0 == iVar1' in enumeration and 'FUN_1421e5dd0' in enumeration

    fields = []
    for name, offset, literal, destination in [
        ('win_audio_api', 0x360, 0x1405c8fbe, 0x1405c8fe7),
        ('mac_audio_api', 0x380, 0x1405c8fff, 0x1405c9028),
        ('win_audio_device_name', 0x3a0, 0x1405c9040, 0x1405c9069),
        ('mac_audio_device_name', 0x3c0, 0x1405c90ae, 0x1405c90d7),
    ]:
        row = next(decoder.disasm(pe.get_data(literal - base, 15), literal))
        assert row.mnemonic == 'lea' and row.op_str.startswith('rdx, [rip + ')
        target = row.address + row.size + struct.unpack('<i', row.bytes[-4:])[0]
        assert pe.get_data(target - base, 64).split(b'\0', 1)[0].decode() == name
        at(destination, 'lea', f'rcx, [rsi + 0x{offset:x}]')
        fields.append({'name': name, 'completeObjectOffset': hex(offset),
                       'parserKeyReference': hex(literal), 'parserDestination': hex(destination)})

    gate = dis(0x1405c7e00, 0x1405c7e2e, True)
    assert [i.op_str for i in gate if i.mnemonic == 'cmp'] == [
        f'qword ptr [rcx + 0x{offset:x}], 0' for offset in [0x360, 0x380, 0x3a0, 0x3c0]]
    assert all(i.op_str == '0x1405c7e2b' for i in gate if i.mnemonic == 'jne')
    at(0x1405cd180, 'movzx', 'eax, byte ptr [rcx + 0x34c]', True)
    at(0x1405c6509, 'lea', 'rdx, [rcx - 0x398]')
    assert 0x738 - 0x398 == 0x3a0
    at(0x1421b8cce, 'call', 'qword ptr [rax + 0xc0]')
    at(0x1421b8cd6, 'jne', '0x1421b8e7f')
    at(0x1421b8da1, 'call', '0x1421b8030')
    at(0x1421b8e95, 'call', 'qword ptr [rax + 0x38]')
    at(0x1421b901e, 'call', '0x1421b80c0')
    at(0x1421b91bf, 'call', '0x1421b8580')
    at(0x1421b8133, 'call', '0x1421c2df0')
    at(0x1421b85df, 'call', '0x1421c2f80')
    at(0x1421b7e6f, 'add', 'rcx, 8')
    at(0x1421b7e73, 'call', '0x1421c27a0')
    factory_lea = at(0x1421c27a0, 'lea', 'rax, [rip + 0x1012151]', True)
    assert factory_lea.address + factory_lea.size + 0x1012151 == 0x1431d48f8
    factory = rtti(0x1431d48f8)
    assert factory['type'] == '.?AVPortAudioConnectionFactory@audio@device@serato@@'
    assert struct.unpack('<Q', pe.get_data(0x1431d48f8 - base, 8))[0] == 0x1421c2840
    audio_descriptor, identity_descriptor = rtti(0x14281caf0), rtti(0x14281cbe8)
    assert audio_descriptor['type'] == identity_descriptor['type'] == '.?AVControllerDescriptor@dj@serato@@'
    assert audio_descriptor['objectOffset'] == '0x10' and identity_descriptor['objectOffset'] == '0x738'
    assert struct.unpack('<Q', pe.get_data(0x14281caf0 + 0xc0 - base, 8))[0] == 0x1405c7e00
    assert struct.unpack('<Q', pe.get_data(0x14281caf0 + 8 - base, 8))[0] == 0x1405cd180
    assert struct.unpack('<Q', pe.get_data(0x14281cbe8 + 0x38 - base, 8))[0] == 0x1405c6500
    at(0x141379ce6, 'call', '0x1421b8b80')
    # The named selector forwards API in R9 and name as fifth stack argument;
    # Ghidra's three-parameter declaration drops both at the indirect call.
    forwarded = dis(0x1421c2f80, 0x1421c2fd5)
    assert not any(i.op_str.startswith(('r9,', 'r9d,', 'r9b,')) for i in forwarded)
    at(0x1421c2fc6, 'mov', 'qword ptr [rsp + 0x20], rsi')
    at(0x1421c303d, 'call', '0x1421202b0')
    thunk = at(0x1421202b0, 'jmp', 'qword ptr [rip + 0x615c3a]', True)
    iat = thunk.address + thunk.size + 0x615c3a
    imp = next((dll.dll.decode(), item.name.decode()) for dll in pe.DIRECTORY_ENTRY_IMPORT
               for item in dll.imports if item.address == iat)
    assert imp == ('VCRUNTIME140.dll', 'strstr')
    ctor = dis(0x1405bead0, 0x1405bf1d3)
    rsi_definitions = [i for i in ctor if i.address <= 0x1405bed7f and i.op_str.startswith(('rsi,', 'esi,'))]
    assert len(rsi_definitions) == 1 and rsi_definitions[0].mnemonic == 'xor' and rsi_definitions[0].op_str == 'esi, esi'
    for offset in [0x370, 0x390, 0x3b0, 0x3d0]:
        assert any(i.mnemonic == 'mov' and i.op_str == f'qword ptr [rdi + 0x{offset:x}], rsi' for i in ctor)
    at(0x1421e5891, 'mov', 'dword ptr [rbp - 0x39], 0x4f495341')
    at(0x1421e59ce, 'mov', 'dword ptr [rsi + 0x40], 3')

    windows = [
        ('Four audio-string length gate', 0x1405c7e00, 0x1405c7e2e, True),
        ('Four strings initialized empty', 0x1405bed15, 0x1405bed98, False),
        ('Windows device-name getter through shared virtual base', 0x1405c6500, 0x1405c6521, False),
        ('Empty audio fields select default path', 0x1421b8cbe, 0x1421b8ce4, False),
        ('Explicit name-length query', 0x1421b8e7f, 0x1421b8e9c, False),
        ('Legacy flag forwarded to VID/PID selector', 0x1421b8ff7, 0x1421b9023, False),
        ('Legacy flag forwarded to named selector', 0x1421b9195, 0x1421b91c4, False),
        ('Named selector switches to legacy factory', 0x1421b85c2, 0x1421b85f2, False),
        ('VID/PID selector switches to legacy factory', 0x1421b810b, 0x1421b813d, False),
        ('Embedded factory construction', 0x1421b7e65, 0x1421b7e7d, False),
        ('Concrete PortAudio factory constructor', 0x1421c27a0, 0x1421c27b6, True),
        ('ABI forwarding omitted by decompiler', 0x1421c2fbb, 0x1421c2fd5, False),
        ('Actual imported substring matcher', 0x1421c301f, 0x1421c3047, False),
    ]
    result = {'binarySha256': SHA, 'scope': 'Static backend-selection evidence; no application/driver execution',
        'explicitAudioPredicate': {'function': '0x1405c7e00', 'interfaceSlot': '0xc0',
            'completeObjectStringOffsets': {'win_audio_api': '0x360', 'mac_audio_api': '0x380',
                'win_audio_device_name': '0x3a0', 'mac_audio_device_name': '0x3c0'},
            'result': 'True if any of four string lengths is nonzero; all start empty'},
        'parserFieldVerification': fields,
        'legacyApiMap': {'initializer': '0x1421e5810', 'ASIO': 3,
            'upstreamEnumReference': 'https://github.com/PortAudio/portaudio/blob/master/include/portaudio.h',
            'limit': 'Enum correspondence does not establish the exact bundled PortAudio fork/version'},
        'selector': {'function': '0x1421b8b80', 'caller': '0x141379a70',
            'emptyAudioFields': 'Default OS connection via 0x1421b8030; legacy flag not queried in that branch',
            'explicitFieldsEmptyWindowsName': 'VID/PID route 0x1421b80c0',
            'explicitFieldsNonemptyWindowsName': 'Name route 0x1421b8580',
            'legacyTrue': 'Embedded PortAudioConnectionFactory, matched by IDs or case-sensitive name substring',
            'legacyFalse': 'AudioDeviceManager refresh and generic AudioConnection wrapper',
            'duplicateMatches': 'Legacy selectors retain the last matching entry; enumeration order is unverified'},
        'factory': factory, 'descriptorInterfaces': [audio_descriptor, identity_descriptor],
        'substringMatcherImport': {'dll': imp[0], 'name': imp[1], 'iat': hex(iat)},
        'abiWarning': 'The three-parameter decompilation of 0x1421c2f80 omits forwarded API R9 and name stack argument; do not infer API is ignored',
        'retainedFocusedReportSha256': reports,
        'assembly': [{'purpose': purpose, 'start': hex(start), 'endExclusive': hex(end),
                      'instructions': [f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in dis(start, end, leaf)]}
                     for purpose, start, end, leaf in windows],
        'limits': ['SL3 support-2 branch still selects discontinued handling',
                   'Default-path prediction assumes the stub reaches this selector; aggregation prerequisites remain',
                   'No external descriptor override, patch, driver registration or runtime route test',
                   'Matching a device is not proof of successful init, streaming, licensing or DVS mapping']}
    out = ROOT / 'docs/evidence/serato500-audio-routing.json'
    out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Validated original PE, four-string gate, backend branches, concrete legacy factory, Windows ABI forwarding and strstr import')


if __name__ == '__main__':
    main()
