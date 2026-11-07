"""Verify selected startup callback dispatch paths in the pinned Serato image."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import struct


SCRIPTS = Path(__file__).resolve().parent
FACTS = """
141539715 lea rdi, [rip + 0x1de4]
141539739 mov qword ptr [rbp + 0xf8], r15
14153974c mov byte ptr [rbp + 0x110], 0
141539785 mov qword ptr [rbp + 0x78], r15
141539795 mov byte ptr [rbp + 0x90], 1
1415397ae lea r8, [rbp + 0xf8]
1415397b5 lea rdx, [rbp + 0x78]
1415397c0 call 0x1419669a0
1415397d9 call 0x141538be0
1415397de mov rdi, rax
14153986c xor r8d, 0x81
14153987d shl r9d, cl
141539882 shr r8d, cl
141539885 or r9d, r8d
14153989f cmp r10, 2
1415398a5 mov qword ptr [rsp + 0x20], rdi
1415398aa mov r9d, 4
1415398b0 lea r8, [rbp - 0x68]
1415398b4 lea rdx, [rsp + 0x68]
1415398bc call 0x141960fb0
14153956e mov r9d, 3
141539580 call 0x141960fb0
1415396fe mov r9d, 6
141539710 call 0x141960fb0
141966a31 call 0x141960f80
141966a47 call 0x1419668c0
1419668f2 mov qword ptr [rcx], rdx
1419668f5 lea rbp, [rcx + 8]
14196691a lea rbp, [rbx + 0x48]
14196693c mov byte ptr [rbx + 0x88], 0
14196109b call 0x14197f720
14197f86f mov dword ptr [rbp - 0x10], eax
14197f8f1 call 0x14197f550
14197f8f6 add qword ptr [r13 + 0x18], 0xd8
14197f90b call 0x14197f2b0
14197f5d0 call 0x1404b5a70
14197f5e3 call 0x1404b5a70
14197f6b9 call 0x1421201f0
14197f6c0 jne 0x14197f6de
14197f6c6 cmp r9d, r14d
14197f6c9 jne 0x14197f6de
14197f6cf lea rcx, [rbx + 0x48]
14197f6d6 call 0x141966ab0
14197f6de add rbx, 0xd8
14197fb99 call 0x1421201f0
14197fba0 jne 0x14197fbbb
14197fba2 cmp dword ptr [rbx + 0x40], r14d
14197fba6 jne 0x14197fbbb
14197fbac lea rcx, [rbx + 0x48]
14197fbb3 call 0x141966b00
141966abf call qword ptr [rax + 0x10]
141966ac9 jne 0x141966aec
141966ad1 jne 0x141966aec
141966ad3 mov byte ptr [rbx + 0x88], 1
141966ada mov rcx, qword ptr [rbx + 0x40]
141966ae6 call qword ptr [rax + 0x10]
141966b04 mov byte ptr [rcx + 0x88], 0
141966b0b mov rcx, qword ptr [rcx + 0x80]
141966b1e jmp qword ptr [rax + 0x10]
14153b504 cmp dl, byte ptr [rcx + 0x288]
14153b50a je 0x14153b517
14153b512 call 0x14153b280
1405a5b02 call 0x141960b40
1405a5b18 je 0x1405a6071
1405a5da8 mov ebx, dword ptr [r12 + 0x48]
1405a5dba mov r8d, ebx
1405a5dc3 call 0x141960a00
1405a5eb8 mov ebx, dword ptr [r12 + 0x48]
1405a5eca mov r8d, ebx
1405a5ed3 call 0x141960ae0
1405a6053 add r12, 0x78
141960a39 call 0x14197f650
141960b19 call 0x14197fb30
14198f9a4 cmp r15d, 5
14198f9a8 jne 0x14198fb38
14198fa64 mov r8d, 5
14198fa71 call 0x14197fb30
14198fb0c mov r8d, r15d
14198fb16 call 0x14197f650
14153b294 cmp byte ptr [rcx + 0x288], sil
14153b29d cmp byte ptr [rcx + 0x289], sil
14153b2ab mov dil, 1
14153b2dc call 0x141960f80
14153b2e4 mov rdx, qword ptr [rcx + 0x98]
14153b2ee call rdx
14153b2f0 test dil, dil
14153b2f3 je 0x14153b36a
14153b2f5 test rax, rax
14153b2f8 jne 0x14153b427
14153b317 je 0x14153b33e
14153b32f mov edx, 0x5d4
14153b337 call 0x14185ec00
14153b356 call qword ptr [rax + 0x58]
14153b369 ret
14153b36a test rax, rax
14153b36d jne 0x14153b3cb
14153b388 je 0x14153b3af
14153b3a0 mov edx, 0x2cb
14153b3a8 call 0x14185ee90
14153b3c7 call qword ptr [rax + 0x58]
14153b3e4 je 0x14153b40b
14153b3fc mov edx, 0x5d4
14153b404 call 0x14185ec00
14153b423 call qword ptr [rax + 0x58]
141988396 mov r8, qword ptr [rcx + 0x48]
14198839d test r8, r8
1419883a0 je 0x1419883c8
1419883b0 call 0x1405e5190
1419883b5 cmp rax, qword ptr [rbx + 0xa8]
1419883bc je 0x1419883c8
1419883be mov rax, qword ptr [rbx + 0x48]
1419883c8 xor eax, eax
141981ba3 xor eax, eax
"""


def updater_messages(app, require, combined_state, override_present):
    rows = {row.address: row for row in app.function(0x14153b280)}
    branches = {
        0x14153b2f3: not combined_state,
        0x14153b2f8: override_present,
        0x14153b36d: override_present,
        0x14153b317: False,  # Normal allocation and call return.
        0x14153b388: False,
        0x14153b3e4: False,
    }
    publications = {0x14153b356:'0x5d4', 0x14153b3c7:'0x2cb', 0x14153b423:'0x5d4'}
    messages = []
    address = 0x14153b2f0
    for _ in range(len(rows)):
        require(address in rows, 'Updater path left its reviewed instruction extent')
        row = rows[address]
        if address in publications:
            messages.append(publications[address])
        if row.mnemonic == 'ret':
            return messages
        next_address = address + row.size
        if row.mnemonic == 'jmp':
            next_address = int(row.op_str, 16)
        elif row.mnemonic.startswith('j'):
            require(address in branches, 'Unexpected condition on updater publication path')
            if branches[address]:
                next_address = int(row.op_str, 16)
        address = next_address
    raise ValueError('Updater publication path did not return')


def inspect(path):
    helpers = runpy.run_path(str(SCRIPTS/'export-serato-clock-handshake-evidence.py'))
    app = helpers['Image'](path, helpers['CURRENT_SHA'])
    require = helpers['require']
    checked = []
    for line in FACTS.strip().splitlines():
        address, instruction = line.split(maxsplit=1)
        mnemonic, _, operands = instruction.partition(' ')
        row = app.at(int(address,16), mnemonic, operands)
        checked.append({'va':hex(row.address), 'bytes':row.bytes.hex()})
    require(app.rip(app.at(0x141539715))==0x14153b500, 'Callback target differs')
    callback_table = app.rip(app.at(0x1415391b4,'lea'))
    require(callback_table==0x142f51930 and
            struct.unpack('<Q',app.data(callback_table+0x10,8))[0]==0x140697220,
            'Callback invoker differs')
    require(app.data(0x140697220,22).hex()=='488bd14863491048034a20488b42080fb6521848ffe0',
            'Callback invocation thunk differs')
    writes = [row.address for row in app.function(0x1415397de) if 0x1415397de<=row.address<=0x1415398bc and
              {'rdi','edi','di','dil'}.intersection(map(row.reg_name,row.regs_access()[1]))]
    require(writes==[0x1415397de], 'Callback argument changed before registration')
    encoded = app.data(app.rip(app.at(0x141539818,'lea')),2)
    decoded = [byte ^ 0x81 for byte in encoded]
    product = bytes(((byte >> index) | (byte << (8 - index))) & 255 for index,byte in enumerate(decoded))
    require(product==b'dj' and app.data(app.rip(app.at(0x141539800,'mov')),4)==b'1.1\0',
            'Callback registration identity differs')
    publishers = runpy.run_path(str(SCRIPTS/'inspect-serato-primary-publishers.py'))
    refresh = 0x1405a5aa0
    callers = publishers['direct_calls'](app, (refresh,))[refresh]
    require(callers==[0x1405a239e,0x1405a2460,0x1405a2497,0x1405a25cc,0x1405a37e2],
            'Direct refresh call inventory differs')
    rlm_table = 0x142fd12b8
    locator, = struct.unpack('<Q',app.data(rlm_table-8,8))
    signature, offset, displacement, name, _, self_rva = struct.unpack('<6I',app.data(locator,24))
    require((signature,offset,displacement)==(1,0,0) and app.base+self_rva==locator and
            app.text(app.base+name+16)=='.?AVRLMAuthorization@authorization@serato@@' and
            struct.unpack('<Q',app.data(rlm_table+0xa8,8))[0]==0x14198f940,
            'RLM dispatch receiver differs')
    jwt_table = 0x142fd09c8
    locator, = struct.unpack('<Q',app.data(jwt_table-8,8))
    signature, offset, displacement, name, _, self_rva = struct.unpack('<6I',app.data(locator,24))
    require((signature,offset,displacement)==(1,0,0) and app.base+self_rva==locator and
            app.text(app.base+name+16)=='.?AVJWTAuthorization@authorization@serato@@' and
            struct.unpack('<Q',app.data(rlm_table+0x98,8))[0]==0x141988390 and
            struct.unpack('<Q',app.data(jwt_table+0x98,8))[0]==0x141981b30,
            'Startup updater service slots differ')
    return {'schema':'sl3.serato-startup-callbacks.v1','applicationSha256':app.sha,
            'inspectorSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'registration':{'callbackConstructor':'0x1419669a0','storage':'0x14197f720',
                            'recordBytes':216,'product':'dj','version':'1.1','category':4,
                            'adjacentRequestCategories':[3,6],
                            'callbackSetter':'0x14153b500','stateUpdater':'0x14153b280'},
            'dispatch':{'matchesProductAndCategory':True,
                        'checkedSet':'0x14197f650','checkedClear':'0x14197fb30',
                        'setRequiresServiceResultZeroAndClearState':True,
                        'refresh':'0x1405a5aa0','directRefreshCalls':[hex(a) for a in callers],
                        'rlmCheckedMethodSlot':'0xa8','rlmCheckedMethodCategory':5,
                        'rlmCheckedMethodMatchesRegistrationCategory':False},
            'updaterPublication':{
                'backendSlot':'0x98','rlmMethod':'0x141988390','jwtMethod':'0x141981b30',
                'jwtNormalReturnIsNull':True,'rlmMethodCanReturnNullOrStoredPointer':True,
                'onNormalAllocationAndCallReturn':[
                    {'combinedState':state, 'overridePointerPresent':override,
                     'messages':updater_messages(app, require, state, override)}
                    for state in (False, True) for override in (False, True)],
                'checkedDelivery':False},
            'checkedInstructions':checked,'liveCallbackInvocationObserved':False,
            'vendorCodeExecuted':False,'installedFilesChanged':False,'deviceAccess':False}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.application.absolute()),indent=2))
