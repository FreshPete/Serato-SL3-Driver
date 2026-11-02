"""Verify legacy SL3 literal retention and current base DriverAPI behavior, offline."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    h=load('generic_driver_image','export-serato-clock-handshake-evidence.py');require=h.require
    current=ROOT/'artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe'
    app=h.Image(current,h.CURRENT_SHA)
    require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe'))==app.sha,'Installed executable differs')
    exports=['sl3_open','sl3_close','sl3_driver_timer','sl3_get_usb_port_status','sl3_get_audio_controls','sl3_set_audio_controls','sl3_set_thrustate_callback']
    patterns=['RaneAsioSL3.dll','.?AVRaneSL3API@driver@device@serato@@']+exports
    inventories=[]
    for version,path,expected in [
        ('2.5.5',ROOT/'artifacts/extracted/Serato DJ Pro 2.5.5/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe',h.OLD_SHA),
        ('2.5.6',ROOT/'artifacts/extracted/Serato DJ Pro 2.5.6/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe','3b04472cd5597fd56266e1c2c86dc298431b0026001aefe4b43aa3b909ee35c5'),
        ('5.0.0',current,app.sha)]:
        raw=path.read_bytes();require(hashlib.sha256(raw).hexdigest()==expected,'Historical image differs')
        folded=raw.lower();rows=[]
        for name in patterns:
            data=folded if name==patterns[0] else raw;text=name.lower() if name==patterns[0] else name
            ascii_count=data.count(text.encode('ascii')+b'\0');wide_count=data.count(text.encode('utf-16-le')+b'\0\0')
            wanted=(0,0) if version=='5.0.0' else ((0,1) if name==patterns[0] else (1,0))
            require((ascii_count,wide_count)==wanted,'Literal retention result differs: '+version+'/'+name)
            rows.append({'text':name,'asciiTerminatedBytePatternHits':ascii_count,'utf16LeTerminatedBytePatternHits':wide_count,
                         'filenameAsciiCaseInsensitiveScan':name==patterns[0]})
        inventories.append({'version':version,'executableSha256':expected,'wholeExecutableBytePatternScan':rows})
    facts=[]
    def fact(va,expected):
        row=app.at(va);require(row.mnemonic+' '+row.op_str==expected,'Instruction differs at '+hex(va))
        facts.append({'va':hex(va),'bytes':bytes(row.bytes).hex(),'assembly':expected})
    for va,expected in [
        (0x140bfe0a2,'mov rax, qword ptr [rdi]'),(0x140bfe0a5,'lea rdx, [rbp - 0x49]'),
        (0x140bfe0a9,'mov rcx, rdi'),(0x140bfe0ac,'call qword ptr [rax + 0x48]'),
        (0x140bfe0af,'mov rdx, rax'),(0x140bfe0b2,'mov rcx, rbx'),
        (0x140bfe0b5,'call 0x140bff9d0'),(0x140bfe0ba,'mov rsi, rax'),
        (0x140bff9eb,'mov rsi, rdx'),(0x140bff9ee,'mov rdi, rcx'),
        (0x140bff9fb,'lea rax, [rip + 0x228695e]'),(0x140bffa02,'mov qword ptr [rcx], rax'),
        (0x140bffa05,'mov byte ptr [rcx + 8], 0'),(0x140bffa0b,'mov dword ptr [rcx + 0xc], ebp'),
        (0x140bffa0e,'mov qword ptr [rcx + 0x48], rbp'),(0x140bffa12,'mov qword ptr [rcx + 0x50], rbp'),
        (0x140bffa16,'mov qword ptr [rcx + 0x58], rbp'),(0x140bffa1a,'mov ecx, 0x28'),
        (0x140bffa1f,'call 0x142117f10'),(0x140bffa35,'mov qword ptr [rdi + 0x50], rax'),
        (0x140bffa48,'movups xmm0, xmmword ptr [rsi]'),(0x140bffa4b,'movups xmmword ptr [rdi + 0x60], xmm0'),
        (0x140bffa4f,'movups xmm1, xmmword ptr [rsi + 0x10]'),(0x140bffa53,'movups xmmword ptr [rdi + 0x70], xmm1'),
        (0x140bffa71,'mov rax, rdi'),
        (0x140c00360,'mov dword ptr [rsp + 0x10], edx'),(0x140c00364,'push rbx'),
        (0x140c00365,'sub rsp, 0x20'),(0x140c00369,'add rcx, 0x50'),
        (0x140c0036d,'lea rdx, [rsp + 0x38]'),(0x140c00372,'mov ebx, r8d'),
        (0x140c00375,'call 0x1405bffa0'),(0x140c0037a,'mov dword ptr [rax], ebx'),
        (0x140c0037c,'mov al, 1'),(0x140c0037e,'add rsp, 0x20'),(0x140c00382,'pop rbx'),(0x140c00383,'ret '),
        (0x140c00240,'sub rsp, 0x48'),(0x140c00244,'lea rdx, [rcx + 0x60]'),
        (0x140c00248,'lea rcx, [rsp + 0x20]'),(0x140c0024d,'call 0x1404a3300'),
        (0x140c00252,'mov rcx, rax'),(0x140c00255,'call 0x140bfffd0'),
        (0x140c0025a,'add rsp, 0x48'),(0x140c0025e,'ret ')]:fact(va,expected)
    ctor=app.function(0x140bff9d0)
    require([(r.address,r.op_str) for r in ctor if r.mnemonic=='call']==[(0x140bffa1f,'0x142117f10'),(0x140bffa7c,'0x142118190')],
            'Base constructor direct call set differs')
    factory=app.function(0x140bfa030)
    generic_calls=[hex(r.address) for r in factory if r.mnemonic=='call' and r.op_str=='0x140bff9d0']
    require(generic_calls==['0x140bfc070','0x140bfcf94','0x140bfd1ae','0x140bfdfe1','0x140bfe0b5'],'Generic factory call sites differ')
    table=app.rip(app.at(0x140bff9fb));require(table==0x142e86360,'Constructor table differs')
    locator=struct.unpack('<Q',app.data(table-8,8))[0];col=struct.unpack('<6I',app.data(locator,24))
    require(col[0]==1 and col[1]==0 and app.base+col[5]==locator and app.text(app.base+col[3]+16)=='.?AVDriverAPI@driver@device@serato@@','Base DriverAPI RTTI differs')
    prior_path=ROOT/'docs/evidence/serato500-supported-contract.json';prior=json.loads(prior_path.read_text(encoding='utf-8'))
    require(prior['binary_sha256']==app.sha and prior['driverApiFactory']['explicitRaneProducts']==['0x18','0x1b','0x20','0x21','0x22','0x25','0x26'] and
            prior['driverApiFactory']['sl3SpecificMatchInThisFactory'] is False,'Prior factory binding differs')
    slots=prior['driverApiFactory']['rtti']['slots'];require(len(slots)==24,'Base virtual slot inventory differs')
    for row in slots:require(struct.unpack('<Q',app.data(table+int(row['offset'],16),8))[0]==int(row['target'],16),'Base virtual target differs')
    prior_checked=0
    for block in prior['excerpts']:
        start,end=int(block['start'],16),int(block['end_exclusive'],16)
        require(0 < end-start <= 65536,'Bounded prior excerpt required')
        rows=list(app.dis.disasm(app.data(start,end-start),start))
        require(rows and rows[0].address==start and rows[-1].address+rows[-1].size==end and
                [f'{r.address:x}: {r.mnemonic} {r.op_str}' for r in rows]==block['instructions'],'Prior contract excerpt differs')
        prior_checked+=len(rows)
    leaves=[]
    for va,length,expected in [
        (0x1404a4540,3,[('mov','al, 1'),('ret','')]),
        (0x1404a4550,3,[('xor','al, al'),('ret','')]),
        (0x1405da5d0,4,[('mov','eax, dword ptr [rcx + 0xc]'),('ret','')]),
        (0x140bfffc0,7,[('cmp','edx, 4'),('setb','al'),('ret','')])]:
        raw=app.data(va,length);rows=list(app.dis.disasm(raw,va))
        require([(r.mnemonic,r.op_str) for r in rows]==expected and rows[-1].address+rows[-1].size==va+length,'Complete leaf differs')
        leaves.append({'va':hex(va),'bytes':raw.hex(),'instructions':[op+' '+args for op,args in expected]})
    focused_path=ROOT/'analysis/serato500-generic-driver-20261102-decompile.json';focused=json.loads(focused_path.read_text(encoding='utf-8-sig'))
    expected={(0x140bff9d0,0x140bffa8e),(0x140bffb30,0x140bfff39),(0x140bfff40,0x140bfffa9),
              (0x140c00360,0x140c00384),(0x140c00240,0x140c0025f),(0x140bfffd0,0x140c00228)}
    found=set();require(focused['binary_sha256']==app.sha,'Focused input differs')
    for row in focused['functions']:
        span=int(row['start'],16),int(row['end_exclusive'],16)
        require(span in expected and span in app.spans and span not in found and row['complete'] is True and row.get('pseudocode') and not row.get('diagnostic'),'Incomplete/different focused function')
        found.add(span)
    require(found==expected,'Focused function set differs')
    log=ROOT/'analysis/serato500-generic-driver-20261102-decompile.log';text=log.read_text(encoding='utf-8')
    require('Loaded 0 additional files' in text and 'Discarded file import due to readOnly option' in text and 'Import succeeded' in text,'Read-only import/cleanup evidence missing')
    require(not list((ROOT/'analysis/ghidra-generic-driver-20261102').iterdir()),'Temporary project remains')
    require(sha(ROOT/'analysis/serato500-generic-driver-input-20261102/Serato DJ Pro.exe')==app.sha,'Isolated analysis copy differs')
    old_path=ROOT/'docs/evidence/serato256-sl3-api-path.json';old=json.loads(old_path.read_text(encoding='utf-8'))
    require(old['binarySha256']==inventories[1]['executableSha256'] and [r['name'] for r in old['exports']]==exports,'Historical named-loader binding differs')
    source_names=['scripts/export-serato-generic-driver-fallback.py','scripts/export-serato-clock-handshake-evidence.py',
                  'scripts/export-serato-supported-evidence.py','scripts/export-serato256-sl3-api-path.py','scripts/ghidra/FocusedDecompile.java']
    result={'schema':'sl3.serato-generic-driver-fallback.v1','applicationSha256':app.sha,'installedMatches':True,
            'legacyLiteralRetention':inventories,'checkedInstructions':facts,'priorContractInstructionsRechecked':prior_checked,
            'baseDriverApi':{'constructor':'0x140bff9d0','vtable':hex(table),'locator':hex(locator),'type':'DriverAPI','slots':slots,
                'factoryDirectConstructionSites':generic_calls,'finalCheckedFactoryCall':'0x140bfe0b5','keyedValueContainerMember':'0x50',
                'constructorStringMember':'0x60','keyedSetter':'0x140c00360','keyedGetter':'0x140bfff40',
                'readinessStringWrapper':'0x140c00240','registryStringPredicate':'0x140bfffd0',
                'constantTrueSlots':['0x8','0xa0'],'constantFalseSlots':['0x38','0x90'],
                'constructorDirectCallTargets':['0x142117f10','0x142118190'],'transportCompletionInferredFromBooleans':False},
            'completeLeaves':leaves,'focusedFunctions':len(found),'focusedReportSha256':sha(focused_path),'focusedLogSha256':sha(log),
            'priorCurrentContractSha256':sha(prior_path),'priorHistoricalNamedLoaderSha256':sha(old_path),
            'localSourceSha256':{n:sha(ROOT/n) for n in source_names},
            'publishedSourceSha256':{n:hashlib.sha256((ROOT/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in source_names},
            'applicationExecuted':False,'applicationModified':False,'deviceAccess':False,'legacyDllLoaded':False,
            'newCurrentExternalRegistrationRouteIdentified':False,'currentSeratoAdmissionVerified':False,
            'limits':['Literal absence is bounded to exact terminated ASCII/UTF-16LE byte patterns in these three original executables, not all modules or generated/encrypted strings.',
                      'The prior seven explicit Rane product matches exclude PID 1; all factory predicates, indirect dispatch and actual runtime entry remain outside a universal exclusion proof.',
                      'The checked base setter writes keyed integer state and returns true. Callbacks, subclasses and transitive callees are not universally exhausted; this is not USB-control completion.',
                      'Constant Boolean methods, key-based detection and generic ASIO availability do not establish primary hardware admission or DVS.',
                      'The genuine SL3 discontinued support path remains independent; no support value, identity, response, resource or account state is changed.']}
    output=ROOT/'docs/evidence/serato500-generic-driver-fallback.json';output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'verified':True,'instructionFacts':len(facts),'priorInstructionsRechecked':prior_checked,'slots':len(slots),'completeLeaves':len(leaves),'focusedFunctions':len(found),'legacyPatterns':len(patterns)}))


if __name__=='__main__':main()
