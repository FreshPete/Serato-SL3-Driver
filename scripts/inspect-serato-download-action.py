"""Identify the original popup callback and prepare a passive, unexecuted observer."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import runpy
import struct

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'scripts/serato-sl3-action-observer.js'


def inspect(application,output=None):
    api=runpy.run_path(str(ROOT/'scripts/export-serato-clock-handshake-evidence.py'))
    image=api['Image'](application,api['CURRENT_SHA']);require=api['require']
    source=SOURCE.read_bytes();match=re.search(r'const points = (\[[\s\S]*?\n  \]);',source.decode('utf-8'))
    require(match is not None,'Literal observer entry inventory required')
    points=ast.literal_eval(match.group(1))
    require([(name,rva) for name,rva,_ in points]==[
        ('popup',0x137df40),('button',0xf25270),('message',0x137b790),('arrival',0x185ee90)],'Observer entry scope differs')
    for name,rva,expected in points:
        require(re.fullmatch('[0-9a-f]{16}',expected) is not None and image.data(image.base+rva,8)==bytes.fromhex(expected),
                'Observer entry differs: '+name)
    table=0x142f2bdb8;locator=struct.unpack('<Q',image.data(table-8,8))[0]
    signature,offset,displacement,type_rva,_,self_rva=struct.unpack('<6I',image.data(locator,24))
    require(signature==1 and offset==0 and displacement==0 and image.base+self_rva==locator,'Callback RTTI locator differs')
    name=image.data(image.base+type_rva+16,512).split(b'\0',1)[0].decode('ascii')
    expected_name='.?AV?$_Func_impl_no_alloc@V<lambda_1>@?1??ShowDriverPopup@DeviceNotificationController@dj@serato@@AEAAXV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@_N10@Z@X$$V@std@@'
    require(name==expected_name,'Exact driver popup callback RTTI required')
    require(struct.unpack('<3Q',image.data(table,24))==(0x141380120,0x141380120,0x141380170),'Callback copy/move/invoke slots differ')
    facts=[]
    for address,operation,operands in [
        (0x14137df7d,'mov','rbx, rcx'),(0x14137df80,'mov','qword ptr [rsp + 0x40], rcx'),
        (0x14137e610,'lea','rax, [rip + 0x1bad7a1]'),(0x14137e617,'mov','qword ptr [rsp + 0x60], rax'),
        (0x14137e61c,'mov','rax, qword ptr [rsp + 0x40]'),(0x14137e621,'mov','qword ptr [rsp + 0x68], rax'),
        (0x14137e648,'lea','r8, [rsp + 0x60]'),(0x14137e654,'call','0x140f25270'),
        (0x14138017c,'mov','rax, qword ptr [rcx + 8]'),(0x141380180,'mov','rbx, qword ptr [rax + 0x40]'),
        (0x1413801a7,'mov','edx, 0x4ff'),(0x1413801b5,'call','0x14185ec00'),
        (0x1413801d4,'call','qword ptr [rax + 0x58]'),
        (0x14137b7c5,'mov','rsi, rcx'),(0x14137bcb2,'mov','rcx, rsi'),(0x14137bcb5,'call','0x14137df40')]:
        row=image.at(address,operation,operands)
        facts.append({'va':hex(address),'bytes':bytes(row.bytes).hex(),'instruction':row.mnemonic+' '+row.op_str})
    require(image.rip(image.at(0x14137e610))==table,'Popup constructs a different callback table')
    copy_bytes=bytes.fromhex('488d0591bcba01488902488b410848894208488bc2c3')
    require(image.data(0x141380120,len(copy_bytes))==copy_bytes,'Unwind-free callback copy leaf differs')
    ranges={}
    for start in (0x14137df40,0x141380170,0x14137b790):
        _,end=next(span for span in image.spans if span[0]==start)
        # This handler's PE extent includes its two-level jump table. Decode
        # the checked code prefix; retain/hash the data rather than calling it code.
        code_end=0x14137c8a0 if start==0x14137b790 else end
        rows=list(image.dis.disasm(image.data(start,code_end-start),start))
        require(rows[0].address==start and rows[-1].address+rows[-1].size==code_end and
                sum(row.size for row in rows)==code_end-start,'Incomplete code-range decoding')
        ranges[hex(start)]={'endExclusive':hex(end),'codeEndExclusive':hex(code_end),
            'embeddedDataBytes':end-code_end,'sha256':hashlib.sha256(image.data(start,end-start)).hexdigest()}
    result={'schema':'sl3.serato-download-action.v1','applicationSha256':image.sha,
        'callbackRtti':name,'callbackTableRva':hex(table-image.base),'invokeSlot':16,'captureOffset':8,
        'capturedValue':'ShowDriverPopup receiver; shallow raw-pointer copy, not a demonstrated lifetime lease',
        'copyLeafSha256':hashlib.sha256(copy_bytes).hexdigest(),'functionRanges':ranges,'instructions':facts,
        'observerSourceSha256':hashlib.sha256(source).hexdigest(),
        'inspectorSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'imageReaderSourceSha256':hashlib.sha256((ROOT/'scripts/export-serato-clock-handshake-evidence.py').read_bytes()).hexdigest(),
        'guardedEntries':points,
        'prepared':False,'observerExecuted':False,'vendorCodeExecuted':False,'invokesCallbacks':False,
        'processAttached':False,'applicationModified':False,'physicalDeviceAccess':False,'liveValidated':False}
    if output is not None:
        output=Path(output).absolute()
        require(output.parent.resolve()==(ROOT/'analysis').resolve() and output.name.startswith('sl3-action-observer-') and
                not output.exists() and not output.is_symlink(),'Fresh analysis/sl3-action-observer-* output required')
        output.mkdir()
        (output/'action-observer.js').write_bytes(source)
        result['prepared']=True
        (output/'preparation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application',type=Path,required=True)
    parser.add_argument('--prepare',type=Path)
    args=parser.parse_args();print(json.dumps(inspect(args.application.absolute(),args.prepare),indent=2))
