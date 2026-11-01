from pathlib import Path
import hashlib
import json
import pefile
import capstone

root = Path(__file__).resolve().parents[1]
sources = [
    ('analysis/serato500-dispatch.json', '1405d02e0'),
    ('analysis/serato500-support-consumer.json', '1405c6a60'),
    ('analysis/serato500-app-support-routing.json', '1421db390'),
    ('analysis/serato500-support-message.json', '1421de6b0'),
    ('analysis/serato500-support-message.json', '1421de0a0'),
    ('analysis/serato500-deferred-action.json', '1421de890'),
    ('analysis/serato500-discontinued-bridge.json', '14213f290'),
    ('analysis/serato500-discontinued-emitter.json', '14213f330'),
    ('analysis/serato500-dispatch.json', '14137b790'),
    ('analysis/serato500-policy-dispatch.json', '14137d800'),
]
rows = []
for path, start in sources:
    source = json.loads((root/path).read_text())
    assert source['binary_sha256'].lower() == '66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265'
    row = next(x.copy() for x in source['functions'] if x['start'] == start)
    code = row.pop('pseudocode', '').replace('\r','')
    code = '\n'.join(x for x in code.splitlines() if x.strip())
    if start == '1421db390':
        code = code[code.index('    FUN_140c00570(*plVar36,&plStack_308);'):code.index('      if (iVar14 == 1) {')]
        row['projection'] = 'Excerpt: supported_apps lookup, values 0/2 and deferred-action enqueue; subsequent connection/stream setup omitted. Full local report under analysis/.'
    elif start == '14137b790':
        code = code[code.index('  case 4:'):code.index('  case 5:')]
        row['projection'] = 'Excerpt: message type 4 only; other notification branches omitted.'
    row['pseudocode'] = code
    rows.append(row)
result = {'binary_sha256': source['binary_sha256'],
          'coverage':source['coverage'], 'functions':rows,
          'interpretation_limit':'Static chain with RTTI-supported virtual dispatch candidates; no debugger call trace, modified executable or restored audio/DVS result.'}
(root/'docs/evidence/serato500-discontinued-path.json').write_text(json.dumps(result,indent=2),encoding='utf-8')

binary = root/'artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe'
pe = pefile.PE(str(binary),fast_load=True)
assert hashlib.sha256(binary.read_bytes()).hexdigest() == result['binary_sha256'].lower()
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
base=pe.OPTIONAL_HEADER.ImageBase
dis=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
ranges=sorted((base+e.struct.BeginAddress,base+e.struct.EndAddress) for e in pe.DIRECTORY_ENTRY_EXCEPTION)
cache={}
spans=[(0x1405d03fd,0x1405d0467),(0x1405c6a60,0x1405c6a68),
       (0x1421db6a8,0x1421db6e0),(0x1421db7f0,0x1421db980),
       (0x1421deb50,0x1421deb91),(0x14213f290,0x14213f2da)]
assembly=[]
for start,end in spans:
    if start==0x1405c6a60:
        selected=list(dis.disasm(pe.get_data(start-base,end-start),start))
        assert [i.mnemonic for i in selected] == ['lea','ret']
    else:
        enclosing=next((lo,hi) for lo,hi in ranges if lo<=start<hi)
        if enclosing not in cache:
            lo,hi=enclosing
            cache[enclosing]=list(dis.disasm(pe.get_data(lo-base,hi-lo),lo))
        selected=[i for i in cache[enclosing] if start<=i.address<end]
        assert selected and selected[0].address==start, f'Invalid excerpt boundary {start:x}'
    assembly.append({'start':hex(start),'end_exclusive':hex(selected[-1].address+selected[-1].size),
                     'instructions':[f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in selected]})
emitter=list(dis.disasm(pe.get_data(0x14213f330-base,0x14213f676-0x14213f330),0x14213f330))
for index,ins in enumerate(emitter):
    if ins.mnemonic=='call' and ins.op_str=='0x14059c190':
        selected=emitter[index-7:index+2]
        assembly.append({'start':hex(selected[0].address),'end_exclusive':hex(selected[-1].address+selected[-1].size),
                         'instructions':[f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in selected]})
(root/'docs/evidence/serato500-support-branch-assembly.json').write_text(json.dumps({'binary_sha256':result['binary_sha256'], 'coverage':'Selected instruction excerpts, with starts checked against disassembly from the enclosing unwind entry (map getter is a separate eight-byte leaf).', 'excerpts':assembly},indent=2),encoding='utf-8')
