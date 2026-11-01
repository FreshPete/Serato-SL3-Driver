"""Verify the historical XML app-name match through the descriptor getter.

Original images are read as data. A conditional static match is not runtime
admission; no vendor code, registry, device or account operation is executed.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]


def load(filename):
    spec=importlib.util.spec_from_file_location(filename.replace('-','_'),ROOT/'scripts'/filename)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(target,sites,legacy,helper):
    image=helper.Image(f'artifacts/extracted/Serato DJ Pro {target["version"]}/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe',target['sha'])
    require=helper.require;facts=[]
    descriptor,*_=legacy.inspect(target)
    image.pe.parse_data_directories(directories=[1])
    imports={item.address:(entry.dll.decode('ascii'),(item.name or b'').decode('ascii'))
             for entry in image.pe.DIRECTORY_ENTRY_IMPORT for item in entry.imports}

    def fact(address,mnemonic,operands=None):
        row=image.at(address,mnemonic,operands)
        facts.append({'va':hex(address),'bytes':bytes(row.bytes).hex(),'assembly':row.mnemonic+' '+row.op_str})
        return row

    def literal(address,text):
        row=fact(address,'lea');value=image.text(image.rip(row));require(value==text,'XML/name literal differs')
        return value

    def rtti(table,type_name,object_offset):
        locator=struct.unpack('<Q',image.data(table-8,8))[0]
        signature,offset,constructor,type_rva,hierarchy,self_rva=struct.unpack('<6I',image.data(locator,24))
        require(signature==1 and image.base+self_rva==locator and offset==object_offset and constructor==0,
                'RTTI receiver identity differs')
        require(image.text(image.base+type_rva+16)==type_name,'RTTI type differs')
        return {'table':hex(table),'locator':hex(locator),'type':type_name,'receiverOffset':hex(offset)}

    def import_jump(address,name):
        row=next(image.dis.disasm(image.data(address,6),address))
        require(row.mnemonic=='jmp' and row.size==6,'Unexpected CRT import thunk')
        iat=image.rip(row);require(imports[iat]==('VCRUNTIME140.dll',name),'CRT import differs')
        return {'thunk':hex(address),'iat':hex(iat),'module':'VCRUNTIME140.dll','name':name}

    # The application-config default constructor installs the exact table used
    # below. This is not an observation of its mutable runtime singleton.
    table=image.rip(fact(sites['config_table_install'],'lea'))
    fact(sites['config_table_install']+7,'mov','qword ptr [rcx], rax')
    config_type=rtti(table,'.?AVAppConfig@@',0)
    reference=image.rip(fact(sites['config_factory']+0x20,'lea'))
    singleton_store=fact(sites['config_factory']+0x2c,'mov')
    require(singleton_store.op_str.endswith(', rcx') and image.rip(singleton_store)==reference,
            'Constructed application object does not feed the returned singleton reference')
    getter=struct.unpack('<Q',image.data(table+0x98,8))[0]
    require(getter==sites['name_getter'],'Application getter changed')
    fact(getter+0x19,'mov','r8d, 9')
    fact(getter+0x25,'mov','qword ptr [rdx + 0x10], 9')
    app=literal(getter+0x2d,'Serato DJ')
    copy=fact(getter+0x34,'call');copy_import=import_jump(copy.operands[0].imm,'memmove')
    fact(getter+0x39,'mov','rax, rbx');fact(getter+0x3c,'mov','byte ptr [rbx + 9], 0')

    # XML strings, current-name dispatch, length+memcmp gate, success byte and
    # accumulation are checked against original instruction boundaries.
    for address,text in zip(sites['xml_literals'],('supported_apps','app','value','app')):literal(address,text)
    for address,mnemonic,operands in sites['parser_facts']:fact(address,mnemonic,operands)
    comparison=import_jump(sites['memcmp'],'memcmp')
    require(descriptor['supportedApps']==['Serato DJ'],'SL3 supported-app declarations changed')

    # The parser's final support byte belongs to its temporary descriptor. Its
    # append helper forwards that base to the checked copy constructor.
    for address,mnemonic,operands in sites['copy_facts']:fact(address,mnemonic,operands)
    table=image.rip(fact(sites['descriptor_table_install'],'lea'))
    fact(sites['descriptor_table_install']+7,'mov','qword ptr [rsi + 0x10], rax')
    descriptor_type=rtti(table,'.?AVControllerDescriptor@@',0x10)
    leaf=struct.unpack('<Q',image.data(table+0x20,8))[0]
    require(leaf==sites['support_leaf'],'Support getter differs')
    leaf_bytes=b'\x0f\xb6\x81'+struct.pack('<I',sites['field']-0x10)+b'\xc3'
    require(image.data(leaf,8)==leaf_bytes,'Support leaf bytes differ')
    require(sites['temp_store']-sites['temp_base']==sites['field'],'Temporary descriptor field offset differs')
    return {'version':target['version'],'binarySha256':target['sha'],'sl3XmlSha256':descriptor['resource']['xmlSha256'],
            'declaredApps':descriptor['supportedApps'],'constructedAppConfig':config_type,'nameGetter':hex(getter),
            'appConfigReference':hex(reference),
            'constructedName':app,'copyImport':copy_import,'comparisonImport':comparison,
            'descriptorInterface':descriptor_type,'supportGetter':hex(leaf),'supportGetterSlot':'0x20',
            'completeObjectSupportOffset':hex(sites['field']),'leafBytes':leaf_bytes.hex(),
            'conditionalStaticAppNameMatch':app in descriptor['supportedApps'],
            'runtimeSingletonOrDescriptorObserved':False,'facts':facts}


def main():
    legacy=load('export-serato-legacy-descriptors.py');helper=load('export-serato-clock-handshake-evidence.py')
    targets=[dict(config_factory=0x1402c4880,config_table_install=0x1402c4921,name_getter=0x1402c7d60,memcmp=0x1408d4c60,
        xml_literals=[0x140356e37,0x140356e55,0x140356e73,0x140356f68],field=0x4d8,
        descriptor_table_install=0x1400f02c8,support_leaf=0x1400e9810,temp_store=0xbd8,temp_base=0x700,
        parser_facts=[(0x140356e30,'xor','r15b, r15b'),(0x140356e33,'mov','dword ptr [rbp + 0x1c], r15d'),
            (0x140356e46,'mov','r13d, 1'),(0x140356ebc,'call','0x1402c4880'),
            (0x140356ece,'call','qword ptr [rax + 0x98]'),(0x140356f05,'cmp','r8, qword ptr [rax + 0x10]'),
            (0x140356efe,'mov','r8, qword ptr [rbp + 0x548]'),
            (0x140356f09,'jne','0x140356f19'),(0x140356f0b,'call','0x1408d4c60'),
            (0x140356f10,'test','eax, eax'),(0x140356f12,'jne','0x140356f19'),
            (0x140356f14,'mov','r14b, 1'),(0x140356f17,'jmp','0x140356f1c'),(0x140356f19,'xor','r14b, r14b'),
            (0x140356f59,'movzx','r15d, r15b'),(0x140356f5d,'test','r14b, r14b'),
            (0x140356f60,'cmovne','r15d, r13d'),(0x140356f64,'mov','dword ptr [rbp + 0x1c], r15d'),
            (0x140356fb7,'jmp','0x140356e6a'),
            (0x14035b840,'mov','eax, dword ptr [rbp + 0x1c]'),(0x14035b843,'mov','byte ptr [rbp + 0xbd8], al'),
            (0x14035b998,'lea','rdx, [rbp + 0x700]'),(0x14035b99f,'call','0x14035cb70')],
        copy_facts=[(0x14035cb8d,'call','0x1400f0230'),(0x1400f0249,'mov','rbp, rdx'),(0x1400f024c,'mov','rsi, rcx'),
                    (0x1400f0be6,'movzx','eax, byte ptr [rbp + 0x4d8]'),(0x1400f0bed,'mov','byte ptr [rsi + 0x4d8], al')]),
        dict(config_factory=0x1402c56f0,config_table_install=0x1402c5791,name_getter=0x1402c8bd0,memcmp=0x1408d81f0,
        xml_literals=[0x140357ca8,0x140357cc6,0x140357ce4,0x140357dd9],field=0x4f0,
        descriptor_table_install=0x1400f0cd8,support_leaf=0x1400ea220,temp_store=0xc10,temp_base=0x720,
        parser_facts=[(0x140357ca1,'xor','r15b, r15b'),(0x140357ca4,'mov','dword ptr [rbp + 0x14], r15d'),
            (0x140357cb7,'mov','r12d, 1'),(0x140357d2d,'call','0x1402c56f0'),
            (0x140357d3f,'call','qword ptr [rax + 0x98]'),(0x140357d76,'cmp','r8, qword ptr [rax + 0x10]'),
            (0x140357d6f,'mov','r8, qword ptr [rbp + 0x560]'),
            (0x140357d7a,'jne','0x140357d8a'),(0x140357d7c,'call','0x1408d81f0'),
            (0x140357d81,'test','eax, eax'),(0x140357d83,'jne','0x140357d8a'),
            (0x140357d85,'mov','r14b, 1'),(0x140357d88,'jmp','0x140357d8d'),(0x140357d8a,'xor','r14b, r14b'),
            (0x140357dca,'movzx','r15d, r15b'),(0x140357dce,'test','r14b, r14b'),
            (0x140357dd1,'cmovne','r15d, r12d'),(0x140357dd5,'mov','dword ptr [rbp + 0x14], r15d'),
            (0x140357e28,'jmp','0x140357cdb'),
            (0x14035c811,'mov','eax, dword ptr [rbp + 0x14]'),(0x14035c814,'mov','byte ptr [rbp + 0xc10], al'),
            (0x14035c9b6,'lea','rdx, [rbp + 0x720]'),(0x14035c9bd,'call','0x14035dbf0')],
        copy_facts=[(0x14035dc0d,'call','0x1400f0c40'),(0x1400f0c59,'mov','rbp, rdx'),(0x1400f0c5c,'mov','rsi, rcx'),
                    (0x1400f1695,'movzx','eax, byte ptr [rbp + 0x4f0]'),(0x1400f169c,'mov','byte ptr [rsi + 0x4f0], al')])]
    versions=[inspect(target,sites,legacy,helper) for target,sites in zip(legacy.TARGETS,targets)]
    record={'scope':'Historical declared-app name match, default AppConfig getter, descriptor byte copy and getter only',
            'versions':versions,'runtimeEligibilityVerified':False,'currentSeratoIntegrationVerified':False,
            'vendorCodeExecuted':False,'exporterSha256':sha(Path(__file__)),
            'dependencySha256':{name:sha(ROOT/'scripts'/name) for name in ('export-serato-legacy-descriptors.py','export-serato-clock-handshake-evidence.py')},
            'limits':['The default constructed AppConfig table/name is checked; runtime singleton mutation/replacement is not excluded',
                      'Conditional static matching is not executed parser acceptance, connection eligibility or audio/DVS support',
                      'The descriptor getter is identified; complete runtime consumer/dispatch coverage is not established']}
    path=ROOT/'docs/evidence/serato-historical-app-support-20261101.json'
    path.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print('Checked both historical app-name paths; conditional match true, runtime admission unverified')


if __name__=='__main__':main()
