"""Hash explicit files or directories; identify PE and Mach-O headers without execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

def inventory(paths):
    for name in paths:
        root=Path(name)
        for path in sorted(root.rglob('*')) if root.is_dir() else [root]:
            if not path.is_file(): continue
            digest=hashlib.sha256()
            with path.open('rb') as source:
                header=source.read(4096); digest.update(header)
                while chunk:=source.read(1024*1024):digest.update(chunk)
            row=dict(path=path.as_posix(),bytes=path.stat().st_size,sha256=digest.hexdigest(),format='unclassified')
            if header[:2]==b'MZ' and len(header)>=64:
                offset=struct.unpack_from('<I',header,60)[0]
                with path.open('rb') as source: source.seek(offset); signature=source.read(6)
                if signature[:4]==b'PE\0\0':
                    row.update(format='PE',machine=hex(struct.unpack_from('<H',signature,4)[0]))
            elif header[:4] in [bytes.fromhex(s) for s in ['cffaedfe','cefaedfe','cafebabe']]:row['format']='Mach-O'
            elif header[:4]==b'xar!':row['format']='XAR'
            elif header[:2]==b'PK':row['format']='ZIP'
            yield row

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('paths',nargs='+');p.add_argument('--output',required=True);a=p.parse_args()
    rows=list(inventory(a.paths));Path(a.output).write_text(json.dumps(rows,indent=2),encoding='utf8');print(f'Inventoried {len(rows)} files')
