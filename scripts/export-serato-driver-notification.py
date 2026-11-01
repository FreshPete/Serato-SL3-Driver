"""Verify current DriverAPI action-6 notification routing offline; never run Serato."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    helper_path = ROOT/'scripts/export-serato-clock-handshake-evidence.py'
    spec = importlib.util.spec_from_file_location('image_reader', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    app = helper.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', helper.CURRENT_SHA)
    require = helper.require
    facts = []

    def fact(address, assembly):
        instruction = app.at(address)
        require(instruction.mnemonic+' '+instruction.op_str == assembly, 'Instruction differs: '+hex(address))
        facts.append({'va': hex(address), 'bytes': bytes(instruction.bytes).hex(), 'assembly': assembly})
        return instruction

    for address, assembly in [
        (0x1421daeb9, 'call qword ptr [rdx + 0x90]'),
        (0x1421daebf, 'movzx r13d, al'),
        (0x1421daef0, 'test r13b, r13b'),
        (0x1421daef3, 'je 0x1421daf2b'),
        (0x1421daf2b, 'test bl, bl'),
        (0x1421daf2d, 'mov dword ptr [rbp + 0x67], 7'),
        (0x1421daf34, 'je 0x1421daf3d'),
        (0x1421daf36, 'mov dword ptr [rbp + 0x67], 6'),
        (0x1421de935, 'movsxd rax, dword ptr [r14 + 0x28]'),
        (0x1421de939, 'cmp eax, 0xe'),
        (0x1421de949, 'mov edx, dword ptr [rcx + rax*4 + 0x21debe4]'),
        (0x1421de950, 'add rdx, rcx'),
        (0x1421de953, 'jmp rdx'),
        (0x1421dea78, 'mov rax, qword ptr [rdi]'),
        (0x1421dea7b, 'mov rbx, qword ptr [rax + 0x38]'),
        (0x14213f786, 'mov edx, 0x52'),
        (0x14213f78e, 'call 0x14185ee90'),
        (0x14213f7ad, 'call qword ptr [rax + 0x58]'),
        (0x14185eec7, 'mov qword ptr [rdi + 0x38], rbx'),
        (0x14137b7cb, 'mov ecx, dword ptr [rdx + 0xc]'),
        (0x14137b7e0, 'dec ecx'),
        (0x14137b7e2, 'cmp ecx, 0x53'),
        (0x14137b7f5, 'movzx eax, byte ptr [rdx + rax + 0x137c8d4]'),
        (0x14137b7fd, 'mov ecx, dword ptr [rdx + rax*4 + 0x137c8a0]'),
        (0x14137b807, 'jmp rcx'),
        (0x14137bdd9, 'mov rdx, rdi'),
        (0x14137bde1, 'call 0x141380440'),
        (0x14137bde7, 'lea rdi, [rsi + 0xb0]'),
        (0x14137bec5, 'call 0x14137b670'),
        (0x141380465, 'call 0x142120260'),
        (0x14137b6d2, 'lea rcx, [rsi + 0xb0]'),
        (0x14137b6d9, 'call 0x14137b450'),
        (0x14137b6e5, 'call 0x140f1fa40'),
        (0x14137b6ed, 'je 0x14137b6f8'),
        (0x14137b6f5, 'call qword ptr [rdx + 0x40]'),
        (0x14137b707, 'call 0x1405f4970'),
        (0x14137b720, 'call 0x141380260'),
    ]:
        fact(address, assembly)
    require(app.rip(fact(0x1421de942, 'lea rcx, [rip - 0x21de949]')) == app.base,
            'Action table base differs')
    require(app.base+struct.unpack('<I', app.data(0x1421debe4+6*4, 4))[0] == 0x1421dea78,
            'Action-6 table entry differs')
    require(app.rip(fact(0x14137b7ee, 'lea rdx, [rip - 0x137b7f5]')) == app.base,
            'Message table base differs')
    index = app.data(0x14137c8d4+0x52-1, 1)[0]
    require(index == 9 and app.base+struct.unpack('<I', app.data(0x14137c8a0+4*index,4))[0] == 0x14137bdd9,
            'Message-0x52 two-level table differs')
    table = 0x1431c3f28
    require(struct.unpack('<Q', app.data(table+0x38, 8))[0] == 0x14213f740, 'Observer slot differs')
    locator = struct.unpack('<Q', app.data(table-8, 8))[0]
    signature, offset, displacement, type_rva, hierarchy, self_rva = struct.unpack('<6I', app.data(locator,24))
    require(signature == 1 and offset == 0x88 and displacement == 0 and app.base+self_rva == locator
            and app.text(app.base+type_rva+16) == '.?AVDeviceManager@@', 'Observer RTTI differs')
    payload_types = []
    for address, name in [(0x141380449, '.?AVUserIO_VoidPtrMessageData@data@message@serato@@'),
                          (0x141380452, '.?AVUserIO_MessageData@data@message@serato@@')]:
        instruction = app.at(address)
        target = app.rip(instruction)
        require(app.text(target+16) == name, 'Message payload RTTI differs')
        facts.append({'va': hex(address), 'bytes': bytes(instruction.bytes).hex(),
                      'assembly': instruction.mnemonic+' '+instruction.op_str})
        payload_types.append({'typeDescriptorVa': hex(target), 'name': name})
    focused_path = ROOT/'analysis/serato500-action6-ui-01.json'
    focused = json.loads(focused_path.read_text(encoding='utf-8-sig'))
    require(focused['binary_sha256'] == app.sha, 'Focused report identity differs')
    focused_rows = []
    for start in [0x140f1fa40, 0x14137b670, 0x141380440, 0x14137b450]:
        row = next(f for f in focused['functions'] if int(f['start'],16) == start)
        require(row['complete'] is True and (start,int(row['end_exclusive'],16)) in app.spans,
                'Focused function incomplete or range differs')
        focused_rows.append({'start': row['start'], 'endExclusive': row['end_exclusive'],
                             'pseudocode': row['pseudocode'].replace('\r','')})
    ranges = []
    for start in [0x1421dad00,0x1421de890,0x14213f740,0x14185ee90,0x14137b790,
                  0x140f1fa40,0x14137b670,0x141380440,0x14137b450]:
        span = next(span for span in app.spans if span[0] == start)
        ranges.append({'start':hex(start),'endExclusive':hex(span[1]),
                       'sha256':hashlib.sha256(app.data(start,span[1]-start)).hexdigest()})
    result = {'scope':'Selected current DriverAPI notification paths in original disk bytes; no application execution',
              'binarySha256':app.sha, 'instructions':facts, 'unwindRanges':ranges, 'focusedFunctions':focused_rows,
              'action':6, 'observer':{'tableVa':hex(table),'completeObjectOffset':offset,'slot':56,'targetVa':'0x14213f740'},
              'messageId':82,'messageTableIndex':index,'messageHandlerCaseVa':'0x14137bdd9','payloadTypes':payload_types,
              'finding':'Conditional DriverAPI action 6 emits UserIO message 0x52; its receiver performs keyed state/object handling through +0xb0 and a conditional virtual +0x40 call.',
              'currentSl3AdmissionVerified':False,'audioOpenVerified':False,'dvsVerified':False,
              'limits':['The actual SL3 stub still takes the discontinued support branch; action 6 is a support-1 counterfactual.',
                        'A notification is neither an ASIO open nor proof of a new blocking hardware/driver requirement.',
                        'The dynamic target and full semantics of virtual +0x40 are not identified.',
                        'No exhaustive call graph, runtime observer identity or complete application path is proven.',
                        'Original descriptor provision, component/handshake/audio selection and legitimate product/account behavior remain independent.'],
              'dependencies':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in
                              [Path(__file__),helper_path,focused_path,ROOT/'scripts/ghidra/FocusedDecompile.java']}}
    output=ROOT/'docs/evidence/serato500-driver-notification.json'
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(f'Verified {len(facts)} instruction facts, nine unwind ranges, two switch mappings, observer RTTI and four focused functions')


if __name__ == '__main__':
    main()
