"""Carve structurally plausible CAB containers from a WiX Burn installer.

Candidates are checked/extracted separately with 7-Zip. This does not execute
the bootstrapper and does not establish installer-level authenticity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

def carve(path, output):
    source = Path(path)
    data = source.read_bytes()
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    rows = []
    start = 0
    while (offset := data.find(b'MSCF', start)) >= 0:
        start = offset + 4
        if offset + 36 > len(data):
            continue
        size = struct.unpack_from('<I', data, offset+8)[0]
        if data[offset+4:offset+8] != bytes(4) or not 36 <= size <= len(data)-offset:
            continue
        chunk = data[offset:offset+size]
        target = destination / f'cab-{offset:x}.cab'
        target.write_bytes(chunk)
        rows.append(dict(offset=hex(offset), bytes=size, path=str(target), sha256=hashlib.sha256(chunk).hexdigest()))
    print(json.dumps(dict(source=str(source),sha256=hashlib.sha256(data).hexdigest(),containers=rows),indent=2))

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('path'); p.add_argument('output')
    carve(**vars(p.parse_args()))
