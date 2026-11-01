"""Verify the original USB-only removal message and CUSBAudioManager dispatch."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = importlib.util.spec_from_file_location('usb_audio_original', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
    h = importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    app = h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', h.CURRENT_SHA)
    h.require(hashlib.sha256(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe').read_bytes()).hexdigest() == app.sha,
              'Installed image differs')
    checks = [
        # The ordinary removal callback checks both component-presence predicates.
        (0x142140ca1, 'call', '0x140c00ad0'), (0x142140ca6, 'test', 'al, al'),
        (0x142140ca8, 'jne', '0x142140e42'), (0x142140cb2, 'call', '0x140c00ab0'),
        (0x142140cb7, 'test', 'al, al'), (0x142140cb9, 'jne', '0x142140e42'),
        # The shared descriptor accessor and virtual-base identity getter calls.
        (0x142140cc7, 'call', '0x140c00570'), (0x142140ce2, 'call', 'qword ptr [rax + 0x18]'),
        (0x142140ce5, 'movzx', 'edi, ax'), (0x142140ce8, 'shl', 'rdi, 0x20'),
        (0x142140d28, 'call', '0x140c00570'), (0x142140d43, 'call', 'qword ptr [rax + 0x20]'),
        (0x142140d46, 'movzx', 'eax, ax'), (0x142140d49, 'shl', 'rax, 0x10'),
        (0x142140d4d, 'add', 'rdi, rax'), (0x142140d8c, 'call', '0x140c00570'),
        (0x142140da7, 'call', 'qword ptr [rax + 0x28]'), (0x142140daa, 'movzx', 'eax, ax'),
        (0x142140dad, 'add', 'rdi, rax'),
        (0x142140e14, 'mov', 'r8, rdi'), (0x142140e17, 'mov', 'edx, 0x2d5'),
        (0x142140e1f, 'call', '0x14185ee90'), (0x142140e3e, 'call', 'qword ptr [rax + 0x58]'),
        # Pointer-shaped message carries an opaque 64-bit scalar without dereference.
        (0x14185eea6, 'mov', 'rbx, r8'), (0x14185eec0, 'lea', 'rax, [rip + 0x17605f1]'),
        (0x14185eec7, 'mov', 'qword ptr [rdi + 0x38], rbx'),
        # Concrete USB audio manager interface construction and subscription.
        (0x14070fda3, 'lea', 'rax, [rip + 0x213338e]'), (0x14070fdaa, 'mov', 'qword ptr [rdi], rax'),
        (0x14070fdad, 'lea', 'rax, [rip + 0x21333b4]'), (0x14070fdb4, 'mov', 'qword ptr [rdi + 0x10], rax'),
        (0x14070fdf4, 'mov', 'r9d, 7'), (0x14070fdfa, 'xor', 'r8d, r8d'),
        (0x14070fdfd, 'mov', 'edx, 0x2d5'), (0x14070fe02, 'lea', 'rcx, [rdi + 0x10]'),
        (0x14070fe06, 'call', '0x14154cd50'),
        # Handler has multiple unwind fragments; verify each target separately.
        (0x1407108e6, 'mov', 'r8d, dword ptr [rdx + 0xc]'), (0x1407108ea, 'mov', 'rdi, rcx'),
        (0x1407108ed, 'sub', 'r8d, 0x2d4'), (0x1407108f4, 'je', '0x1407109a1'),
        (0x1407108fa, 'sub', 'r8d, 1'), (0x1407108fe, 'je', '0x140710974'),
        (0x140710974, 'mov', 'rax, qword ptr [rdx]'), (0x140710977, 'mov', 'rcx, rdx'),
        (0x14071097a, 'call', 'qword ptr [rax + 0x38]'), (0x14071097d, 'mov', 'rcx, rax'),
        (0x140710980, 'movzx', 'r9d, ax'), (0x140710984, 'shr', 'rcx, 0x10'),
        (0x140710988, 'shr', 'rax, 0x20'), (0x14071098c, 'movzx', 'r8d, cx'),
        (0x140710990, 'lea', 'rcx, [rdi - 0x10]'), (0x140710994, 'movzx', 'edx, ax'),
        (0x14071099c, 'jmp', '0x1407103b0'),
        # Disconnect path matches the transformed identity before requesting change.
        (0x1407103cb, 'mov', 'esi, r8d'), (0x1407103ce, 'mov', 'ebx, edx'),
        (0x1407103d0, 'mov', 'r14, rcx'), (0x140710403, 'movups', 'xmm0, xmmword ptr [rip + 0x2132dce]'),
        (0x14071040d, 'movsd', 'xmm0, qword ptr [rip + 0x2132dd3]'),
        (0x14071042c, 'xor', 'ebx, 0x13e5'), (0x140710466, 'xor', 'esi, 0x13e5'),
        (0x1407104a0, 'call', '0x141960f80'), (0x1407104a8, 'mov', 'rdx, qword ptr [rcx + 0x98]'),
        (0x1407104b2, 'call', 'rdx'), (0x1407104e8, 'cmp', 'rdx, rax'),
        (0x1407104eb, 'jne', '0x14071064c'), (0x1407104f1, 'call', '0x141960f80'),
        (0x1407104f9, 'mov', 'r8, qword ptr [rcx + 0x90]'), (0x140710500, 'xor', 'edx, edx'),
        (0x140710505, 'call', 'r8'),
        (0x140710565, 'lea', 'rax, [r14 + 0x50]'), (0x140710569, 'mov', 'qword ptr [rax + 0x10], r15'),
        (0x140710577, 'mov', 'byte ptr [rax], 0'), (0x140710588, 'call', '0x14070ff10'),
        (0x14071061e, 'xor', 'r9d, r9d'), (0x140710621, 'xor', 'r8d, r8d'),
        (0x140710624, 'mov', 'edx, 0x2ca'), (0x14071062c, 'call', '0x14185ee90'),
        (0x140710648, 'call', 'qword ptr [rax + 0x58]'),
    ]
    instructions = []
    for va, op, operands in checks:
        i = app.at(va, op, operands)
        instructions.append({'va': hex(va), 'bytes': i.bytes.hex(), 'instruction': op+' '+operands})
    classes = []
    for table, offset, name, slots in (
        (0x142843138, 0, '.?AVCUSBAudioManager@@', {}),
        (0x142843168, 0x10, '.?AVCUSBAudioManager@@', {0x18: 0x1407108e0}),
        (0x142fbf4b8, 0, '.?AVUserIO_VoidPtrMessageData@data@message@serato@@', {0x38: 0x140790070}),
        (0x14281cbe8, 0x738, '.?AVControllerDescriptor@dj@serato@@',
         {0x18: 0x1405c7d80, 0x20: 0x1405c7130, 0x28: 0x1405c6530}),
    ):
        locator = struct.unpack('<Q', app.data(table-8, 8))[0]
        col = struct.unpack('<6I', app.data(locator, 24))
        h.require(col[0] == 1 and col[1] == offset and app.base+col[5] == locator and app.text(app.base+col[3]+16) == name,
                  'USB audio removal RTTI differs')
        for slot, target in slots.items():
            h.require(struct.unpack('<Q', app.data(table+slot, 8))[0] == target, 'USB audio removal slot differs')
        classes.append({'type': name, 'vtable': hex(table), 'objectOffset': offset,
                        'checkedSlots': {hex(k): hex(v) for k, v in slots.items()}})
    h.require(app.rip(app.at(0x14070fda3)) == 0x142843138 and app.rip(app.at(0x14070fdad)) == 0x142843168 and
              app.rip(app.at(0x14185eec0)) == 0x142fbf4b8, 'Concrete table construction differs')
    h.require(app.data(0x140790070, 5) == bytes.fromhex('488b4138c3'), 'Scalar message getter differs')
    identity_getters = []
    for name, va, raw, delta, field in (
        ('VID', 0x1405c7d80, '0fb78170f9ffffc3', 0x690, 0xa8),
        ('PID', 0x1405c7130, '0fb78172f9ffffc3', 0x68e, 0xaa),
        ('revision', 0x1405c6530, '0fb78174f9ffffc3', 0x68c, 0xac),
    ):
        h.require(app.data(va, 8) == bytes.fromhex(raw) and 0x738-delta == field, 'Identity getter/field differs')
        identity_getters.append({'field':name,'getter':hex(va),'bytes':raw,'completeObjectFieldOffset':hex(field)})
    h.require(app.data(app.rip(app.at(0x140710403)), 16)+app.data(app.rip(app.at(0x14071040d)), 8)
              == b'Disconnecting USB device', 'Disconnect diagnostic differs')
    # These small pointer-presence helpers are not audio close calls.
    for va, raw in ((0x140502ae0, '488339000f94c0c3'),):
        h.require(app.data(va, len(bytes.fromhex(raw))) == bytes.fromhex(raw), 'Presence predicate primitive differs')
    for va, op, operands in ((0x140c00ab4, 'add', 'rcx, 0x10'), (0x140c00ab8, 'xor', 'edx, edx'),
                             (0x140c00aba, 'call', '0x140502ae0'), (0x140c00abf, 'xor', 'al, 1'),
                             (0x140c00ad4, 'xor', 'edx, edx'), (0x140c00ad6, 'call', '0x140502ae0'),
                             (0x140c00adb, 'xor', 'al, 1'), (0x140c0058a, 'mov', 'rax, qword ptr [rcx + 0x30]')):
        i = app.at(va, op, operands)
        instructions.append({'va':hex(va),'bytes':i.bytes.hex(),'instruction':op+' '+operands})
    result = {'scope':'Static USB-only removal through concrete USB audio manager; no final ASIO close or live callback proof',
              'applicationSha256':app.sha,'classes':classes,'instructions':instructions,'identityGetters':identity_getters,
              'message':{'id':0x2d5,'onlyWhenComponentPointersAt0And16Absent':True,
                         'payload':'(uint16 VID << 32) + (uint16 PID << 16) + uint16 revision',
                         'payloadStorageOffset':0x38,'busAddressOrUsbIdentityStringIncluded':False},
              'handler':{'receiverOffset':0x10,'messageSlot':0x18,'removalTarget':'0x1407103b0',
                         'diagnostic':'Disconnecting USB device','matchGuard':True,
                         'identityTransformationFullyInterpreted':False,'matchingBranchVirtualCall':{'slot':0x90,'argumentEdx':0},
                         'matchingBranchPublishes':{'messageId':0x2ca,'scalarPayload':0},
                         'finalAsioStopDisposeReleaseProved':False,'liveDispatchProved':False},
              'limits':['Callback and message delivery remain conditional; runtime receiver/service binding not observed',
                        'The 0x2d5 path precedes ordinary device-list 0x2df publication and is not that message',
                        'Concrete ASIO close/reopen consumer of 0x2ca or virtual slot 0x90 remains to be recovered',
                        'No application patch, device/USB request, firmware, registration, account or security operation']}
    (ROOT/'docs/evidence/serato500-usb-audio-removal.json').write_text(json.dumps(result, indent=2)+'\n',encoding='utf-8')
    print('Verified USB-only 0x2d5 identity message, concrete USB audio manager receiver and conditional disconnect/0x2ca publication; final ASIO close remains unproved')


if __name__ == '__main__':
    main()
