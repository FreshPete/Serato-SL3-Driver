"""Inspect the pinned PLA disk image offline; never load it or start a session."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

import capstone
import pefile

ROOT = Path(__file__).resolve().parents[1]
IMAGE_SHA = 'c36da0d945877ac66f1cf5761f93e4ca593d9ce01433a2941129449338ca3740'
PDB_SHA = 'a1a6f6ed626d0a14362b47e6b646d0d437fd9331f5bca6be550aacd6ce61bc6d'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def main():
    reference = ROOT/'artifacts/references/windows-pla'
    image, pdb = reference/'pla.dll', reference/'pla.pdb'
    require(sha(image) == IMAGE_SHA and sha(pdb) == PDB_SHA, 'Unreviewed PLA image/PDB')
    helper_path = ROOT/'scripts/export-usbhub3-state-symbols.py'
    spec = importlib.util.spec_from_file_location('identity_parser', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    identity, pdb_id = helper.image_identity(image), helper.pdb_identity(pdb)
    require(identity['guid'] == pdb_id['guid'] and pdb_id['infoAge'] >= identity['age']
            and pdb_id['dbiAge'] == identity['age'], 'PLA PDB identity mismatch')
    symbols_path = ROOT/'analysis/pla-all-public-symbols.json'
    symbols = json.loads(symbols_path.read_text(encoding='utf-8-sig'))
    require(symbols['imageSha256'] == IMAGE_SHA and symbols['pdbSha256'] == PDB_SHA
            and symbols['rsds'] == identity and symbols['pdbIdentity'] == pdb_id,
            'Cached symbols belong to another module')
    generator = ROOT/'analysis/pla-all-public-symbols.py'
    require(symbols['generatorSha256'] == sha(generator), 'Cached symbol generator changed')
    pe = pefile.PE(str(image))
    base = pe.OPTIONAL_HEADER.ImageBase
    require(pe.FILE_HEADER.Machine == 0x8664 and base == 0x180000000, 'Unexpected image ABI')
    dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    dis.detail = True
    functions, instructions = [], {}
    for name, start, end in [
            ('_TraceDataCollector::put_ExtendedModes', 0x53cc0, 0x53d82),
            ('_TraceDataCollector::get_ExtendedModes', 0xa7460, 0xa7525),
            ('TraceSession::get_Mode', 0x8bbb0, 0x8bf21),
            ('TraceSession::Commit', 0x87690, 0x884d8),
            ('TraceSession::Start', 0x17610, 0x18054)]:
        require(any(s['name'] == name and s['rva'] == start for s in symbols['symbols']),
                'Function symbol mismatch: '+name)
        require(any(e.struct.BeginAddress == start and e.struct.EndAddress == end
                    for e in pe.DIRECTORY_ENTRY_EXCEPTION), 'Unwind range mismatch: '+name)
        raw = pe.get_data(start, end-start)
        decoded = list(dis.disasm(raw, base+start))
        require(decoded and sum(i.size for i in decoded) == len(raw), 'Incomplete function decoding')
        instructions.update({i.address-base: i for i in decoded})
        functions.append({'symbol': name, 'startRva': hex(start), 'endRva': hex(end),
                          'sha256': hashlib.sha256(raw).hexdigest()})
    facts = []

    def instruction(rva, expected):
        i = instructions[rva]
        require(i.mnemonic+' '+i.op_str == expected, 'Instruction mismatch at '+hex(rva))
        facts.append({'rva': hex(rva), 'bytes': bytes(i.bytes).hex(), 'assembly': expected})

    for rva, text in [
            (0x53cd7, 'mov esi, edx'),
            (0x53d64, 'mov dword ptr [rdi + 0xb4], esi'),
            (0xa7501, 'mov eax, dword ptr [rdi + 0xb4]'),
            (0xa750b, 'mov dword ptr [rsi], eax'),
            (0x8bbf8, 'mov rsi, rdx'),
            (0x8bd7e, 'mov rcx, qword ptr [rbp - 0x80]'),
            (0x8bd82, 'lea rdx, [rsp + 0x74]'),
            (0x8bd87, 'mov rax, qword ptr [rcx]'),
            (0x8bd8a, 'mov rax, qword ptr [rax + 0x150]'),
            (0x8bd91, 'call 0x18014a010'),
            (0x8be3c, 'lea rdx, [rsp + 0x70]'),
            (0x8be5b, 'or dword ptr [rsp + 0x74], r12d'),
            (0x8be7f, 'or dword ptr [rsp + 0x74], 2'),
            (0x8bea3, 'or dword ptr [rsp + 0x74], 0x20'),
            (0x8bec2, 'mov eax, dword ptr [rsp + 0x74]'),
            (0x8becd, 'bts eax, 0xb'),
            (0x8bed5, 'mov dword ptr [rsi], eax'),
            (0x87703, 'mov r15, rdx'),
            (0x87c6b, 'mov rax, qword ptr [r14]'),
            (0x87c6e, 'lea rbx, [r15 + 0x40]'),
            (0x87c72, 'mov rdx, rbx'),
            (0x87c75, 'mov rcx, r14'),
            (0x87c78, 'mov rax, qword ptr [rax + 0x268]'),
            (0x87c7f, 'call 0x18014a010'),
            (0x17a54, 'mov rax, qword ptr [r14]'),
            (0x17a5a, 'mov r15, qword ptr [rbp - 0x68]'),
            (0x17a62, 'mov rdx, r15'),
            (0x17a65, 'mov rax, qword ptr [rax + 0x278]'),
            (0x17a6c, 'call 0x18014a010'),
            (0x17c88, 'mov r8, r15'),
            (0x17c8b, 'call qword ptr [rip + 0x13bd3e]')]:
        instruction(rva, text)
    slots = []
    for table, table_rva, slot, target in [
            ("TraceSession::`vftable'", 0x14b6e8, 0x268, 0x8bbb0),
            ("TraceSession::`vftable'", 0x14b6e8, 0x278, 0x87690),
            ("_TraceDataCollector::`vftable'", 0x14bbe8, 0x150, 0xa7460)]:
        require(any(s['name'] == table and s['rva'] == table_rva for s in symbols['symbols']),
                'Vtable symbol mismatch')
        require(struct.unpack('<Q', pe.get_data(table_rva+slot, 8))[0] == base+target,
                'Vtable pointer mismatch')
        slots.append({'table': table, 'tableRva': hex(table_rva), 'slot': hex(slot), 'targetRva': hex(target)})
    call = instructions[0x17c8b]
    iat = call.address+call.size+call.operands[0].mem.disp
    require(call.size == 7 and iat == base+0x1539d0, 'Prefixed IAT call mismatch')
    require(any(i.address == iat and i.name == b'StartTraceW'
                for entry in pe.DIRECTORY_ENTRY_IMPORT for i in entry.imports), 'StartTraceW import mismatch')
    dependencies = [Path(__file__), helper_path, generator, symbols_path,
                    ROOT/'analysis/pla-installed-image.json', reference/'acquisition.json']
    result = {'scope': 'Pinned disk-image static candidate path; no execution of PLA or live session',
              'imageSha256': IMAGE_SHA, 'pdbSha256': PDB_SHA, 'rsds': identity, 'pdbIdentity': pdb_id,
              'functions': functions, 'instructions': facts, 'vtableSlots': slots,
              'startTraceIatRva': hex(iat-base), 'requestedSystemLoggerMode': '0x02000000',
              'finding': 'The inspected base get_Mode path reads raw ExtendedModes and adds bits; it does not narrow the raw value to older documented flags.',
              'runtimeFlagForwardingVerified': False, 'actualDispatchVerified': False,
              'liveImageRundownVerified': False, 'independentStopValidated': False, 'readinessAdmission': False,
              'limits': ['Static base-vtable links are conditional on actual dynamic dispatch.',
                         'Selected instruction assertions are not exhaustive control-flow or alias analysis.',
                         'Properties offset 0x40 uses the Windows x64 EVENT_TRACE_PROPERTIES ABI; no compiled layout check was completed.',
                         'Internal TraceSession::Commit is distinct from the public PLA validation-only Commit.',
                         'Installed disk image does not attest the service loaded image or historical USBHUB3 identity.',
                         'No source started, effective runtime modes queried, ETL produced, or USB operation performed.'],
              'dependencies': {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in dependencies}}
    output = ROOT/'docs/evidence/pla-image-mode-path-20261031.json'
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified pinned PLA image/PDB, five complete function ranges, 31 instruction facts, three vtable links and StartTraceW IAT')


if __name__ == '__main__':
    main()
