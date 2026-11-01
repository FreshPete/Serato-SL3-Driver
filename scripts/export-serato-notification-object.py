"""Bind current Serato action-6 UI object provenance and checked virtual targets.

Original PE bytes and focused reports only. No vendor execution, installed-file
modification, descriptor substitution or product/account predicate alteration.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    spec=importlib.util.spec_from_file_location('notification_image',ROOT/'scripts/export-serato-clock-handshake-evidence.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    app=helper.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe',helper.CURRENT_SHA)
    require=helper.require
    require(sha(Path(r'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe'))==app.sha,'Installed executable differs')
    routing_path=ROOT/'docs/evidence/serato500-driver-notification.json'
    routing=json.loads(routing_path.read_text(encoding='utf-8-sig'))
    require(routing['binarySha256']==app.sha and routing['action']==6 and routing['messageId']==0x52 and
            routing['messageHandlerCaseVa']=='0x14137bdd9','Earlier notification route differs')
    facts=[]

    def fact(address,expected):
        instruction=app.at(address)
        require(instruction.mnemonic+' '+instruction.op_str==expected,'Instruction differs: '+hex(address))
        facts.append({'va':hex(address),'bytes':bytes(instruction.bytes).hex(),'assembly':expected})
        return instruction

    def rtti(table,name,offset):
        locator=struct.unpack('<Q',app.data(table-8,8))[0]
        signature,actual,displacement,td,hierarchy,self_rva=struct.unpack('<6I',app.data(locator,24))
        require(signature==1 and actual==offset and displacement==0 and app.base+self_rva==locator and
                app.text(app.base+td+16)==name,'RTTI differs: '+hex(table))
        return {'tableVa':hex(table),'locatorVa':hex(locator),'completeObjectOffset':offset,'type':name,
                'hierarchyRva':hierarchy}

    classes=[rtti(0x142f2b598,'.?AVDeviceNotificationController@dj@serato@@',0),
             rtti(0x142f29b28,'.?AVEngine@engine@dj@serato@@',0),
             rtti(0x142eb2078,'.?AVNotificationCenter@notification@serato@@',0),
             rtti(0x142eb2828,'.?AVNotification@notification@serato@@',0),
             rtti(0x142b828c0,'.?AVQmlNotification@notification@serato@@',0x10)]
    require(struct.unpack('<Q',app.data(0x142f2b598+0x18,8))[0]==0x14137b790,'Receiver vtable slot differs')
    require(app.rip(fact(0x14137b164,'lea rax, [rip + 0x1bb042d]'))==0x142f2b598,'Receiver constructor table differs')
    require(app.rip(fact(0x1413707b5,'lea rax, [rip + 0x1bb936c]'))==0x142f29b28,'Engine constructor table differs')
    for address,expected in [
        (0x14137b155,'mov rdi, r8'),(0x14137b172,'mov qword ptr [r14 + 0x48], rdi'),
        (0x141370760,'mov rax, rsp'),(0x14137077f,'lea rbp, [rax - 0x118]'),
        (0x141370f9f,'mov r15, qword ptr [rbp + 0x178]'),(0x141370fa6,'mov r8, r15'),
        (0x141370faf,'call 0x14137b140'),(0x14137b6de,'mov rdx, qword ptr [rax]'),
        (0x14137b6e1,'mov rcx, qword ptr [rsi + 0x48]'),
        (0x14137b6e5,'call 0x140f1fa40'),(0x14137b6f5,'call qword ptr [rdx + 0x40]'),
        (0x140f25fc9,'mov rcx, qword ptr [rcx + 0x18]'),(0x140f25fcd,'call 0x140f05950'),
        (0x140f25fdb,'mov byte ptr [rsp + 0x30], 0'),(0x140f25fe8,'call qword ptr [rax + 0x10]'),
        (0x140f25fee,'mov edx, 9'),(0x140f25ff6,'call qword ptr [rax + 0x78]'),
        (0x140f26005,'mov byte ptr [rsp + 0x30], 0'),(0x140f2601c,'call qword ptr [rax + 0x10]'),
        (0x140f279bb,'mov byte ptr [rsp + 0x30], 1'),(0x140f279ce,'mov edx, 0xa'),
        (0x140f279e5,'mov byte ptr [rsp + 0x30], 1')]:fact(address,expected)
    # This small tail-jump has no unwind record. Check its exact five-byte
    # instruction independently, rather than attributing a neighbouring range.
    thunk=next(app.dis.disasm(app.data(0x1409c5f00,5),0x1409c5f00))
    require(thunk.size==5 and thunk.mnemonic=='jmp' and thunk.op_str=='0x140f25fc0','QML notification thunk differs')
    facts.append({'va':hex(thunk.address),'bytes':bytes(thunk.bytes).hex(),'assembly':thunk.mnemonic+' '+thunk.op_str})
    require(struct.unpack('<Q',app.data(0x142eb2828+0x40,8))[0]==0x140f25fc0 and
            struct.unpack('<Q',app.data(0x142b828c0+0x40,8))[0]==0x1409c5f00,'Notification slot-0x40 targets differ')
    require(struct.unpack('<Q',app.data(0x142eb2828+0x48,8))[0]==0x140f279a0,'Contrasting base slot differs')
    hierarchy=app.base+classes[-1]['hierarchyRva']
    _,_,count,array=struct.unpack('<4I',app.data(hierarchy,16));require(1<=count<=32,'Unexpected base count')
    bases=[]
    for rva in struct.unpack('<'+'I'*count,app.data(app.base+array,count*4)):
        td,contained,mdisp,pdisp,vdisp,attributes,child=struct.unpack('<IIiiiII',app.data(app.base+rva,28))
        bases.append({'type':app.text(app.base+td+16),'memberDisplacement':mdisp,'vbtableDisplacement':pdisp,'vdisp':vdisp})
    require(any(b['type']=='.?AVNotification@notification@serato@@' and b['memberDisplacement']==0x10 and
                b['vbtableDisplacement']==-1 for b in bases),'QML Notification base at +0x10 differs')
    signatures=[m.group()[:-1] for m in re.finditer(rb'\.\?AV[^\x00]{1,4096}\x00',app.raw)
                if b'??0Engine@engine@dj@serato@@' in m.group() and b'Func_impl' not in m.group()]
    require(len(signatures)==1 and b'AEAVCUserIODJSyncManager@@AEAVNotificationCenter@notification@4@AEAVCStatusBarManager@@' in signatures[0],
            'Enclosing constructor type signature differs')
    # Entry-RSP+0x60 is explicit argument eleven after this/reg arguments in the
    # observed x64 constructor. Type annotation comes from the complete RTTI
    # signature, not a shortened decompiler prototype or an unwrapped symbol.
    require(0x178-0x118==0x60,'Constructor stack derivation differs')
    focused_path=ROOT/'analysis/serato500-device-notification-ctor-20261101.json'
    focused=json.loads(focused_path.read_text());require(focused['binary_sha256']==app.sha,'Focused input differs')
    spans=[]
    for start,end in [(0x14137b140,0x14137b3df),(0x141370760,0x141371957)]:
        row=next(r for r in focused['functions'] if int(r['start'],16)==start)
        require(row['complete'] is True and int(row['end_exclusive'],16)==end and (start,end) in app.spans,
                'Focused constructor incomplete or wrong range')
        spans.append({'start':hex(start),'endExclusive':hex(end)})
    result={'scope':'Static object provenance for current action-6 notification; no admitted SL3 session',
            'binarySha256':app.sha,'priorRoutingEvidenceSha256':sha(routing_path),'receiverType':'DeviceNotificationController',
            'storedDependency':{'type':'NotificationCenter','receiverOffset':'0x48','constructorRegister':'r8',
                                'engineEntryRspOffset':'0x60','engineExplicitArgument':11,
                                'rttiSignatureSha256':hashlib.sha256(signatures[0]).hexdigest()},
            'checkedNotificationSlot':'0x40','baseImplementation':'0x140f25fc0','qmlSecondaryThunk':'0x1409c5f00',
            'checkedCallbackBoolean':False,'baseVirtualEventNumber':9,'contrastBaseSlot':'0x48','contrastSlotCallbackBoolean':True,
            'contrastVirtualEventNumber':10,'classes':classes,'qmlBaseRecords':bases,'instructionFacts':facts,
            'focusedConstructors':spans,'runtimeDispatchObserved':False,'audioAdmissionVerified':False,
            'licensingMeaningAssigned':False,'currentSl3ConnectionVerified':False,
            'limits':['The original unchanged SL3 still selects support 2; action 6 is conditional on a different support branch.',
                      'Checked base and QML implementations do not enumerate every possible runtime subclass or callback consequence.',
                      'A Boolean callback value is not named an audio/driver/licensing result or a proven user-visible operation.',
                      'This identifies notification-object handling; genuine descriptor, handshake, transport and DVS admission remain separate.'],
            'sources':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [Path(__file__),
                ROOT/'scripts/export-serato-clock-handshake-evidence.py',focused_path,
                routing_path,ROOT/'scripts/export-serato-driver-notification.py',
                ROOT/'analysis/serato500-device-notification-ctor-20261101.log',
                ROOT/'analysis/serato500-notification-types-20261101.json']}}
    (ROOT/'docs/evidence/serato500-notification-object.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Verified receiver/engine/NotificationCenter provenance, five RTTI tables, {len(facts)} instructions and two complete constructors')


if __name__=='__main__':main()
