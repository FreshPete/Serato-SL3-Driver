"""Execution-free PE metadata, selected strings, RIP references and unwind ranges.

RIP search covers common x64 MOV/LEA encodings only; it is not a complete xref
analysis. Unwind entries bound machine code, not recovered source functions.
"""
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import re
import struct
import pefile
import capstone

def report(path, pattern):
    data = Path(path).read_bytes()
    pe = pefile.PE(data=data)
    base = pe.OPTIONAL_HEADER.ImageBase
    strings = []
    for encoding, regex in [('ascii', rb'[ -~]{5,}'), ('utf-16le', rb'(?:[ -~]\x00){5,}')]:
        for match in re.finditer(regex, data):
            value = match.group().decode(encoding)
            if re.search(pattern, value, re.I):
                try:
                    rva = pe.get_rva_from_offset(match.start())
                except pefile.PEFormatError:
                    continue
                if rva is None:
                    continue
                strings.append(dict(text=value, encoding=encoding, offset=hex(match.start()), va=hex(base+rva)))
    by_va = {int(row['va'], 16): row for row in strings}
    ranges = sorted((e.struct.BeginAddress, e.struct.EndAddress) for e in getattr(pe, 'DIRECTORY_ENTRY_EXCEPTION', []))
    starts = [b for b, e in ranges]
    dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    references = []
    for section in pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        raw = section.get_data()
        for m in re.finditer(rb'[\x48-\x4f][\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....', raw, re.S):
            rva = section.VirtualAddress + m.start()
            target = base+rva+7+struct.unpack_from('<i', m.group(), 3)[0]
            if target not in by_va:
                continue
            idx = bisect.bisect_right(starts, rva)-1
            bounds = ranges[idx] if idx >= 0 and rva < ranges[idx][1] else None
            row = dict(instruction_va=hex(base+rva), offset=hex(section.PointerToRawData+m.start()),
                       string_va=hex(target), text=by_va[target]['text'],
                       unwind_range=[hex(base+x) for x in bounds] if bounds else None)
            if bounds and bounds[1]-bounds[0] < 16000:
                code = pe.get_data(bounds[0], bounds[1]-bounds[0])
                row['assembly'] = [f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in dis.disasm(code, base+bounds[0])]
            references.append(row)
    imports = {e.dll.decode(errors='replace'): [i.name.decode(errors='replace') if i.name else f'ordinal:{i.ordinal}' for i in e.imports]
               for e in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', [])}
    exports = [dict(name=e.name.decode(errors='replace') if e.name else None, rva=hex(e.address), ordinal=e.ordinal)
               for e in getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', [])]
    return dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), machine=hex(pe.FILE_HEADER.Machine),
                image_base=hex(base), sections=[dict(name=s.Name.rstrip(b'\0').decode(errors='replace'),rva=hex(s.VirtualAddress),
                raw_offset=hex(s.PointerToRawData),characteristics=hex(s.Characteristics)) for s in pe.sections],
                imports=imports, exports=exports, strings=strings, rip_references=references,
                limitation='MOV/LEA byte candidates require instruction-boundary review; absence is not proof of absent functionality.')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('path'); p.add_argument('output')
    p.add_argument('--pattern', default=r'RaneSL3|RaneAsioSL3|sl3_|Rane SL ?3|DeviceDiscontinued|kDiscontinuedDevice|^bundles$')
    args = p.parse_args()
    result = report(args.path, args.pattern)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:len(result[k]) for k in ['strings','rip_references','imports','exports']}))
