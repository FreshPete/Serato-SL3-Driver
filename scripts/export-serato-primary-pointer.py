"""Verify primary-pointer registration identity and one USB-only publisher; no app/device execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    spec=importlib.util.spec_from_file_location('primary_pointer_image',ROOT/'scripts/export-serato-clock-handshake-evidence.py')
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);require=h.require
    app=h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe',h.CURRENT_SHA)
    require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe'))==app.sha,'Installed image differs')
    priors=[]
    for file,expected in [('serato500-descriptor-precedence.json','90aa41ffa9f65fdf4f4f8a4061771a74cc2c978db6cc77365e6dbab34d465613'),
                          ('serato500-wireless-notification.json','bee28d9c16b428ba3431e8e2fe88cbf607e4d5d8d63f870379ae5a4e755416f1')]:
        path=ROOT/'docs/evidence'/file;require(sha(path)==expected,'Prior report changed')
        value=json.loads(path.read_text(encoding='utf-8'));require(value['binarySha256']==app.sha,'Prior image differs')
        for row in value['checkedInstructions']:
            if isinstance(row,str):
                address,expected_assembly=row.split(': ',1);actual=app.at(int(address,16))
                require(actual.mnemonic+' '+actual.op_str==expected_assembly,'Prior instruction assembly differs')
            else:
                raw=bytes.fromhex(row['bytes']);require(app.data(int(row['va'],16),len(raw))==raw,'Prior instruction bytes differ')
        priors.append({'file':file,'sha256':expected,'instructionsRechecked':len(value['checkedInstructions'])})
    checks=[
      (0x1405033f2,'mov rdi, rcx'),(0x1405033f5,'xor esi, esi'),(0x14050340d,'lea rax, [rip + 0x2305074]'),
      (0x140503414,'mov qword ptr [rdi], rax'),(0x140503462,'mov qword ptr [rdi + 0xd8], rsi'),
      (0x140503469,'mov qword ptr [rdi + 0xe0], rsi'),(0x140503477,'mov qword ptr [rdi + 0xf0], rsi'),
      (0x140503492,'mov edx, 0x2ca'),(0x140503497,'mov rcx, rdi'),(0x14050349a,'call 0x14154cd50'),
      (0x1405056b6,'cmp dword ptr [rdx + 0xc], 0x2ca'),(0x1405056bd,'mov rbx, rcx'),
      (0x1405056c0,'jne 0x1405057a8'),(0x1405056c6,'mov rax, qword ptr [rdx]'),(0x1405056c9,'mov rcx, rdx'),
      (0x1405056d9,'call qword ptr [rax + 0x38]'),(0x1405056dc,'mov rsi, rax'),(0x1405056df,'test rax, rax'),
      (0x1405056e2,'je 0x14050573d'),(0x1405056e4,'mov rcx, qword ptr [rip + 0x39a6b0d]'),
      (0x1405056eb,'call 0x1404d10d0'),(0x1405056f0,'test al, al'),(0x1405056f2,'jne 0x14050579b'),
      (0x1405056f8,'xor edi, edi'),(0x1405056fa,'mov rdx, rsi'),(0x1405056fd,'mov rcx, rbx'),
      (0x140505700,'mov qword ptr [rbx + 0xf0], rdi'),(0x140505707,'call 0x140505900'),
      (0x14050570c,'lea rcx, [rbx + 0x90]'),(0x140505713,'xor r8d, r8d'),(0x140505716,'mov edx, 1'),
      (0x14050571b,'call 0x14154c060'),(0x140505727,'lea rdx, [rsi + 0x28]'),(0x140505730,'call 0x1404a3300'),
      (0x140505738,'mov rcx, rbx'),(0x14050573b,'jmp 0x14050577e'),(0x14050573d,'xor edi, edi'),
      (0x14050573f,'lea rcx, [rbx + 0x90]'),(0x140505749,'mov qword ptr [rbx + 0xf0], rdi'),
      (0x140505750,'xor edx, edx'),(0x140505752,'call 0x14154c060'),
      (0x14050578d,'mov edx, 0x2d3'),(0x140505796,'call 0x1404d0d70'),
      (0x14050591e,'mov rdi, rdx'),(0x140505921,'mov rsi, rcx'),(0x140505924,'mov rax, qword ptr [rcx + 0xd8]'),
      (0x14050592b,'mov r8, qword ptr [rcx + 0xe0]'),(0x140505932,'cmp rax, r8'),(0x140505935,'je 0x140505955'),
      (0x140505940,'mov rcx, qword ptr [rax]'),(0x140505943,'cmp rcx, rdi'),(0x140505946,'je 0x140505a49'),
      (0x14050594c,'add rax, 0x10'),(0x140505950,'cmp rax, r8'),(0x140505953,'jne 0x140505940'),
      (0x140505a1f,'mov qword ptr [rsi + 0xf0], 0'),(0x140505a49,'mov qword ptr [rsi + 0xf0], rcx'),
      (0x140505a50,'jmp 0x140505a2a'),
      (0x1407108e6,'mov r8d, dword ptr [rdx + 0xc]'),(0x1407108ea,'mov rdi, rcx'),
      (0x1407108ed,'sub r8d, 0x2d4'),(0x1407108f4,'je 0x1407109a1'),
      (0x1407109a1,'mov rax, qword ptr [rdx]'),(0x1407109a4,'mov rcx, rdx'),(0x1407109a7,'call qword ptr [rax + 0x38]'),
      (0x1407109aa,'mov rcx, rax'),(0x1407109ad,'movzx r9d, ax'),(0x1407109b1,'shr rcx, 0x10'),
      (0x1407109b5,'shr rax, 0x20'),(0x1407109b9,'movzx r8d, cx'),(0x1407109bd,'lea rcx, [rdi - 0x10]'),
      (0x1407109c1,'movzx edx, ax'),(0x1407109c9,'jmp 0x1407100b0'),
      (0x1407100d0,'mov r15d, r9d'),(0x1407100d3,'mov r14d, r8d'),(0x1407100d6,'mov esi, edx'),
      (0x1407100d8,'mov rdi, rcx'),(0x1407100db,'xor r12d, r12d'),
      (0x14071013a,'mov r9d, r15d'),(0x14071013d,'mov r8d, r14d'),(0x140710140,'mov edx, esi'),
      (0x140710142,'mov rcx, qword ptr [rip + 0x379c087]'),(0x140710149,'call 0x140505360'),
      (0x14071014e,'mov rbx, rax'),(0x140710151,'cmp dword ptr [rax + 0x154], r12d'),
      (0x140710158,'je 0x1407101d2'),(0x1407101cd,'jmp 0x140710285'),
      (0x1407101d2,'mov r9d, r15d'),(0x1407101d5,'mov r8d, r14d'),(0x1407101d8,'mov edx, esi'),
      (0x1407101da,'mov rcx, rdi'),(0x1407101dd,'call 0x14070ff10'),(0x1407101e2,'test al, al'),
      (0x1407101e4,'je 0x140710285'),(0x140710271,'mov r8, rbx'),(0x140710274,'mov edx, 0x2ca'),
      (0x140710279,'mov rcx, qword ptr [rip + 0x379c748]'),(0x140710280,'call 0x1404db170'),
      (0x1404db187,'mov rsi, r8'),(0x1404db18a,'mov ebp, edx'),(0x1404db18c,'mov rbx, rcx'),
      (0x1404db1c9,'mov r8, rsi'),(0x1404db1cc,'mov edx, ebp'),(0x1404db1d1,'call 0x14185ee90'),
      (0x1404db1f0,'call qword ptr [rax + 0x58]')]
    facts=[]
    for va,expected in checks:
        r=app.at(va);require(r.mnemonic+' '+r.op_str==expected,'Instruction differs at '+hex(va))
        facts.append({'va':hex(va),'bytes':bytes(r.bytes).hex(),'assembly':expected})
    require(app.rip(app.at(0x140710142))==0x143eac1d0 and app.rip(app.at(0x140710279))==0x143eac9c8,'Manager/sink globals differ')
    # Register preservation is scoped to the zero-kind publishing branch, not its rejected-kind logging branch.
    aliases={h.capstone.x86.X86_REG_RBX,h.capstone.x86.X86_REG_EBX,h.capstone.x86.X86_REG_BX,h.capstone.x86.X86_REG_BL,h.capstone.x86.X86_REG_BH}
    require(not any(set(r.regs_access()[1])&aliases for r in app.function(0x1407100b0) if 0x1407101d2<=r.address<0x140710271),
            'Lookup result overwritten on publishing branch')
    tables=[]
    for table,name,offset,slots in [(0x142808488,'.?AVPrimaryDeviceManager@@',0,{0x18:0x1405056b0,0x30:0x140505500}),
       (0x142843168,'.?AVCUSBAudioManager@@',16,{0x18:0x1407108e0}),
       (0x142fbf4b8,'.?AVUserIO_VoidPtrMessageData@data@message@serato@@',0,{0x38:0x140790070})]:
        locator=struct.unpack('<Q',app.data(table-8,8))[0];col=struct.unpack('<6I',app.data(locator,24))
        require(col[0]==1 and col[1]==offset and app.base+col[5]==locator and app.text(app.base+col[3]+16)==name,'RTTI differs')
        for slot,target in slots.items():require(struct.unpack('<Q',app.data(table+slot,8))[0]==target,'Concrete slot differs')
        tables.append({'table':hex(table),'type':name,'completeObjectOffset':offset,'slots':{hex(k):hex(v) for k,v in slots.items()}})
    leaves=[]
    for va,length,expected in [(0x140505500,8,[('mov','rax, qword ptr [rcx + 0xf0]'),('ret','')]),
       (0x1404d10d0,8,[('movzx','eax, byte ptr [rcx + 0x319]'),('ret','')]),
       (0x140790070,5,[('mov','rax, qword ptr [rcx + 0x38]'),('ret','')])]:
        raw=app.data(va,length);decoded=list(app.dis.disasm(raw,va))
        require([(r.mnemonic,r.op_str) for r in decoded]==expected,'Complete getter differs')
        leaves.append({'start':hex(va),'bytes':raw.hex(),'instructions':[op+' '+args for op,args in expected]})
    logical=(0x1405056b0,0x1405057ae)
    fragments=[(0x1405056b0,0x1405056cc),(0x1405056cc,0x1405057a8),(0x1405057a8,0x1405057ae)]
    require(all(span in app.spans for span in fragments) and all(a[1]==b[0] for a,b in zip(fragments,fragments[1:])), 'Handler fragment union differs')
    path=ROOT/'analysis/serato500-primary-store-20261102-decompile.json';focused=json.loads(path.read_text(encoding='utf-8-sig'))
    expected={(0x1405033d0,0x1405035cd),logical,(0x140505900,0x140505ad4),
              (0x1407100b0,0x1407103a8),(0x14070ff10,0x1407100a4),(0x1404db170,0x1404db209)}
    found=set();require(focused['binary_sha256']==app.sha,'Focused image differs')
    for row in focused['functions']:
        span=(int(row['start'],16),int(row['end_exclusive'],16))
        require(span in expected and (span in app.spans or span==logical) and span not in found and row.get('complete') is True and
                row.get('pseudocode') and not row.get('diagnostic'),'Focused range differs/incomplete');found.add(span)
    require(found==expected,'Focused function set differs')
    log=ROOT/'analysis/serato500-primary-store-20261102-decompile.log';text=log.read_text(encoding='utf-8')
    require(all(s in text for s in ['Loaded 0 additional files','Discarded file import due to readOnly option','Import succeeded']),'Read-only import not verified')
    require(not list((ROOT/'analysis/ghidra-primary-store-20261102').iterdir()),'Temporary project remains')
    source=['scripts/export-serato-primary-pointer.py','scripts/export-serato-clock-handshake-evidence.py','scripts/ghidra/FocusedDecompile.java']
    result={'schema':'sl3.serato-primary-pointer.v1','binarySha256':app.sha,'installedMatches':True,'checkedInstructions':facts,
      'priorEvidence':priors,'rttiTables':tables,'completeGetterLeaves':leaves,
      'pointerStore':{'manager':'PrimaryDeviceManager','getterSlot':'0x30','member':'0xf0','setter':'0x140505900',
         'vectorBegin':'0xd8','vectorEnd':'0xe0','stride':16,'acceptance':'Exact pointer identity with first QWORD of a registered vector entry',
         'miss':'Clear +0xf0; diagnostic path','sameIdentityFieldsSufficient':False,'successfulStoreBlockPerformsUsbOrAudioOperation':False},
      'messageHandler':{'id':'0x2ca','method':'0x1405056b0','payloadGetterSlot':'0x38','nullPayload':'Clear pointer, update state with zero and send 0x2d3',
         'nonnullExclusionGetter':'0x1404d10d0','exclusionField':'0x319','exclusionFieldMeaningEstablished':False,
         'excludedNonnullPayload':'Leave this handler before pointer/state update','otherNonnullPayload':'Clear pointer, call identity-checked setter, update state with one, send 0x2d3',
         'stateUpdateDoesNotIndependentlyProvePointerAccepted':True},
      'selectedUsbOnlyProducer':{'concreteManager':'CUSBAudioManager','incomingMessage':'0x2d4','case':'0x1407109a1',
         'callback':'0x1407100b0','identity':'VID/PID/revision from packed scalar','numericLookup':'0x140505360',
         'requiredDescriptorKindAtOffset154':0,'requiredHelperTrue':'0x14070ff10','publisher':'0x1404db170',
         'publishedMessage':'0x2ca','publishedPayload':'Same descriptor pointer returned by numeric lookup',
         'priorSupportOrComponentGatesExhausted':False,'physicalCallObserved':False},
      'focusedFunctions':len(found),'logicalHandlerUnwindFragments':[[hex(lo),hex(hi)] for lo,hi in fragments],
      'focusedRanges':[{'start':hex(lo),'endExclusive':hex(hi),'sha256':hashlib.sha256(app.data(lo,hi-lo)).hexdigest(),
                         'logicalUnionOfThreeUnwindFragments':(lo,hi)==logical} for lo,hi in sorted(expected)],
      'focusedReportSha256':sha(path),'focusedLogSha256':sha(log),'temporaryProjectAbsent':True,
      'localSourceSha256':{n:sha(ROOT/n) for n in source},'publishedSourceSha256':{n:hashlib.sha256((ROOT/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in source},
      'applicationExecuted':False,'applicationModified':False,'deviceAccess':False,'messageInjected':False,'descriptorInserted':False,
      'otherDeviceIdentityAdopted':False,'currentSl3AdmissionVerified':False,'audioOpened':False,'twoDeckDvsVerified':False,
      'limits':['Selected local writer and one matching publisher only; all pointer writers, message producers, dynamic receivers and prior eligibility paths are not exhausted.',
                'A nonzero stored pointer or local state update is not support, account entitlement, audio readiness, verified HID or working DVS.',
                'Zero kind and a successful helper are conditional producer gates, not an observed execution on the discontinued SL3 stub.',
                'The helper has service/notification dependencies; its full audio and backend result remains unverified.',
                'A matching VID/PID or an independently allocated equal descriptor does not satisfy exact registered-pointer membership; no injection route is provided.']}
    out=ROOT/'docs/evidence/serato500-primary-pointer.json';out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'verified':True,'instructionFacts':len(facts),'priorInstructionChecks':sum(v['instructionsRechecked'] for v in priors),
                     'rttiTables':len(tables),'completeGetterLeaves':len(leaves),'focusedFunctions':len(found),
                     'handlerUnwindFragments':len(fragments),'currentSl3AdmissionVerified':False}))

if __name__=='__main__':main()
