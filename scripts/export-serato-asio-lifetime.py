"""Verify installed Serato's ASIO object lifecycle from original PE bytes only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lifetime_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
require = helper.require


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    app = helper.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', helper.CURRENT_SHA)
    require(digest(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe')) == app.sha, 'Installed image differs')
    require(app.pe.FILE_HEADER.Machine == 0x8664 and app.pe.OPTIONAL_HEADER.Magic == 0x20b, 'Expected Windows x64 PE')
    app.pe.parse_data_directories(directories=[1])
    imports = {entry.address: (descriptor.dll.decode(), entry.name.decode() if entry.name else str(entry.ordinal))
               for descriptor in app.pe.DIRECTORY_ENTRY_IMPORT for entry in descriptor.imports}
    reports = {}
    for name in ('serato500-pa-asio-initialize-03.json', 'serato500-pa-asio-open-04.json', 'serato500-asio-construction.json',
                 'serato500-asio-registry.json', 'serato500-asio-type.json', 'serato500-asio-object-lifetime-01.json',
                 'serato500-asio-object-lifetime-02.json', 'serato500-asio-object-lifetime-03.json'):
        path = ROOT/'analysis'/name
        report = json.loads(path.read_text(encoding='utf-8-sig'))
        require(report['binary_sha256'] == app.sha, 'Wrong focused image')
        for row in report['functions']:
            require(row['complete'] and (int(row['start'], 16), int(row['end_exclusive'], 16)) in app.spans, 'Incomplete/mismatched selected unwind range')
        reports[name] = digest(path)
    # These small SDK-style wrappers have no unwind entry. Their complete byte
    # extents are explicit; do not disassemble from arbitrary excerpt offsets.
    leaf_ranges = [(0x142205170, 0x142205195), (0x142221e60, 0x142221e7c),
                   (0x142222160, 0x142222179), (0x142222180, 0x142222199)]
    leaves = {}
    for start, end in leaf_ranges:
        rows = list(app.dis.disasm(app.data(start, end-start), start))
        require(rows and rows[-1].address+rows[-1].size == end, 'Incomplete explicit leaf disassembly')
        leaves.update({row.address: row for row in rows})
    instructions = []

    def check(address, opcode, operands):
        row = leaves[address] if address in leaves else app.at(address)
        require(row.mnemonic == opcode and row.op_str == operands, f'Instruction differs at {address:x}')
        instructions.append({'va': hex(address), 'bytes': row.bytes.hex(), 'opcode': opcode, 'operands': operands})
        return row

    checks = [
        # Successful legacy enumeration setup, then unload; actual open reloads.
        (0x142218a91, 'call', '0x142217040'), (0x142218a98, 'jne', '0x142218df3'),
        (0x142218ce9, 'call', '0x142221e80'), (0x142218cee, 'jmp', '0x142218d67'),
        (0x142217361, 'call', '0x142217040'), (0x142217050, 'call', '0x142222980'),
        (0x14221709b, 'call', '0x142222020'), (0x14222207e, 'call', 'qword ptr [rax + 0x18]'),
        (0x142222a6f, 'call', '0x142222af0'), (0x142222a80, 'call', '0x1422223c0'),
        (0x1422223f2, 'cmp', 'qword ptr [rax + 0x298], 0'),
        (0x1422223fc, 'lea', 'rcx, [rax + 4]'), (0x142222400, 'mov', 'qword ptr [rsp + 0x20], rdi'),
        (0x142222405, 'mov', 'r9, rcx'), (0x142222408, 'xor', 'edx, edx'), (0x14222240a, 'mov', 'r8d, 1'),
        (0x14222241d, 'mov', 'qword ptr [rbx + 0x298], rax'),
        (0x142221e95, 'call', '0x142222af0'), (0x142222af6, 'mov', 'edx, dword ptr [rcx + 0x14]'),
        (0x142222b01, 'call', '0x1422222d0'), (0x1422222ea, 'mov', 'rcx, qword ptr [rax + 0x298]'),
        (0x1422222f9, 'call', 'qword ptr [rdx + 0x10]'), (0x1422222fc, 'mov', 'qword ptr [rbx + 0x298], 0'),
        (0x142216ce4, 'call', '0x142221e60'), (0x142216ce9, 'call', '0x142221e80'),
        (0x142221e75, 'jmp', 'qword ptr [rax + 0xa0]'),
        # Actual PortAudio start/stop dispatch is distinct from Close/ASIOExit.
        (0x1422181fe, 'call', '0x142222160'), (0x1422182b1, 'call', '0x142222180'),
        (0x142222175, 'jmp', 'qword ptr [rax + 0x38]'), (0x142222195, 'jmp', 'qword ptr [rax + 0x40]'),
        # Newer JUCE device construction, COM pointer field and dummy I/O.
        (0x1422083d1, 'call', '0x142210950'), (0x142210a1d, 'call', '0x142211340'),
        (0x142210a2a, 'call', '0x142212f30'), (0x14220e91a, 'call', 'qword ptr [rax + 0x18]'),
        (0x14220d82c, 'call', 'qword ptr [rax + 0x98]'), (0x142210bc3, 'call', '0x14220d6f0'),
        (0x142210bee, 'call', 'qword ptr [rax + 0x38]'), (0x142210bf1, 'mov', 'ecx, 0x50'),
        (0x142210bf6, 'call', '0x142205170'), (0x142210c02, 'call', 'qword ptr [rax + 0x40]'),
        (0x142205170, 'mov', 'eax, ecx'), (0x142205172, 'cmp', 'ecx, 0xa'),
        (0x142205175, 'jge', '0x14220518c'), (0x14220518c, 'mov', 'ecx, eax'),
        (0x142212f3c, 'add', 'rcx, 0x60'), (0x142212f40, 'add', 'rax, 0x38'),
        (0x142212f44, 'mov', 'qword ptr [rsp + 0x20], rax'),
        (0x142212f49, 'mov', 'r9, rcx'), (0x142212f4c, 'xor', 'edx, edx'), (0x142212f4e, 'mov', 'r8d, 1'),
        (0x142211361, 'call', 'qword ptr [rax + 0x10]'), (0x14221136e, 'mov', 'qword ptr [rbx], 0'),
        (0x142208ea3, 'call', '0x142211340'),
        # Existing non-null JUCE objects need not always be recreated by open.
        (0x14220f2a5, 'cmp', 'qword ptr [rdi + 0x38], r14'), (0x14220f2a9, 'jne', '0x14220f2e7'),
        (0x14220f2b3, 'call', '0x142210950'),
        (0x14220f663, 'cmp', 'byte ptr [rdi + 0x7b5], 0'), (0x14220f66a, 'je', '0x14220f734'),
        (0x14220f673, 'call', '0x142211340'), (0x14220f67b, 'call', '0x142211340'),
        (0x14220f688, 'call', '0x142212f30'), (0x14220f695, 'call', '0x14220e8c0'),
    ]
    for address, opcode, operands in checks:
        check(address, opcode, operands)
    import_checks = []
    for va, name in ((0x142222410, 'CoCreateInstance'), (0x142212f54, 'CoCreateInstance'), (0x14220518e, 'Sleep')):
        row = leaves[va] if va in leaves else app.at(va)
        target = app.rip(row)
        require(target in imports and imports[target][1] == name, 'Wrong actual import')
        import_checks.append({'va': hex(va), 'iat': hex(target), 'module': imports[target][0], 'name': name})
    for address, target in ((0x142221e84, 0x1440b7f58), (0x142221e8e, 0x1440b7f60), (0x142221e9c, 0x1440b7f58)):
        require(app.rip(app.at(address)) == target, 'Wrong legacy manager/interface global')
    # RTTI, constructor installation and virtual-slot entry establish JUCE type.
    vtable = 0x1431dd708
    col = struct.unpack('<Q', app.data(vtable-8, 8))[0]
    fields = struct.unpack('<6I', app.data(col, 24))
    require(fields[0] == 1 and fields[1] == 0 and fields[5]+app.base == col, 'RTTI locator differs')
    type_name = app.text(app.base+fields[3]+16)
    require(type_name == '.?AVASIOAudioIODevice@juce@@' and app.rip(app.at(0x1422081c4)) == vtable, 'Wrong JUCE object construction')
    require(struct.unpack('<Q', app.data(vtable+0x30, 8))[0] == 0x14220f230, 'Wrong JUCE open slot')
    sdk = ROOT/'artifacts/references/asio-sdk-2.3.4/ASIOSDK/common/iasiodrv.h'
    unknown = Path('C:/Program Files (x86)/Windows Kits/10/Include/10.0.19041.0/um/unknwnbase.h')
    names = re.findall(r'\bvirtual\s+(?:ASIOBool|ASIOError|void|long)\s+(\w+)\s*\(', sdk.read_text())
    require('interface IASIO : public IUnknown' in sdk.read_text(), 'IASIO inheritance differs')
    slots = {name: (3+i)*8 for i, name in enumerate(names)}
    require({k: slots[k] for k in ('init', 'start', 'stop', 'createBuffers', 'disposeBuffers')} == {
        'init': 0x18, 'start': 0x38, 'stop': 0x40, 'createBuffers': 0x98, 'disposeBuffers': 0xa0}, 'SDK slot map differs')
    inherited = re.findall(r'virtual\s+(?:HRESULT|ULONG)\s+STDMETHODCALLTYPE\s+(\w+)\s*\(', unknown.read_text())
    require(inherited[:3] == ['QueryInterface', 'AddRef', 'Release'], 'IUnknown method order differs')
    build_path = ROOT/'artifacts/build/native/native-build-Release.json'
    build = json.loads(build_path.read_text(encoding='utf-8-sig'))
    owner_files = ['src/asio/com_server.cpp', 'src/asio/driver_facade.hpp', 'src/asio/host_session.cpp', 'src/asio/driver_configuration.cpp']
    ownership = {}
    for file in owner_files:
        require(digest(ROOT/file).upper() == build['inputs'][file].upper(), 'Current rebuilt owner differs from tested source')
        ownership[file] = digest(ROOT/file)
    require('object=new Device;' in (ROOT/'src/asio/com_server.cpp').read_text() and
            'HostSession session_;' in (ROOT/'src/asio/driver_facade.hpp').read_text(), 'Per-COM-object owner model changed')
    dll = ROOT/'artifacts/build/native/Release/sl3_asio.dll'
    require(digest(dll).upper() == build['asioComponent']['comDllSha256'].upper(), 'Built ASIO DLL differs')
    reference_lf_hashes = {
        'DriverFile.h': '079dcf53753e4fac7629585ca6d5dc6ac2498748c83bf5dd6f41f604fe0f31b6',
        'RedirectorAccess.h': '5ebfc813cd984bfd1eb29a5c97780c7412e660a692b33daf0831191b9ada0b84',
        'UsbDkHelper.cpp': '6790c5a9a67c7f64164198511cd855c1c7054d80850a86d7713831f5ed4b5350',
    }
    transport_sources = {}
    for name in ('DriverFile.h', 'RedirectorAccess.h', 'UsbDkHelper.cpp'):
        path = ROOT/'artifacts/references/usbdk-1.0.22'/name
        require(hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == reference_lf_hashes[name],
                f'Reviewed exact-commit helper reference differs: {name}')
        transport_sources[name] = digest(path)
    redirector = (ROOT/'artifacts/references/usbdk-1.0.22/RedirectorAccess.h').read_text()
    file_owner = (ROOT/'artifacts/references/usbdk-1.0.22/DriverFile.h').read_text()
    exports = (ROOT/'artifacts/references/usbdk-1.0.22/UsbDkHelper.cpp').read_text()
    require(re.search(r'HANDLE\s+GetSystemHandle\(\)\s+const\s*\{\s*return\s+m_hDriver;', redirector) is not None
            and re.search(r'~UsbDkDriverFile\(\)\s*\{\s*CloseHandle\(m_hDriver\);', file_owner) is not None
            and 'return deviceHandle->RedirectorAccess->GetSystemHandle();' in exports
            and 'deviceHandle->RedirectorAccess.reset();' in exports, 'Reviewed helper ownership contract differs')
    result = {'scope': 'Static installed Serato ASIO object lifecycle; no vendor execution or physical application test',
              'binarySha256': app.sha, 'installedImageMatches': True, 'focusedReports': reports,
              'boundaryCheckedInstructions': instructions, 'actualImports': import_checks,
              'explicitLeafRanges': [[hex(a), hex(b)] for a, b in leaf_ranges],
              'juceType': {'vtable': hex(vtable), 'locator': hex(col), 'name': type_name, 'openVirtualSlot': '0x30'},
              'sdk': {'iasioHeaderSha256': digest(sdk), 'iunknownHeaderSha256': digest(unknown), 'slots': slots, 'releaseSlot': '0x10'},
              'rebuiltOwner': {'sourceHashes': ownership, 'dllSha256': digest(dll), 'scope': 'One HostSession per successfully configured COM Device/DriverFacade; final destruction releases its device'},
              'transportHandleOwnership': {'reviewedCommit': '84752c30037956149d53b498005b5368616f9257', 'referenceHashes': transport_sources,
                                           'systemHandleBorrowed': True, 'closeOwner': 'UsbDkRedirectorAccess/UsbDkDriverFile destroyed by UsbDk_StopRedirect',
                                           'limits': 'Source ownership check only; does not establish completed kernel/USB re-enumeration when StopRedirect returns'},
              'findings': ['Successful legacy enumeration initializes then releases the selected IASIO object; actual stream open loads/initializes again',
                           'Legacy stream close disposes buffers and releases its IASIO object; ordinary stream stop uses the separate stop slot',
                           'JUCE ASIO device setup creates/initializes an IASIO object, creates dummy buffers and starts/stops it with an 80-ms Sleep between',
                           'JUCE open initializes a missing object and has a conditional +0x7b5 branch that releases/recreates it; this is not unconditional every open',
                           'Our per-object retention does not establish safe successive object release/recreation on hardware'],
              'limits': ['Preferred image VAs and selected unwind/leaf ranges; no complete control-flow recovery or runtime reachability claim',
                         'Exact bundled PortAudio/JUCE versions and active SL3 backend selection remain unverified',
                         'Reset flag source is separately verified by export-serato-asio-reset-evidence.py; real application object timings remain unestablished',
                         'No broker/service, descriptor override, account/product bypass, registration or native device operation was introduced']}
    (ROOT/'docs/evidence/serato500-asio-object-lifetime.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified installed PE, successful legacy enumerate/release/recreate, JUCE dummy start/stop and conditional recreation; native cross-object validation remains open')


if __name__ == '__main__':
    main()
