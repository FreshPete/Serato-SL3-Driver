"""Find x64 displacement candidates and confirm instructions in unwind ranges.

This establishes instruction operands only, not the type of the addressed object.
Candidates outside unwind ranges or in functions larger than 64 KiB are omitted.
"""
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import struct
import capstone
import pefile

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('binary'); p.add_argument('output'); p.add_argument('displacement', type=lambda s: int(s, 0))
    args = p.parse_args()
    raw = Path(args.binary).read_bytes()
    pe = pefile.PE(data=raw, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    base = pe.OPTIONAL_HEADER.ImageBase
    ranges = sorted((e.struct.BeginAddress+base, e.struct.EndAddress+base) for e in pe.DIRECTORY_ENTRY_EXCEPTION)
    starts = [x[0] for x in ranges]
    candidates = set()
    needle = struct.pack('<i', args.displacement)
    for section in pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        data = section.get_data(); offset = data.find(needle)
        while offset >= 0:
            va = base + section.VirtualAddress + offset
            i = bisect.bisect_right(starts, va)-1
            if i >= 0 and va < ranges[i][1] and ranges[i][1]-ranges[i][0] < 65536:
                candidates.add(ranges[i])
            offset = data.find(needle, offset+1)
    dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    rows = []
    for start, end in sorted(candidates):
        instructions = list(dis.disasm(pe.get_data(start-base, end-start), start))
        for index, ins in enumerate(instructions):
            if f'0x{args.displacement:x}]' in ins.op_str or f'0x{args.displacement:x} ' in ins.op_str:
                rows.append({'at': hex(ins.address), 'instruction': f'{ins.mnemonic} {ins.op_str}',
                             'range': [hex(start), hex(end)],
                             'context': [f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in instructions[max(0,index-4):index+5]]})
    Path(args.output).write_text(json.dumps({'binary_sha256':hashlib.sha256(raw).hexdigest(),
        'coverage':__doc__, 'displacement':hex(args.displacement), 'references': rows}, indent=2), encoding='utf-8')
    print('\n'.join(str({k:r[k] for k in ['at','instruction','range']}) for r in rows))
