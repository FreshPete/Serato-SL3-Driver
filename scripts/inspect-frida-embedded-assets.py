"""Read native asset descriptors from a hash-bound PE; never load that image."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import uuid


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def descriptor_rva(code, rva):
    """Accept only the observed five-instruction, 24-byte descriptor copy."""
    import capstone as cs
    from capstone.x86 import X86_OP_MEM, X86_OP_REG, X86_REG_RAX, X86_REG_RCX, X86_REG_RIP, X86_REG_XMM0
    engine = cs.Cs(cs.CS_ARCH_X86, cs.CS_MODE_64)
    engine.detail = True
    instructions = []
    for instruction in engine.disasm(code[:48], rva):
        instructions.append(instruction)
        if instruction.mnemonic == 'ret':
            break
    require(len(instructions) == 5, 'Unexpected asset getter instruction count')
    a, b, c, d, e = instructions
    require([x.mnemonic for x in (a, b, d, e)] == ['mov', 'mov', 'movups', 'ret'] and
            c.mnemonic in ('movaps', 'movups'), 'Unexpected asset getter instructions')
    require([len(x.operands) for x in instructions] == [2, 2, 2, 2, 0], 'Unexpected getter operands')

    def reg(operand, expected, size):
        return operand.type == X86_OP_REG and operand.reg == expected and operand.size == size

    def memory(operand, base, size, displacement=None):
        return (operand.type == X86_OP_MEM and operand.size == size and operand.mem.base == base and
                operand.mem.index == 0 and operand.mem.segment == 0 and
                (displacement is None or operand.mem.disp == displacement))

    require(reg(a.operands[0], X86_REG_RAX, 8) and memory(a.operands[1], X86_REG_RIP, 8) and
            memory(b.operands[0], X86_REG_RCX, 8, 16) and reg(b.operands[1], X86_REG_RAX, 8) and
            reg(c.operands[0], X86_REG_XMM0, 16) and memory(c.operands[1], X86_REG_RIP, 16) and
            memory(d.operands[0], X86_REG_RCX, 16, 0) and reg(d.operands[1], X86_REG_XMM0, 16),
            'Getter does not copy the expected descriptor fields')
    first = c.address + c.size + c.operands[1].mem.disp
    last = a.address + a.size + a.operands[1].mem.disp
    require(first >= 0 and last == first + 16, 'Getter descriptor fields are not contiguous')
    return first, sha(b''.join(bytes(x.bytes) for x in instructions))


def inspect(build, expected, publics_path, summary_path):
    import pefile
    build = build.resolve()
    candidate = build / 'subprojects/frida-python/frida/_frida.pyd'
    raw = candidate.read_bytes()
    require(re.fullmatch('[0-9a-f]{64}', expected) is not None and sha(raw) == expected,
            'Candidate identity differs')
    pe = pefile.PE(data=raw)
    require(pe.FILE_HEADER.Machine == 0x8664 and pe.OPTIONAL_HEADER.Magic == 0x20b, 'AMD64 PE32+ required')

    def image_data(rva, size):
        require(type(rva) is int and type(size) is int and rva >= 0 and 0 <= size <= len(raw), 'Invalid image span')
        section = next((s for s in pe.sections if s.VirtualAddress <= rva and
                        rva + size <= s.VirtualAddress + min(s.Misc_VirtualSize, s.SizeOfRawData)), None)
        require(section is not None, 'Span is not fully backed by one image section')
        offset = section.PointerToRawData + rva - section.VirtualAddress
        require(offset + size <= len(raw), 'Image span is truncated')
        return raw[offset:offset + size]

    summary = summary_path.read_text()
    guid_match = re.search(r'GUID:\s*\{([0-9A-Fa-f-]+)\}', summary)
    age_match = re.search(r'Age:\s*(\d+)', summary)
    require(guid_match is not None and age_match is not None, 'PDB identity summary missing')
    codeviews = [pe.get_data(x.struct.AddressOfRawData, x.struct.SizeOfData)
                 for x in pe.DIRECTORY_ENTRY_DEBUG if x.struct.Type == 2]
    require(len(codeviews) == 1 and codeviews[0].startswith(b'RSDS'), 'Unique RSDS identity required')
    codeview = codeviews[0]
    require(uuid.UUID(guid_match.group(1)) == uuid.UUID(bytes_le=codeview[4:20]) and
            int(age_match.group(1)) == struct.unpack_from('<I', codeview, 20)[0], 'PDB identity differs from PE')
    publics_text = publics_path.read_text()
    symbols = {}
    for name, flags, section, offset in re.findall(
            r'`([^`]+)`\s+flags = ([^\n]+), addr = (\d+):(\d+)', publics_text):
        symbols.setdefault(name, []).append((flags, int(section), int(offset)))

    src = build / 'subprojects/frida-core/src'
    groups = {
        'agent': ('frida-data-agent.c', 'frida_data_agent_get_', 'frida-data-agent-blob.obj.p',
                  {f'{name}-{arch}.dll' for name in ('frida-agent', 'dbghelp', 'symsrv')
                   for arch in ('x86_64', 'x86', 'arm64')}),
        'helper': ('frida-data-helper-process.c', 'frida_data_helper_get_', 'frida-data-helper-process.vapi.p',
                   {f'frida-helper-{arch}.exe' for arch in ('x86_64', 'x86', 'arm64')}),
    }
    assets, spans, manifest_hashes = [], [], {}
    base = pe.OPTIONAL_HEADER.ImageBase
    for group, (manifest_name, prefix, directory, expected_names) in groups.items():
        manifest = (src / manifest_name).read_bytes()
        manifest_hashes[manifest_name] = sha(manifest)
        entries = re.findall(rb'\{ "([a-z0-9_.-]+)", (_[a-z0-9_]+), (\d+), (\d+) \}', manifest)
        require(len(entries) == len(expected_names) and {x[0].decode() for x in entries} == expected_names,
                'Generated asset inventory differs')
        expected_getters = {prefix + re.sub('[.-]', '_', name) + '_blob' for name in expected_names}
        require({name for name in symbols if name.startswith(prefix)} == expected_getters,
                'PDB getter inventory differs')
        for encoded_name, _, encoded_length, encoded_size in entries:
            name = encoded_name.decode('ascii')
            getter = prefix + re.sub('[.-]', '_', name) + '_blob'
            matches = symbols[getter]
            require(len(matches) == 1 and matches[0][0] == 'function', 'Unique getter symbol required')
            _, section_number, offset = matches[0]
            require(1 <= section_number <= len(pe.sections), 'Invalid PDB section')
            section = pe.sections[section_number - 1]
            require(section.Characteristics & 0x20000000 and offset < section.Misc_VirtualSize,
                    'Getter must reside in executable image section')
            getter_rva = section.VirtualAddress + offset
            descriptor, getter_sha = descriptor_rva(image_data(getter_rva, 48), getter_rva)
            name_pointer, data_pointer, length, size = struct.unpack('<QQII', image_data(descriptor, 24))
            embedded_name = image_data(name_pointer - base, len(name) + 1)
            require(embedded_name == encoded_name + b'\0' and length == int(encoded_length) and
                    size == int(encoded_size) and length == size, 'Image asset descriptor differs from manifest')
            payload = (src / directory / name).read_bytes()
            require(len(payload) == length, 'Staged asset length differs')
            entry = {'group': group, 'name': name, 'bytes': length, 'uncompressedBytes': size,
                     'getterRva': getter_rva, 'getterCodeSha256': getter_sha, 'descriptorRva': descriptor,
                     'sha256': sha(payload), 'emptyPlaceholder': not length}
            if length:
                require('x86_64' in name, 'Unexpected non-native payload')
                data_rva = data_pointer - base
                require(image_data(data_rva, length) == payload, 'Final image payload differs from staged asset')
                with pefile.PE(data=payload) as asset:
                    require(asset.FILE_HEADER.Machine == 0x8664, 'Embedded payload is not AMD64')
                    require(bool(asset.FILE_HEADER.Characteristics & 0x2000) == name.endswith('.dll'),
                            'Embedded image kind differs')
                    entry['imports'] = sorted({x.dll.decode('ascii').lower() for attribute in
                                               ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT')
                                               for x in getattr(asset, attribute, [])})
                entry['dataRva'] = data_rva
                require(not any(data_rva < end and start < data_rva + length for start, end in spans),
                        'Nonempty payload spans overlap')
                spans.append((data_rva, data_rva + length))
            assets.append(entry)
    require(len(spans) == 4, 'Expected exactly four nonempty native payloads')
    return {'schema': 'sl3.frida-embedded-assets.v1', 'candidateSha256': expected,
            'pdbSha256': sha(candidate.with_suffix('.pdb').read_bytes()),
            'pdbGuid': str(uuid.UUID(guid_match.group(1))), 'pdbAge': int(age_match.group(1)),
            'publicSymbolDumpSha256': sha(publics_path.read_bytes()), 'summaryDumpSha256': sha(summary_path.read_bytes()),
            'generatedManifestSha256': manifest_hashes, 'assets': assets,
            'listedNativeAssetsMatchFinalImage': True, 'wholeImageAttested': False,
            'nativeAssetsExecuted': False, 'candidateLoaded': False, 'deviceOpened': False,
            'securityHoldCleared': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--public-symbols', type=Path, required=True)
    parser.add_argument('--pdb-summary', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.build, args.expected_sha256, args.public_symbols, args.pdb_summary), indent=2))
