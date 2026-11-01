"""Recover selected MSVC x64 RTTI complete-object locators and vtable candidates.

Validates locator signature, self RVA and type-descriptor RVA. Tables end at the
first non-executable pointer, capped at 64 slots. This does not recover all C++
types, inheritance semantics, function ABI or runtime dispatch targets.
"""
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import re
import struct
import pefile


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('binary'); ap.add_argument('output'); ap.add_argument('pattern')
    args = ap.parse_args()
    data = Path(args.binary).read_bytes()
    pe = pefile.PE(data=data, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    base = pe.OPTIONAL_HEADER.ImageBase
    spans = sorted((base+e.struct.BeginAddress, base+e.struct.EndAddress) for e in pe.DIRECTORY_ENTRY_EXCEPTION)
    starts = [x[0] for x in spans]
    sections = [s for s in pe.sections if not s.Characteristics & 0x20000000]
    code = [(base+s.VirtualAddress, base+s.VirtualAddress+s.Misc_VirtualSize)
            for s in pe.sections if s.Characteristics & 0x20000000]
    rows = []
    for match in re.finditer(rb'\.\?AV[ -~]{1,1024}', data):
        name = match.group().decode('ascii')
        if not re.search(args.pattern, name):
            continue
        type_rva = pe.get_rva_from_offset(match.start()) - 16
        locators = []
        for section in sections:
            raw = section.get_data()
            at = raw.find(struct.pack('<I', type_rva))
            while at >= 0:
                start = at - 12
                if start >= 0 and start+24 <= len(raw):
                    sig, offset, cd_offset, td, hierarchy, self_rva = struct.unpack_from('<6I', raw, start)
                    locator_rva = section.VirtualAddress + start
                    if sig == 1 and self_rva == locator_rva:
                        tables = []
                        for pointer_section in sections:
                            pointers = pointer_section.get_data()
                            pos = pointers.find(struct.pack('<Q', base+locator_rva))
                            while pos >= 0:
                                vt = base+pointer_section.VirtualAddress+pos+8
                                slots = []
                                for i in range(64):
                                    if pos+8*(i+2) > len(pointers):
                                        break
                                    target = struct.unpack_from('<Q', pointers, pos+8*(i+1))[0]
                                    if not any(lo <= target < hi for lo, hi in code):
                                        break
                                    index = bisect.bisect_right(starts, target)-1
                                    bounds = spans[index] if index >= 0 and target < spans[index][1] else None
                                    slots.append({'offset':hex(i*8), 'target':hex(target),
                                                  'unwind_range':[hex(x) for x in bounds] if bounds else None})
                                if slots:
                                    tables.append({'va':hex(vt), 'slots':slots})
                                pos = pointers.find(struct.pack('<Q', base+locator_rva), pos+1)
                        locators.append({'va':hex(base+locator_rva), 'object_offset':hex(offset),
                                         'constructor_displacement':cd_offset, 'tables':tables})
                at = raw.find(struct.pack('<I', type_rva), at+1)
        rows.append({'decorated_type':name, 'type_descriptor_va':hex(base+type_rva), 'locators':locators})
    result = {'binary_sha256':hashlib.sha256(data).hexdigest(), 'coverage':__doc__, 'classes':rows}
    Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    for row in rows:
        print(row['decorated_type'], [(l['object_offset'],[(t['va'],len(t['slots'])) for t in l['tables']]) for l in row['locators']])
