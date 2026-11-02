"""Verify the current HID verifier construction/gates; export no protocol payloads."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import capstone

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/file)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    h = load('hid_verifier_image', 'export-serato-clock-handshake-evidence.py')
    app = h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', h.CURRENT_SHA)
    require = h.require
    require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe')) == app.sha, 'Installed image differs')
    facts = []
    def fact(va, expected):
        row = app.at(va)
        require(row.mnemonic+' '+row.op_str == expected, 'Instruction differs at '+hex(va))
        facts.append({'va': hex(va), 'bytes': bytes(row.bytes).hex(), 'assembly': expected})
        return row
    checks = [
        (0x1405c7fe0,'mov rsi, rcx'), (0x1405c80b9,'mov r15, rax'),
        (0x1405c80bc,'mov qword ptr [rsp + 0x50], rax'),
        (0x1405c81cd,'lea rdx, [rip + 0x22551d4]'), (0x1405c81e9,'mov dword ptr [rsi + 0x20], 1'),
        (0x1405c81f2,'lea rdx, [rip + 0x22551c7]'), (0x1405c820e,'mov dword ptr [rsi + 0x20], 2'),
        (0x1405c8217,'lea rdx, [rip + 0x22551ba]'), (0x1405c8237,'mov dword ptr [rsi + 0x20], 3'),
        (0x1405c9f35,'mov byte ptr [rsi + 0xd4], 0'),
        (0x1405c9f3c,'lea rdx, [rip + 0x2253b6d]'), (0x1405c9f4b,'cmp byte ptr [r13 + 0x11], 0'),
        (0x1405c9f50,'je 0x1405c9f6f'), (0x1405c9f52,'test rax, rax'), (0x1405c9f55,'je 0x1405c9f6f'),
        (0x1405c9f57,'xor r8d, r8d'), (0x1405c9f61,'mov rcx, rax'),
        (0x1405c9f64,'call 0x141b17690'), (0x1405c9f69,'mov byte ptr [rsi + 0xd4], al'),
        (0x1405cb83f,'xor r15d, r15d'),
        (0x1405cc46c,'mov dword ptr [rsi + 0x314], 3'), (0x1405cc476,'lea rdx, [rip + 0x2251c63]'),
        (0x1405cc47d,'mov rbx, qword ptr [rsp + 0x50]'), (0x1405cc482,'mov rcx, rbx'),
        (0x1405cc485,'call 0x141b17da0'), (0x1405cc48a,'test rax, rax'), (0x1405cc48d,'je 0x1405cc4d0'),
        (0x1405cc48f,'lea rdx, [rip + 0x2251c46]'), (0x1405cc496,'mov rcx, rbx'),
        (0x1405cc499,'call 0x141b17da0'), (0x1405cc49e,'test rax, rax'), (0x1405cc4a1,'je 0x1405cc4d0'),
        (0x1405cc4a3,'mov dword ptr [rsi + 0x314], 2'), (0x1405cc4ad,'jmp 0x1405cc50b'),
        (0x1405cc4d0,'lea rdx, [rip + 0x2251c09]'), (0x1405cc4d7,'mov rcx, rbx'),
        (0x1405cc4da,'call 0x141b17da0'), (0x1405cc4df,'test rax, rax'), (0x1405cc4e2,'je 0x1405cc4ed'),
        (0x1405cc4e4,'mov dword ptr [rsi + 0x314], r15d'), (0x1405cc4eb,'jmp 0x1405cc50b'),
        (0x1405cc4ed,'lea rdx, [rip + 0x2251be8]'), (0x1405cc4f4,'mov rcx, rbx'),
        (0x1405cc4f7,'call 0x141b17da0'), (0x1405cc4fc,'test rax, rax'), (0x1405cc4ff,'je 0x1405cc50b'),
        (0x1405cc501,'mov dword ptr [rsi + 0x314], 1'),
        (0x14054613a,'mov r14, r8'), (0x14054613d,'mov r15, rdx'), (0x140546140,'mov r13, rcx'),
        (0x14054655d,'mov rax, qword ptr [r14]'), (0x140546560,'mov ecx, dword ptr [rax + 0x314]'),
        (0x140546566,'cmp ecx, 1'), (0x140546569,'je 0x140546604'),
        (0x14054656f,'cmp ecx, 2'), (0x140546572,'je 0x140546604'), (0x1405465ff,'jmp 0x140546e9d'),
        (0x140546888,'mov rcx, qword ptr [r14]'), (0x14054688b,'add rcx, 0x10'),
        (0x14054688f,'mov rax, qword ptr [rcx]'), (0x140546892,'call qword ptr [rax + 0x90]'),
        (0x140546898,'test al, al'), (0x14054689a,'je 0x140546ace'),
        (0x1405468a0,'cmp byte ptr [r13 + 0xc1], 0'), (0x1405468a8,'jne 0x140546ace'),
        (0x140546ace,'mov rax, qword ptr [r14]'), (0x140546ad1,'cmp dword ptr [rax + 0x154], 6'),
        (0x140546ad8,'jne 0x140546c68'), (0x140546ade,'lea r8, [rsp + 0x60]'),
        (0x140546ae3,'mov rdx, r15'), (0x140546ae6,'lea rcx, [rbp - 0x20]'),
        (0x140546aea,'call 0x140544620'),
        (0x140544638,'mov r15, r8'), (0x14054463b,'mov r14, rdx'), (0x140544643,'mov ecx, 0x78'),
        (0x140544648,'call 0x142117f10'), (0x14054466e,'lea rax, [rip + 0x22cbdb3]'),
        (0x140544675,'mov qword ptr [rbx], rax'), (0x140544678,'lea rcx, [rbx + 0x10]'),
        (0x1405446b3,'mov rax, qword ptr [r14]'), (0x1405446b6,'mov qword ptr [rsp + 0x38], rax'),
        (0x1405446c4,'lea r8, [rsp + 0x28]'), (0x1405446c9,'lea rdx, [rsp + 0x38]'),
        (0x1405446ce,'call 0x140628130'),
        (0x14062814f,'mov r14, r8'), (0x140628152,'mov r15, rdx'), (0x140628155,'mov rsi, rcx'),
        (0x1406281a6,'mov rax, qword ptr [rdx]'), (0x1406281a9,'mov qword ptr [rsi + 0x20], rax'),
        (0x1406281f9,'mov rax, qword ptr [r14]'), (0x1406281fc,'mov qword ptr [rsi + 0x30], rax'),
        (0x140628236,'mov rcx, qword ptr [rsi + 0x20]'), (0x14062823a,'call 0x14050eb60'), (0x14062823f,'mov edi, eax'),
        (0x140628241,'mov rcx, qword ptr [rsi + 0x20]'), (0x140628245,'call 0x140b12d00'), (0x14062824a,'mov ebx, eax'),
        (0x14062824c,'mov rcx, qword ptr [rsi + 0x20]'), (0x140628250,'call 0x1405b3020'),
        (0x140628255,'mov r9d, edi'), (0x140628258,'mov r8d, ebx'), (0x14062825b,'mov edx, eax'),
        (0x14062825d,'mov rcx, qword ptr [rip + 0x3883f6c]'), (0x140628264,'call 0x140505360'),
        (0x140628269,'mov qword ptr [rsi + 0x40], rax'),
        (0x140546c02,'lea rcx, [r13 + 0xc8]'), (0x140546c09,'call 0x140545080'),
        (0x140546c0e,'mov rcx, qword ptr [rax]'), (0x140546c11,'call 0x140628c30'),
        (0x140628c3a,'mov rdi, rcx'), (0x140628c3f,'cmp byte ptr [rcx + 0x1c], bl'),
        (0x140628c42,'jne 0x140628cc1'), (0x140628c4f,'mov byte ptr [rdi + 0x1c], 1'),
        (0x140628cac,'call 0x1406282f0'), (0x140628cb4,'mov qword ptr [rdi + 0x48], rbx'),
        (0x140628cbe,'call qword ptr [rax + 0x20]'),
    ]
    for va, expected in checks: fact(va, expected)
    aliases = {capstone.x86.X86_REG_R15, capstone.x86.X86_REG_R15D, capstone.x86.X86_REG_R15W, capstone.x86.X86_REG_R15B}
    for start, lo, hi in [(0x1405c7f90,0x1405cb83f,0x1405cc4e4),(0x140546110,0x14054613d,0x140546aea)]:
        require(not any(set(row.regs_access()[1]) & aliases for row in app.function(start) if lo < row.address < hi),
                'Preserved zero/connection register was overwritten')
    stack_stores = [row.address for row in app.function(0x1405c7f90)
                    if row.mnemonic == 'mov' and row.op_str.startswith('qword ptr [rsp + 0x50],')]
    require(stack_stores == [0x1405c7fe3,0x1405c80bc], 'Parser root storage mutated')
    literals = []
    for va, text in [(0x1405c81cd,'native_pro_device'),(0x1405c81f2,'native_intro_device'),(0x1405c8217,'osa_device'),
                     (0x1405c9f3c,'has_hid'),(0x1405cc476,'midi'),(0x1405cc48f,'hid'),(0x1405cc4d0,'midi'),(0x1405cc4ed,'hid')]:
        require(app.text(app.rip(app.at(va))) == text, 'XML field literal differs')
        literals.append({'referenceVA':hex(va),'text':text})
    tables = []
    for table, name, offset, slot, target in [
        (0x142810290,'.?AVHidManager@@',16,8,0x140546110),
        (0x14281caf0,'.?AVControllerDescriptor@dj@serato@@',16,0x90,0x1405c7f30),
        (0x142810428,'.?AV?$_Ref_count_obj2@VHidDeviceVerifier@@@std@@',0,None,None)]:
        locator=struct.unpack('<Q',app.data(table-8,8))[0]; col=struct.unpack('<6I',app.data(locator,24))
        require(col[0]==1 and col[1]==offset and app.base+col[5]==locator and app.text(app.base+col[3]+16)==name, 'RTTI binding differs')
        if slot is not None: require(struct.unpack('<Q',app.data(table+slot,8))[0]==target, 'Virtual slot differs')
        tables.append({'table':hex(table),'type':name,'completeObjectOffset':offset,'slot':hex(slot) if slot is not None else None,'target':hex(target) if target else None})
    leaves=[]
    for va,length,expected in [
        (0x1405c7f30,21,[('cmp','byte ptr [rcx + 0xc4], 0'),('je','0x1405c7f42'),('cmp','dword ptr [rcx + 0x10], 2'),
                         ('jne','0x1405c7f42'),('mov','al, 1'),('ret',''),('xor','al, al'),('ret','')]),
        (0x14050eb60,4,[('mov','eax, dword ptr [rcx + 0x40]'),('ret','')]),
        (0x140b12d00,4,[('mov','eax, dword ptr [rcx + 0x3c]'),('ret','')]),
        (0x1405b3020,4,[('mov','eax, dword ptr [rcx + 0x38]'),('ret','')])]:
        raw=app.data(va,length);rows=list(app.dis.disasm(raw,va))
        require([(r.mnemonic,r.op_str) for r in rows]==expected and rows[-1].address+rows[-1].size==va+length,'Leaf extent/body differs')
        leaves.append({'va':hex(va),'bytes':raw.hex(),'instructions':[op+' '+args for op,args in expected]})
    path=ROOT/'analysis/serato500-hid-contract-20261102-decompile.json';focused=json.loads(path.read_text(encoding='utf-8-sig'))
    expected={(0x140544620,0x140544787),(0x140628130,0x1406282ea),(0x140628c30,0x140628cd2),(0x140505360,0x140505466)}
    found=set(); require(focused['binary_sha256']==app.sha,'Focused image differs')
    for row in focused['functions']:
        span=(int(row['start'],16),int(row['end_exclusive'],16))
        require(span in expected and span in app.spans and span not in found and row['complete'] is True and row.get('pseudocode') and not row.get('diagnostic'),'Focused function incomplete/different')
        found.add(span)
    require(found==expected,'Focused function set differs')
    log=ROOT/'analysis/serato500-hid-contract-20261102-decompile.log';text=log.read_text(encoding='utf-8')
    require('Loaded 0 additional files' in text and 'Discarded file import due to readOnly option' in text and 'Import succeeded' in text, 'Read-only import/cleanup evidence missing')
    require(not list((ROOT/'analysis/ghidra-hid-contract-20261102').iterdir()),'Temporary Ghidra project remains')
    callback_path=ROOT/'analysis/serato500-handshake-dispatch-20261102-decompile.json'
    callbacks=json.loads(callback_path.read_text(encoding='utf-8-sig'))
    require(callbacks['binary_sha256']==app.sha,'Prior callback image differs')
    callback_rows=[row for row in callbacks['functions'] if row['start']=='140546110']
    require(len(callback_rows)==1 and callback_rows[0]['end_exclusive']=='140546ee3' and
            callback_rows[0]['complete'] is True and callback_rows[0].get('pseudocode') and
            not callback_rows[0].get('diagnostic') and (0x140546110,0x140546ee3) in app.spans,'Prior callback report differs')
    prior=ROOT/'docs/evidence/serato500-descriptor-precedence.json'
    require(json.loads(prior.read_text(encoding='utf-8'))['binarySha256']==app.sha,'Prior primary-lookup identity differs')
    profiles=load('hid_verifier_profiles','export-serato-component-profiles.py')
    archive=(ROOT/profiles.r.APP_RELATIVE).with_name('userio_resources.bin').read_bytes()
    require(hashlib.sha256(archive).hexdigest()==profiles.r.ARCHIVE_SHA and Path('C:/Program Files/Serato/Serato DJ Pro/userio_resources.bin').read_bytes()==archive,'Archive differs')
    seed=app.data(0x142f2de98,16)
    key=struct.unpack('<4I',bytes((((x^0xcf)>>(n&7))|((x^0xcf)<<((8-(n&7))&7)))&255 for n,x in enumerate(seed)))
    size=struct.unpack_from('<Q',archive)[0]
    entries=profiles.r.parse_index(profiles.r.decode_block(archive[8:8+size],key),len(archive),8+size)
    metadata=[];histogram=Counter(); selected=[]
    for entry in entries:
        data,crc=profiles.r.unpack_member(archive[entry['offset']:entry['offset']+entry['size']],key,entry['name'])
        if entry['name'].endswith('.xsd'): continue
        safe=re.sub(rb'<!DOCTYPE\s+[A-Za-z_][A-Za-z0-9_.:-]*\s*>',b'',data,flags=re.I)
        require(b'<!DOCTYPE' not in safe.upper() and b'<!ENTITY' not in safe.upper(),'Unsupported XML declarations')
        root=ET.fromstring(safe);midi=len(root.findall('midi'));hid=len(root.findall('hid'))
        require(midi<=1 and hid<=1,'Ambiguous root control sections')
        projection=2 if midi and hid else (0 if midi else (1 if hid else 3))
        for node in root.iter():
            if node.tag not in ('native_pro_device','native_intro_device','osa_device'):continue
            row={'resource':entry['name'],'kind':node.tag,'xmlSha256':hashlib.sha256(data).hexdigest(),'zipCrc32':crc,
                 'rootMidiSection':bool(midi),'rootHidSection':bool(hid),'parserControlTypeProjection':projection}
            metadata.append(row);histogram[str(projection)]+=1
            if entry['name'] in ('hid/hid_mwm_phase.xml','audio/serato_virtual_audio.xml'):selected.append(row)
    require(len(entries)==229 and len(metadata)==197 and len(selected)==2,'Resource inventory differs')
    legacy=load('hid_verifier_legacy','export-serato-legacy-descriptors.py'); old=[]
    for target in legacy.TARGETS:
        evidence,_,_,xml=legacy.inspect(target);root=ET.fromstring(xml)
        old.append({'version':target['version'],'binarySha256':target['sha'],'xmlSha256':hashlib.sha256(xml).hexdigest(),
                    'rootMidiSection':root.find('midi') is not None,'rootHidSection':root.find('hid') is not None})
    source_names=['scripts/export-serato-hid-verifier.py','scripts/export-serato-clock-handshake-evidence.py',
                  'scripts/export-serato-component-profiles.py','scripts/inspect-serato-resource-archive.py',
                  'scripts/export-serato-legacy-descriptors.py','scripts/ghidra/FocusedDecompile.java']
    result={'schema':'sl3.serato-hid-verifier.v1','binarySha256':app.sha,'installedMatches':True,'checkedInstructions':facts,
            'rttiTables':tables,'completeLeaves':leaves,'xmlFieldReferences':literals,
            'parserControlTypes':{'fieldOffset':'0x314','rootSections':{'midi_only':0,'hid_only':1,'both':2,'neither':3},'distinctFromCapabilityOrMidiDirection':True},
            'conditionalDescriptorGetter':{'table':'0x14281caf0','slot':'0x90','receiverOffset':16,'completeByteOffset':'0xd4','byteSource':'has_hid',
                'completeKindOffset':'0x20','requiredKind':2,'kindName':'native_intro_device','parserContextAlsoGatesHasHid':True,'actualVirtualReceiverObserved':False},
            'verifierConstruction':{'factory':'0x140544620','allocationBytes':120,'controlBlockType':'std::_Ref_count_obj2<HidDeviceVerifier>',
                'constructor':'0x140628130','connectionSharedMember':'0x20','secondSharedMember':'0x30','primaryNumericLookup':'0x140505360',
                'connectionIdentityFields':{'vendor':'0x38','product':'0x3c','revision':'0x40'},'returnedDescriptorMember':'0x40',
                'startMethod':'0x140628c30','startedFlag':'0x1c','workerMember':'0x48','fullWorkerOrProtocolTraced':False},
            'resourceMetadata':{'archiveSha256':profiles.r.ARCHIVE_SHA,'all229MemberCrcsVerified':True,'recognizedNodes':197,
                'controlSectionProjectionHistogram':dict(sorted(histogram.items())),'metadataSha256':hashlib.sha256(json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                'selectedProfiles':selected,'historicalSl3RootSections':old,'projectionIsRuntimePrediction':False},
            'focusedReportSha256':sha(path),'focusedLogSha256':sha(log),'focusedFunctions':len(found),'temporaryProjectAbsent':True,
            'priorPrimaryLookupEvidenceSha256':sha(prior),'priorCallbackFocusedReportSha256':sha(callback_path),
            'localSourceSha256':{n:sha(ROOT/n) for n in source_names},
            'publishedSourceSha256':{n:hashlib.sha256((ROOT/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in source_names},
            'applicationExecuted':False,'applicationModified':False,'deviceAccess':False,'authenticationMaterialExported':False,
            'otherDeviceIdentityAdopted':False,'handshakeReplyFabricated':False,'currentSeratoAdmissionVerified':False,
            'limits':['Incoming HidManager descriptor provenance and all dispatchers remain unexhausted; concrete getter semantics are conditional on its class.',
                      'Root sections, has_hid, midi_direction and handshake kind are separate contracts; raw USB capability is not a HID connection.',
                      'The verifier performs an existing primary numeric lookup; this does not expose a new external registration/provider route.',
                      'Worker body, messages, responses, actual connection, account entitlement and runtime success remain unverified.',
                      'Historical XML is not a current admitted description; Phase remains accessory data, not an SL3 primary-device substitute.']}
    output=ROOT/'docs/evidence/serato500-hid-verifier.json'
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'verified':True,'instructionFacts':len(facts),'rttiTables':len(tables),'completeLeaves':len(leaves),'focusedFunctions':len(found),
                      'resourceProjectionHistogram':dict(histogram),'historicalSl3Sections':old,'authenticationMaterialExported':False}))


if __name__=='__main__':main()
