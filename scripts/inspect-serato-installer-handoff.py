"""Verify click/helper origins and the original installer-completion handoff offline."""
import argparse
import hashlib
from pathlib import Path
import json
import runpy
import struct

ROOT=Path(__file__).resolve().parents[1]
APP_SHA='66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265'


def inspect(application):
    reader=runpy.run_path(str(ROOT/'scripts/export-serato-clock-handshake-evidence.py'))
    image=reader['Image'](application,APP_SHA)
    require=reader['require'];facts=[];ranges={}
    groups={
        'genericMessageHelper':[
            (0x14154b4cc,'mov','ebx, r9d'),(0x14154b4cf,'mov','r14d, r8d'),
            (0x14154b4d2,'mov','r15d, edx'),(0x14154b4db,'cmp','r9d, -1'),
            (0x14154b4df,'jne','0x14154b56f'),
            (0x14154b548,'mov','edx, r15d'),(0x14154b54e,'call','0x14185ec00'),
            (0x14154b56b,'jl','0x14154b520'),
            (0x14154b5aa,'mov','edx, r15d'),(0x14154b5b0,'call','0x14185ec00'),
            (0x14154b5b5,'jmp','0x14154b5ba'),(0x14154b5cc,'call','0x14154b860')],
        'clickPublisher':[
            (0x1413801a7,'mov','edx, 0x4ff'),(0x1413801ac,'mov','r8d, 1'),
            (0x1413801b5,'call','0x14185ec00'),(0x1413801ba,'jmp','0x1413801bf'),
            (0x1413801d4,'call','qword ptr [rax + 0x58]')],
        'installerCompletion':[
            (0x1405b0ac7,'mov','byte ptr [rbp + 0x118], 0'),
            (0x1405b0ae6,'call','0x142120260'),(0x1405b0aeb,'mov','rbx, rax'),(0x1405b0aee,'test','rax, rax'),
            (0x1405b0af1,'je','0x1405b0c90'),
            (0x1405b0b22,'call','qword ptr [rax + 0x48]'),(0x1405b0b25,'test','al, al'),
            (0x1405b0b27,'je','0x1405b0c4e'),
            (0x1405b0b3f,'call','qword ptr [rax + 0x18]'),(0x1405b0b42,'mov','r15d, 0xffff'),
            (0x1405b0b48,'cmp','ax, r15w'),(0x1405b0b4c,'jne','0x1405b0bd8'),
            (0x1405b0b64,'call','qword ptr [rax + 0x20]'),(0x1405b0b67,'cmp','ax, r15w'),
            (0x1405b0b6b,'jne','0x1405b0bd8'),(0x1405b0b9c,'mov','edx, 0x68b'),
            (0x1405b0c0a,'mov','edx, 0x51'),(0x1405b0c16,'call','0x1404db170'),
            (0x1405b0c1b,'cmp','byte ptr [rbx + 0x522], 0'),(0x1405b0c22,'je','0x1405b0c4e'),
            (0x1405b0c2e,'mov','dword ptr [rsp + 0x20], 7'),
            (0x1405b0c39,'mov','r8, rbx'),(0x1405b0c3c,'mov','edx, 0x2ca'),
            (0x1405b0c48,'call','0x1404db170')],
        'installedDriverNotice':[
            (0x14213f77c,'mov','dword ptr [rsp + 0x20], ebp'),
            (0x14213f786,'mov','edx, 0x52'),(0x14213f78e,'call','0x14185ee90'),
            (0x14213f7ad,'call','qword ptr [rax + 0x58]')],
        'noticeDispatch':[
            (0x14137b7cb,'mov','ecx, dword ptr [rdx + 0xc]'),(0x14137b7e0,'dec','ecx'),
            (0x14137b7f5,'movzx','eax, byte ptr [rdx + rax + 0x137c8d4]'),
            (0x14137b7fd,'mov','ecx, dword ptr [rdx + rax*4 + 0x137c8a0]'),
            (0x14137b807,'jmp','rcx'),
            (0x14137bde1,'call','0x141380440'),(0x14137bde7,'lea','rdi, [rsi + 0xb0]'),
            (0x14137bec5,'call','0x14137b670'),(0x14137bf2d,'call','0x14137b450'),
            (0x14137bf32,'cmp','byte ptr [rax + 8], 0'),(0x14137bf36,'je','0x14137beb1'),
            (0x14137bf78,'jmp','0x14137c870'),
            (0x14137bfb6,'call','0x141380440'),(0x14137bfbb,'mov','rdx, rax'),
            (0x14137bfbe,'mov','rcx, rsi'),(0x14137bfc1,'call','0x14137b670'),
            (0x14137bfc6,'jmp','0x14137c870')],
        'keyedNoticeHelper':[
            (0x14137b6a1,'add','rcx, 0xb0'),(0x14137b6a8,'call','0x1404a2730'),
            (0x14137b6b6,'jne','0x14137b726'),(0x14137b6cd,'jne','0x14137b726'),
            (0x14137b6e5,'call','0x140f1fa40'),(0x14137b6ed,'je','0x14137b6f8'),
            (0x14137b6f5,'call','qword ptr [rdx + 0x40]'),
            (0x14137b707,'call','0x1405f4970'),(0x14137b720,'call','0x141380260')],
    }
    expected_ranges={'genericMessageHelper':(0x14154b4b0,0x14154b5f0),
                     'clickPublisher':(0x141380170,0x1413801e3),
                     'installerCompletion':(0x1405b0a40,0x1405b0ca4),
                     'installedDriverNotice':(0x14213f740,0x14213f7f3),
                     'noticeDispatch':(0x14137b790,0x14137c928),
                     'keyedNoticeHelper':(0x14137b670,0x14137b74d)}
    for group,entries in groups.items():
        start,end=expected_ranges[group]
        require((start,end) in image.spans,'Expected function boundary differs: '+group)
        code_end=0x14137c8a0 if group=='noticeDispatch' else end
        decoded=[row for row in image.function(start) if row.address<code_end]
        require(sum(row.size for row in decoded)==code_end-start,'Incomplete code decoding: '+group)
        ranges[group]={'start':hex(start),'endExclusive':hex(end),
                       'sha256':hashlib.sha256(image.data(start,end-start)).hexdigest()}
        if code_end!=end:
            ranges[group]['codeEndExclusive']=hex(code_end)
        for address,operation,operands in entries:
            row=image.at(address,operation,operands)
            facts.append({'group':group,'va':hex(address),'bytes':bytes(row.bytes).hex(),
                          'instruction':row.mnemonic+' '+row.op_str})
    table_base=image.rip(image.at(0x14137b7ee,'lea'))
    require(table_base==image.base,'Notice dispatch table base differs')
    for message,index,target in ((0x51,8,0x14137bfaf),(0x52,9,0x14137bdd9)):
        require(image.data(table_base+0x137c8d4+message-1,1)[0]==index and
                table_base+struct.unpack('<I',image.data(table_base+0x137c8a0+4*index,4))[0]==target,
                f'Notice dispatch table differs for {message:#x}')
    require({image.rip(image.at(address,'mov')) for address in (0x1405b0c0f,0x1405b0c41,0x14213f756)}
            == {0x143eac9c8},'The notice and selection publishers use different message systems')
    return {'schema':'sl3.serato-installer-handoff.v1','applicationSha256':image.sha,
        'functionRanges':ranges,'instructions':facts,
        'helperOrigin':'0x154b5b5 is a return within a generic message helper, not unique evidence of a startup action',
        'clickOrigin':'0x13801ba follows the fixed 0x4ff click-message construction',
        'noticeHandoff':{'messageSystemGlobal':'0x143eac9c8','keyedNoticeHelper':'0x14137b670',
            'keyedCollectionOffset':'0xb0',
            'installerMessage':{'id':0x51,'dispatchIndex':8,'case':'0x14137bfaf','callsHelperDirectly':True},
            'installedDriverMessage':{'id':0x52,'dispatchIndex':9,'case':'0x14137bdd9',
                'canSkipHelperWhenKeyedByteNonzero':True},
            'separatePrimaryPublication':True},
        'primaryPublication':{'message':0x2ca,'descriptorArgumentRegister':'r8',
            'requiresNonNullCast':True,'requiresDriverPredicateSlot':'0x48',
            'requiresNonSentinelIdentityPath':True,'requiresDescriptorByteNonZero':'0x522',
            'stackArgument':7},
        'scope':'Selected original instruction and branch guards; no full call graph or runtime object/lifetime claim',
        'automaticStartImplemented':False,'vendorCodeExecuted':False,'applicationModified':False,
        'registryWritten':False,'physicalDeviceAccess':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=inspect(args.application.absolute())
    if args.output:
        with args.output.open('x',encoding='utf-8',newline='\n') as stream:
            json.dump(result,stream,indent=2)
            stream.write('\n')
    print(json.dumps(result,indent=2))
