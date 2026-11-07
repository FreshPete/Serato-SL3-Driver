"""Verify USB arrival publication, dispatch and subscription in the pinned Serato PE."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import struct

ROOT = Path(__file__).resolve().parents[1]

# The complete PE extents bind each selected instruction to its decoded body.
SPANS = {
    0x1404c0000: 0x1404c3966,
    0x1404c4300: 0x1404c437c,
    0x1404c65c0: 0x1404c671c,
    0x140520efe: 0x140521018,
    0x140530500: 0x14053078b,
    0x14070fd70: 0x14070fe59,
    0x140710720: 0x14071089b,
    0x1407108a0: 0x1407108dd,
    0x141373a40: 0x141373c0d,
    0x141543cf0: 0x14154426c,
    0x141544850: 0x141544a2e,
    0x141544a30: 0x141544c5e,
    0x141545210: 0x14154549d,
    0x141545800: 0x141545ae0,
    0x141545ae0: 0x141545c11,
    0x141546370: 0x141546703,
    0x141546710: 0x141546a7f,
    0x1415477e0: 0x1415479ff,
    0x14154c370: 0x14154c59f,
    0x14154c5a0: 0x14154c872,
    0x14154cd50: 0x14154cf87,
    0x14154cf90: 0x14154d1f0,
    0x14185ec90: 0x14185ecdf,
    0x14185ee90: 0x14185eee3,
    0x14213ddc0: 0x14213eeca,
}

# These leaf bodies have no PE unwind entry.
LEAF_SPANS = {
    0x140625870: 0x1406258db,
    0x140ff9740: 0x140ff9747,
    0x14154c960: 0x14154c964,
}

FACTS = """
1404c3367 mov rcx, qword ptr [rip + 0x39e965a]
1404c336e call 0x141546370
1404c4318 mov rcx, qword ptr [rip + 0x39e86a9]
1404c431f call 0x141546370
1404c662d call 0x141543cf0
1404c6632 mov rdi, rax
1404c6635 jmp 0x1404c6639
1404c667a mov qword ptr [rip + 0x39e6347], rdi
141373a5a mov r8d, dword ptr [rdx + 0xc]
141373a5e sub r8d, 0x2ca
141373a65 je 0x141373bce
141373a6b sub r8d, 1
141373a6f je 0x141373afa
141373a75 cmp r8d, 0x309
141373a7c jne 0x141373bf8
141373a82 mov rcx, qword ptr [rip + 0x2b38f2f]
141373a89 call 0x140530500
141373a8e lea rcx, [rsp + 0x40]
141373a93 call 0x140710720
141373a99 mov rcx, qword ptr [rax]
141373a9c call 0x1407108a0
140530595 mov edx, 0x2d0
14053059d call 0x14185ec00
1405305ef mov edx, 0x645
1405305f7 call 0x14185ec00
140530617 lea rcx, [rsi + 0x1c2]
140530627 test cl, cl
140530629 jne 0x140530643
14053062b lea rcx, [rsi + 0x1c3]
14053063b test cl, cl
14053063d je 0x14053071c
140530643 mov rdi, qword ptr [rsi + 0x1c8]
14053064a mov r15, qword ptr [rsi + 0x1d0]
140530682 call 0x140502ae0
140530689 jne 0x1405306db
1405306ac call 0x14052c650
1405306b3 jne 0x1405306db
1405306d5 call 0x140525710
14053070f add rdi, 0x10
140530716 jne 0x140530660
14071073e cmp qword ptr [rip + 0x37bef53], rdi
140710745 jne 0x14071085d
140710762 call 0x14070fd70
1407108a6 mov rbx, rcx
1407108a9 call 0x141960f80
1407108ae mov rcx, rax
1407108b1 mov rdx, qword ptr [rax]
1407108b4 call qword ptr [rdx + 0x98]
1407108ba test rax, rax
1407108bd je 0x1407108d7
1407108bf mov edx, 0x13e5
1407108c4 mov rcx, rbx
1407108c7 mov r9d, edx
1407108ca mov r8d, edx
1407108d2 jmp 0x14070ff10
1407108dc ret
14070fd92 mov rdx, qword ptr [rip + 0x379cc2f]
14070fd99 lea rcx, [rdi + 0x10]
14070fd9d call 0x14154c960
14070fdad lea rax, [rip + 0x21333b4]
14070fdb4 mov qword ptr [rdi + 0x10], rax
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
141544874 mov rax, qword ptr [r9 + 8]
14154487b imul rcx, qword ptr [r9 + 0x20]
141544880 mov r8, qword ptr [rax + rbp*8]
141544884 add r8, rcx
141544887 add r8, rsi
14154488a lea rcx, [r8 + r8*2]
14154488e mov rax, qword ptr [r9 + 0x28]
141544892 lea rcx, [rax + rcx*8]
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
14185ee9e mov r10d, r9d
14185eea1 mov r9d, dword ptr [rsp + 0x60]
14185eead mov r8d, r10d
14185eebb call 0x14185ec90
14185ecc2 mov dword ptr [rcx + 0xc], edx
14185ecc5 mov dword ptr [rcx + 0x10], r8d
14185ecc9 mov dword ptr [rcx + 0x14], r9d
14213ea99 mov rdi, qword ptr [rip + 0x1d6df28]
14213eabe mov dword ptr [rsp + 0x20], 7
14213eac6 xor r9d, r9d
14213eacc mov edx, 0x2d4
14213ead4 call 0x14185ee90
14213eaf8 call qword ptr [rax + 0x58]
1415469bf je 0x141546a4a
1415469d5 call qword ptr [rax + 0x18]
1415469d8 sub eax, 1
1415469db je 0x1415469e4
1415469dd cmp eax, 1
1415469e0 jne 0x141546a38
1415469e2 jmp 0x141546a4a
141546a19 call 0x14185ec00
141546a26 mov qword ptr [rdi], rax
141546a38 mov rdx, qword ptr [rdi]
141546a44 call 0x141545ae0
141545b25 mov qword ptr [rsp + 0x30], rbp
141545b2f add rdi, 0x158
141545ba0 movups xmm0, xmmword ptr [rsp + 0x30]
141545ba5 movups xmmword ptr [rcx], xmm0
141545ba8 inc qword ptr [rdi + 0x20]
1415463e9 lea rcx, [r14 + 0x158]
1415463f0 lea rdx, [rbp + 7]
1415463f4 call 0x140625870
1406258d2 mov qword ptr [r9 + 0x20], rax
1406258d6 mov qword ptr [rdx + 0x20], rcx
141546429 mov r8, qword ptr [rbp + 0x27]
14154645a movups xmm0, xmmword ptr [rcx]
141546465 mov qword ptr [rbp + 0x27], rax
14154647f movq r13, xmm0
141546484 mov eax, dword ptr [r13 + 0xc]
141546488 mov dword ptr [r14 + 0x1f0], eax
141546531 movsxd rdx, dword ptr [r13 + 0x14]
141546535 mov rax, qword ptr [r14 + 8]
141546539 movsxd rcx, dword ptr [r14 + 0x1f0]
141546540 imul rcx, qword ptr [r14 + 0x20]
141546545 mov r8, qword ptr [rax + rdx*8]
141546549 add r8, rcx
14154654c movsxd rax, dword ptr [r13 + 0x10]
141546550 add r8, rax
141546553 lea rcx, [r8 + r8*2]
141546557 mov rax, qword ptr [r14 + 0x28]
14154655b lea r12, [rax + rcx*8]
1415465b1 mov rdi, qword ptr [r12 + 8]
1415465b6 mov rbx, qword ptr [r12]
1415465c3 call 0x1405207d0
141546622 mov rcx, qword ptr [rbx]
141546625 mov rax, qword ptr [rcx]
141546628 mov rdx, r13
14154662b call qword ptr [rax + 8]
14154662e add rbx, 0x10
141546643 call qword ptr [rax]
140ff9740 mov rax, qword ptr [rcx]
140ff9743 jmp qword ptr [rax + 0x18]
"""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect(application):
    helpers = runpy.run_path(str(ROOT/'scripts/export-serato-clock-handshake-evidence.py'))
    app = helpers['Image'](application, helpers['CURRENT_SHA'])
    require = helpers['require']
    ranges = []
    decoded = {}
    for first, end in sorted((SPANS | LEAF_SPANS).items()):
        if first in LEAF_SPANS:
            body = list(app.dis.disasm(app.data(first,end-first),first))
        else:
            require((first, end) in app.spans, 'PE function extent differs: '+hex(first))
            body = app.function(first)
        require(sum(row.size for row in body) == end-first, 'Incomplete decode: '+hex(first))
        decoded.update((row.address,row) for row in body)
        ranges.append({'start':hex(first), 'endExclusive':hex(end), 'sha256':sha(app.data(first,end-first)),
                       'peUnwindExtent':first in SPANS})

    facts = []
    for line in FACTS.strip().splitlines():
        address, mnemonic, *parts = line.split(maxsplit=2)
        operands = parts[0] if parts else ''
        va = int(address,16)
        row = decoded.get(va)
        require(row is not None and (row.mnemonic,row.op_str)==(mnemonic,operands),
                'Instruction differs: '+hex(va))
        facts.append({'va':hex(va), 'bytes':row.bytes.hex(), 'assembly':' '.join((mnemonic,*parts))})

    for address in (0x1404c3367,0x1404c4318,0x1404c667a,0x14070fd92,0x14213ea99):
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
    listener_table=0x142843168
    require(app.rip(app.at(0x14070fdad))==listener_table,'USB manager listener table differs')
    listener_slots={0x08:0x140ff9740,0x18:0x1407108e0}
    for slot,target in listener_slots.items():
        require(struct.unpack('<Q',app.data(listener_table+slot,8))[0]==target,'USB manager listener slot differs')
    engine_table=0x142f29b28
    require(struct.unpack('<Q',app.data(engine_table+0x18,8))[0]==0x141373a40,'Engine handler slot differs')
    steps=[row.op_str for row in app.function(0x141373a40) if
           0x141373a82<=row.address<=0x141373a9c and row.mnemonic=='call']
    require(steps==['0x140530500','0x140710720','0x1407108a0'],'Engine startup call order differs')

    return {'schema':'sl3.serato-usb-subscription.v2','applicationSha256':app.sha,
            'inspectorSha256':sha(Path(__file__).read_bytes()),
            'messageSystem':{'global':'0x143eac9c8','table':hex(table),'slots':{hex(k):hex(v) for k,v in slots.items()}},
            'engineStartup':{'message':0x5d4,'handler':'0x141373a40','callOrder':steps,
                             'existingMidiSelection':{'requiresEitherManagerByte':['0x1c2','0x1c3'],
                                                      'selectionCallback':'0x140525710'},
                             'postConstructionUsbHelper':{'authorizationSlot':'0x98','requiresNonNullResult':True,
                                 'identityArguments':[0x13e5]*3,'usesMessageDeviceIdentity':False,
                                 'stateHelper':'0x14070ff10'}},
            'arrival':{'message':0x2d4,'route':7,'subscriptionSlot':'0x10','dispatchPublishSlot':'0x58',
                       'entryBytes':16,'stateRefreshCallInCheckedRegistrationPath':False},
            'state':{'message':0x692,'route':7,'subscriptionSlot':'0x20','refreshHelper':'0x1415477e0',
                     'matchingStateRecordMarkOffset':'0x30','actualDeliveryObserved':False},
            'dispatch':{'queueOffset':'0x158','enqueue':'0x141545ae0','drain':'0x141546370',
                        'matchingKey':{'message':0x2d4,'address':0,'route':7},
                        'listenerTableOffset':'0x28','listenerLookupAtDrain':True,
                        'managerListenerTable':hex(listener_table),
                        'managerListenerSlots':{hex(k):hex(v) for k,v in listener_slots.items()},
                        'actualEnqueueOrDeliveryObserved':False},
            'ranges':ranges,'instructionFacts':facts,
            'scope':'Selected static publish, enqueue, drain and registration paths. Actual publish-filter outcome, registration order, delivery and other replay paths remain open.',
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
