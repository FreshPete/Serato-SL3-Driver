"""Verify the USB-arrival identity and passive observation boundaries in Serato 5.0."""

import argparse
import json
from pathlib import Path
import runpy
import struct


ROOT = Path(__file__).resolve().parents[1]
FACTS = {
    0x14213ddf8:'mov r12, rdx',0x14213de06:'xor r14d, r14d',
    0x14213de92:'mov dword ptr [rsp + 0x40], r14d',0x14213de97:'mov dword ptr [rsp + 0x44], r14d',
    0x14213de9c:'mov rcx, qword ptr [r12]',0x14213dea0:'call 0x140c00aa0',
    0x14213deb3:'mov rcx, qword ptr [r12]',0x14213deb9:'je 0x14213e292',
    0x14213debf:'lea rdx, [rsp + 0x68]',0x14213dec4:'call 0x140c00570',
    0x140c0058a:'mov rax, qword ptr [rcx + 0x30]',0x140c0058e:'mov qword ptr [rdx], rax',
    0x140c00591:'mov rax, qword ptr [rcx + 0x38]',0x140c00595:'mov qword ptr [rdx + 8], rax',
    0x14213dfbf:'mov rdx, qword ptr [rsp + 0x68]',0x14213dfc4:'mov rax, qword ptr [rdx + 8]',
    0x14213dfc8:'movsxd rcx, dword ptr [rax + 4]',0x14213dfcc:'add rdx, 8',0x14213dfd0:'add rcx, rdx',
    0x14213dfd6:'call qword ptr [rax + 0x18]',0x14213dfd9:'movzx eax, ax',
    0x14213dfdc:'mov dword ptr [rsp + 0x40], eax',
    0x14213dff7:'call qword ptr [rax + 0x20]',0x14213dffa:'movzx eax, ax',
    0x14213dffd:'mov dword ptr [rsp + 0x44], eax',
    0x14213e018:'call qword ptr [rax + 0x28]',0x14213e01b:'movzx edi, ax',
    0x14213e289:'mov qword ptr [rbp - 0x68], rdi',0x14213e28d:'jmp 0x14213e3e7',
    0x14213e292:'mov qword ptr [rbp - 0x68], r14',
    0x14213ea74:'mov r14d, dword ptr [rsp + 0x44]',0x14213ea84:'shl ecx, 0x10',
    0x14213ea87:'mov ebx, dword ptr [rsp + 0x40]',0x14213ea8b:'shl rbx, 0x20',
    0x14213ea8f:'mov rax, qword ptr [rbp - 0x68]',0x14213ea93:'add rax, rcx',0x14213ea96:'add rbx, rax',
    0x14213eabe:'mov dword ptr [rsp + 0x20], 7',0x14213eac6:'xor r9d, r9d',
    0x14213eac9:'mov r8, rbx',0x14213eacc:'mov edx, 0x2d4',0x14213ead4:'call 0x14185ee90',
    0x14185eea6:'mov rbx, r8',0x14185eec7:'mov qword ptr [rdi + 0x38], rbx',
    0x14185ecc2:'mov dword ptr [rcx + 0xc], edx',0x14185ecc9:'mov dword ptr [rcx + 0x14], r9d',
    0x14213eaf8:'call qword ptr [rax + 0x58]',0x141546731:'mov rdi, rdx',
    0x1415469bf:'je 0x141546a4a',0x1415469d2:'mov rdx, qword ptr [rdi]',
    0x1415469d5:'call qword ptr [rax + 0x18]',0x1415469d8:'sub eax, 1',
    0x1415469db:'je 0x1415469e4',0x1415469dd:'cmp eax, 1',
    0x1415469e0:'jne 0x141546a38',0x1415469e2:'jmp 0x141546a4a',
    0x141546a14:'xor edx, edx',0x141546a19:'call 0x14185ec00',
    0x141546a26:'mov qword ptr [rdi], rax',0x141546a38:'mov rdx, qword ptr [rdi]',
    0x141546a3e:'xor r8d, r8d',0x141546a44:'call 0x141545ae0',
    0x141545af8:'mov rbp, rdx',0x141545b25:'mov qword ptr [rsp + 0x30], rbp',
    0x141545af4:'movzx esi, r8b',0x141545b2a:'mov byte ptr [rsp + 0x38], sil',
    0x141545ba0:'movups xmm0, xmmword ptr [rsp + 0x30]',0x141545ba5:'movups xmmword ptr [rcx], xmm0',
    0x141545ba8:'inc qword ptr [rdi + 0x20]',0x141545bac:'mov eax, 0x80000000',
    0x14154647f:'movq r13, xmm0',0x14154655f:'mov rbx, qword ptr [r12 + 8]',
    0x141546564:'sub rbx, qword ptr [r12]',0x141546568:'sar rbx, 4',0x14154656e:'test rbx, rbx',
    0x14154645d:'movups xmmword ptr [rbp - 0x39], xmm0',
    0x141546612:'movzx r12d, byte ptr [rbp - 0x31]',0x141546617:'test r12b, r12b',
    0x14154661a:'je 0x141546622',0x14154661c:'cmp dword ptr [rbx + 8], 1',
    0x141546620:'je 0x14154662e',0x141546628:'mov rdx, r13',0x14154662b:'call qword ptr [rax + 8]',
    0x141546637:'mov rax, qword ptr [r13]',0x141546640:'mov rcx, r13',
    0x141546643:'call qword ptr [rax]',0x1407108e6:'mov r8d, dword ptr [rdx + 0xc]',
}

