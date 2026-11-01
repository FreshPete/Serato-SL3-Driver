"""Read Mach-O CPU slices, dylib dependencies and SL3 symbols without execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

def report(path):
    data = Path(path).read_bytes()
    slices = [(0,len(data))]
    if data[:4] == bytes.fromhex('cafebabe'):
        count = struct.unpack_from('>I',data,4)[0]
        slices = []
        for i in range(count):
            cpu,sub,offset,size,align = struct.unpack_from('>IIIII',data,8+i*20)
            if offset+size > len(data): raise ValueError('Fat slice beyond EOF')
            slices.append((offset,size))
    result = []
    for offset,size in slices:
        image = data[offset:offset+size]
        is64 = image[:4] == bytes.fromhex('cffaedfe')
        if image[:4] not in [bytes.fromhex('cffaedfe'),bytes.fromhex('cefaedfe')]:
            raise ValueError('Unsupported Mach-O magic')
        magic,cpu,sub,filetype,ncmds,cmdbytes,flags = struct.unpack_from('<7I',image)
        pos = 32 if is64 else 28
        libs, symbols = [], []
        for i in range(ncmds):
            cmd,length = struct.unpack_from('<II',image,pos)
            if length < 8 or pos+length > len(image): raise ValueError('Invalid load command')
            if cmd & 0x7fffffff in [0xc,0x18,0x1f,0xd]:
                name_offset = struct.unpack_from('<I',image,pos+8)[0]
                libs.append(dict(command=hex(cmd),name=image[pos+name_offset:pos+length].split(bytes(1))[0].decode(errors='replace')))
            if cmd == 2:
                symoff,nsyms,stroff,strsize = struct.unpack_from('<IIII',image,pos+8)
                for index in range(nsyms):
                    entry = symoff+index*(16 if is64 else 12)
                    string_index = struct.unpack_from('<I',image,entry)[0]
                    value = struct.unpack_from('<Q' if is64 else '<I',image,entry+8)[0]
                    name = image[stroff+string_index:stroff+strsize].split(bytes(1))[0].decode(errors='replace')
                    if 'sl3' in name.lower(): symbols.append(dict(name=name,value=hex(value),type=image[entry+4]))
            pos += length
        result.append(dict(offset=hex(offset),bytes=size,cpu=hex(cpu),architecture={7:'i386',0x1000007:'x86_64',0x100000c:'arm64'}.get(cpu,'unknown'),filetype=filetype,libraries=libs,sl3_symbols=symbols))
    return dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),slices=result,
                signature_status='Not verified; Windows structural inspection is not codesign/pkgutil validation')

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root');p.add_argument('output');a=p.parse_args()
    rows=[]
    for path in Path(a.root).rglob('*'):
        if path.is_file() and path.read_bytes()[:4] in [bytes.fromhex(x) for x in ['cafebabe','cffaedfe','cefaedfe']]: rows.append(report(path))
    Path(a.output).write_text(json.dumps(rows,indent=2),encoding='utf8')
    print(json.dumps([dict(path=r['path'],architectures=[s['architecture'] for s in r['slices']]) for r in rows],indent=2))
