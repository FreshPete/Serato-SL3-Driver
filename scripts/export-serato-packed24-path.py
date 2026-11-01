"""Check original Serato legacy ASIO type-17 format/converter dispatch offline."""
import hashlib
import json
from pathlib import Path
import struct

import capstone
import pefile

ROOT = Path(__file__).resolve().parents[1]
SHA = '66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265'
BINARY = ROOT/'artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    raw = BINARY.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SHA and sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe')) == SHA,
            'Original installed/extracted executable differs')
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    require(base == 0x140000000, 'Unexpected image base')
    dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    dis.detail = True
    evidence = []

    def data(va, size):
        raw = pe.get_data(va-base, size)
        require(len(raw) == size, 'Truncated image read')
        return raw

    def u32(va):
        return struct.unpack('<I', data(va, 4))[0]

    def at(va, mnemonic, operands):
        row = next(dis.disasm(data(va, 15), va))
        require(row.mnemonic == mnemonic and row.op_str == operands, 'Instruction differs: '+hex(va))
        evidence.append({'va': hex(va), 'bytes': row.bytes.hex(), 'instruction': mnemonic+' '+operands})
        return row

    def mapped(table, mapping, value):
        index = data(mapping+value, 1)[0]
        return base+u32(table+4*index)

    # Code and adjacent jump tables have separate extents. Tables are data.
    at(0x142216b90, 'cmp', 'ecx, 0x1b')
    at(0x142216b9f, 'movzx', 'eax, byte ptr [rdx + rax + 0x2216be8]')
    at(0x142216ba7, 'mov', 'ecx, dword ptr [rdx + rax*4 + 0x2216bd4]')
    require(mapped(0x142216bd4, 0x142216be8, 17) == 0x142216bc5, 'ASIO type-17 format case differs')
    at(0x142216bc5, 'mov', 'eax, 4')
    # The application's own type-name switch corroborates the numeric identity.
    require(base+u32(0x142216b18+17*4) == 0x142216afc, 'Type-name case differs')
    name = at(0x142216afc, 'lea', 'rcx, [rip + 0xfd1515]')
    name_va = name.address+name.size+name.operands[1].mem.disp
    require(data(name_va, 16).split(b'\0', 1)[0] == b'ASIOSTInt24LSB\n', 'Type-name literal differs')
    # Input/output optional byte-order/shift normalizers default to null/zero.
    for start, table, terminal in ((0x142217e40, 0x142217f30, 0x142217f2e),
                                    (0x142217fa0, 0x142218090, 0x14221808e)):
        at(start, 'xor', 'eax, eax')
        at(start+2, 'mov', 'dword ptr [r8], eax')
        at(start+5, 'mov', 'qword ptr [rdx], rax')
        require(base+u32(table+17*4) == terminal, 'Type-17 normalizer case differs')
        at(terminal, 'ret', '')
    # Sample-byte-width helper masks the non-interleaved flag then dispatches.
    at(0x1422158b0, 'btr', 'ecx, 0x1f')
    require(mapped(0x1422158f4, 0x142215908, 4-1) == 0x1422158e2, 'Packed-24 width case differs')
    at(0x1422158e2, 'mov', 'eax, 3')
    require(mapped(0x1422158f4, 0x142215908, 1-1) == 0x1422158e8, 'Float width case differs')
    at(0x1422158e8, 'mov', 'eax, 4')
    # Open forwards mapped host formats into the shared buffer processor.
    checks = [
        (0x1422179de,'mov','ecx, ebx'), (0x1422179e0,'call','0x142216b90'),
        (0x1422179f5,'mov','esi, eax'), (0x1422179f7,'call','0x142217e40'),
        (0x142217a3b,'call','0x142216b90'), (0x142217a50,'mov','r10d, eax'),
        (0x142217a53,'call','0x142217fa0'), (0x142217a7e,'mov','r9d, esi'),
        (0x142217ad1,'mov','dword ptr [rsp + 0x30], r10d'), (0x142217adf,'call','0x142221680'),
        (0x142221698,'mov','r13d, r9d'), (0x1422216a2,'mov','r12d, r8d'),
        (0x1422217c8,'mov','edx, r12d'), (0x1422217cb,'mov','ecx, r13d'),
        (0x1422217d1,'call','0x142223d80'), (0x1422217d9,'mov','qword ptr [rbx + 0x28], rax'),
        (0x14222187a,'mov','r15d, dword ptr [rsp + 0x80]'),
        (0x142221894,'mov','ebp, dword ptr [rsp + 0x78]'),
        (0x1422218b4,'mov','edx, r15d'), (0x1422218b7,'mov','ecx, ebp'),
        (0x1422218bc,'call','0x142223d80'), (0x1422218c4,'mov','qword ptr [rbx + 0x48], rax'),
        (0x142223d80,'btr','ecx, 0x1f'), (0x142223dac,'btr','edx, 0x1f'),
        (0x142223f46,'btr','edx, 0x1f'),
    ]
    for va, mnemonic, operands in checks:
        at(va, mnemonic, operands)
    require(mapped(0x1422240d0, 0x1422240ec, 4-1) == 0x142223f46 and
            mapped(0x142224184, 0x1422241a0, 1-1) == 0x142223f6b, 'Input 4-to-1 dispatch differs')
    require(mapped(0x1422240d0, 0x1422240ec, 1-1) == 0x142223dac and
            mapped(0x14222410c, 0x142224128, 4-1) == 0x142223e01, 'Output 1-to-4 dispatch differs')

    def pointer(va, mnemonic, operands, slot, target):
        row = at(va, mnemonic, operands)
        mem = [op.mem for op in row.operands if op.type == capstone.x86.X86_OP_MEM][0]
        require(row.address+row.size+mem.disp == slot and struct.unpack('<Q', data(slot, 8))[0] == target,
                'Initial converter table pointer differs')
        return {'instruction': hex(va), 'slot': hex(slot), 'initialFunction': hex(target)}

    input_pointer = pointer(0x142223f6b,'mov','rax, qword ptr [rip + 0x1862c76]',0x143a86be8,0x142223640)
    output_pointers = [
        pointer(0x142223e0d,'mov','rax, qword ptr [rip + 0x1862d14]',0x143a86b28,0x142222db0),
        pointer(0x142223e16,'cmovne','rax, qword ptr [rip + 0x1862d02]',0x143a86b20,0x142222d40),
        pointer(0x142223e1f,'mov','rax, qword ptr [rip + 0x1862d12]',0x143a86b38,0x142222ef0),
        pointer(0x142223e28,'cmovne','rax, qword ptr [rip + 0x1862d00]',0x143a86b30,0x142222e60),
    ]
    at(0x142223e04,'and','ecx, 2')
    at(0x142223e07,'test','r8b, 1')
    at(0x142223e0b,'je','0x142223e1f')
    # Decode three little-endian bytes, place signed container in high 24 bits,
    # then convert signed int32 -> double -> scaled double -> float32.
    for va, mnemonic, operands in [
        (0x142223655,'lea','eax, [r9 + r9*2]'), (0x14222365f,'shl','rdx, 2'),
        (0x142223670,'movzx','eax, byte ptr [r8 + 1]'),
        (0x142223675,'movzx','ecx, byte ptr [r8 + 2]'), (0x14222367a,'shl','ecx, 8'),
        (0x14222367d,'or','ecx, eax'), (0x14222367f,'movzx','eax, byte ptr [r8]'),
        (0x142223683,'shl','ecx, 8'), (0x142223689,'or','ecx, eax'),
        (0x14222368b,'shl','ecx, 8'), (0x14222368e,'movd','xmm0, ecx'),
        (0x142223692,'cvtdq2pd','xmm0, xmm0'), (0x142223696,'mulsd','xmm0, xmm1'),
        (0x14222369a,'cvtpd2ps','xmm0, xmm0'), (0x14222369e,'movss','dword ptr [r11], xmm0'),
    ]:
        at(va, mnemonic, operands)
    at(0x14222364d,'movsd','xmm1, qword ptr [rip + 0xfba4c3]')
    require(struct.unpack('<d', data(0x1431ddb18, 8))[0] == 2**-31, 'Input normalization constant differs')
    # No-clip/no-dither output variant: inspect only, not adopted as a new policy.
    at(0x142222d4d,'movss','xmm1, dword ptr [rip + 0xdc8893]')
    require(struct.unpack('<f', data(0x142feb5e8, 4))[0] == 2**31, 'Output scale differs')
    for va, mnemonic, operands in [
        (0x142222d55,'lea','eax, [rdx + rdx*2]'), (0x142222d78,'mulss','xmm0, xmm1'),
        (0x142222d7c,'cvttss2si','ecx, xmm0'), (0x142222d82,'sar','eax, 8'),
        (0x142222d85,'mov','byte ptr [r10], al'), (0x142222d8a,'sar','eax, 0x10'),
        (0x142222d8d,'sar','ecx, 0x18'), (0x142222d90,'mov','byte ptr [r10 + 1], al'),
        (0x142222d94,'mov','byte ptr [r10 + 2], cl'),
    ]:
        at(va, mnemonic, operands)
    projections = []
    for signed in (-8388608,-8388607,-1,0,1,8388606,8388607):
        raw = (signed & 0xffffff).to_bytes(3,'little')
        high = int.from_bytes(raw,'little') << 8
        signed32 = high-2**32 if high & 2**31 else high
        projected = struct.unpack('<f', struct.pack('<f', signed32*2**-31))[0]
        require(projected == signed/2**23, 'Derived input projection differs')
        projections.append({'rawLittleEndian': raw.hex(), 'signed24': signed, 'derivedFloat32': projected})
    result = {
        'scope': 'Execution-free original legacy ASIO type-17 format and conditional converter-table path; no application audio validation',
        'binarySha256': SHA, 'asioType': 17, 'asioTypeName': 'ASIOSTInt24LSB',
        'exporterSha256': sha(Path(__file__)),
        'hostFormat': 4, 'hostBytesPerSample': 3, 'floatUserFormat': 1, 'floatBytesPerSample': 4,
        'type17ExtraInputNormalizer': None, 'type17ExtraOutputNormalizer': None,
        'processorInputConverterOffset': '0x28', 'processorOutputConverterOffset': '0x48',
        'inputPointer': input_pointer, 'outputPointers': output_pointers,
        'inputNormalization': 'signed24 / 8388608; derived from high-aligned signed32 times 2^-31',
        'derivedInputProjections': projections,
        'outputFlagCases': {'0':'0x142222ef0','1':'0x142222db0','2':'0x142222e60','3':'0x142222d40'},
        'instructions': evidence,
        'primaryReference': 'https://github.com/PortAudio/portaudio/blob/master/include/portaudio.h',
        'limits': ['Initial converter pointers are PE data, not a live-memory observation; runtime replacement is not excluded',
                   'User float format and legacy-backend selection are conditions, not observed choices for SL3',
                   'The installed fork/version is not identified from the upstream format constants',
                   'Input projections are mathematical consequences of checked instructions, not executed application or physical audio',
                   'Output rounding/clipping/dithering depends on flags; no general float round-trip or bit-perfect playback claim',
                   'No current SL3 admission, device/control handshake, account entitlement, native reopen, analogue or DVS validation',
                   'No application, descriptor, registry, identity, security policy, driver or firmware modification'],
    }
    (ROOT/'docs/evidence/serato500-packed24-path.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Verified original legacy ASIO type-17 mapping, 3-byte width, conditional float converters and input normalization')


if __name__ == '__main__':
    main()
