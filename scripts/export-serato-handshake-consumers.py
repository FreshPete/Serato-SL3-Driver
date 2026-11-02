"""Verify scoped current MIDI kind consumption and separate HID comparison."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import capstone

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT/'artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    spec = importlib.util.spec_from_file_location('sl3_handshake_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    app = h.Image(ORIGINAL, h.CURRENT_SHA); require = h.require
    require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe')) == app.sha, 'Installed executable differs')
    facts = []
    def fact(address, expected):
        row = app.at(address)
        require(row.mnemonic+' '+row.op_str == expected, 'Instruction differs at '+hex(address))
        facts.append({'va':hex(address),'bytes':bytes(row.bytes).hex(),'assembly':expected})
        return row
    checks = [
        (0x1405c7fe0,'mov rsi, rcx'),
        (0x1405c84e8,'mov dword ptr [rsi + 0x154], edi'),
        (0x1405c8550,'mov dword ptr [rsi + 0x154], ecx'),
        (0x140505229,'mov rsi, rax'),(0x140505261,'mov rax, rsi'),
        (0x140525a3f,'call 0x1405050b0'),(0x140525a44,'mov r15, rax'),
        (0x140526a73,'test r15, r15'),(0x140526a76,'je 0x140526b1d'),
        (0x140526a7c,'mov rcx, r15'),(0x140526a7f,'call 0x1405c7de0'),
        (0x140526a84,'test al, al'),(0x140526a86,'je 0x140526af0'),
        (0x140526aa8,'mov ecx, 0x18'),(0x140526aad,'call 0x142117f10'),
        (0x140526ac2,'mov rdx, rsi'),(0x140526acd,'call 0x1404b5df0'),
        (0x140526ad2,'mov r8, rax'),(0x140526ad5,'mov rdx, r15'),
        (0x140526ad8,'mov rcx, rbx'),(0x140526adb,'call 0x140603d40'),
        (0x140526ae5,'mov rdx, rax'),(0x140526ae8,'mov rcx, rdi'),(0x140526aeb,'call 0x14060a8f0'),
        (0x140603d4c,'mov qword ptr [rcx], rdx'),(0x140603d53,'mov rdi, rcx'),(0x140603dc8,'mov rax, rdi'),
        (0x14060a8fd,'mov qword ptr [rcx + 0x108], rdx'),
        (0x140609d57,'mov rbx, qword ptr [r13 + 0x108]'),(0x140609d5e,'test rbx, rbx'),
        (0x140609d61,'je 0x140609d90'),(0x140609d82,'lea rdx, [rsp + 0x60]'),
        (0x140609d87,'mov rcx, rbx'),(0x140609d8a,'call 0x140603de0'),
        (0x140603e0f,'mov r12, rcx'),(0x140603ee4,'mov rcx, qword ptr [r12]'),
        (0x140603eed,'mov edx, dword ptr [rcx + 0xd0]'),
        (0x140603ef3,'mov ecx, dword ptr [rcx + 0x154]'),(0x140603ef9,'call 0x1406042f0'),
        (0x140604305,'sub ecx, 1'),(0x140604308,'je 0x1406043b2'),
        (0x14060430e,'cmp ecx, 1'),(0x140604311,'je 0x140604330'),
        (0x140604316,'call 0x1404b91b0'),(0x14060431b,'xor al, al'),
        (0x14054613a,'mov r14, r8'),(0x140546ace,'mov rax, qword ptr [r14]'),
        (0x140546ad1,'cmp dword ptr [rax + 0x154], 6'),(0x140546ad8,'jne 0x140546c68'),
        (0x140546aea,'call 0x140544620'),
    ]
    for address, assembly in checks:
        fact(address,assembly)
    aliases={capstone.x86.X86_REG_R15,capstone.x86.X86_REG_R15D,capstone.x86.X86_REG_R15W,capstone.x86.X86_REG_R15B}
    restores=[row for row in app.function(0x140525710)
              if 0x140525a44 < row.address < 0x140526adb and set(row.regs_access()[1]) & aliases]
    require([(row.address,row.mnemonic,row.op_str) for row in restores]==[(0x140525cda,'pop','r15')],
            'Unexpected descriptor register write before construction')
    # The sole restore is on an early-return epilogue, not a continuing path.
    for address,assembly in [(0x140525cda,'pop r15'),(0x140525cdc,'pop r14'),(0x140525cde,'pop r13'),
                             (0x140525ce0,'pop r12'),(0x140525ce2,'pop rdi'),(0x140525ce3,'ret ' )]:
        fact(address,assembly)
    previous=ROOT/'docs/evidence/serato500-descriptor-precedence.json'
    previous_value=json.loads(previous.read_text(encoding='utf-8'))
    require(previous_value['binarySha256']==app.sha and previous_value['installedMatches'] is True,'Lookup evidence identity differs')
    # Deliberately export no message template, challenge, key or reply bytes.
    leaf = list(app.dis.disasm(app.data(0x1405c7de0,18),0x1405c7de0))
    require([(x.mnemonic,x.op_str) for x in leaf] == [('mov','rax, qword ptr [rcx + 0x180]'),
        ('cmp','qword ptr [rcx + 0x178], rax'),('setne','al'),('ret','')], 'Nonempty-vector getter differs')
    require(leaf[-1].address+leaf[-1].size == 0x1405c7df2, 'Getter extent differs')
    tables = []
    for table, name, offset, slot, target in [
        (0x14281caa8,'.?AVControllerDescriptor@dj@serato@@',0,8,0x1405c7f90),
        (0x142823cc0,'.?AVCMIDIInputManager@@',0,0x18,0x140609900),
        (0x142810290,'.?AVHidManager@@',16,8,0x140546110)]:
        locator = struct.unpack('<Q',app.data(table-8,8))[0]; col = struct.unpack('<6I',app.data(locator,24))
        require(col[0]==1 and col[1]==offset and app.base+col[5]==locator and app.text(app.base+col[3]+16)==name,
                'RTTI class/subobject differs')
        require(struct.unpack('<Q',app.data(table+slot,8))[0]==target,'RTTI-bound method slot differs')
        tables.append({'table':hex(table),'decoratedType':name,'subobjectOffset':offset,'slot':hex(slot),'target':hex(target)})
    # Preserve the current map's labels; old numeric kinds are not portable.
    labels = ['NONE','SERATO_DJ','NUMARK','VESTAX','NOVATION','AKAI','SERATO_DJ_HID','ATC_HID_PIR']
    literals = [0x14281ccd8,0x14281ccf0,0x14281cd10,0x14281cd28,0x14281cd40,0x14281cd58,0x14281cd70,0x14281cd90]
    stores = [0x1405c1802,0x1405c1926,0x1405c1a4a,0x1405c1b80,0x1405c1c8b,0x1405c1cdf,0x1405c1d33,0x1405c1d87]
    mapping = []
    require(any(row.mnemonic=='xor' and row.op_str=='r15d, r15d' for row in app.function(0x1405c1750)[:40]),
            'Enum zero register not initialized')
    for value,(label,literal,store) in enumerate(zip(labels,literals,stores)):
        require(app.text(literal)=='HANDSHAKE_TYPE_'+label,'Current enum literal differs')
        app.at(store,'mov','dword ptr [rbp + 0xf], '+('r15d' if value==0 else str(value)))
        mapping.append({'kind':value,'name':label,'midiPredicateBranch':hex(0x1406043b2 if value==1 else 0x140604330) if value in (1,2) else 'default_false'})
    reports = []
    path=ROOT/'analysis/serato500-handshake-dispatch-20261102-decompile.json';v=json.loads(path.read_text(encoding='utf-8-sig'))
    require(v['binary_sha256']==app.sha,'Focused report image differs')
    expected={(0x140603de0,0x1406042ea),(0x1406042f0,0x1406043f2),(0x140609900,0x14060a753),(0x140546110,0x140546ee3)}
    found=set()
    for row in v['functions']:
        span=int(row['start'],16),int(row['end_exclusive'],16)
        require(span in expected and span in app.spans and span not in found and row['complete'] is True and
                row.get('pseudocode') and not row.get('diagnostic'),'Unexpected/incomplete focused function')
        found.add(span)
    require(found==expected,'Focused function set differs')
    log=ROOT/'analysis/serato500-handshake-dispatch-20261102-decompile.log';text=log.read_text(encoding='utf-8',errors='replace')
    require('Loaded 0 additional files' in text and 'Discarded file import due to readOnly option' in text and 'Import succeeded' in text,
            'Read-only tool cleanup evidence missing')
    constructor_spans=[(0x140603d40,0x140603d7f),(0x140603d7f,0x140603dc3),(0x140603dc3,0x140603dd1)]
    require(all(x in app.spans for x in constructor_spans),'Split constructor unwind regions differ')
    result={'schema':'sl3.serato-handshake-consumers.v1','applicationSha256':app.sha,'installedMatches':True,
        'checkedInstructions':facts,'rttiTables':tables,'currentKindMapAndStaticMidiBranchProjection':mapping,
        'descriptorProvenance':{'primaryLookupCall':'0x140525a3f','processorConstructor':'0x140603d40',
            'storedDescriptorOffset':'0x0','managerProcessorMember':'0x108','setterCall':'0x140526aeb',
            'managerCallback':'0x140609900','processorCall':'0x140609d8a','kindRead':'0x140603ef3',
            'splitConstructorUnwindRegions':[[hex(a),hex(b)] for a,b in constructor_spans],
            'descriptorRegisterPreservedUntilConstruction':True,
            'priorLookupEvidenceCanonicalSha256':hashlib.sha256(json.dumps(previous_value,sort_keys=True,separators=(',',':')).encode()).hexdigest()},
        'creationGate':{'getter':'0x1405c7de0','getterBytes':app.data(0x1405c7de0,18).hex(),
            'vectorBeginOffset':'0x178','vectorEndOffset':'0x180','requiresNonemptyVectorUnderThisBranch':True,
            'additionalPointerConditionsExist':True,'vectorXmlKeyAssigned':False},
        'midiPredicate':{'function':'0x1406042f0','kind1Target':'0x1406043b2','kind2Target':'0x140604330',
            'otherKindsReturnFalseAt':'0x14060431b','protocolResultVerified':False},
        'hidComparison':{'function':'0x140546110','rttiType':'HidManager','incomingArgument':3,
            'pointeeFieldOffset':'0x154','comparedValue':6,'fullIncomingDescriptorProvenanceExhausted':False},
        'focusedReportSha256':sha(path),'focusedLogSha256':sha(log),'focusedFunctions':len(found),
        'sourceSha256':{name:sha(ROOT/name) for name in ['scripts/export-serato-handshake-consumers.py',
            'scripts/export-serato-clock-handshake-evidence.py','scripts/ghidra/FocusedDecompile.java']},
        'applicationExecuted':False,'applicationModified':False,'deviceAccess':False,'authenticationMaterialExported':False,
        'otherDeviceKindAdopted':False,'handshakeReplyFabricated':False,'currentSeratoAdmissionVerified':False,
        'limits':['This is the scoped CMIDIInputManager response path, not a universal dispatcher or successful handshake.',
            'The HID callback comparison is separately class-bound; all incoming descriptor provenance/callers remain unexamined.',
            'Vector nonemptiness and further pointer conditions gate processor creation; kind alone does not create it.',
            'No payload templates, keys or challenge/reply bytes are included in this report.',
            'Other indirect/raw-USB handshake paths and all possible later mutations are not exhausted.',
            'The unchanged genuine SL3 discontinued branch remains independent of these conditional consumers.']}
    (ROOT/'docs/evidence/serato500-handshake-consumers.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'verified':True,'instructionFacts':len(facts),'rttiTables':len(tables),'focusedFunctions':len(found),'authenticationMaterialExported':False}))


if __name__=='__main__':
    main()
