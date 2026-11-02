"""Verify HID success-message wireless handling; publish no keys or HID protocol data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def main():
    h=load('wireless_image','export-serato-clock-handshake-evidence.py');require=h.require
    app=h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe',h.CURRENT_SHA)
    require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe'))==app.sha,'Installed image differs')
    prior_path=ROOT/'docs/evidence/serato500-hid-task.json'
    require(sha(prior_path)=='10325f3dc77cc2726bd273ffc15d6ec841422a5d8189dde156bea25c3d47e98f','Prior HID task proof differs')
    prior=json.loads(prior_path.read_text(encoding='utf-8'))
    for row in prior['checkedInstructions']:
        require(app.data(int(row['va'],16),len(bytes.fromhex(row['bytes']))).hex()==row['bytes'],'Prior instruction changed')
    facts=[]
    checks=[
        (0x140627b6f,'xor ebp, ebp'),(0x140627bdb,'lea rsi, [rax + 0x10]'),(0x140627bdf,'test rax, rax'),(0x140627be2,'cmove rsi, rbp'),
        (0x140627be6,'mov rdi, qword ptr [rip + 0x3884ddb]'),(0x140627c12,'mov edx, 0x2e3'),(0x140627c1a,'call 0x14185ec90'),
        (0x140627c1f,'lea rax, [rip + 0x21fde1a]'),(0x140627c26,'mov qword ptr [rbx], rax'),
        (0x140627c29,'mov qword ptr [rbx + 0x38], rsi'),(0x140627c2d,'mov dword ptr [rbx + 8], 5'),(0x140627c4e,'call qword ptr [rax + 0x58]'),
        (0x14185ecc2,'mov dword ptr [rcx + 0xc], edx'),(0x14185ecc5,'mov dword ptr [rcx + 0x10], r8d'),
        (0x1405db210,'mov rsi, rcx'),(0x1405db213,'mov rdx, qword ptr [rip + 0x38d17ae]'),(0x1405db21a,'call 0x14154c960'),
        (0x1405db239,'lea rax, [rip + 0x2244d20]'),(0x1405db240,'mov qword ptr [rsi], rax'),
        (0x1405db4af,'mov edx, 0x2e3'),(0x1405db4b4,'mov rcx, rsi'),(0x1405db4b7,'call 0x14154cd50'),
        (0x1405df4a8,'mov rsi, rdx'),(0x1405df4ab,'mov rbx, rcx'),(0x1405df4be,'mov ecx, dword ptr [rdx + 0xc]'),
        (0x1405df4c1,'cmp ecx, 0x1fc'),(0x1405df4c7,'jg 0x1405df643'),(0x1405df643,'cmp ecx, 0x33b'),
        (0x1405df649,'jg 0x1405e124d'),(0x1405df655,'sub ecx, 0x224'),(0x1405df65b,'cmp ecx, 0xd0'),
        (0x1405df661,'ja 0x1405e1619'),(0x1405df667,'movsxd rax, ecx'),(0x1405df66a,'lea rdx, [rip - 0x5df671]'),
        (0x1405df671,'movzx eax, byte ptr [rdx + rax + 0x5e16f0]'),(0x1405df679,'mov ecx, dword ptr [rdx + rax*4 + 0x5e1680]'),
        (0x1405df680,'add rcx, rdx'),(0x1405df683,'jmp rcx'),
        (0x1405e0bcb,'lea r9, [rip + 0x34b2f6e]'),(0x1405e0bd2,'lea r8, [rip + 0x34a8adf]'),
        (0x1405e0bdb,'mov rcx, rsi'),(0x1405e0bde,'call 0x142120260'),(0x1405e0be3,'test rax, rax'),(0x1405e0be6,'je 0x1405e0d10'),
        (0x1405e0bec,'mov r13, qword ptr [rax + 0x38]'),(0x1405e0bf0,'test r13, r13'),(0x1405e0bf3,'je 0x1405e1619'),
        (0x1405e0bf9,'mov rax, qword ptr [r13]'),(0x1405e0bfd,'mov rcx, r13'),(0x1405e0c00,'call qword ptr [rax + 0x40]'),
        (0x1405e0c03,'test al, al'),(0x1405e0c05,'je 0x1405e1619'),(0x1405e0c28,'mov edx, 0x637'),
        (0x1405e0c30,'call 0x14154e400'),(0x1405e0c3f,'call rdx'),(0x1405e0c41,'mov edi, eax'),
        (0x1405e0c4d,'neg edi'),(0x1405e0c4f,'sbb edi, edi'),(0x1405e0c51,'and edi, 2'),(0x1405e0c54,'mov esi, edi'),
        (0x1405e0c5d,'call qword ptr [rax + 0x50]'),(0x1405e0c60,'add eax, edi'),(0x1405e0c62,'cmp edi, eax'),(0x1405e0c64,'jge 0x1405e0cfc'),
        (0x1405e0c6f,'mov edi, 1'),(0x1405e0c74,'mov ebx, esi'),
        (0x1405e0cb2,'mov r9d, esi'),(0x1405e0cb5,'mov r8d, edi'),(0x1405e0cb8,'mov edx, 0x580'),
        (0x1405e0cc0,'call 0x14185ec00'),(0x1405e0ce1,'call qword ptr [rax + 0x58]'),(0x1405e0ce5,'inc esi'),
        (0x1405e0cee,'call qword ptr [rax + 0x50]'),(0x1405e0cf1,'add eax, ebx'),(0x1405e0cf3,'cmp esi, eax'),(0x1405e0cf5,'jl 0x1405e0c80'),
        (0x1405e0cfc,'mov byte ptr [rbx + 0x171], 1'),(0x1405e0d06,'call 0x1405e2af0'),(0x1405e0d0b,'jmp 0x1405e1619'),
        (0x14185ec0e,'mov r10d, r9d'),(0x14185ec16,'mov ebx, r8d'),(0x14185ec1d,'mov r8d, r10d'),
        (0x14185ec2b,'call 0x14185ec90'),(0x14185ec30,'lea rax, [rip + 0x16f3909]'),(0x14185ec37,'mov dword ptr [rdi + 0x38], ebx'),
        (0x1405c7fe0,'mov rsi, rcx'),(0x1405c8365,'xor edi, edi'),(0x1405c843b,'mov byte ptr [rsi + 0x128], dil'),
        (0x1405c8442,'lea rdx, [rip + 0x2255cf7]'),(0x1405c844c,'call 0x141b17da0'),
        (0x1405c8463,'call 0x141b17690'),(0x1405c8468,'mov byte ptr [rsi + 0x128], al'),
        (0x1405c9877,'mov dword ptr [rsi + 0x47c], r15d'),(0x1405c987e,'lea rdx, [rip + 0x2254003]'),
        (0x1405c9888,'call 0x141b17da0'),(0x1405c989f,'call 0x141b17620'),(0x1405c98a7,'call qword ptr [rip + 0x216d12b]'),
        (0x1405c98ad,'mov dword ptr [rsi + 0x47c], eax'),
        (0x1404c0d2b,'call 0x1405033d0'),(0x1404c0d35,'mov qword ptr [rip + 0x39eb494], rax'),
        (0x1405033f2,'mov rdi, rcx'),(0x14050340d,'lea rax, [rip + 0x2305074]'),(0x140503414,'mov qword ptr [rdi], rax'),
        (0x1405035b3,'mov rax, rdi'),(0x1405e2af9,'mov rcx, qword ptr [rip + 0x38c96d0]'),
        (0x1405e2b03,'call qword ptr [rax + 0x30]'),(0x1405e2b06,'test rax, rax'),(0x1405e2b09,'je 0x1405e2b7d'),
        (0x1405e2b0b,'cmp byte ptr [rbx + 0x171], 0'),(0x1405e2b12,'je 0x1405e2b7d'),
        (0x1405e2b14,'cmp byte ptr [rbx + 0x94], 0'),(0x1405e2b1b,'je 0x1405e2b7d'),
        (0x1405e2b1d,'cmp dword ptr [rax + 0x464], 0'),(0x1405e2b24,'je 0x1405e2b7d'),
        (0x1405e2b26,'mov ecx, dword ptr [rax + 0x46c]'),(0x1405e2b2e,'cmp ecx, 4'),(0x1405e2b31,'jge 0x1405e2b66'),
        (0x1405e2b3a,'mov dword ptr [rbx + 0x174], 1'),(0x1405e2b4e,'mov edx, 0x637'),(0x1405e2b5b,'call 0x1404bcce0'),
        (0x1405e2b66,'cmp ecx, 4'),(0x1405e2b69,'mov edx, 2'),(0x1405e2b6e,'cmove eax, edx'),
        (0x1405e2b71,'mov dword ptr [rbx + 0x174], eax'),(0x1405e2b7d,'xor eax, eax'),(0x1405e2b7f,'mov dword ptr [rbx + 0x174], eax')]
    for va,expected in checks:
        r=app.at(va);require(r.mnemonic+' '+r.op_str==expected,'Instruction differs at '+hex(va))
        facts.append({'va':hex(va),'bytes':bytes(r.bytes).hex(),'assembly':expected})
    sink=app.rip(app.at(0x140627be6));require(sink==app.rip(app.at(0x1405db213))==0x143eac9c8,'Sink global differs')
    require(app.rip(app.at(0x1404c0d35))==app.rip(app.at(0x1405e2af9))==0x143eac1d0,'Primary manager global differs')
    index=app.data(0x1405e16f0+0x2e3-0x224,1)[0]
    target=app.base+struct.unpack('<I',app.data(0x1405e1680+4*index,4))[0]
    require(index==20 and target==0x1405e0bc6 and app.rip(app.at(0x1405df66a))==app.base,'Message switch differs')
    names=[(0x1405c8442,'is_wireless_device'),(0x1405c987e,'num_wireless_decks')]
    for va,name in names:require(app.text(app.rip(app.at(va)))==name,'Parser field name differs')
    tables=[]
    for table,name,offset,slots in [
      (0x142825a40,'.?AV?$UserIO_TemplateMessageData@PEBVDeviceDescriptor@composite@device@serato@@@data@message@serato@@',0,{}),
      (0x14281ff60,'.?AVCUserIOConnectionControl@@',0,{0x18:0x1405df470}),
      (0x14281caf0,'.?AVControllerDescriptor@dj@serato@@',16,{0x40:0x1405c7f80,0x50:0x1405c6ff0}),
      (0x142808488,'.?AVPrimaryDeviceManager@@',0,{0x30:0x140505500}),
      (0x142f52540,'.?AVUserIO_IntMessageData@data@message@serato@@',0,{})]:
        locator=struct.unpack('<Q',app.data(table-8,8))[0];col=struct.unpack('<6I',app.data(locator,24))
        require(col[0]==1 and col[1]==offset and app.base+col[5]==locator and app.text(app.base+col[3]+16)==name,'RTTI differs')
        for slot,method in slots.items():require(struct.unpack('<Q',app.data(table+slot,8))[0]==method,'Slot differs')
        tables.append({'table':hex(table),'type':name,'completeObjectOffset':offset,'slots':{hex(k):hex(v) for k,v in slots.items()}})
    require(app.text(app.rip(app.at(0x1405e0bcb))+16)==tables[0]['type'] and
            app.text(app.rip(app.at(0x1405e0bd2))+16)=='.?AVUserIO_MessageData@data@message@serato@@','Message cast type differs')
    for va,table in [(0x140627c1f,0x142825a40),(0x1405db239,0x14281ff60),(0x14050340d,0x142808488),(0x14185ec30,0x142f52540)]:require(app.rip(app.at(va))==table,'Concrete table installation differs')
    leaves=[]
    for va,length,expected in [(0x1405c7f80,8,[('movzx','eax, byte ptr [rcx + 0x118]'),('ret','')]),
                               (0x1405c6ff0,7,[('mov','eax, dword ptr [rcx + 0x46c]'),('ret','')]),
                               (0x140505500,8,[('mov','rax, qword ptr [rcx + 0xf0]'),('ret','')])]:
        raw=app.data(va,length);decoded=list(app.dis.disasm(raw,va))
        require([(r.mnemonic,r.op_str) for r in decoded]==expected,'Complete getter differs')
        leaves.append({'start':hex(va),'bytes':raw.hex(),'instructions':[op+' '+args for op,args in expected]})
    archive_module=load('wireless_archive','inspect-serato-resource-archive.py')
    archive_path=(ROOT/archive_module.APP_RELATIVE).with_name('userio_resources.bin');archive=archive_path.read_bytes()
    require(sha(archive_path)==archive_module.ARCHIVE_SHA and Path('C:/Program Files/Serato/Serato DJ Pro/userio_resources.bin').read_bytes()==archive,'Archive differs')
    seed=app.data(0x142f2de98,16)
    key=struct.unpack('<4I',bytes((((x^0xcf)>>(n&7))|((x^0xcf)<<((8-(n&7))&7)))&255 for n,x in enumerate(seed)))
    size=struct.unpack_from('<Q',archive)[0];entries=archive_module.parse_index(archive_module.decode_block(archive[8:8+size],key),len(archive),8+size)
    selected=[e for e in entries if e['name']=='hid/hid_mwm_phase.xml'];require(len(entries)==229 and len(selected)==1,'Profile inventory differs')
    entry=selected[0];data,crc=archive_module.unpack_member(archive[entry['offset']:entry['offset']+entry['size']],key,entry['name'])
    safe=re.sub(rb'<!DOCTYPE\s+[A-Za-z_][A-Za-z0-9_.:-]*\s*>',b'',data,flags=re.I)
    require(b'<!DOCTYPE' not in safe.upper() and b'<!ENTITY' not in safe.upper(),'Unsupported XML declaration')
    document=ET.fromstring(safe);nodes=[n for n in document.iter() if n.tag in ('native_pro_device','native_intro_device','osa_device')]
    require(len(nodes)==1 and nodes[0].tag=='osa_device' and document.find('hid') is not None,'Phase kind/section differs')
    values={}
    for name,expected in [('is_wireless_device','true'),('num_wireless_decks','2')]:
        rows=nodes[0].findall(name);require(len(rows)==1 and rows[0].get('value')==expected,'Allowlisted Phase field differs');values[name]=expected
    focused_path=ROOT/'analysis/serato500-wireless-notification-20261102-final-decompile.json';focused=json.loads(focused_path.read_text(encoding='utf-8-sig'))
    expected={(0x1405db1e0,0x1405dcebf),(0x1405df470,0x1405e17c1),(0x1405e2af0,0x1405e2b8b),(0x14185ec00,0x14185ec52),(0x14185ec90,0x14185ecdf)}
    require(focused['binary_sha256']==app.sha,'Focused image differs');found=set()
    for row in focused['functions']:
        span=(int(row['start'],16),int(row['end_exclusive'],16))
        require(span in expected and span in app.spans and span not in found and row.get('complete') is True and
                row.get('pseudocode') and not row.get('diagnostic'),'Focused function differs/incomplete');found.add(span)
    require(found==expected,'Focused set differs')
    log=ROOT/'analysis/serato500-wireless-notification-20261102-final-decompile.log';text=log.read_text(encoding='utf-8')
    require(all(s in text for s in ['Loaded 0 additional files','Discarded file import due to readOnly option','Import succeeded']),'Focused read-only import not verified')
    require(not list((ROOT/'analysis/ghidra-wireless-notification-20261102-final').iterdir()),'Temporary project remains')
    source=['scripts/export-serato-wireless-notification.py','scripts/export-serato-clock-handshake-evidence.py','scripts/inspect-serato-resource-archive.py','scripts/ghidra/FocusedDecompile.java']
    result={'schema':'sl3.serato-wireless-notification.v1','binarySha256':app.sha,'installedMatches':True,'checkedInstructions':facts,
      'priorHidTaskSha256':sha(prior_path),'priorInstructionBytesRechecked':len(prior['checkedInstructions']),
      'message':{'id':'0x2e3','distinctTypeFieldAtOffset8':5,'payloadAtOffset38':'descriptor interface pointer, complete object +16',
                 'sinkGlobal':hex(sink),'subscriber':'CUserIOConnectionControl','handler':'0x1405df470','switchIndex':index,'case':hex(target)},
      'rttiTables':tables,'completeGetterLeaves':leaves,
      'wirelessDescriptorFields':{'receiverCompleteObjectOffset':16,'slot40':{'completeField':'0x128','xmlName':'is_wireless_device'},
                                  'slot50':{'completeField':'0x47c','xmlName':'num_wireless_decks'},'otherConcreteImplementationsExhausted':False},
      'caseActions':{'requiresNonNullCastAndPayload':True,'requiresSlot40Nonzero':True,'queryId':'0x637','loopStart':'0 if queried integer is zero, otherwise 2',
                     'loopCountSource':'slot +0x50, reevaluated at loop edge','publishedMessage':'0x580','integerPayload':1,
                     'indexParameter':'current loop index','connectionControlFlagSet':'0x171','thenCalls':'0x1405e2af0'},
      'updateHelper':{'primaryManagerGlobal':'0x143eac1d0','getterSlot':'0x30','concreteGetterStoredPointer':'0xf0',
                      'requiresNonNullStoredPointer':True,'requiredControllerBytes':['0x171','0x94'],'requiredReturnedObjectDwordNonzero':'0x464',
                      'deckCountComparedAt':'0x46c','stateField':'0x174','state':'0 if a gate fails; otherwise 1 below four decks, 2 at four, 0 above four',
                      'actualReturnedDescriptorOrAccountStateObserved':False},
      'phaseProjection':{'resource':entry['name'],'kind':nodes[0].tag,'rootHidSection':True,'fields':values,'xmlSha256':hashlib.sha256(data).hexdigest(),
                         'selectedMemberCrc32':crc,'selectedMemberCrcVerified':True,'archiveSha256':archive_module.ARCHIVE_SHA,'resourceEntries':len(entries),'runtimeStatePrediction':False},
      'focusedFunctions':len(found),'focusedReportSha256':sha(focused_path),'focusedLogSha256':sha(log),'temporaryProjectAbsent':True,
      'functionExtents':[{'start':hex(lo),'endExclusive':hex(hi),'sha256':hashlib.sha256(app.data(lo,hi-lo)).hexdigest()} for lo,hi in sorted(expected)],
      'localSourceSha256':{n:sha(ROOT/n) for n in source},'publishedSourceSha256':{n:hashlib.sha256((ROOT/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in source},
      'applicationExecuted':False,'applicationModified':False,'deviceAccess':False,'authenticationMaterialExported':False,
      'phaseConnectedOrVerified':False,'otherDeviceIdentityAdopted':False,'currentSl3AdmissionVerified':False,'twoDeckDvsVerified':False,
      'limits':['Selected subscriber/handler and concrete getter implementations only; actual bus delivery and dynamic receivers remain unobserved.',
                'Message 0x580 payload/index is checked; its full consumers and physical deck/audio result remain outside this proof.',
                'The stored primary-manager pointer and raw field gates are checked; no successful account/product, DVS predicate or device admission is inferred.',
                'Phase metadata is an unchanged accessory declaration; it neither creates a primary SL3 description nor restores its discontinued support path.',
                'Only allowlisted field names/values and metadata are exported; no XML body, key, challenge or reply material is published.']}
    output=ROOT/'docs/evidence/serato500-wireless-notification.json';output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'verified':True,'instructionFacts':len(facts),'priorInstructionBytesRechecked':len(prior['checkedInstructions']),
                     'rttiTables':len(tables),'completeGetterLeaves':len(leaves),'switchMappings':1,'focusedFunctions':len(found),
                     'phaseAllowlistedFields':values,'currentSl3AdmissionVerified':False}))

if __name__=='__main__':main()