POINTS = {
    'constructor':0x14185ee90,'publishPolicyResult':0x1415469d8,
    'enqueued':0x141545bac,'listenerLookup':0x14154656e,
    'handlerEntry':0x1407108e0,'dispatchFinished':0x141546637,
}


def inspect(application):
    h = runpy.run_path(str(ROOT/'scripts/export-serato-clock-handshake-evidence.py'))
    app = h['Image'](application,h['CURRENT_SHA'])
    require = h['require']
    facts = []
    for va, assembly in FACTS.items():
        row = app.at(va)
        require(f'{row.mnemonic} {row.op_str}'==assembly,f'Instruction differs at {va:#x}')
        facts.append({'va':hex(va),'bytes':bytes(row.bytes).hex(),'assembly':assembly})
    registers = {'rdi','edi','di','dil'}
    writes = [row.address for row in app.function(0x14213ddc0) if 0x14213e01b<=row.address<=0x14213e289 and
              registers.intersection(map(row.reg_name,row.regs_access()[1]))]
    require(writes==[0x14213e01b],'Revision register changes on the selected path')
    require(app.rip(app.at(0x14185eec0,'lea'))==0x142fbf4b8,'Pointer-shaped message table differs')

    table = 0x14281cbe8
    locator = struct.unpack('<Q',app.data(table-8,8))[0]
    col = struct.unpack('<6I',app.data(locator,24))
    require(col[0]==1 and col[1]==0x738 and app.base+col[5]==locator and
            app.text(app.base+col[3]+16)=='.?AVControllerDescriptor@dj@serato@@','Descriptor interface differs')
    getters = []
    for slot,field in ((0x18,0xa8),(0x20,0xaa),(0x28,0xac)):
        target = struct.unpack('<Q',app.data(table+slot,8))[0]
        raw = b'\x0f\xb7\x81'+struct.pack('<i',field-col[1])+b'\xc3'
        require(app.data(target,len(raw))==raw,'Descriptor getter differs')
        getters.append({'slot':hex(slot),'target':hex(target),'completeField':hex(field),'bytes':raw.hex()})
    return {'schema':'sl3.serato-usb-arrival-identity.v1','applicationSha256':app.sha,
            'descriptorGetters':getters,'messageId':'0x2d4','route':7,'payload':'(descriptor_vid << 32) + (descriptor_pid << 16) + descriptor_revision',
            'selectedRevisionSource':'controller_descriptor','payloadIncludesBusOrAddress':False,
            'publishPolicy':{'replaceResult':1,'dropResult':2,'originalPathQueueFlag':0,
                             'nonzeroQueueFlagSkipsListenerType':1},
            'observationPoints':{name:{'va':hex(va),'entryBytes':app.data(va,8).hex()} for name,va in POINTS.items()},
            'checkedInstructions':facts,'liveDispatchObserved':False}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application',required=True,type=Path)
    print(json.dumps(inspect(parser.parse_args().application),indent=2))
