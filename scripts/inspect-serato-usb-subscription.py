"""Verify the USB arrival and state subscription paths in the pinned Serato PE."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import struct

ROOT = Path(__file__).resolve().parents[1]

# The complete PE extents bind each selected instruction to its decoded body.
SPANS = {
    0x1404c65c0: 0x1404c671c,
    0x14070fd70: 0x14070fe59,
    0x141543cf0: 0x14154426c,
    0x141544850: 0x141544a2e,
    0x141544a30: 0x141544c5e,
    0x141545210: 0x14154549d,
    0x141545800: 0x141545ae0,
    0x141546710: 0x141546a7f,
    0x1415477e0: 0x1415479ff,
    0x14154cd50: 0x14154cf87,
    0x14154cf90: 0x14154d1f0,
    0x14213ddc0: 0x14213eeca,
}

FACTS = """
1404c662d call 0x141543cf0
1404c6632 mov rdi, rax
1404c6635 jmp 0x1404c6639
1404c667a mov qword ptr [rip + 0x39e6347], rdi
14070fd92 mov rdx, qword ptr [rip + 0x379cc2f]
14070fd99 lea rcx, [rdi + 0x10]
14070fd9d call 0x14154c960
14070fdd9 mov r9d, 7
14070fddf xor r8d, r8d
14070fde2 mov edx, 0x2d4
14070fde7 lea rcx, [rdi + 0x10]
14070fdeb call 0x14154cd50
14070fdfd mov edx, 0x2d5
14070fe06 call 0x14154cd50
14070fe0f mov r9d, 7
14070fe15 xor r8d, r8d
14070fe18 mov edx, 0x692
14070fe1d lea rcx, [rdi + 0x10]
14070fe21 call 0x14154cf90
14070fe37 mov edx, 0x693
14070fe40 call 0x14154cd50
141543d0e lea rax, [rip + 0x1a0e3c3]
141543d15 mov qword ptr [rcx], rax
14154c960 mov qword ptr [rcx + 8], rdx
14154cdba mov rcx, qword ptr [r8 + 8]
14154cdec call qword ptr [rax + 0x10]
14154ce33 call 0x14154c5a0
14154c730 call qword ptr [rax + 0x10]
14154d00e mov rcx, qword ptr [r8 + 8]
14154d03b call qword ptr [rax + 0x20]
14154d07f call 0x14154c370
14154c4be call qword ptr [rax + 0x20]
1415452c7 call 0x141544850
1415452f9 call 0x141544850
14154488e mov rax, qword ptr [r9 + 0x28]
1415448b0 cmp qword ptr [rax], r8
1415448b5 add rax, 0x10
1415448dd movups xmmword ptr [rdx], xmm0
1415448e0 add qword ptr [rcx + 8], 0x10
141544a13 call 0x140520eb0
140520f7f movups xmmword ptr [r14], xmm0
140520f92 call 0x1405207d0
140520fa2 call 0x1405207d0
140520fe0 mov qword ptr [rsi], rdi
140520ffb mov qword ptr [rsi + 8], rbp
140521004 mov qword ptr [rsi + 0x10], rcx
1415458e7 call 0x141544a30
14154590c call 0x141544a30
141544a80 imul rcx, r8, 0x2b
141544a8c add rcx, r15
141544aa2 call 0x1415438a0
141544ac9 mov qword ptr [rdx], rdi
141544c2c mov dword ptr [rsp + 0x20], r15d
141544c31 mov r9d, r14d
141544c34 mov r8d, ebp
141544c37 mov edx, esi
141544c3d call 0x1415477e0
141547855 mov rdi, qword ptr [rbp + 0xc8]
141547886 cmp dword ptr [rsi], eax
14154788a cmp dword ptr [rsi + 4], r13d
141547890 cmp dword ptr [rsi + 8], r12d
141547896 cmp dword ptr [rsi + 0xc], r15d
1415478a1 mov dword ptr [rsi + 0x30], eax
141547910 mov rcx, qword ptr [rbp + 0xa8]
141547930 cmp dword ptr [rbx + rcx], esi
141547935 cmp dword ptr [rbx + rcx + 4], r13d
14154793c cmp dword ptr [rbx + rcx + 8], r12d
141547943 cmp dword ptr [rbx + rcx + 0xc], r15d
14154794f mov dword ptr [rbx + rcx + 0x30], eax
14213ea99 mov rdi, qword ptr [rip + 0x1d6df28]
14213eabe mov dword ptr [rsp + 0x20], 7
14213eacc mov edx, 0x2d4
14213ead4 call 0x14185ee90
14213eaf8 call qword ptr [rax + 0x58]
141546a44 call 0x141545ae0
"""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect(application):
    helpers = runpy.run_path(str(ROOT/'scripts/export-serato-clock-handshake-evidence.py'))
    app = helpers['Image'](application, helpers['CURRENT_SHA'])
    require = helpers['require']
    ranges = []
    for first, end in SPANS.items():
        require((first, end) in app.spans, 'PE function extent differs: '+hex(first))
        body = app.function(first)
        require(sum(row.size for row in body) == end-first, 'Incomplete decode: '+hex(first))
        ranges.append({'start':hex(first), 'endExclusive':hex(end), 'sha256':sha(app.data(first,end-first))})

    facts = []
    for line in FACTS.strip().splitlines():
        address, mnemonic, operands = line.split(maxsplit=2)
        va = int(address,16)
        if va == 0x14154c960:
            row = next(app.dis.disasm(app.data(va,4),va))
        else:
            row = app.at(va,mnemonic,operands)
        require((row.mnemonic,row.op_str)==(mnemonic,operands),'Instruction differs: '+hex(va))
        facts.append({'va':hex(va), 'bytes':row.bytes.hex(), 'assembly':mnemonic+' '+operands})

    for address in (0x1404c667a,0x14070fd92,0x14213ea99):
        require(app.rip(app.at(address))==0x143eac9c8,'Message system global differs')
    table=0x142f520d8
    require(app.rip(app.at(0x141543d0e))==table,'Message system constructor table differs')
    locator=struct.unpack('<Q',app.data(table-8,8))[0]
    signature,offset,displacement,name,_,self_rva=struct.unpack('<6I',app.data(locator,24))
    require((signature,offset,displacement)==(1,0,0) and app.base+self_rva==locator and
            app.text(app.base+name+16)=='.?AVMessageSystem@system@message@serato@@','Message system RTTI differs')
    slots={0x10:0x141545210,0x20:0x141545800,0x58:0x141546710}
    for slot,target in slots.items():
        require(struct.unpack('<Q',app.data(table+slot,8))[0]==target,'Message system slot differs')

    return {'schema':'sl3.serato-usb-subscription.v1','applicationSha256':app.sha,
            'inspectorSha256':sha(Path(__file__).read_bytes()),
            'messageSystem':{'global':'0x143eac9c8','table':hex(table),'slots':{hex(k):hex(v) for k,v in slots.items()}},
            'arrival':{'message':0x2d4,'route':7,'subscriptionSlot':'0x10','dispatchPublishSlot':'0x58',
                       'entryBytes':16,'stateRefreshCallInCheckedRegistrationPath':False},
            'state':{'message':0x692,'route':7,'subscriptionSlot':'0x20','refreshHelper':'0x1415477e0',
                     'matchingStateRecordMarkOffset':'0x30','actualDeliveryObserved':False},
            'ranges':ranges,'instructionFacts':facts,
            'scope':'Static selected message publication and registration paths. Pending delivery, later publication, and other replay paths remain open.',
            'normalSeratoSelectionVerified':False,'vendorCodeExecuted':False,'installedFilesChanged':False,'deviceAccess':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output and args.output.exists():
        parser.error('Fresh evidence output required')
    result=inspect(args.application.absolute())
    rendered=json.dumps(result,indent=2)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(rendered)
    else:
        print(rendered,end='')
