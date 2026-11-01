"""Project static Rane startup evidence; never loads or executes the driver.

Maps the binary's embedded KMDF bind table to installed WDK header indices.
Checking two current header revisions supports index stability but does not
replace verified 1.7 ABI types or a runtime USB trace.
"""
from pathlib import Path
import hashlib
import json
import re
import struct
import capstone
import pefile

root=Path(__file__).resolve().parents[1]
binary=root/'artifacts/extracted/rane-windows/x64/strmdrv.sys'
raw=binary.read_bytes()
digest=hashlib.sha256(raw).hexdigest()
assert digest=='e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5'
pe=pefile.PE(data=raw,fast_load=True)
base=pe.OPTIONAL_HEADER.ImageBase
size,component,major,minor,build,count,table,module=struct.unpack('<I4xQIIIIQQ',pe.get_data(0x16110-base,48))
assert (size,major,minor,build,count,table)==(48,1,7,6001,387,0x16220)
headers=[]
maps=[]
for version in ['1.15','1.35']:
    path=root/f'tools/wdk-10.0.28000.2526/c/Include/wdf/kmdf/{version}/wdffuncenum.h'
    text=path.read_text(encoding='utf-8-sig')
    mapping={int(index):name for name,index in re.findall(r'(Wdf\w+)TableIndex\s*=\s*(\d+)',text)}
    maps.append(mapping)
    headers.append({'version':version,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
assert all(maps[0].get(i)==maps[1].get(i) for i in range(count))
source=json.loads((root/'analysis/rane-kernel-startup.json').read_text())
assert source['binary_sha256'].lower()==digest
selected=['00019008','00019880','00019b18','00019c48','0001968c',
          '000197e0','00019990','00011330','00011420','000114c8',
          '000116a0','0001184c','000118c4','00011a1c','00011a90']
functions=[]
dis=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
dis.detail=True
for address in selected:
    row=next(f.copy() for f in source['functions'] if f['start']==address)
    start=int(row['start'],16); end=int(row['end_exclusive'],16)
    row['pseudocode']='\n'.join(x for x in row['pseudocode'].replace('\r','').splitlines() if x.strip())
    calls=[]
    for ins in dis.disasm(pe.get_data(start-base,end-start),start):
        if ins.mnemonic!='call':
            continue
        for operand in ins.operands:
            if operand.type==capstone.CS_OP_MEM and operand.mem.base==capstone.x86.X86_REG_RIP:
                target=ins.address+ins.size+operand.mem.disp
                if table<=target<table+count*8 and (target-table)%8==0:
                    index=(target-table)//8
                    calls.append({'instruction_va':hex(ins.address),'table_slot_va':hex(target),
                                  'index':index,'wdk_name':maps[0].get(index)})
    row['mapped_wdf_calls']=calls
    if address in ['00019008','0001968c','000116a0','0001184c','00011a90']:
        row['assembly']=[f'{i.address:x}: {i.mnemonic} {i.op_str}'
                         for i in dis.disasm(pe.get_data(start-base,end-start),start)]
    functions.append(row)
# These stores register the four callbacks in the zeroed 0x88-byte structure.
# Preserve instruction evidence rather than trusting decompiler parameter types.
callback_stores=[
    (0x19041,0x19880,0x19048,0x1f8,0x28,'EvtDevicePrepareHardware'),
    (0x19050,0x19990,0x1905f,0x200,0x30,'EvtDeviceReleaseHardware'),
    (0x19067,0x1968c,0x19071,0x1d8,0x08,'EvtDeviceD0Entry'),
    (0x19079,0x197e0,0x19087,0x1e8,0x18,'EvtDeviceD0Exit'),
]
callbacks=[]
for lea_va,target,store_va,stack_offset,field_offset,name in callback_stores:
    lea=next(dis.disasm(pe.get_data(lea_va-base,7),lea_va))
    assert lea.mnemonic=='lea' and lea.operands[1].mem.base==capstone.x86.X86_REG_RIP
    assert lea.address+lea.size+lea.operands[1].mem.disp==target
    store=next(dis.disasm(pe.get_data(store_va-base,8),store_va))
    assert store.mnemonic=='mov' and store.operands[0].mem.base==capstone.x86.X86_REG_RSP
    assert store.operands[0].mem.disp==stack_offset
    assert stack_offset-0x1d0==field_offset
    callbacks.append({'name':name,'function_va':hex(target),'field_offset':hex(field_offset),
                      'registration_assembly':[f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in [lea,store]]})
result={'binary_sha256':digest,'coverage':source['coverage'],
        'bind_info':{'va':'0x16110','component':pe.get_data(component-base,24).decode('utf-16le').split('\0')[0],
                     'major':major,'minor':minor,'build':build,'function_count':count,'function_table_va':hex(table)},
        'header_checks':headers,'matching_index_prefix':count,'callbacks':callbacks,'functions':functions,
        'interpretation':'Four-interface configuration selects settings [0,1,1,0]. D0 entry resets audio pipes, allocates requests, attempts command 0x03 before starting the interrupt reader, conditionally starts that reader and sends command 0x36, then conditionally applies a requested sample rate. Commands use 64-byte interrupt OUT frames, not EP0 vendor requests. This is static recovery, not captured USB traffic or a proven fix for WinUSB startup.'}
(root/'docs/evidence/rane-kernel-startup.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'bind_info':result['bind_info'],'functions':len(functions),'mapped_calls':sum(len(f['mapped_wdf_calls']) for f in functions)}))
