"""Verify current HID task/control flow; export no keys, message bytes or reply algorithm."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def main():
    h=load('hid_task_image','scripts/export-serato-clock-handshake-evidence.py');require=h.require
    app=h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe',h.CURRENT_SHA)
    require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe'))==app.sha,'Installed image differs')
    priors=[]
    for file,expected in [('serato500-hid-verifier.json','ae44188b3f0e7517340125626a32849760f4f96a210d18cacc2f0d3d171753f8'),
                          ('serato500-midi-field-sources.json','8fbeb191ebd822716a0990631b2781330d5feb32e0a23a13f1f7236eaeebafde')]:
        path=ROOT/'docs/evidence'/file;require(sha(path)==expected,'Prior evidence changed')
        prior=json.loads(path.read_text(encoding='utf-8'))
        require(prior.get('binarySha256',prior.get('applicationSha256'))==app.sha,'Prior image differs')
        for row in prior['checkedInstructions']:
            require(app.data(int(row['va'],16),len(bytes.fromhex(row['bytes']))).hex()==row['bytes'],'Prior instruction bytes differ')
        priors.append({'file':file,'sha256':expected,'instructionBytesRechecked':len(prior['checkedInstructions'])})
    facts=[]
    checks=[
        (0x140628c3a,'mov rdi, rcx'),(0x140628c3f,'cmp byte ptr [rcx + 0x1c], bl'),
        (0x140628c44,'xor edx, edx'),(0x140628c46,'mov rcx, qword ptr [rcx + 0x30]'),(0x140628c4a,'call 0x140627b60'),
        (0x140628c4f,'mov byte ptr [rdi + 0x1c], 1'),(0x140628c53,'mov ecx, 0x50'),
        (0x140628c93,'mov rax, qword ptr [rdi]'),(0x140628c96,'mov qword ptr [rsp + 0x20], rax'),
        (0x140628c9b,'mov rax, qword ptr [rdi + 8]'),(0x140628c9f,'mov qword ptr [rsp + 0x28], rax'),
        (0x140628ca4,'lea rdx, [rsp + 0x20]'),(0x140628cac,'call 0x1406282f0'),
        (0x140628cb4,'mov qword ptr [rdi + 0x48], rbx'),(0x140628cbe,'call qword ptr [rax + 0x20]'),
        (0x140628304,'mov rbx, rdx'),(0x140628307,'mov rdi, rcx'),(0x14062830a,'call 0x1405b2f20'),
        (0x14062830f,'lea rax, [rip + 0x21fd7da]'),(0x140628316,'mov qword ptr [rdi], rax'),
        (0x140628330,'mov rax, qword ptr [rbx]'),(0x140628333,'mov qword ptr [rdi + 0x40], rax'),
        (0x140628337,'mov rax, qword ptr [rbx + 8]'),(0x14062833b,'mov qword ptr [rdi + 0x48], rax'),
        (0x14062833f,'mov byte ptr [rdi + 0x3d], 1'),
        (0x1405b2ff6,'cmp byte ptr [rcx + 0x3c], 0'),(0x1405b2ffd,'jne 0x1405b3018'),
        (0x1405b2fff,'mov rdx, rcx'),(0x1405b3009,'call 0x1404db050'),(0x1405b300e,'mov byte ptr [rbx + 0x3c], 1'),
        (0x140628860,'cmp byte ptr [rcx + 0x10], dil'),(0x140628864,'jne 0x1406288f9'),
        (0x14062886a,'call 0x140628500'),(0x14062886f,'test al, al'),(0x140628871,'je 0x1406288f9'),
        (0x140628530,'cmp byte ptr [rcx + 0x10], sil'),(0x140628534,'je 0x14062853d'),
        (0x140628536,'mov al, 1'),(0x140628538,'jmp 0x14062873d'),
        (0x14062853d,'mov rcx, qword ptr [rcx + 0x30]'),(0x140628541,'call 0x140627140'),
        (0x140628546,'test al, al'),(0x140628548,'je 0x140628626'),(0x140628551,'call 0x1406287f0'),
        (0x140628556,'test al, al'),(0x140628558,'je 0x140628572'),
        (0x14062855a,'mov dl, 1'),(0x14062855c,'mov rcx, qword ptr [rdi + 0x30]'),(0x140628560,'call 0x140627b60'),
        (0x140628568,'call 0x140628ce0'),
        (0x140628621,'jmp 0x140628739'),(0x140628626,'mov ebx, dword ptr [rdi + 0x14]'),(0x140628629,'call qword ptr [rip + 0x210daf1]'),
        (0x14062862f,'sub eax, ebx'),(0x140628631,'cmp eax, 0x1388'),(0x140628636,'jbe 0x140628739'),
        (0x14062863c,'cmp dword ptr [rdi + 0x18], 0xc'),(0x140628640,'jge 0x140628704'),
        (0x1406286fd,'call 0x140628960'),(0x14062872a,'call 0x140628ce0'),
        (0x14062872f,'mov rcx, qword ptr [rdi + 0x30]'),(0x140628733,'mov rax, qword ptr [rcx]'),
        (0x140628736,'call qword ptr [rax + 0x10]'),(0x140628739,'movzx eax, byte ptr [rdi + 0x10]'),
        (0x140628830,'mov byte ptr [rdi + 0x10], 1'),(0x140628840,'movzx eax, bl'),
        (0x140628988,'mov rsi, rcx'),(0x14062898b,'mov rcx, qword ptr [rcx + 0x40]'),
        (0x140628993,'mov rdx, qword ptr [rcx + 0x168]'),(0x14062899a,'mov rcx, qword ptr [rcx + 0x160]'),
        (0x1406289a1,'call 0x1404fcb90'),(0x140628b40,'mov rcx, qword ptr [rsi + 0x20]'),
        (0x140628b44,'call 0x14069b930'),(0x140628b49,'call qword ptr [rip + 0x210d5d1]'),
        (0x140628b4f,'mov dword ptr [rsi + 0x14], eax'),(0x140628b52,'inc dword ptr [rsi + 0x18]'),
        (0x140628b55,'mov dl, 1'),(0x140628b57,'mov rcx, qword ptr [rsi + 0x30]'),(0x140628b5b,'call 0x140627c60'),
        (0x140627144,'add rcx, 0x8d'),(0x140627150,'movzx eax, byte ptr [rax]'),
        (0x140627b6c,'mov rsi, rcx'),(0x140627b71,'mov byte ptr [rsp + 0x58], dl'),
        (0x140627b75,'lea rcx, [rsp + 0x58]'),(0x140627b7a,'call 0x1404e6950'),(0x140627b7f,'movzx ebx, al'),
        (0x140627b82,'lea rcx, [rsi + 0x8e]'),(0x140627b89,'call 0x1404a2ee0'),(0x140627b8e,'xchg byte ptr [rax], bl'),
        (0x140627b90,'lea rcx, [rsi + 0x8e]'),(0x140627b97,'call 0x1404a2ee0'),(0x140627b9c,'movzx ecx, byte ptr [rax]'),
        (0x140627b9f,'nop '),(0x140627ba0,'test cl, cl'),(0x140627ba2,'je 0x140627c52'),
        (0x140627bd6,'call 0x140505360'),(0x140627c12,'mov edx, 0x2e3'),
        (0x140627c29,'mov qword ptr [rbx + 0x38], rsi'),(0x140627c2d,'mov dword ptr [rbx + 8], 5'),
        (0x140627c4e,'call qword ptr [rax + 0x58]'),
        (0x140628ce6,'cmp byte ptr [rcx + 0x1c], 0'),(0x140628cef,'mov rcx, qword ptr [rcx + 0x48]'),
        (0x140628cf8,'mov rax, qword ptr [rcx]'),(0x140628cfb,'mov dl, 1'),
        (0x140628cfd,'call qword ptr [rax + 0x28]'),(0x140628d00,'mov qword ptr [rbx + 0x48], 0')]
    for va,assembly in checks:
        row=app.at(va);require(row.mnemonic+' '+row.op_str==assembly,'Instruction differs at '+hex(va))
        facts.append({'va':hex(va),'bytes':bytes(row.bytes).hex(),'assembly':assembly})
    table=0x142825af0;locator=struct.unpack('<Q',app.data(table-8,8))[0];col=struct.unpack('<6I',app.data(locator,24))
    require(app.rip(app.at(0x14062830f))==table and col[0]==1 and col[1]==0 and app.base+col[5]==locator and
            app.text(app.base+col[3]+16)=='.?AVHidDeviceVerifierTask@@','Task RTTI differs')
    slots={8:0x140628940,16:0x140628910,32:0x1405b2ff0}
    for slot,target in slots.items():require(struct.unpack('<Q',app.data(table+slot,8))[0]==target,'Task slot differs')
    leaf=app.data(0x140628910,14);rows=list(app.dis.disasm(leaf,0x140628910))
    require([(r.mnemonic,r.op_str) for r in rows]==[('mov','rcx, qword ptr [rcx + 0x40]'),('test','rcx, rcx'),('jne','0x140628850'),('ret','')], 'Task update leaf differs')
    helpers=[]
    for va,expected in [(0x1404e6950,[('movzx','eax, byte ptr [rcx]'),('ret','')]),(0x1404a2ee0,[('mov','rax, rcx'),('ret','')])]:
        raw=app.data(va,4);decoded=list(app.dis.disasm(raw,va))
        require([(r.mnemonic,r.op_str) for r in decoded]==expected,'Setter helper differs')
        helpers.append({'start':hex(va),'bytes':raw.hex(),'instructions':[op+' '+args for op,args in expected]})
    imports={}
    app.pe.parse_data_directories(directories=[1])
    for module in app.pe.DIRECTORY_ENTRY_IMPORT:
        for item in module.imports:
            if item.name:imports[item.address]=(module.dll.decode(),item.name.decode())
    sites=[]
    for va in [0x140628629,0x140628b49]:
        entry=imports.get(app.rip(app.at(va)));require(entry and entry[0].lower()=='winmm.dll' and entry[1]=='timeGetTime','Clock import differs')
        sites.append({'va':hex(va),'module':entry[0],'name':entry[1]})
    focused_path=ROOT/'analysis/serato500-hid-task-20261102-decompile.json'
    focused=json.loads(focused_path.read_text(encoding='utf-8-sig'))
    expected={(0x1406282f0,0x14062838b),(0x1405b2ff0,0x1405b3020),(0x140628500,0x1406287ed),
              (0x1406287f0,0x14062884e),(0x140628850,0x140628904),(0x140628960,0x140628c29)}
    found=set();require(focused['binary_sha256']==app.sha,'Focused image differs')
    for row in focused['functions']:
        span=(int(row['start'],16),int(row['end_exclusive'],16))
        require(span in expected and span in app.spans and span not in found and row.get('complete') is True and
                row.get('pseudocode') and not row.get('diagnostic'),'Focused function differs/incomplete');found.add(span)
    require(found==expected,'Focused function set differs')
    log=ROOT/'analysis/serato500-hid-task-20261102-decompile.log';text=log.read_text(encoding='utf-8')
    require(all(s in text for s in ['Loaded 0 additional files','Discarded file import due to readOnly option','Import succeeded']),'Read-only focused import not verified')
    require(not list((ROOT/'analysis/ghidra-hid-task-20261102').iterdir()),'Temporary project remains')
    functions=[]
    for lo,hi in sorted(expected|{(0x140628ce0,0x140628d0e),(0x140627b60,0x140627c5f),(0x140627140,0x140627159)}):
        require((lo,hi) in app.spans,'Function extent differs')
        functions.append({'start':hex(lo),'endExclusive':hex(hi),'sha256':hashlib.sha256(app.data(lo,hi-lo)).hexdigest()})
    names=['scripts/export-serato-hid-task.py','scripts/export-serato-clock-handshake-evidence.py','scripts/ghidra/FocusedDecompile.java']
    result={'schema':'sl3.serato-hid-task.v1','binarySha256':app.sha,'installedMatches':True,'checkedInstructions':facts,
        'priorEvidence':priors,'taskType':'HidDeviceVerifierTask','taskVtable':hex(table),'rttiCompleteObjectOffset':0,
        'taskSlots':{hex(k):hex(v) for k,v in slots.items()},'taskUpdateLeaf':{'start':'0x140628910','bytes':leaf.hex()},
        'completeSetterHelperLeaves':helpers,'checkedFunctionExtents':functions,'actualClockImports':sites,'focusedFunctions':len(found),
        'focusedReportSha256':sha(focused_path),'focusedLogSha256':sha(log),'temporaryProjectAbsent':True,
        'descriptorDataDependency':{'descriptorMember':'0x40','beginOffset':'0x160','endOffset':'0x168','priorFieldName':'secret_key',
                                    'distinctFromMidiProcessorKeyVector':True,'keyValuesReadOrPublished':False},
        'pollState':{'method':'0x140628500','successFlagOffset':'0x10','returnsStatusByteDespiteVoidDecompilation':True,
                     'noResponseElapsedThresholdMilliseconds':5000,'comparison':'unsigned elapsed strictly greater than threshold',
                     'signedAttemptCountLimit':12,'initiationMethod':'0x140628960','actualAttemptOrTimingObserved':False},
        'successNotification':{'setter':'0x140627b60','stateByteOffset':'0x8e','conditionalMessageType':5,
                               'eventConstructorArgument':'0x2e3','sinkVirtualSlot':'0x58','downstreamAdmissionMeaningEstablished':False},
        'localSourceSha256':{n:sha(ROOT/n) for n in names},
        'publishedSourceSha256':{n:hashlib.sha256((ROOT/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in names},
        'applicationExecuted':False,'applicationModified':False,'deviceAccess':False,'keyBearingXmlRead':False,
        'authenticationMaterialExported':False,'handshakeReplyFabricated':False,'otherDeviceIdentityAdopted':False,
        'currentSeratoAdmissionVerified':False,'twoDeckDvsVerified':False,
        'limits':['Static selected task/state-machine flow only; full scheduler, indirect transport and downstream event consumers remain unexhausted.',
                  'The connection message helper is identified by call provenance; physical HID traffic, status and protocol success were not observed.',
                  'Secret-key storage is named by prior pinned field proof; values, generated buffers, transformations and reply comparison algorithm are omitted.',
                  'Retry branch constants are not measured timing, an end-to-end deadline or permission to retry the SL3 transport.',
                  'A local verifier flag or notification is not primary-device admission, account entitlement, working audio or DVS.',
                  'Historical SL3 root sections and generic audio do not supply this descriptor-specific HID contract.']}
    path=ROOT/'docs/evidence/serato500-hid-task.json';path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'verified':True,'instructionFacts':len(facts),'priorInstructionBytesRechecked':sum(p['instructionBytesRechecked'] for p in priors),
                      'rttiTables':1,'taskSlots':3,'completeDispatchLeaves':1,'completeSetterHelperLeaves':len(helpers),'functionExtents':len(functions),'focusedFunctions':len(found),
                      'authenticationMaterialExported':False,'currentSeratoAdmissionVerified':False}))

if __name__=='__main__':main()
