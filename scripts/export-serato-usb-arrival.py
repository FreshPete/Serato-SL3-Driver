"""Verify the conditional USB-arrival bridge and state/version gates; never run Serato."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
CHECKS=[
    (0x1405c9cca, 'mov qword ptr [rsi + 0xd8], 0'),
    (0x1405c9ced, 'lea rdx, [rip + 0x2253de4]'),
    (0x1405c9cf4, 'mov rcx, r12'),
    (0x1405c9cf7, 'call 0x141b17da0'),
    (0x1405c9cfc, 'mov rbx, rax'),
    (0x1405c9cff, 'test rax, rax'),
    (0x1405c9d02, 'je 0x1405c9f35'),
    (0x1405c9d08, 'xor r8d, r8d'),
    (0x1405c9d0b, 'lea rdx, [rip + 0x2253df6]'),
    (0x1405c9d12, 'mov rcx, rax'),
    (0x1405c9d15, 'call 0x141b17620'),
    (0x1405c9d1a, 'test rax, rax'),
    (0x1405c9d1d, 'je 0x1405c9d6c'),
    (0x1405c9d1f, 'xor r8d, r8d'),
    (0x1405c9d47, 'call 0x1404a67b0'),
    (0x1405c9d4c, 'mov rcx, rax'),
    (0x1405c9d4f, 'xor r8d, r8d'),
    (0x1405c9d52, 'xor edx, edx'),
    (0x1405c9d54, 'call qword ptr [rip + 0x216cc96]'),
    (0x1405c9d5a, 'mov dword ptr [rsi + 0xd8], eax'),
    (0x14070fdd1, 'mov word ptr [rdi + 0x70], si'),
    (0x14070ffd3, 'mov r8, qword ptr [rcx + 0xa0]'),
    (0x14070ffda, 'mov rdx, rbx'),
    (0x14070ffdd, 'mov rcx, rax'),
    (0x14070ffe0, 'call r8'),
    (0x14070ffe3, 'test al, al'),
    (0x14070ffe5, 'je 0x14071005e'),
    (0x14070ffef, 'mov r8, qword ptr [rcx + 0x90]'),
    (0x14070fff6, 'mov rdx, rbx'),
    (0x14070fff9, 'mov rcx, rax'),
    (0x14070fffc, 'call r8'),
    (0x14070ffff, 'movzx esi, al'),
    (0x140710002, 'mov rbx, qword ptr [rip + 0x379c9bf]'),
    (0x14071001d, 'mov r8d, esi'),
    (0x140710020, 'mov dword ptr [rsp + 0x30], ebp'),
    (0x140710024, 'mov dword ptr [rsp + 0x28], ebp'),
    (0x140710028, 'mov dword ptr [rsp + 0x20], 7'),
    (0x140710030, 'xor r9d, r9d'),
    (0x140710033, 'mov edx, 0x693'),
    (0x140710038, 'mov rcx, rax'),
    (0x14071003b, 'call 0x14185ec00'),
    (0x14071004f, 'mov rax, qword ptr [rbx]'),
    (0x140710052, 'lea rdx, [rsp + 0x70]'),
    (0x140710057, 'mov rcx, rbx'),
    (0x14071005a, 'call qword ptr [rax + 0x50]'),
    (0x14071005e, 'lea rcx, [rdi + 0x71]'),
    (0x140710062, 'call 0x1404a2ee0'),
    (0x140710067, 'movzx ecx, byte ptr [rax]'),
    (0x14071006b, 'test cl, cl'),
    (0x14071006d, 'jne 0x140710092'),
    (0x14071006f, 'lea rcx, [rdi + 0x70]'),
    (0x140710073, 'call 0x1404a2ee0'),
    (0x140710078, 'movzx ecx, byte ptr [rax]'),
    (0x14071007c, 'test cl, cl'),
    (0x14071007e, 'jne 0x140710092'),
    (0x140710080, 'xor al, al'),
    (0x140710092, 'mov al, 1'),
    (0x1407108e6, 'mov r8d, dword ptr [rdx + 0xc]'),
    (0x1407108ea, 'mov rdi, rcx'),
    (0x1407108ed, 'sub r8d, 0x2d4'),
    (0x1407108f4, 'je 0x1407109a1'),
    (0x1407108fa, 'sub r8d, 1'),
    (0x1407108fe, 'je 0x140710974'),
    (0x140710905, 'sub r8d, 0x3bd'),
    (0x14071090c, 'je 0x140710944'),
    (0x14071090e, 'cmp r8d, 1'),
    (0x140710912, 'jne 0x140710939'),
    (0x140710914, 'mov rax, qword ptr [rdx]'),
    (0x140710917, 'mov rcx, rdx'),
    (0x14071091a, 'call qword ptr [rax + 0x10]'),
    (0x14071091d, 'lea rcx, [rsp + 0x38]'),
    (0x140710922, 'mov byte ptr [rsp + 0x38], al'),
    (0x140710926, 'call 0x1404e6950'),
    (0x14071092b, 'lea rcx, [rdi + 0x61]'),
    (0x14071092f, 'movzx ebx, al'),
    (0x140710932, 'call 0x1404a2ee0'),
    (0x140710937, 'xchg byte ptr [rax], bl'),
    (0x140710944, 'mov rax, qword ptr [rdx]'),
    (0x140710947, 'mov rcx, rdx'),
    (0x14071094a, 'call qword ptr [rax + 0x10]'),
    (0x14071094d, 'lea rcx, [rsp + 0x38]'),
    (0x140710952, 'mov byte ptr [rsp + 0x38], al'),
    (0x140710956, 'call 0x1404e6950'),
    (0x14071095b, 'lea rcx, [rdi + 0x60]'),
    (0x14071095f, 'movzx ebx, al'),
    (0x140710962, 'call 0x1404a2ee0'),
    (0x140710967, 'xchg byte ptr [rax], bl'),
    (0x140c00ab4, 'add rcx, 0x10'),
    (0x140c00ab8, 'xor edx, edx'),
    (0x140c00aba, 'call 0x140502ae0'),
    (0x140c00abf, 'xor al, 1'),
    (0x140c00ac5, 'ret '),
    (0x140c00ad4, 'xor edx, edx'),
    (0x140c00ad6, 'call 0x140502ae0'),
    (0x140c00adb, 'xor al, 1'),
    (0x140c00ae1, 'ret '),
    (0x140c00cd0, 'lea rdx, [rbp + 0x50]'),
    (0x140c00cd4, 'mov rcx, r15'),
    (0x140c00cd7, 'call 0x140c005b0'),
    (0x140c00cdd, 'mov rsi, qword ptr [rbp + 0x50]'),
    (0x140c00ce1, 'test rsi, rsi'),
    (0x140c00ce4, 'je 0x140c00d3e'),
    (0x140c00ce6, 'mov rax, qword ptr [rbx]'),
    (0x140c00ce9, 'mov rcx, rbx'),
    (0x140c00cec, 'call qword ptr [rax + 0x60]'),
    (0x140c00cef, 'mov edi, eax'),
    (0x140c00cf1, 'mov rcx, rsi'),
    (0x140c00cf4, 'call 0x14050eb60'),
    (0x140c00cf9, 'mov ebx, eax'),
    (0x140c00d33, 'cmp ebx, edi'),
    (0x140c00d35, 'setae r12b'),
    (0x140c00d39, 'jmp 0x140c00e40'),
    (0x140c00d3e, 'lea rdx, [rbp + 0x70]'),
    (0x140c00d42, 'mov rcx, r15'),
    (0x140c00d45, 'call 0x14050f560'),
    (0x140c00d4b, 'mov rsi, qword ptr [rbp + 0x70]'),
    (0x140c00d4f, 'test rsi, rsi'),
    (0x140c00d52, 'je 0x140c00e08'),
    (0x140c00d58, 'mov rax, qword ptr [rbx]'),
    (0x140c00d5b, 'mov rcx, rbx'),
    (0x140c00d5e, 'call qword ptr [rax + 0x60]'),
    (0x140c00d61, 'mov edi, eax'),
    (0x140c00d63, 'mov rcx, rsi'),
    (0x140c00d66, 'call 0x140b1a280'),
    (0x140c00d6b, 'mov esi, eax'),
    (0x140c00d6d, 'cmp eax, edi'),
    (0x140c00d6f, 'setae r12b'),
    (0x140c00e08, 'mov r12b, 1'),
    (0x140c01213, 'movzx eax, r12b'),
    (0x14213dd2f, 'mov rbx, rdx'),
    (0x14213dd32, 'lea rax, [rip + 0x87]'),
    (0x14213dd39, 'mov qword ptr [rsp + 0x20], rax'),
    (0x14213dd3e, 'mov dword ptr [rsp + 0x28], 0'),
    (0x14213dd46, 'movaps xmm0, xmmword ptr [rsp + 0x20]'),
    (0x14213dd4b, 'movdqa xmmword ptr [rsp + 0x20], xmm0'),
    (0x14213dd51, 'lea r8, [rcx - 0x88]'),
    (0x14213dd58, 'add rcx, 0x18'),
    (0x14213dd5c, 'mov r9, rdx'),
    (0x14213dd5f, 'lea rdx, [rsp + 0x20]'),
    (0x14213dd64, 'call 0x14213ae20'),
    (0x14213ddf8, 'mov r12, rdx'),
    (0x14213ddfb, 'mov rsi, rcx'),
    (0x14213ddfe, 'mov qword ptr [rbp - 0x38], rcx'),
    (0x14213de02, 'mov qword ptr [rbp - 0x10], rdx'),
    (0x14213ea5a, 'mov rcx, qword ptr [r12]'),
    (0x14213ea5e, 'call 0x140c00ad0'),
    (0x14213ea63, 'test al, al'),
    (0x14213ea65, 'jne 0x14213eafe'),
    (0x14213ea6b, 'mov rcx, qword ptr [r12]'),
    (0x14213ea6f, 'call 0x140c00ab0'),
    (0x14213ea74, 'mov r14d, dword ptr [rsp + 0x44]'),
    (0x14213ea79, 'test al, al'),
    (0x14213ea7b, 'jne 0x14213eb03'),
    (0x14213ea81, 'mov ecx, r14d'),
    (0x14213ea84, 'shl ecx, 0x10'),
    (0x14213ea87, 'mov ebx, dword ptr [rsp + 0x40]'),
    (0x14213ea8b, 'shl rbx, 0x20'),
    (0x14213ea8f, 'mov rax, qword ptr [rbp - 0x68]'),
    (0x14213ea93, 'add rax, rcx'),
    (0x14213ea96, 'add rbx, rax'),
    (0x14213eac6, 'xor r9d, r9d'),
    (0x14213eac9, 'mov r8, rbx'),
    (0x14213eacc, 'mov edx, 0x2d4'),
    (0x14213ead1, 'mov rcx, rax'),
    (0x14213ead4, 'call 0x14185ee90'),
    (0x14213eaed, 'mov rax, qword ptr [rdi]'),
    (0x14213eaf0, 'lea rdx, [rsp + 0x48]'),
    (0x14213eaf5, 'mov rcx, rdi'),
    (0x14213eaf8, 'call qword ptr [rax + 0x58]'),
    (0x14213eafc, 'jmp 0x14213eb06'),
    (0x14213eafe, 'mov r14d, dword ptr [rsp + 0x44]'),
    (0x1421db993, 'xor r14d, r14d'),
    (0x1421dcbf0, 'call 0x140c00af0'),
    (0x1421dcbf5, 'mov ecx, 0x30'),
    (0x1421dcbfa, 'test al, al'),
    (0x1421dcbfc, 'je 0x1421dcda4'),
    (0x1421dcc02, 'call 0x142117f10'),
    (0x1421dcc07, 'mov rdi, rax'),
    (0x1421dcc0a, 'mov qword ptr [rsp + 0x2a0], rax'),
    (0x1421dcc12, 'test rax, rax'),
    (0x1421dcc15, 'je 0x1421dcc65'),
    (0x1421dcc17, 'mov dword ptr [rsp + 0x50], r14d'),
    (0x1421dcc50, 'lea r9, [rsp + 0x50]'),
    (0x1421dcc55, 'mov r8, rbx'),
    (0x1421dcc58, 'mov rdx, rax'),
    (0x1421dcc5b, 'mov rcx, rdi'),
    (0x1421dcc5e, 'call 0x1421de6b0'),
    (0x1421dccaf, 'lea rdx, [rsp + 0x70]'),
    (0x1421dccb4, 'mov rcx, rbx'),
    (0x1421dccb7, 'call 0x1421de0a0'),
    (0x1421dcdb9, 'mov dword ptr [rsp + 0x50], 8'),
    (0x1421de6cc, 'mov rbx, rcx'),
    (0x1421de6cf, 'mov qword ptr [rcx], rax'),
    (0x1421de6d2, 'mov rsi, r9'),
    (0x1421de71b, 'mov eax, dword ptr [rsi]'),
    (0x1421de71d, 'mov esi, 0xffffffff'),
    (0x1421de722, 'mov dword ptr [rbx + 0x28], eax'),
    (0x1421de935, 'movsxd rax, dword ptr [r14 + 0x28]'),
    (0x1421de939, 'cmp eax, 0xe'),
    (0x1421de93c, 'ja 0x1421deb91'),
    (0x1421de942, 'lea rcx, [rip - 0x21de949]'),
    (0x1421de949, 'mov edx, dword ptr [rcx + rax*4 + 0x21debe4]'),
    (0x1421de950, 'add rdx, rcx'),
    (0x1421de953, 'jmp rdx'),
    (0x1421de955, 'mov rax, qword ptr [rdi]'),
    (0x1421de958, 'mov rbx, qword ptr [rax + 8]'),
    (0x1421de95c, 'lea rcx, [rbp - 0x20]'),
]

CHECKS.append((0x14070ff1c, 'mov rdi, rcx'))

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    spec=importlib.util.spec_from_file_location('usb_arrival_image',ROOT/'scripts/export-serato-clock-handshake-evidence.py')
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);require=h.require
    app=h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe',h.CURRENT_SHA)
    require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe'))==app.sha,'Installed image differs')
    prior_path=ROOT/'docs/evidence/serato500-primary-pointer.json'
    require(sha(prior_path)=='ebb7f30213856cc6bb72643e86c54e1ea7f754b961cb40671c6a5fc3fc5872c2','Prior primary-pointer proof differs')
    prior=json.loads(prior_path.read_text(encoding='utf-8'))
    for row in prior['checkedInstructions']:
        raw=bytes.fromhex(row['bytes']);require(app.data(int(row['va'],16),len(raw))==raw,'Prior instruction bytes differ')
    facts=[]
    for va,expected in sorted(CHECKS):
        r=app.at(va);require(r.mnemonic+' '+r.op_str==expected,'Instruction differs at '+hex(va))
        facts.append({'va':hex(va),'bytes':bytes(r.bytes).hex(),'assembly':expected})
    require(len({va for va,_ in CHECKS})==len(CHECKS),'Duplicate instruction facts')
    aliases={h.capstone.x86.X86_REG_R14,h.capstone.x86.X86_REG_R14D,h.capstone.x86.X86_REG_R14W,h.capstone.x86.X86_REG_R14B}
    require(not any(set(r.regs_access()[1])&aliases for r in app.function(0x1421db390) if 0x1421db993<r.address<0x1421dcc17),'Action-zero register overwritten')
    require(app.rip(app.at(0x14213dd32))==0x14213ddc0,'Scheduled callback differs')
    require(app.rip(app.at(0x1421de942))==app.base and app.base+struct.unpack('<I',app.data(0x1421debe4,4))[0]==0x1421de955,'Action-zero table differs')
    tables=[]
    for table,prefix,offset,slots in [(0x1431c3f28,'.?AVDeviceManager@@',0x88,{8:0x14213dd20}),
        (0x14281caf0,'.?AVControllerDescriptor@dj@serato@@',16,{0x60:0x1405c6fe0}),
        (0x142843168,'.?AVCUSBAudioManager@@',16,{0x18:0x1407108e0})]:
        loc=struct.unpack('<Q',app.data(table-8,8))[0];col=struct.unpack('<6I',app.data(loc,24));name=app.text(app.base+col[3]+16)
        require(col[0]==1 and col[1]==offset and app.base+col[5]==loc and name==prefix,'RTTI differs')
        for slot,target in slots.items():require(struct.unpack('<Q',app.data(table+slot,8))[0]==target,'Slot differs')
        tables.append({'table':hex(table),'type':name,'completeObjectOffset':offset,'slots':{hex(k):hex(v) for k,v in slots.items()}})
    action_table=app.rip(app.at(0x1421de6c5));loc=struct.unpack('<Q',app.data(action_table-8,8))[0];col=struct.unpack('<6I',app.data(loc,24))
    action_name=app.text(app.base+col[3]+16)
    require(col[0]==1 and col[1]==0 and app.base+col[5]==loc and 'DispatchDeviceDeferredAction' in action_name,'Deferred action RTTI differs')
    tables.append({'table':hex(action_table),'type':action_name,'completeObjectOffset':0,'slots':{}})
    leaves=[]
    for va,length,expected in [(0x1405c6fe0,7,[('mov','eax, dword ptr [rcx + 0xc8]'),('ret','')]),
        (0x1404a2ee0,4,[('mov','rax, rcx'),('ret','')]),(0x1404e6950,4,[('movzx','eax, byte ptr [rcx]'),('ret','')]),
        (0x140502ae0,8,[('cmp','qword ptr [rcx], 0'),('sete','al'),('ret','')])]:
        raw=app.data(va,length);decoded=list(app.dis.disasm(raw,va))
        require([(r.mnemonic,r.op_str) for r in decoded]==expected,'Complete helper differs')
        leaves.append({'start':hex(va),'bytes':raw.hex(),'instructions':[op+' '+args for op,args in expected]})
    require(app.text(app.rip(app.at(0x1405c9ced)))=='firmware_check' and
            app.text(app.rip(app.at(0x1405c9d0b)))=='minimum_version_number','Version field name differs')
    ctor=app.function(0x14070fd70)
    zero=[r for r in ctor if r.address<0x14070fdd1 and r.mnemonic=='xor' and r.op_str=='esi, esi']
    require(len(zero)==1,'Constructor flag-zero source differs')
    rsi_aliases={h.capstone.x86.X86_REG_RSI,h.capstone.x86.X86_REG_ESI,h.capstone.x86.X86_REG_SI,h.capstone.x86.X86_REG_SIL}
    require(not any(set(r.regs_access()[1])&rsi_aliases for r in ctor if zero[0].address<r.address<0x14070fdd1),'Constructor zero overwritten')
    path=ROOT/'analysis/serato500-usb-arrival-20261102-decompile.json';focused=json.loads(path.read_text(encoding='utf-8-sig'))
    expected={(0x14213dd20,0x14213ddbb),(0x14213ddc0,0x14213eeca),(0x1421de890,0x1421dec20),
              (0x1421de6b0,0x1421de7a5),(0x140c00af0,0x140c012c7)}
    require(focused['binary_sha256']==app.sha,'Focused image differs');found=set()
    for row in focused['functions']:
        span=(int(row['start'],16),int(row['end_exclusive'],16))
        require(span in expected and span in app.spans and span not in found and row.get('complete') is True and
                row.get('pseudocode') and not row.get('diagnostic'),'Focused range differs/incomplete');found.add(span)
    require(found==expected,'Focused set differs')
    reused=[]
    for file,start,end in [('serato500-app-support-routing.json',0x1421db390,0x1421dd9d3),
                           ('serato500-primary-store-20261102-decompile.json',0x14070ff10,0x1407100a4)]:
        p=ROOT/'analysis'/file;value=json.loads(p.read_text(encoding='utf-8-sig'))
        require(value['binary_sha256']==app.sha,'Reused image differs')
        rows=[r for r in value['functions'] if int(r['start'],16)==start]
        require(len(rows)==1 and int(rows[0]['end_exclusive'],16)==end and (start,end) in app.spans and rows[0].get('complete') is True and
                rows[0].get('pseudocode') and not rows[0].get('diagnostic'),'Reused focused range differs')
        reused.append({'file':file,'sha256':sha(p),'start':hex(start),'endExclusive':hex(end)})
    require(reused[1]['sha256']==prior['focusedReportSha256'],'Prior helper focus changed')
    log=ROOT/'analysis/serato500-usb-arrival-20261102-decompile.log';text=log.read_text(encoding='utf-8')
    require(all(s in text for s in ['Loaded 0 additional files','Discarded file import due to readOnly option','Import succeeded']),'Read-only import not verified')
    require(not list((ROOT/'analysis/ghidra-usb-arrival-20261102').iterdir()),'Temporary project remains')
    source=['scripts/export-serato-usb-arrival.py','scripts/export-serato-clock-handshake-evidence.py','scripts/ghidra/FocusedDecompile.java']
    result={'schema':'sl3.serato-usb-arrival.v1','binarySha256':app.sha,'installedMatches':True,'checkedInstructions':facts,
      'priorPrimaryPointerSha256':sha(prior_path),'priorInstructionBytesRechecked':len(prior['checkedInstructions']),
      'rttiTables':tables,'completeHelperLeaves':leaves,
      'actionBridge':{'selectedWorkerPredicate':'0x140c00af0','nonzeroSelects':0,'zeroSelects':8,'ordinalMember':'0x28',
          'actionZeroSwitchCase':'0x1421de955','observerSlot':'0x08','observerTarget':'0x14213dd20',
          'scheduledCallback':'0x14213ddc0','observerToCompleteObjectAdjustment':-136,'schedulerDeliveryObserved':False},
      'selectedArrivalProducer':{'callback':'0x14213ddc0','requiresAbsentComponentMembers':['0x0 HID','0x10 MIDI'],
          'presenceHelpers':['0x140c00ad0','0x140c00ab0'],'message':'0x2d4','payload':'Packed scalar assembled in checked local branch',
          'otherProducerBranchesExhausted':False,'allPayloadWordProvenanceExhausted':False,'actualSl3PathObserved':False},
      'versionPredicate':{'method':'0x140c00af0','descriptorSlot':'0x60','concreteCompleteField':'0xd8',
          'source':'firmware_check.minimum_version_number','comparison':'Connection-derived DWORD >= required DWORD, unsigned',
          'neitherConnectionBranchResult':True,'actualDeviceVersionVerified':False,'firmwareWritten':False,
          'notAFullComponentOrAdmissionPredicate':True},
      'usbHelperReturn':{'method':'0x14070ff10','stateBytes':['0x70','0x71'],'return':'Nonzero first byte OR nonzero second byte',
          'constructorInitialValue':0,'stateMessages':{'0x692':'complete object +0x70','0x693':'complete object +0x71'},
          'messageValue':'Low byte from message virtual +0x10, exchanged into corresponding state byte',
          'serviceSlots':['0xa0','0x90'],'serviceResultPublishedAs':'0x693','serviceResultDirectlyReturned':False,
          'dispatchSynchronousOrAsynchronousEstablished':False,'meaningAsActualAudioReadinessEstablished':False},
      'freshFocusedFunctions':len(found),'focusedReportSha256':sha(path),'focusedLogSha256':sha(log),'reusedFocusedFunctions':reused,
      'focusedRanges':[{'start':hex(lo),'endExclusive':hex(hi),'sha256':hashlib.sha256(app.data(lo,hi-lo)).hexdigest()} for lo,hi in sorted(expected)],
      'temporaryProjectAbsent':True,'localSourceSha256':{n:sha(ROOT/n) for n in source},
      'publishedSourceSha256':{n:hashlib.sha256((ROOT/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in source},
      'applicationExecuted':False,'applicationModified':False,'deviceAccess':False,'messageInjected':False,'firmwareOrVersionPolicyModified':False,
      'otherDeviceIdentityAdopted':False,'currentSl3AdmissionVerified':False,'audioOpened':False,'twoDeckDvsVerified':False,
      'limits':['Selected conditional action-zero and USB-only emission branch; prior support/component acquisition, scheduler delivery and every producer are not exhausted.',
                'The original SL3 discontinued support path is unchanged; reaching a local callback is not an observed working connection.',
                'The version predicate is not a full component count, hardware readiness, firmware-update instruction or licensing result.',
                'State messages may update the helper result; delivery timing, service identity, full backend selection and genuine physical audio remain unverified.',
                'Packed scalar field provenance beyond the selected composition is not exhaustively traced; no physical USB revision is inferred.',
                'No descriptor, firmware threshold, state message, account, resource, device identity or security setting was altered.']}
    out=ROOT/'docs/evidence/serato500-usb-arrival.json';out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'verified':True,'instructionFacts':len(facts),'priorInstructionBytesRechecked':len(prior['checkedInstructions']),
        'rttiTables':len(tables),'completeHelperLeaves':len(leaves),'freshFocusedFunctions':len(found),
        'reusedFocusedFunctions':len(reused),'actionZeroMappingVerified':True,'currentSl3AdmissionVerified':False}))

if __name__=='__main__':main()
