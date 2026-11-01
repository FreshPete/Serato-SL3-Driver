"""Export bounded, execution-free evidence for the current supported-device contract.

Requires retained focused-analysis reports and analysis dependencies. Verifies the
exact PE hash, decodes instruction excerpts from unwind boundaries, and keeps
static predictions distinct from observed application/hardware behaviour.
"""
import hashlib
import json
import re
import struct
from pathlib import Path

import capstone
import pefile

ROOT = Path(__file__).resolve().parents[1]
SHA = '66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265'
BINARY = ROOT / 'artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe'


def focused(file, start):
    report = json.loads((ROOT / 'analysis' / file).read_text())
    assert report['binary_sha256'].lower() == SHA
    function = next(f for f in report['functions'] if f['start'] == start)
    assert function['complete']
    return function['pseudocode'].replace('\r', '')


def main():
    raw = BINARY.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SHA
    pe = pefile.PE(data=raw, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    base = pe.OPTIONAL_HEADER.ImageBase
    spans = sorted((base + e.struct.BeginAddress, base + e.struct.EndAddress)
                   for e in pe.DIRECTORY_ENTRY_EXCEPTION)
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    cache = {}

    def instructions(start, end, leaf=False):
        span = (start, end) if leaf else next((lo, hi) for lo, hi in spans if lo <= start < hi)
        assert end <= span[1]
        if span not in cache:
            cache[span] = list(decoder.disasm(pe.get_data(span[0] - base, span[1] - span[0]), span[0]))
        return [i for i in cache[span] if start <= i.address < end]

    def window(rows, purpose):
        assert rows
        return {'purpose': purpose, 'start': hex(rows[0].address),
                'end_exclusive': hex(rows[-1].address + rows[-1].size),
                'instructions': [f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in rows]}

    factory = focused('serato500-supported-contract.json', '140bfa030')
    pairs = re.findall(r'sVar4 == 0x1cc5\) &&\s*\(sVar4 = .*?sVar4 == (0x[0-9a-f]+|\d+)\)', factory)
    pids = sorted({int(value, 0) for value in pairs})
    assert pids == [0x18, 0x1b, 0x20, 0x21, 0x22, 0x25, 0x26]
    body = instructions(0x140bfa030, 0x140bfe1a8)
    # The compiler hoists this manufacturer constant into R12D and reuses it.
    manufacturer_tests = []
    constant = None
    for n, instruction in enumerate(body):
        if instruction.mnemonic == 'mov' and instruction.op_str.startswith('r12d, 0x'):
            constant = int(instruction.op_str.split(', ')[1], 0)
        if instruction.mnemonic == 'cmp' and instruction.op_str == 'ax, r12w' and constant == 0x1cc5:
            manufacturer_tests.append(n)
    assert len(manufacturer_tests) == len(pids)
    excerpts = [window(body[max(0, n - 3):n + 10], 'Rane-specific DriverAPI selection') for n in manufacturer_tests]
    constant_index = next(n for n, i in enumerate(body) if i.op_str == 'r12d, 0x1cc5')
    excerpts.insert(0, window(body[constant_index:constant_index + 2], 'Hoisted Rane vendor constant'))
    generic_calls = [n for n, i in enumerate(body) if i.mnemonic == 'call' and i.op_str == '0x140bff9d0']
    n = generic_calls[-1]
    excerpts.append(window(body[n - 10:n + 5], 'Final generic DriverAPI fallback'))

    excerpts += [window(instructions(lo, hi, leaf), purpose) for lo, hi, leaf, purpose in [
        (0x1405ce77c, 0x1405ce79b, False, 'Zero 0x740-byte descriptor object before its constructor'),
        (0x1405cd180, 0x1405cd188, True, 'Legacy audio flag getter: interface +0x34C / complete +0x35C'),
        (0x1405c7da0, 0x1405c7da8, True, 'HID getter: interface +0xC4 / complete +0xD4'),
        (0x1405c7e30, 0x1405c7e38, True, 'Raw USB getter: interface +0x10C / complete +0x11C'),
        (0x1405c8f80, 0x1405c9140, False, 'Audio API/name and MIDI-direction parser references; WDMKS literal comparison'),
        (0x1405c9f20, 0x1405ca040, False, 'has_hid and requires_usb parser field writes'),
        (0x140c00000, 0x140c00011, False, 'Empty driver-detection key returns AL=1, not failure'),
        (0x140c00152, 0x140c00187, False, 'Nonempty key uses HKLM RegOpenKeyExW KEY_READ and tests success'),
        (0x140c001ef, 0x140c00208, False, 'Preserve nonempty-key Boolean return after cleanup'),
        (0x140c00230, 0x140c00237, True, 'DriverAPI slots +0x48/+0x58 delegate to slot +0x50'),
        (0x140c00240, 0x140c0025f, False, 'DriverAPI slot +0x50 copies registry-key string at +0x60 then checks it'),
        (0x1404a4550, 0x1404a4553, True, 'Generic DriverAPI slot +0x90 returns false'),
        (0x14220d817, 0x14220d832, False, 'Initial buffer helper invokes IASIO slot +0x98 (createBuffers)'),
    ]]
    enclosing = next((lo, hi) for lo, hi in spans if lo == 0x1405bead0)
    ctor = list(decoder.disasm(pe.get_data(enclosing[0] - base, enclosing[1] - enclosing[0]), enclosing[0]))
    default_legacy = next(n for n, i in enumerate(ctor) if '0x35c]' in i.op_str and i.mnemonic == 'mov')
    assert ctor[default_legacy].op_str.endswith(', 1')
    excerpts.append(window(ctor[max(0, default_legacy - 2):default_legacy + 2], 'Constructor defaults use_legacy_portaudio to true'))

    def rtti(vtable):
        locator = struct.unpack('<Q', pe.get_data(vtable - base - 8, 8))[0]
        signature, offset, displacement, type_rva, hierarchy, self_rva = struct.unpack('<6I', pe.get_data(locator - base, 24))
        assert signature == 1 and base + self_rva == locator
        return {'vtable': hex(vtable), 'locator': hex(locator), 'object_offset': offset,
                'decorated_type': pe.get_string_at_rva(type_rva + 16).decode(),
                'slots': [{'offset': hex(n * 8), 'target': hex(struct.unpack('<Q', pe.get_data(vtable - base + n * 8, 8))[0])}
                          for n in range(24)]}

    midi = focused('serato500-supported-initialization.json', '1405c6ef0')
    assert 'uVar5 = 3' in midi and 'uVar5 = 0' in midi
    for literal in [0x14281d358, 0x14281d35c]:
        assert pe.get_string_at_rva(literal - base) in [b'in', b'out']
    readiness = focused('serato500-supported-initialization.json', '1421dad00')
    begin = readiness.index('  cVar3 = (**(code **)(*plStack_a8 + 0x50))();')
    end = readiness.index('  uStackX_10 = uStackX_8;', begin)
    registry = pe.get_data(0x1431dd908 - base, 64).decode('utf-16-le').split('\0', 1)[0]
    assert registry.lower() == 'software\\asio'
    registry_fields = {}
    for address, expected in [(0x1431dd938, 'clsid'), (0x1431dd948, 'InprocServer32'), (0x1431dd9a0, 'description')]:
        actual = pe.get_data(address - base, 128).decode('utf-16-le').split('\0', 1)[0]
        assert actual == expected
        registry_fields[hex(address)] = actual
    warmup = focused('serato500-asio-registry.json', '142210950')
    warmup_begin = warmup.index('          FUN_142213180(param_1);')
    warmup_end = warmup.index('          goto code_r0x000142210c42;', warmup_begin)
    result = {
        'binary_sha256': SHA,
        'coverage': 'Static focused decompilation and boundary-checked PE excerpts. No modified application or debugger/runtime call trace.',
        'driverApiFactory': {'function': '0x140bfa030', 'raneVendor': '0x1cc5', 'explicitRaneProducts': [hex(p) for p in pids],
                             'sl3Product': '0x1', 'sl3SpecificMatchInThisFactory': False,
                             'fallbackConstructor': '0x140bff9d0', 'rtti': rtti(0x142e86360)},
        'readinessProjection': {'source': '0x1421dad00', 'pseudocode': readiness[begin:end],
                                'limit': 'These virtual calls target DriverAPI, not ControllerDescriptor; action names are not inferred.'},
        'stubStaticPrediction': {'descriptorInterfaceOffset': '0x10', 'hasHid': False, 'requiresUsb': False,
                                 'midiDirectionString': '', 'midiDirectionGetterReturn': 3,
                                 'expectedMidiComponentCount': 1, 'useLegacyPortaudio': True,
                                 'windowsAudioApiString': '', 'windowsAudioDeviceName': '',
                                 'limit': 'Derived from zeroing, constructor, identity-only helper and getters; not a runtime patch experiment.'},
        'asioBackend': {'rttiVtable': '0x1431dd8d0', 'scanFunction': '0x142212470',
                        'registryRoot': 'HKEY_LOCAL_MACHINE', 'registrySubkey': registry,
                        'createFunction': '0x14220d200', 'deviceConstructor': '0x142208150',
                        'registryInfoFunction': '0x142209dd0', 'registryFieldLiterals': registry_fields,
                        'warmupFunction': '0x142210950', 'warmupProjection': warmup[warmup_begin:warmup_end],
                        'limit': 'Backend exists; no proof of routing the SL3 descriptor into it or opening rebuilt audio.'},
        'excerpts': excerpts,
        'decompilerCautions': ['140bfffd0/140c00240 are inferred void by Ghidra; AL return is visible in machine code.',
                              'DriverAPI factory is not an audio stream initializer or a licensing check.']
    }
    destination = ROOT / 'docs/evidence/serato500-supported-contract.json'
    destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'Exported {len(excerpts)} instruction excerpts and the supported-device contract')


if __name__ == '__main__':
    main()
