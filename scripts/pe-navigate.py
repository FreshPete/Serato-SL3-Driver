"""Execution-free x64 PE navigation. Direct-call candidates are boundary checked.

No complete control-flow or indirect-call recovery is claimed. Leaf functions
without unwind entries require an explicit start:end range for disassembly.
"""
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import re
import struct
import capstone
import pefile


def navigate(path, targets):
    data = Path(path).read_bytes()
    pe = pefile.PE(data=data, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    base = pe.OPTIONAL_HEADER.ImageBase
    ranges = sorted((base + x.struct.BeginAddress, base + x.struct.EndAddress)
                    for x in getattr(pe, 'DIRECTORY_ENTRY_EXCEPTION', []))
    starts = [x[0] for x in ranges]
    dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    cache = {}

    def bounds(va):
        index = bisect.bisect_right(starts, va) - 1
        return ranges[index] if index >= 0 and va < ranges[index][1] else None

    def instructions(span):
        if span not in cache:
            cache[span] = list(dis.disasm(pe.get_data(span[0]-base, span[1]-span[0]), span[0]))
        return cache[span]

    rows = []
    for target in targets:
        parts = [int(x, 0) for x in target.split(':')]
        va = parts[0]
        span = tuple(parts) if len(parts) == 2 else bounds(va)
        callers = []
        pointers = []
        rip_refs = []
        for section in pe.sections:
            raw = section.get_data()
            if section.Characteristics & 0x20000000:
                for match in re.finditer(rb'\xe8....', raw, re.S):
                    at = base + section.VirtualAddress + match.start()
                    if at + 5 + struct.unpack_from('<i', match.group(), 1)[0] != va:
                        continue
                    enclosing = bounds(at)
                    if enclosing and any(i.address == at and i.mnemonic == 'call'
                                         and i.op_str == hex(va) for i in instructions(enclosing)):
                        callers.append({'call_va': hex(at), 'range': [hex(x) for x in enclosing]})
                for match in re.finditer(rb'[\x48-\x4f][\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....', raw, re.S):
                    at = base + section.VirtualAddress + match.start()
                    if at + 7 + struct.unpack_from('<i', match.group(), 3)[0] != va:
                        continue
                    enclosing = bounds(at)
                    if enclosing and any(i.address == at and i.size == 7 and i.mnemonic in ['mov','lea']
                                         for i in instructions(enclosing)):
                        rip_refs.append({'instruction_va':hex(at), 'range':[hex(x) for x in enclosing]})
            else:
                needle = struct.pack('<Q', va)
                offset = raw.find(needle)
                while offset >= 0:
                    pointers.append(hex(base + section.VirtualAddress + offset))
                    offset = raw.find(needle, offset+1)
        rows.append({'target': hex(va), 'range': [hex(x) for x in span] if span else None,
                     'direct_callers': callers, 'rip_references':rip_refs, 'data_qword_pointers': pointers,
                     'assembly': [f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in instructions(span)] if span else []})
    return {'binary_sha256': hashlib.sha256(data).hexdigest(), 'image_base': hex(base),
            'coverage': __doc__, 'targets': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary')
    parser.add_argument('output')
    parser.add_argument('targets', nargs='+')
    args = parser.parse_args()
    result = navigate(args.binary, args.targets)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    for row in result['targets']:
        print(row['target'], row['range'], 'callers', len(row['direct_callers']), 'rip_refs', len(row['rip_references']), 'pointers', len(row['data_qword_pointers']))
