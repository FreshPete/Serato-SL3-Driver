"""Inventory direct pointer-message publishers in the pinned Serato 5.0 image."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import struct
from types import SimpleNamespace
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PUBLISH = 0x1404db170
CONSTRUCT = 0x14185ee90
SECOND_PUBLISH = 0x1404dfe10
BOUND_PUBLISH = 0x14154bdc0
SELECT = 0x2ca


def module(name):
    return runpy.run_path(str(ROOT/'scripts'/name))


def direct_calls(app, targets):
    calls = {target: [] for target in targets}
    for section in app.pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        data = section.get_data()
        start = app.base + section.VirtualAddress
        # Match one byte at a time so an opcode-looking operand cannot hide a
        # following candidate. Confirm it at a decoded instruction boundary.
        for match in re.finditer(rb'[\xe8\xe9]', data):
            offset = match.start()
            if offset + 5 > len(data):
                break
            address = start + offset
            target = address + 5 + struct.unpack_from('<i', data, offset + 1)[0]
            if target in calls:
                row = app.at(address)
                if row.mnemonic not in ('call','jmp') or row.op_str != hex(target):
                    raise ValueError(f'Unclassified branch candidate at {address:#x}')
                calls[target].append(address)
    return calls


def argument(app, address):
    rows = app.function(address)
    index = next(i for i,row in enumerate(rows) if row.address==address)
    for row in reversed(rows[max(0,index-14):index]):
        if row.mnemonic in ('call','jmp','ret'):
            break
        if not {'rdx','edx','dx','dh','dl'}.intersection(map(row.reg_name,row.regs_access()[1])):
            continue
        if row.mnemonic=='mov' and row.op_str.startswith('edx, '):
            source = row.op_str.split(', ',1)[1]
            literal = int(source,0) if re.fullmatch(r'(?:0x[0-9a-f]+|[0-9]+)',source) else None
            return {'call':hex(address),'function':hex(rows[0].address),'argumentInstruction':hex(row.address),
                    'idSource':source,'literalId':hex(literal) if literal is not None else None}
        break
    raise ValueError(f'No bounded ID setup at {address:#x}')


def profile(app, candidate_path, require):
    recipe = module('prepare-serato-installed-phase-archive.py')
    reader = SimpleNamespace(**module('inspect-serato-resource-archive.py'))
    archive = module('prepare-serato-sl3-archive.py')
    raw = candidate_path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==recipe['PHASE_SHA'],'Expected the prepared SL3 Phase archive')
    seed = app.data(app.base+0x2f2de98,16)
    key = struct.unpack('<4I',bytes((((x^0xcf)>>(n&7))|((x^0xcf)<<((8-(n&7))&7)))&255 for n,x in enumerate(seed)))
    _, entries = archive['inspect_index'](raw,key,reader)
    row = entries[-1]
    xml, _ = reader.unpack_member(raw[row['offset']:row['offset']+row['size']],key,row['name'])
    require(hashlib.sha256(xml).hexdigest()==recipe['XML_SHA'],'Expected the exact prepared descriptor')
    device, = ET.fromstring(xml).findall('native_pro_device')
    require(device.get('name')=='Rane SL3' and
            device.find('has_hid').get('value')=='false' and device.find('hid') is None and
            device.find('midi') is None,'Prepared profile control contract differs')
    return {'archiveSha256':recipe['PHASE_SHA'],'descriptorSha256':recipe['XML_SHA'],'type':device.tag,
            'hasHid':False,'hidSection':False,'midiSection':False}


def edit_box_contract(app, require):
    table, slot, handler = 0x14286ff10, 0x98, 0x140795400
    locator = struct.unpack('<Q',app.data(table-8,8))[0]
    signature, offset, _, type_rva, _, self_rva = struct.unpack('<6I',app.data(locator,24))
    require(signature==1 and offset==0 and app.base+self_rva==locator and
            app.text(app.base+type_rva+16)=='.?AVCGUIEditBox@@','Edit-box RTTI differs')
    require(struct.unpack('<Q',app.data(table+slot,8))[0]==handler,'Edit-box virtual target differs')
    for constructor, store in ((0x140793386,0x14079338d),(0x1407934fc,0x140793503)):
        require(app.rip(app.at(constructor,'lea'))==table,'Edit-box constructor table differs')
        app.at(store,'mov','qword ptr [rdi], rax')
    for start, end, aliases in (
        (0x140795419,0x140795881,{'rdi','edi','di','dil'}),
        (0x1404dfe27,0x1404dfe69,{'rsi','esi','si','sil'}),
        (0x14185eea6,0x14185eec7,{'rbx','ebx','bx','bl','bh'}),
    ):
        writes = [row.address for row in app.function(start) if start<=row.address<=end and
                  aliases.intersection(map(row.reg_name,row.regs_access()[1]))]
        require(writes==[start],'Edit-box pointer register changed before forwarding')
    return {'type':'CGUIEditBox','vtable':hex(table),'slot':hex(slot),'handler':hex(handler),
            'defaultId':'disabled_minus_one','fieldOffsets':['0x2c0','0x2d0'],
            'defaultNotificationIds':['0x5e6','0x5e7'],
            'configuredCalls':['0x14079580d','0x140795881'],'payload':'complete_edit_box_receiver',
            'pointerIsRegisteredDescriptor':False,'laterMessageIdWritersExhausted':False}


def inspect(application, candidate):
    api = module('export-serato-clock-handshake-evidence.py')
    require = api['require']
    app = api['Image'](application,api['CURRENT_SHA'])
    calls = direct_calls(app,(PUBLISH,CONSTRUCT,SECOND_PUBLISH,BOUND_PUBLISH))
    require(tuple(map(len,calls.values()))==(10,64,20,5),'Direct pointer call inventory differs')
    groups = {hex(target):[argument(app,address) for address in addresses] for target,addresses in calls.items()}
    require({row['call']:row['idSource'] for row in groups[hex(SECOND_PUBLISH)] if row['literalId'] is None}
            == {'0x14079580d':'dword ptr [rdi + 0x2c0]', '0x140795881':'dword ptr [rdi + 0x2d0]'},
            'Forwarded nonliteral message arguments differ')
    positive = {
        0x1405294b2: 'midi', 0x1405b0c48: 'installer_completion', 0x140710280: 'usb_audio_manager',
        0x140545b53: 'hid_existing_connection', 0x140546aa6: 'hid_new_connection',
    }
    clear = {0x140527b28,0x140545666,0x14071062c,0x140718d6c,0x141373ba0}
    require({int(row['call'],16) for rows in groups.values() for row in rows if row['literalId']==hex(SELECT)}
            == set(positive)|clear,'Immediate primary-pointer publication inventory differs')

    facts = {
        0x140527afa:'test r8, r8',0x140527afd:'jne 0x140527b49',0x140545657:'xor r8d, r8d',
        0x140529482:'je 0x1405294b9',0x1405294a3:'mov r8, r12',0x1405b0c39:'mov r8, rbx',
        0x140710271:'mov r8, rbx',0x140710621:'xor r8d, r8d',0x140718d61:'xor r8d, r8d',
        0x141373b95:'xor r8d, r8d',0x140545923:'mov rbp, qword ptr [rbx + 0x50]',
        0x14054593b:'lea rcx, [rbp + 0x10]',0x140545942:'call qword ptr [rax + 0x90]',
        0x14054594a:'je 0x140545b76',0x140545958:'jne 0x140545b76',
        0x140545a37:'jne 0x140545b18',0x140545a4f:'jne 0x140545b18',
        0x140545b48:'mov r8, rbp',0x140545b72:'call qword ptr [rax + 0x58]',
        0x140546560:'mov ecx, dword ptr [rax + 0x314]',0x140546569:'je 0x140546604',
        0x140546572:'je 0x140546604',0x140546892:'call qword ptr [rax + 0x90]',
        0x14054689a:'je 0x140546ace',0x1405468a8:'jne 0x140546ace',
        0x1405468ae:'mov rdi, qword ptr [r14]',0x140546989:'jne 0x140546a6b',
        0x1405469a1:'jne 0x140546a6b',0x140546a9b:'mov r8, rdi',
        0x140546ac5:'call qword ptr [rax + 0x58]',0x1404dfe90:'call qword ptr [rax + 0x50]',
        0x140793413:'mov dword ptr [rdi + 0x2c0], 0xffffffff',
        0x14079342b:'mov dword ptr [rdi + 0x2d0], 0xffffffff',
        0x140793589:'mov dword ptr [rdi + 0x2c0], 0xffffffff',
        0x1407935a0:'mov dword ptr [rdi + 0x2d0], 0xffffffff',
        0x140795419:'mov rdi, rcx',0x1407957df:'cmp edx, -1',0x1407957e2:'je 0x140795817',
        0x140795803:'mov r8, rdi',0x140795835:'mov edx, 0x5e6',
        0x140795853:'cmp edx, -1',0x140795856:'je 0x14079588b',
        0x140795877:'mov r8, rdi',0x1407958a9:'mov edx, 0x5e7',
        0x1404dfe27:'mov rsi, r8',0x1404dfe69:'mov r8, rsi',0x1404dfe71:'call 0x14185ee90',
        0x14185eea6:'mov rbx, r8',0x14185eec7:'mov qword ptr [rdi + 0x38], rbx',
        0x14050591e:'mov rdi, rdx',0x140505940:'mov rcx, qword ptr [rax]',
        0x140505943:'cmp rcx, rdi',0x140505946:'je 0x140505a49',
    }
    checked = []
    for address, expected in facts.items():
        row = app.at(address)
        require(f'{row.mnemonic} {row.op_str}'==expected,f'Instruction differs at {address:#x}')
        checked.append({'va':hex(address),'bytes':bytes(row.bytes).hex(),'assembly':expected})
    return {'schema':'sl3.serato-primary-publishers.v1','applicationSha256':app.sha,
            'directCallArguments':groups,'nonNullSelectionPaths':{hex(k):v for k,v in positive.items()},
            'nullSelectionCalls':[hex(k) for k in sorted(clear)],'instructionChecks':checked,
            'preparedProfile':profile(app,candidate,require),
            'editBoxNotifications':edit_box_contract(app,require),
            'limits':['Immediate IDs at decoded direct calls only',
                      'Later edit-box field assignments and indirect call targets are unresolved',
                      'No Serato process, USB access or runtime route verified']}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application',required=True,type=Path)
    parser.add_argument('--candidate',required=True,type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.application,args.candidate),indent=2))
