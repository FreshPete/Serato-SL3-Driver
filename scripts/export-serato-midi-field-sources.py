"""Verify descriptor field names/byte-vector provenance; export no secret values."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import capstone

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def main():
    spec = importlib.util.spec_from_file_location('sl3_midi_fields_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    app = h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', h.CURRENT_SHA)
    require = h.require
    require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe')) == app.sha, 'Installed image differs')
    facts = []
    def fact(va, expected):
        row = app.at(va); require(row.mnemonic+' '+row.op_str == expected, 'Instruction differs at '+hex(va))
        facts.append({'va': hex(va), 'assembly': expected, 'bytes': bytes(row.bytes).hex()})
        return row
    checks = [
        (0x1405beadc, 'mov rdi, rcx'), (0x1405beadf, 'xor esi, esi'),
        (0x1405beb52, 'lea rax, [rip + 0x225df4f]'), (0x1405beb59, 'mov qword ptr [rdi], rax'),
        (0x1405bec59, 'mov qword ptr [rdi + 0x160], rsi'), (0x1405bec60, 'mov qword ptr [rdi + 0x168], rsi'),
        (0x1405bec67, 'mov qword ptr [rdi + 0x170], rsi'), (0x1405bec6e, 'mov qword ptr [rdi + 0x178], rsi'),
        (0x1405bec75, 'mov qword ptr [rdi + 0x180], rsi'), (0x1405bec7c, 'mov qword ptr [rdi + 0x188], rsi'),
        (0x1405c7fe0, 'mov rsi, rcx'),
        (0x1405c8002, 'lea rdx, [rbp + 0x2d0]'), (0x1405c800e, 'call 0x1405c01c0'),
        (0x1405c8013, 'lea rdx, [rbp + 0x400]'), (0x1405c801a, 'mov rcx, rax'), (0x1405c801d, 'call 0x1405c71f0'),
        (0x1405c8023, 'lea rdx, [rbp + 0x388]'), (0x1405c802f, 'call 0x1405c0210'),
        (0x1405c8034, 'lea rdx, [rbp + 0x3e0]'), (0x1405c803b, 'mov rcx, rax'), (0x1405c803e, 'call 0x1405c7280'),
        (0x1405c84a1, 'movzx eax, word ptr [rsi + 0xaa]'), (0x1405c84a8, 'mov dword ptr [rsi + 0xd0], eax'),
        (0x1405c84ae, 'lea rdx, [rip + 0x2254fd3]'), (0x1405c84b5, 'mov rcx, r12'), (0x1405c84b8, 'call 0x141b17da0'),
        (0x1405c84bd, 'test rax, rax'), (0x1405c84c0, 'je 0x1405c84e8'),
        (0x1405c84c2, 'xor r8d, r8d'), (0x1405c84c5, 'lea rdx, [rip + 0x2254f34]'),
        (0x1405c84cc, 'mov rcx, rax'), (0x1405c84cf, 'call 0x141b17620'),
        (0x1405c84d4, 'xor r8d, r8d'), (0x1405c84d7, 'xor edx, edx'),
        (0x1405c84d9, 'mov rcx, rax'),
        (0x1405c84dc, 'call qword ptr [rip + 0x216e50e]'), (0x1405c84e2, 'mov dword ptr [rsi + 0xd0], eax'),
        (0x1405c8562, 'lea rcx, [rsi + 0x160]'), (0x1405c8569, 'call 0x1405cd970'),
        (0x1405c856e, 'lea rcx, [rbp + 0x400]'), (0x1405c8575, 'call 0x1404a67b0'),
        (0x1405c857a, 'mov rdx, rax'), (0x1405c857d, 'mov rcx, r12'), (0x1405c8580, 'call 0x141b17da0'),
        (0x1405c85eb, 'mov byte ptr [rsp + 0x30], al'), (0x1405c85ef, 'lea rdx, [rsp + 0x30]'),
        (0x1405c85f4, 'lea rcx, [rsi + 0x160]'), (0x1405c85fb, 'call 0x1405cde40'),
        (0x1405c8617, 'lea rcx, [rsi + 0x178]'), (0x1405c861e, 'call 0x1405cd970'),
        (0x1405c8623, 'lea rcx, [rbp + 0x3e0]'), (0x1405c862a, 'call 0x1404a67b0'),
        (0x1405c862f, 'mov rdx, rax'), (0x1405c8632, 'mov rcx, r12'), (0x1405c8635, 'call 0x141b17da0'),
        (0x1405c863a, 'test rax, rax'), (0x1405c863d, 'je 0x1405c86c7'),
        (0x1405c8643, 'xor r8d, r8d'), (0x1405c8646, 'lea rdx, [rip + 0x2254db3]'),
        (0x1405c864d, 'mov rcx, rax'), (0x1405c8650, 'call 0x141b17620'),
        (0x1405c8655, 'lea rdx, [rip + 0x223c074]'), (0x1405c865c, 'mov rcx, rax'),
        (0x1405c865f, 'call qword ptr [rip + 0x216ea03]'),
        (0x1405c8670, 'mov r8d, 2'), (0x1405c8676, 'lea rdx, [rip + 0x2255bcb]'),
        (0x1405c867d, 'mov rcx, rbx'),
        (0x1405c8680, 'call qword ptr [rip + 0x216e99a]'), (0x1405c8686, 'test eax, eax'),
        (0x1405c8688, 'jne 0x1405c86c7'), (0x1405c868a, 'xor edx, edx'), (0x1405c868c, 'mov r8d, 0x10'),
        (0x1405c8692, 'mov rcx, rbx'),
        (0x1405c8695, 'call qword ptr [rip + 0x216e345]'), (0x1405c869b, 'mov byte ptr [rsp + 0x30], al'),
        (0x1405c869f, 'lea rdx, [rsp + 0x30]'), (0x1405c86a4, 'lea rcx, [rsi + 0x178]'),
        (0x1405c86ab, 'call 0x1405cde40'), (0x1405c86b0, 'lea rdx, [rip + 0x223c019]'),
        (0x1405c86b7, 'xor ecx, ecx'), (0x1405c86b9, 'call qword ptr [rip + 0x216e9a9]'),
        (0x1405c86bf, 'mov rbx, rax'), (0x1405c86c2, 'test rax, rax'), (0x1405c86c5, 'jne 0x1405c8670'),
        (0x140603eed, 'mov edx, dword ptr [rcx + 0xd0]'),
    ]
    for va, assembly in checks:
        fact(va, assembly)
    aliases = {capstone.x86.X86_REG_RSI, capstone.x86.X86_REG_ESI, capstone.x86.X86_REG_SI, capstone.x86.X86_REG_SIL}
    require(not any(set(r.regs_access()[1]) & aliases for r in app.function(0x1405bead0)
                    if 0x1405beadf < r.address < 0x1405bec7c), 'Constructor zero register overwritten')
    table = app.rip(app.at(0x1405beb52)); locator = struct.unpack('<Q', app.data(table-8, 8))[0]
    col = struct.unpack('<6I', app.data(locator, 24))
    require(table == 0x14281caa8 and col[0] == 1 and col[1] == 0 and app.base+col[5] == locator and
            app.text(app.base+col[3]+16) == '.?AVControllerDescriptor@dj@serato@@' and
            struct.unpack('<Q', app.data(table+8, 8))[0] == 0x1405c7f90, 'Constructor/parser RTTI differs')
    functions = []
    for start, end, digest in [
        (0x1405c01c0, 0x1405c020e, 'b2bd0e24487ed48e663c1e1e5c4baa147dcc4a8556839cceb72689818a0ba319'),
        (0x1405c0210, 0x1405c025b, 'a9ade8cf74dc4261d306d434116ab761f60373b63ff3fc4e7f46c3073e0a18e4'),
        (0x1405c71f0, 0x1405c7279, '4d53191a37f672761e297bc68c61e3cf69961de00c3e1146a1ca820dfd170f6c'),
        (0x1405c7280, 0x1405c732e, '6a2241c3dcdbd14484320a1087f3cd63b6e1e09ede78e1810091f332b225f0db'),
        (0x1405bead0, 0x1405bf1d3, '6062c32e5b0234e897008bf75b4a63bfe9a18da98ef31441404e92c7ae8db045')]:
        require((start, end) in app.spans and hashlib.sha256(app.data(start, end-start)).hexdigest() == digest,
                'Inspected field-name/constructor function bytes differ')
        functions.append({'start': hex(start), 'endExclusive': hex(end), 'sha256': digest})
    # This decodes only the two XML property NAMES, not their values. No
    # userio archive, key-bearing XML or protocol packet is opened here.
    field_names = []
    for ref, length, name, vector in [(0x1405c01c4, 10, 'secret_key', '0x160'),
                                      (0x1405c0214, 17, 'secret_serato_key', '0x178')]:
        data = app.data(app.rip(app.at(ref)), length)
        decoded = bytes((((byte ^ 0xfa) >> (n & 7)) | ((byte ^ 0xfa) << (8-(n & 7)))) & 255 for n, byte in enumerate(data))
        require(decoded.decode('ascii') == name, 'Decoded XML property name differs')
        field_names.append({'fieldName': name, 'nameLength': length, 'copySourceReference': hex(ref), 'vectorBeginOffset': vector})
    for va, literal in [(0x1405c84ae, 'midi_id'), (0x1405c84c5, 'value'), (0x1405c8646, 'value'), (0x1405c8655, ', '),
                        (0x1405c8676, '0xxx'), (0x1405c86b0, ', ')]:
        require(app.text(app.rip(app.at(va))) == literal, 'XML/token field literal differs')
    leaves = []
    for start, end, expected in [
        (0x1404a67b0, 0x1404a67bf, [('cmp', 'qword ptr [rcx + 0x18], 0xf'), ('jbe', '0x1404a67bb'),
            ('mov', 'rax, qword ptr [rcx]'), ('ret', ''), ('mov', 'rax, rcx'), ('ret', '')]),
        (0x1405cd970, 0x1405cd97e, [('mov', 'rax, qword ptr [rcx]'), ('cmp', 'rax, qword ptr [rcx + 8]'),
            ('je', '0x1405cd97d'), ('mov', 'qword ptr [rcx + 8], rax'), ('ret', '')]),
        (0x1405cde40, 0x1405cde5d, [('mov', 'r8, rdx'), ('mov', 'rdx, qword ptr [rcx + 8]'),
            ('cmp', 'rdx, qword ptr [rcx + 0x10]'), ('je', '0x1405cde58'), ('movzx', 'eax, byte ptr [r8]'),
            ('mov', 'byte ptr [rdx], al'), ('inc', 'qword ptr [rcx + 8]'), ('ret', ''), ('jmp', '0x1405bc380')])]:
        rows = list(app.dis.disasm(app.data(start, end-start), start))
        require([(r.mnemonic, r.op_str) for r in rows] == expected and rows[-1].address+rows[-1].size == end, 'Leaf extent/body differs')
        leaves.append({'start': hex(start), 'endExclusive': hex(end), 'instructionCount': len(rows),
                       'sha256': hashlib.sha256(app.data(start, end-start)).hexdigest()})
    app.pe.parse_data_directories(directories=[1])
    imports = {e.address: (d.dll.decode(), e.name.decode() if e.name else '') for d in app.pe.DIRECTORY_ENTRY_IMPORT for e in d.imports}
    sites = []
    for ref, dll, name in [(0x1405c84dc, 'convert', 'strtoul'), (0x1405c865f, 'string', 'strtok'),
                           (0x1405c8680, 'string', 'strncmp'), (0x1405c8695, 'convert', 'strtol'),
                           (0x1405c86b9, 'string', 'strtok')]:
        require(imports[app.rip(app.at(ref))] == ('api-ms-win-crt-'+dll+'-l1-1-0.dll', name), 'Actual CRT import differs')
        sites.append({'call': hex(ref), 'dll': imports[app.rip(app.at(ref))][0], 'symbol': name})
    consumers = json.loads((ROOT/'docs/evidence/serato500-handshake-consumers.json').read_text())
    require(consumers['applicationSha256'] == app.sha and consumers['installedMatches'] is True and
            consumers['creationGate']['vectorBeginOffset'] == '0x178', 'Prior creation-gate identity differs')
    focused_path = ROOT/'analysis/serato500-midi-field-20261102-decompile.json'
    focused = json.loads(focused_path.read_text(encoding='utf-8-sig'))
    require(focused['binary_sha256'] == app.sha and len(focused['functions']) == len(functions), 'Focused field report differs')
    require({(int(r['start'], 16), int(r['end_exclusive'], 16)) for r in focused['functions']} ==
            {(int(r['start'], 16), int(r['endExclusive'], 16)) for r in functions} and
            all(r['complete'] is True and r.get('pseudocode') and not r.get('diagnostic') for r in focused['functions']), 'Incomplete focused functions')
    legacy_path = ROOT/'docs/evidence/serato-legacy-sl3-descriptors.json'; legacy = json.loads(legacy_path.read_text())
    historical = []
    for row in legacy['targets']:
        path = ROOT/f'artifacts/extracted/Serato DJ Pro {row["version"]}/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe'
        require(sha(path) == row['binarySha256'] and row['resource']['deviceSecretFieldEmpty'] is True and
                'secret_serato_key' not in row['fields'] and row['fields']['handshake_type'] == 'HANDSHAKE_TYPE_DRIVER_API', 'Prior historical projection differs')
        historical.append({'version': row['version'], 'binarySha256': row['binarySha256'], 'secretKeyEmpty': True,
                           'secretSeratoKeyValueFieldListed': False, 'handshakeType': row['fields']['handshake_type']})
    result = {'schema': 'sl3.serato-midi-field-sources.v1', 'applicationSha256': app.sha, 'installedMatches': True,
              'checkedInstructions': facts, 'checkedFunctions': functions, 'checkedLeafBodies': leaves, 'actualImportSites': sites,
              'fieldNamesOnly': field_names, 'constructorVectorsInitiallyEmpty': ['0x160', '0x178'],
              'processorCreationVectorField': 'secret_serato_key', 'processorCreationGate': 'descriptor+0x178 != descriptor+0x180',
              'midiId': {'offset': '0xd0', 'defaultSource': 'zero-extended 16-bit product ID at +0xaa',
                         'overrideField': 'midi_id', 'overrideConversion': 'strtoul(value, nullptr, 0), stored as DWORD'},
              'tokenParsing': {'delimiters': 'comma and space', 'checkedPrefixBytes': 2,
                               'prefix': '0x', 'numericConversion': 'strtol(token, nullptr, 16), low byte stored',
                               'firstNonmatchingTokenStopsThisLoop': True, 'strictRangeValidationEstablished': False,
                               'missingValueAttributeStandaloneResultAssigned': False},
              'growthTailTarget': '0x1405bc380', 'growthSlowPathExhausted': False,
              'priorConsumersCanonicalSha256': canonical_sha(consumers), 'priorLegacyProjectionCanonicalSha256': canonical_sha(legacy),
              'historicalProjectionWithRecheckedExecutableHashes': historical,
              'focusedReportSha256': sha(focused_path),
              'sourceSha256': {name: sha(ROOT/name) for name in ['scripts/export-serato-midi-field-sources.py',
                  'scripts/export-serato-clock-handshake-evidence.py', 'scripts/ghidra/FocusedDecompile.java']},
              'applicationExecuted': False, 'applicationModified': False, 'deviceAccess': False,
              'keyValuesOrProtocolMessagesExported': False, 'keyBearingXmlReadByThisVerifier': False,
              'handshakeImplementedOrBypassed': False, 'currentSeratoAdmissionVerified': False,
              'limits': ['Field-name and typed storage provenance only; no secret values, reply templates or successful protocol results.',
                         'This is one MIDI processor creation gate, not all current control/handshake engines.',
                         'Generic constructor defaults do not prove all later descriptor mutations or actual runtime contents.',
                         'Historical emptiness/absence uses the prior verified descriptor projection, not a newly executed legacy connection.',
                         'No key from another product is adopted; legitimate SL3 registration/control/audio/DVS remain unresolved.']}
    (ROOT/'docs/evidence/serato500-midi-field-sources.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({'verified': True, 'instructionFacts': len(facts), 'focusedFunctions': len(functions),
                      'leafBodies': len(leaves), 'actualImports': len(sites), 'secretValuesExported': False}))


if __name__ == '__main__':
    main()
