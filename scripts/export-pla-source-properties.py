"""Verify selected PLA source-property paths in pinned disk bytes; never execute PLA."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

import capstone
import pefile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    helper_path = ROOT/'scripts/export-pla-image-mode-path.py'
    spec = importlib.util.spec_from_file_location('pla_mode', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    reference = ROOT/'artifacts/references/windows-pla'
    image, pdb = reference/'pla.dll', reference/'pla.pdb'
    require(sha(image) == helper.IMAGE_SHA and sha(pdb) == helper.PDB_SHA,
            'Unreviewed PLA disk image/PDB')
    symbols_path = ROOT/'analysis/pla-all-public-symbols.json'
    generator = ROOT/'analysis/pla-all-public-symbols.py'
    symbols = json.loads(symbols_path.read_text(encoding='utf-8-sig'))
    require(symbols['imageSha256'] == helper.IMAGE_SHA and symbols['pdbSha256'] == helper.PDB_SHA
            and symbols['generatorSha256'] == sha(generator), 'Unbound public-symbol cache')
    pe = pefile.PE(str(image))
    base = pe.OPTIONAL_HEADER.ImageBase
    require(pe.FILE_HEADER.Machine == 0x8664 and base == 0x180000000, 'Unexpected ABI')
    dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    dis.detail = True
    instructions, functions = {}, []
    ranges = [
        ('HDataCollector::Load', 0x123c90, 0x12476b),
        ('HTraceDataCollector::Load', 0x126d00, 0x128741),
        ('DataCollectorSet::put_SegmentMaxSize', 0x52c50, 0x52e43),
        ('DataCollectorSet::get_SegmentMaxSize', 0xc1bc0, 0xc1c85),
        ('_TraceDataCollector::get_Guid', 0xa76d0, 0xa7798),
        ('TraceSession::Commit', 0x87690, 0x884d8),
        ('TraceSession::Query', 0x1e7b0, 0x1f377),
        ('CreateClassObject<_TraceDataCollector>', 0x1f5bc, 0x1f8bf),
        ('_TraceDataCollector::_TraceDataCollector', 0x1f8c8, 0x1fa8e),
    ]
    for name, start, end in ranges:
        require(any(s['name'] == name and s['rva'] == start for s in symbols['symbols']),
                'Public symbol differs: '+name)
        require(any(e.struct.BeginAddress == start and e.struct.EndAddress == end
                    for e in pe.DIRECTORY_ENTRY_EXCEPTION), 'Unwind range differs: '+name)
        raw = pe.get_data(start, end-start)
        decoded = list(dis.disasm(raw, base+start))
        require(decoded and sum(i.size for i in decoded) == len(raw), 'Incomplete decoding: '+name)
        instructions.update({i.address-base: i for i in decoded})
        functions.append({'symbol': name, 'startRva': hex(start), 'endRva': hex(end),
                          'sha256': hashlib.sha256(raw).hexdigest()})
    facts = []
    for rva, expected in [
        (0x123cd1, 'mov rdi, rcx'),
        (0x12448b, 'mov rcx, qword ptr [rdi + 0x80]'),
        (0x124492, 'lea rdx, [rdi + 0x32]'),
        (0x124499, 'mov rax, qword ptr [rax + 0xa0]'),
        (0x124666, 'lea rdx, [rdi + 0x74]'),
        (0x12466d, 'mov rax, qword ptr [rax + 0xe0]'),
        (0x126d3d, 'xor r15d, r15d'),
        (0x126d40, 'mov rsi, rcx'),
        (0x127238, 'mov rcx, rsi'),
        (0x12723b, 'call 0x180123c90'),
        (0x12736e, 'cmp word ptr [rsi + 0x32], r15w'),
        (0x127373, 'je 0x18012741e'),
        (0x127379, 'mov rcx, qword ptr [rsi + 0x130]'),
        (0x127380, 'mov edx, dword ptr [rsi + 0x74]'),
        (0x127386, 'mov rax, qword ptr [rax + 0xe8]'),
        (0x12738d, 'call 0x18014a010'),
        (0x127421, 'movzx edx, word ptr [rsi + 0x32]'),
        (0x127428, 'mov rax, qword ptr [rax + 0xa8]'),
        (0x128523, 'cmp dword ptr [rsi + 0x74], r15d'),
        (0x128527, 'je 0x1801285d5'),
        (0x12852d, 'cmp word ptr [rsi + 0x32], r15w'),
        (0x128532, 'jne 0x1801285d5'),
        (0x128540, 'mov edx, ebx'),
        (0x128545, 'mov rax, qword ptr [rax + 0x30]'),
        (0x52c93, 'mov esi, edx'),
        (0x52c95, 'mov rbx, rcx'),
        (0x52e06, 'mov dword ptr [rbx + 0x90], esi'),
        (0xc1c61, 'mov eax, dword ptr [rdi + 0x90]'),
        (0xc1c6b, 'mov dword ptr [rsi], eax'),
        (0x87703, 'mov r15, rdx'),
        (0x87c2a, 'lea rdx, [r15 + 0x3c]'),
        (0x87c31, 'mov rax, qword ptr [rax + 0xe0]'),
        (0x87f10, 'lea rdx, [rbp - 0x20]'),
        (0x87f17, 'mov rax, qword ptr [rax + 0x180]'),
        (0xa7771, 'movups xmm0, xmmword ptr [rdi + 0xc0]'),
        (0xa777c, 'movdqu xmmword ptr [rsi], xmm0'),
        (0x87ff4, 'jne 0x18008808e'),
        (0x8808e, 'movups xmm0, xmmword ptr [rbp - 0x20]'),
        (0x88092, 'movdqu xmmword ptr [r15 + 0x18], xmm0'),
        (0x126ec3, 'mov rcx, qword ptr [rsi + 0x130]'),
        (0x126eca, 'xor r8d, r8d'),
        (0x126ecd, 'mov rdx, qword ptr [r14]'),
        (0x126ed3, 'mov rax, qword ptr [rax + 0x1d8]'),
        (0x126eda, 'call 0x18014a010'),
        (0x126edf, 'mov rcx, qword ptr [rsi + 0x130]'),
        (0x1e906, 'call 0x18001f5bc'),
        (0x1e90b, 'mov qword ptr [rbp - 0x78], rax'),
        (0x1e93f, 'call 0x18001faa0'),
        (0x1e98a, 'mov r8, rsi'),
        (0x1e98d, 'xor ecx, ecx'),
        (0x1e98f, 'call qword ptr [rip + 0x135062]'),
        (0x1e99b, 'cmp eax, 0x1069'),
        (0x1e9a6, 'mov ebx, 0x80300002'),
        (0x1f660, 'call 0x18001f8c8'),
        (0x1f8d4, 'mov rbx, rcx'),
        (0x1f929, 'xorps xmm0, xmm0'),
        (0x1f962, 'movups xmmword ptr [rbx + 0xc0], xmm0'),
        (0x87fa6, 'test r12d, r12d'),
        (0x87fa9, 'jne 0x18008809d'),
        (0x87faf, 'test r13d, r13d'),
        (0x87fb2, 'jne 0x18008809d'),
        (0x87fd6, 'mov rax, qword ptr [rbp - 0x20]'),
        (0x87fda, 'sub rax, qword ptr [rip + 0xcfddf]'),
        (0x87fe3, 'mov rax, qword ptr [rbp - 0x18]'),
        (0x87fe7, 'sub rax, qword ptr [rip + 0xcfdda]'),
        (0x87ffa, 'lea rcx, [r15 + 0x18]'),
        (0x87ffe, 'call qword ptr [rip + 0xcb2e3]'),
    ]:
        i = instructions[rva]
        require(i.mnemonic+' '+i.op_str == expected, 'Instruction differs at '+hex(rva))
        facts.append({'rva': hex(rva), 'bytes': bytes(i.bytes).hex(), 'assembly': expected})
    slots = []
    for table, table_rva, slot, name, target in [
        ("TraceSession::`vftable'", 0x14b6e8, 0xe0, 'DataCollectorSet::get_SegmentMaxSize', 0xc1bc0),
        ("TraceSession::`vftable'", 0x14b6e8, 0xe8, 'DataCollectorSet::put_SegmentMaxSize', 0x52c50),
        ("_TraceDataCollector::`vftable'", 0x14bbe8, 0xa0, '_DataCollector<ITraceDataCollector>::get_LogCircular', None),
        ("_TraceDataCollector::`vftable'", 0x14bbe8, 0xa8, '_DataCollector<ITraceDataCollector>::put_LogCircular', 0x85110),
        ("_TraceDataCollector::`vftable'", 0x14bbe8, 0x180, '_TraceDataCollector::get_Guid', 0xa76d0),
        ("_TraceDataCollector::`vftable'", 0x14bbe8, 0x188, '_TraceDataCollector::put_Guid', 0x44ef0),
        ("HTraceDataCollector::`vftable'", 0x14dc38, 0x30, 'HDataCollector::SetCycle', 0x125060),
        ("TraceSession::`vftable'", 0x14b6e8, 0x1d8, 'TraceSession::Query', 0x1e7b0),
    ]:
        actual = struct.unpack('<Q', pe.get_data(table_rva+slot, 8))[0]-base
        require((target is None or actual == target)
                and any(s['name'] == name and s['rva'] == actual for s in symbols['symbols'])
                and any(s['name'] == table and s['rva'] == table_rva for s in symbols['symbols']),
                'Vtable/symbol binding differs: '+name)
        slots.append({'table': table, 'tableRva': hex(table_rva), 'slot': hex(slot),
                      'targetRva': hex(actual), 'targetSymbol': name})
    imports = []
    for call_rva, expected_iat, name, dll in [
        (0x87ffe, 0x1532e8, b'UuidCreate', b'RPCRT4.dll'),
        (0x1e98f, 0x1539f8, b'QueryTraceW', b'api-ms-win-eventing-legacy-l1-1-0.dll'),
    ]:
        i = instructions[call_rva]
        actual = i.address+i.size+i.operands[0].mem.disp-base
        require(actual == expected_iat and any(entry.dll == dll and item.name == name
                and item.address == base+actual for entry in pe.DIRECTORY_ENTRY_IMPORT for item in entry.imports),
                'Import binding differs: '+name.decode())
        imports.append({'callRva': hex(call_rva), 'iatRva': hex(actual), 'name': name.decode(), 'dll': dll.decode()})
    null_rva = 0x157dc0
    require(pe.get_data(null_rva, 16) == bytes(16), 'Expected GUID_NULL constant')
    for rva, offset in [(0x87fda, 0), (0x87fe7, 8)]:
        i = instructions[rva]
        require(i.address+i.size+i.operands[1].mem.disp-base == null_rva+offset,
                'GUID_NULL comparison reference differs')
    # A narrow instruction inventory, not an assertion about all indirect aliases/callees.
    slot_loads = []
    for rva, i in instructions.items():
        if not 0x126d00 <= rva < 0x128741 or i.mnemonic != 'mov' or len(i.operands) != 2:
            continue
        destination, source = i.operands
        if (destination.type == capstone.x86.X86_OP_REG and destination.reg == capstone.x86.X86_REG_RAX
                and source.type == capstone.x86.X86_OP_MEM and source.mem.base == capstone.x86.X86_REG_RAX
                and source.mem.index == 0):
            slot_loads.append({'rva': hex(rva), 'slot': hex(source.mem.disp)})
    require(slot_loads and not any(int(row['slot'],16) in (0x180,0x188) for row in slot_loads),
            'Unexpected direct collector GUID slot load; review transfer path')
    result = {
        'scope': 'Selected static disk-image source-property paths; no PLA/session or USB execution',
        'imageSha256': sha(image), 'pdbSha256': sha(pdb),
        'functions': functions, 'instructions': facts, 'vtableSlots': slots,
        'imports': imports, 'guidNullConstantRva': hex(null_rva),
        'serviceLoadDirectRaxVtableSlotLoads': slot_loads,
        'finding': 'The inspected HTraceDataCollector::Load forwards SegmentMaxSize into TraceSession only when LogCircular is nonzero; a nonzero sequential limit follows a separate SetCycle virtual path.',
        'guidFinding': 'The service loader queries a fresh TraceSession; its inspected Query creates a collector with a zero GUID. The base properties builder has a GUID_NULL path calling UuidCreate into Wnode.Guid. No direct mov rax,[rax+0x180/0x188] GUID accessor slot loads occur in the decoded service Load function; this narrow inventory is not exhaustive alias/callee analysis. These paths make service-generated identity a candidate explanation, not proof of the historical mismatch.',
        'effectiveNativeLimitVerified': False, 'guidMismatchResolved': False,
        'readinessAdmission': False,
        'limits': ['Static paths are conditional on real object types, successful calls and dispatch.',
                   'The separate sequential virtual path is not decoded or proved to stop at the configured size.',
                   'The original live query discarded its returned GUID; it cannot be reconstructed here.',
                   'Persisted service XML readback does not necessarily expose the inner native-session collector.',
                   'Neither a fresh generated GUID nor an expected-configuration GUID is admitted as the original native identity without live evidence.',
                   'This is consistent with the saved MaxFileSize=0 header, not proof of the historical service execution path.',
                   'No circular logging, source-policy relaxation or new live test is selected.'],
        'references': [
            'https://learn.microsoft.com/en-us/windows/win32/api/pla/nf-pla-idatacollectorset-get_segmentmaxsize',
            'https://learn.microsoft.com/en-us/windows/win32/api/evntrace/ns-evntrace-event_trace_properties',
            'https://learn.microsoft.com/en-us/windows/win32/api/rpcdce/nf-rpcdce-uuidcreate'],
        'dependencies': {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p)
                         for p in [Path(__file__), helper_path, generator, symbols_path]},
    }
    output = ROOT/'docs/evidence/pla-source-properties-20261031.json'
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(f'Verified {len(functions)} full ranges, {len(facts)} instruction facts and {len(slots)} vtable links')


if __name__ == '__main__':
    main()
