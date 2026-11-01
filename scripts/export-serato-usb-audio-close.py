"""Verify conditional USB removal -> engine disconnect -> legacy ASIO close."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = importlib.util.spec_from_file_location('removal_close_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
    h = importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    app = h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe',h.CURRENT_SHA)
    h.require(hashlib.sha256(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe').read_bytes()).hexdigest() == app.sha,
              'Installed application differs')
    leaf_ranges = ((0x1404a4550,0x1404a4553),(0x1421e6120,0x1421e6125),
                   (0x1422201b0,0x14222020d),(0x142220210,0x142220241),
                   (0x142222180,0x142222199),(0x142221e60,0x142221e7c))
    leaves = {}
    for start,end in leaf_ranges:
        rows = list(app.dis.disasm(app.data(start,end-start),start))
        h.require(rows and rows[-1].address+rows[-1].size == end,'Incomplete explicit leaf range')
        leaves.update({i.address:i for i in rows})
    checks = [
        # The earlier opaque service resolves to authorization, not an audio owner.
        (0x141960f90,'call','0x1419605a0'), (0x141960f95,'mov','rax, qword ptr [rip + 0x26cb8bc]'),
        (0x1419605dd,'call','0x141960a60'), (0x1419605e2,'mov','rdx, qword ptr [rax]'),
        (0x1419605f3,'mov','qword ptr [rip + 0x26cc25e], rdx'),
        (0x141960a6f,'cmp','dword ptr [rip + 0x26cbddb], edi'), (0x141960a75,'jne','0x141960aa7'),
        (0x141960a8e,'call','0x141984590'), (0x141960abe,'call','0x14197fce0'),
        (0x1419845b0,'lea','rax, [rip + 0x164cd01]'), (0x1419845b7,'mov','qword ptr [r14], rax'),
        (0x14197fcee,'lea','rax, [rip + 0x1650cd3]'), (0x14197fcf5,'mov','qword ptr [rbx], rax'),
        # Engine is a separate 0x2ca subscriber with a directly bound handler.
        (0x1413707b5,'lea','rax, [rip + 0x1bb936c]'),
        (0x1413718bb,'mov','edx, 0x2ca'), (0x1413718c0,'mov','rcx, rbx'), (0x1413718c3,'call','0x14154cf90'),
        (0x141373a5a,'mov','r8d, dword ptr [rdx + 0xc]'), (0x141373a5e,'sub','r8d, 0x2ca'),
        (0x141373a65,'je','0x141373bce'), (0x141373bce,'mov','rax, qword ptr [rdx]'),
        (0x141373bd4,'call','qword ptr [rax + 0x10]'), (0x1404a4550,'xor','al, al'), (0x1404a4552,'ret',''),
        (0x141373bd7,'cmp','al, byte ptr [rbx + 0x2b0]'), (0x141373bdd,'je','0x141373bf8'),
        (0x141373bdf,'mov','byte ptr [rbx + 0x2b0], al'), (0x141373bea,'je','0x141373bf3'),
        (0x141373bf3,'call','0x141373130'),
        (0x141373193,'mov','rcx, qword ptr [rsi + 0x1b8]'), (0x14137319a,'call','0x141377800'),
        # Connection controller disconnect checks state then closes/deletes +0xc0.
        (0x14137782f,'cmp','qword ptr [rcx + 0xb0], rbx'), (0x141377836,'jne','0x1413778a2'),
        (0x14137788b,'lea','rdx, [rip + 0x1bb2f56]'),
        (0x141377979,'lea','rdx, [rip + 0x1bb2ed8]'), (0x141377a56,'call','0x14137a830'),
        (0x14137a84c,'cmp','qword ptr [rcx + 0xc0], 0'), (0x14137a854,'je','0x14137a987'),
        (0x14137a959,'mov','rcx, qword ptr [rdi + 0xc0]'), (0x14137a960,'mov','rax, qword ptr [rcx]'),
        (0x14137a963,'call','qword ptr [rax + 0x10]'), (0x14137a966,'mov','rcx, qword ptr [rdi + 0xc0]'),
        (0x14137a96d,'mov','qword ptr [rdi + 0xc0], 0'), (0x14137a980,'mov','edx, 1'),
        (0x14137a985,'call','qword ptr [rax]'),
        # The setup selector's returned connection becomes the same +0xc0 owner.
        (0x141379cda,'lea','rdx, [rsp + 0x48]'), (0x141379ce6,'call','0x1421b8b80'),
        (0x14137a01b,'mov','rax, qword ptr [rsp + 0x48]'), (0x14137a02c,'mov','qword ptr [rsi + 0xc0], rax'),
        # Conditional legacy PortAudio connection close.
        (0x1421e6120,'jmp','0x1421e7ba0'),
        (0x1421e7c14,'cmp','byte ptr [rip + 0x1ece632], 0'), (0x1421e7c1b,'je','0x1421e7e4d'),
        (0x1421e7c28,'mov','rcx, qword ptr [rip + 0x1ece5f9]'), (0x1421e7c2f,'call','0x1422155d0'),
        (0x1421e7c36,'test','eax, eax'), (0x1421e7c38,'je','0x1421e7cb4'),
        (0x1421e7cb4,'mov','rcx, qword ptr [rip + 0x1ece56d]'), (0x1421e7cbb,'call','0x142215620'),
        # Generic abort uses raw stream +0x10 interface, checks stopped, calls +0x18.
        (0x1422155d9,'call','0x1422155a0'), (0x1422155de,'test','eax, eax'), (0x1422155e0,'jne','0x142215611'),
        (0x1422155e2,'mov','rax, qword ptr [rbx + 0x10]'), (0x1422155e9,'mov','rdx, qword ptr [rax + 0x20]'),
        (0x1422155ed,'call','rdx'), (0x1422155ef,'test','eax, eax'), (0x1422155f1,'jne','0x142215606'),
        (0x1422155f3,'mov','rax, qword ptr [rbx + 0x10]'), (0x1422155fa,'mov','rdx, qword ptr [rax + 0x18]'),
        (0x142215603,'jmp','rdx'),
        # Generic close validates the stream, aborts if required, then calls slot 0.
        (0x142215629,'call','0x1422155a0'), (0x142215633,'call','0x142215d30'),
        (0x14221563a,'jne','0x142215674'), (0x142215641,'mov','rdi, qword ptr [rbx + 0x10]'),
        (0x142215645,'mov','rax, qword ptr [rdi + 0x20]'), (0x142215649,'call','rax'),
        (0x14221564b,'cmp','eax, 1'), (0x14221564e,'je','0x142215661'),
        (0x142215654,'mov','rax, qword ptr [rdi + 0x18]'), (0x14221565b,'call','rax'),
        (0x14221565d,'test','eax, eax'), (0x14221565f,'jne','0x142215669'),
        (0x142215661,'mov','rax, qword ptr [rdi]'), (0x142215667,'call','rax'),
        # ASIO host initializes callback and blocking stream tables with same close/abort.
        (0x142218eac,'lea','rbx, [rip - 0x2573]'), (0x142218ecb,'lea','rdx, [rip - 0x2252]'),
        (0x142218ef0,'lea','rcx, [r13 + 0x48]'), (0x142218f33,'mov','qword ptr [rsp + 0x20], rbx'),
        (0x142218f38,'call','0x1422201b0'),
        (0x142218f49,'lea','rcx, [r13 + 0xa8]'), (0x142218f82,'lea','rdx, [rip - 0x2309]'),
        (0x142218fa4,'mov','qword ptr [rsp + 0x20], rbx'), (0x142218fa9,'call','0x1422201b0'),
        (0x1422201b0,'mov','rax, qword ptr [rsp + 0x28]'), (0x1422201b5,'mov','qword ptr [rcx + 0x18], rax'),
        (0x142220201,'mov','qword ptr [rcx], rdx'),
        # ASIO open selects one of those host members for raw stream interface +0x10.
        (0x1422171a8,'mov','r14, rcx'), (0x142217606,'mov','ecx, 0xa8'), (0x142217612,'mov','edx, 0x48'),
        (0x14221761e,'cmove','edx, ecx'), (0x142217628,'add','rdx, r14'), (0x142217631,'call','0x142220210'),
        (0x142220234,'mov','qword ptr [rcx + 0x10], rdx'),
        # ASIO abort/close reach real interface stop/dispose/unload/release.
        (0x142216956,'call','0x142222180'), (0x142222195,'jmp','qword ptr [rax + 0x40]'),
        (0x142216ce4,'call','0x142221e60'), (0x142221e75,'jmp','qword ptr [rax + 0xa0]'),
        (0x142216ce9,'call','0x142221e80'), (0x142221e95,'call','0x142222af0'),
        (0x142222b01,'call','0x1422222d0'), (0x1422222f9,'call','qword ptr [rdx + 0x10]'),
        (0x1422222fc,'mov','qword ptr [rbx + 0x298], 0'),
    ]
    instructions=[]
    for va,op,operands in checks:
        i=leaves[va] if va in leaves else app.at(va)
        h.require(i.mnemonic==op and i.op_str==operands,f'Instruction differs at {va:x}')
        instructions.append({'va':hex(va),'bytes':i.bytes.hex(),'instruction':(op+' '+operands).rstrip()})
    classes=[]
    for table,offset,name,slots in (
        (0x142fd12b8,0,'.?AVRLMAuthorization@authorization@serato@@',{}),
        (0x142fd09c8,0,'.?AVJWTAuthorization@authorization@serato@@',{}),
        (0x142f29b28,0,'.?AVEngine@engine@dj@serato@@',{0x18:0x141373a40}),
        (0x142fbf4b8,0,'.?AVUserIO_VoidPtrMessageData@data@message@serato@@',{0x10:0x1404a4550}),
        (0x1431d7248,0,'.?AVPortAudioConnection@audio@device@serato@@',{0x10:0x1421e6120}),
    ):
        locator=struct.unpack('<Q',app.data(table-8,8))[0];col=struct.unpack('<6I',app.data(locator,24))
        h.require(col[0]==1 and col[1]==offset and app.base+col[5]==locator and app.text(app.base+col[3]+16)==name,'RTTI differs')
        for slot,target in slots.items():h.require(struct.unpack('<Q',app.data(table+slot,8))[0]==target,'Concrete slot differs')
        classes.append({'type':name,'vtable':hex(table),'objectOffset':offset,'slots':{hex(k):hex(v) for k,v in slots.items()}})
    for va,target in ((0x1419845b0,0x142fd12b8),(0x14197fcee,0x142fd09c8),(0x1413707b5,0x142f29b28),
                       (0x142218eac,0x142216940),(0x142218ecb,0x142216c80),(0x142218f82,0x142216c80)):
        h.require(app.rip(app.at(va))==target,'Concrete construction/callback target differs')
    h.require(app.rip(app.at(0x141960f95))==app.rip(app.at(0x1419605f3)),'Service getter/factory globals differ')
    h.require(app.rip(app.at(0x1421e7c28))==app.rip(app.at(0x1421e7cb4)),'Abort/close raw stream globals differ')
    diagnostics={}
    for va,text in ((0x14137788b,'Audio connection, disconnecting aborted - already disconnected'),
                     (0x141377979,"Audio connection, disconnecting from '")):
        target=app.rip(app.at(va));h.require(app.text(target)==text,'Disconnect diagnostic differs');diagnostics[hex(va)]=text
    result={'scope':'Conditional original-image USB removal notification to Engine disconnect and legacy ASIO stop/dispose/Release',
            'applicationSha256':app.sha,'instructions':instructions,'classes':classes,'diagnostics':diagnostics,
            'serviceBoundary':{'factory':'0x141960a60','types':['RLMAuthorization','JWTAuthorization'],
                               'audioCloseFromThisCallClaimed':False,'authorizationModifiedOrBypassed':False},
            'engine':{'messageId':0x2ca,'handler':'0x141373a40','voidPointerPayloadBooleanGetter':False,
                      'requiresPriorFlagDifferent':True,'flagOffset':0x2b0,'disconnect':'0x141373130'},
            'connection':{'controllerDisconnect':'0x141377800','requiresActiveDescriptor':True,
                          'close':'0x14137a830','connectionFieldOffset':0xc0,'virtualCloseSlot':0x10,'deletingDestructorSlot':0},
            'legacyAsio':{'conditionalOnSelectedLegacyConnectionAndValidActiveAsioStream':True,
                          'connectionClose':'0x1421e7ba0','rawStreamGlobal':hex(app.rip(app.at(0x1421e7c28))),
                          'genericAbort':'0x1422155d0','genericClose':'0x142215620',
                          'streamTableClose':'0x142216c80','streamTableAbort':'0x142216940',
                          'iasioStopSlot':0x40,'iasioDisposeBuffersSlot':0xa0,'iunknownReleaseSlot':0x10,
                          'failureBranchesPreserved':True},
            'liveApplicationDispatchVerified':False,'currentSl3AudioAdmissionVerified':False,
            'limits':['Static conditional calls do not establish a live instantiated backend, callback delivery or successful teardown',
                      'The engine ignores an unchanged state flag; active connection/stream and error guards remain',
                      'JUCE close mapping is not claimed from this legacy-only chain',
                      'No account, authorization, image/resource, driver/USB, registration, firmware or security operation']}
    (ROOT/'docs/evidence/serato500-usb-audio-close.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Verified separate authorization boundary and conditional removal/Engine/legacy-ASIO stop-dispose-Release chain; no runtime dispatch or SL3 admission proof')


if __name__=='__main__':
    main()
