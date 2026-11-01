"""Verify retained 2.5.6 SL3 API factory/loader code without executing vendor code."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
SHA = '3b04472cd5597fd56266e1c2c86dc298431b0026001aefe4b43aa3b909ee35c5'


def main():
    helper_path = ROOT/'scripts/export-serato-clock-handshake-evidence.py'
    spec = importlib.util.spec_from_file_location('image_reader', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    app = helper.Image('artifacts/extracted/Serato DJ Pro 2.5.6/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe', SHA)
    require = helper.require
    app.pe.parse_data_directories(directories=[1])
    facts = []

    def fact(va, mnemonic, operands=None):
        i = app.at(va, mnemonic, operands)
        facts.append({'va': hex(va), 'bytes': bytes(i.bytes).hex(), 'assembly': i.mnemonic+' '+i.op_str})
        return i

    for va, mnemonic, operands in [
            (0x140681b27, 'mov', 'r12d, 1'),
            (0x140682de1, 'mov', 'edi, 0x1cc5'),
            (0x140683cc6, 'call', 'qword ptr [rax + 0x18]'),
            (0x140683cc9, 'cmp', 'ax, di'),
            (0x140683ccc, 'jne', '0x140683d3b'),
            (0x140683cd4, 'call', 'qword ptr [rax + 0x20]'),
            (0x140683cd7, 'cmp', 'ax, r12w'),
            (0x140683cdb, 'jne', '0x140683d3b'),
            (0x140683ce5, 'jne', '0x140683d2f'),
            (0x140683ce7, 'mov', 'ecx, 0xa8'),
            (0x140683cfe, 'mov', 'rcx, rax'),
            (0x140683d01, 'call', '0x140694100'),
            (0x14069410d, 'call', '0x1406889b0'),
            (0x14069411a, 'mov', 'qword ptr [rbx], rax'),
            (0x14069414e, 'call', '0x14069d900'),
            (0x14069d92a, 'mov', 'qword ptr [rdi + 0x60], rax'),
            (0x14069da17, 'call', 'qword ptr [rdi + 0x70]'),
            (0x14069da1a, 'mov', 'qword ptr [rdi + 0x68], rax'),
            (0x14069da1e, 'test', 'rax, rax'),
            (0x14069da21, 'je', '0x14069daba'),
            (0x14069da27, 'mov', 'byte ptr [rdi + 8], 1')]:
        fact(va, mnemonic, operands)
    vtable = 0x1449cdff8
    require(app.rip(fact(0x140694113, 'lea')) == vtable, 'Constructor vtable mismatch')
    locator = struct.unpack('<Q', app.data(vtable-8, 8))[0]
    sig, offset, displacement, type_rva, hierarchy, self_rva = struct.unpack('<6I', app.data(locator, 24))
    require(sig == 1 and offset == displacement == 0 and app.base+self_rva == locator,
            'Invalid complete-object locator')
    require(app.text(app.base+type_rva+16) == '.?AVRaneSL3API@driver@device@serato@@', 'Wrong RTTI class')
    require(struct.unpack('<Q', app.data(vtable+8, 8))[0] == 0x14069d900, 'Loader virtual slot mismatch')

    def imported_call(va, expected):
        target = app.rip(fact(va, 'call'))
        require(any(i.address == target and i.name == expected.encode('ascii')
                    for entry in app.pe.DIRECTORY_ENTRY_IMPORT for i in entry.imports), 'Unexpected imported call')
        return {'callVa': hex(va), 'iatVa': hex(target), 'name': expected}

    imports = [imported_call(0x14069d924, 'LoadLibraryW')]
    exports = []
    for lea, call, store, name, slot in [
            (0x14069d937, 0x14069d941, 0x14069d947, 'sl3_open', 0x70),
            (0x14069d94f, 0x14069d95f, 0x14069d965, 'sl3_close', 0x78),
            (0x14069d972, 0x14069d97d, 0x14069d983, 'sl3_driver_timer', 0x80),
            (0x14069d993, 0x14069d99e, 0x14069d9a4, 'sl3_get_usb_port_status', 0x88),
            (0x14069d9b4, 0x14069d9bf, 0x14069d9c5, 'sl3_get_audio_controls', 0x90),
            (0x14069d9d5, 0x14069d9e0, 0x14069d9e6, 'sl3_set_audio_controls', 0x98),
            (0x14069d9f6, 0x14069da01, 0x14069da07, 'sl3_set_thrustate_callback', 0xa0)]:
        address = app.rip(fact(lea, 'lea'))
        require(app.text(address) == name, 'Export name mismatch')
        imports.append(imported_call(call, 'GetProcAddress'))
        fact(store, 'mov', f'qword ptr [rdi + {hex(slot)}], rax')
        exports.append({'name': name, 'stringVa': hex(address), 'memberOffset': hex(slot)})
    functions = []
    for va, end in [(0x140681ae0, 0x140684c0e), (0x140694100, 0x14069415d), (0x14069d900, 0x14069db55)]:
        rows = app.function(va)
        require(rows[0].address == va and rows[-1].address+rows[-1].size == end
                and sum(i.size for i in rows) == end-va, 'Incomplete function decoding')
        functions.append({'startVa': hex(va), 'endVa': hex(end),
                          'sha256': hashlib.sha256(app.data(va, end-va)).hexdigest()})
    result = {'scope': 'Original 2.5.6.1001 static SL3 API path; no execution or application modification',
              'binarySha256': SHA, 'factoryVa': '0x140681ae0', 'constructorVa': '0x140694100',
              'loaderVa': '0x14069d900', 'vtableVa': hex(vtable), 'completeObjectLocatorVa': hex(locator),
              'rttiType': '.?AVRaneSL3API@driver@device@serato@@', 'exports': exports,
              'functions': functions, 'instructionFacts': facts, 'imports': imports,
              'runtimeBranchEntryVerified': False, 'dllPathVerified': False, 'connectionVerified': False,
              'currentSeratoIntegrationVerified': False,
              'limits': ['Selected factory case uses preloaded VID/PID comparison registers; no exhaustive reachability proof is claimed.',
                         'Retained data, factory and loader do not override discontinued support or prove connection eligibility.',
                         'LoadLibraryW uses a runtime global wide string; its populated path was not observed.',
                         'No vendor exports, transport, firmware, entitlement checks or application binary were executed or modified.'],
              'sources': {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in (Path(__file__), helper_path)}}
    output = ROOT/'docs/evidence/serato256-sl3-api-path.json'
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified original 2.5.6 SL3 constructor/factory, RTTI, loader imports and seven export resolutions')


if __name__ == '__main__':
    main()
