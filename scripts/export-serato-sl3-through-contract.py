"""Verify historical SL3 control order/polarity from original bytes; no execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('clock_contract', ROOT / 'scripts/export-serato-clock-handshake-evidence.py')
clock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clock)
require = clock.require


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    old = clock.Image('artifacts/extracted/Serato DJ Pro 2.5.5/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe', clock.OLD_SHA)
    driver = clock.Image('artifacts/extracted/rane-windows/x64/RaneAsioSL3.dll', clock.DRIVER_SHA)
    old.pe.parse_data_directories(directories=[1])
    getproc_slots = {item.address for library in old.pe.DIRECTORY_ENTRY_IMPORT for item in library.imports
                     if item.name == b'GetProcAddress' and library.dll.lower() == b'kernel32.dll'}
    require(len(getproc_slots) == 1, 'GetProcAddress import differs')
    checks = []

    def at(address, op, operands):
        row = old.at(address, op, operands)
        checks.append({'va': hex(address), 'instruction': f'{row.mnemonic} {row.op_str}'})
        return row

    # Validate the actual RTTI locator and complete-object vtable, not just a
    # report's guessed class name or another Rane class's identically sized API.
    table, locator, descriptor = 0x1447b9b08, 0x14482fbe0, 0x144cfaac0
    require(struct.unpack('<Q', old.data(table - 8, 8))[0] == locator, 'Vtable locator differs')
    sig, offset, constructor, type_rva, _, self_rva = struct.unpack('<6I', old.data(locator, 24))
    require((sig, offset, constructor, old.base + type_rva, old.base + self_rva) ==
            (1, 0, 0, descriptor, locator), 'SL3 RTTI locator differs')
    require(old.text(descriptor + 16) == '.?AVRaneSL3API@driver@device@serato@@', 'SL3 RTTI name differs')
    slots = {0xb0: 0x140691cb0, 0xb8: 0x140691c10, 0xc0: 0x140691ae0}
    require(all(struct.unpack('<Q', old.data(table + slot, 8))[0] == target for slot, target in slots.items()),
            'SL3 control methods differ')

    # The seven named exports are loaded into this object. Check the selected
    # getter/setter/callback pointer slots directly against their string sources.
    for lea, store, name, member in [
        (0x14069b084, 0x14069b095, 'sl3_get_audio_controls', '0x90'),
        (0x14069b0a5, 0x14069b0b6, 'sl3_set_audio_controls', '0x98'),
        (0x14069b0c6, 0x14069b0d7, 'sl3_set_thrustate_callback', '0xa0')]:
        row = old.at(lea, 'lea')
        require(old.text(old.rip(row)) == name, 'Named export differs')
        at(store, 'mov', f'qword ptr [rdi + {member}], rax')
    for call in (0x14069b08f, 0x14069b0b0, 0x14069b0d1):
        require(old.rip(old.at(call, 'call')) in getproc_slots, 'Export resolver import differs')

    # Setter's three-way branch, inverted Boolean byte and one-byte invocation.
    for address, op, operands in [
        (0x140691cb4, 'cmp', 'byte ptr [rcx + 8], 0'),
        (0x140691cbd, 'xor', 'r8b, 1'), (0x140691cc1, 'mov', 'byte ptr [rsp + 0x30], r8b'),
        (0x140691cc6, 'test', 'edx, edx'), (0x140691cc8, 'je', '0x140691ce2'),
        (0x140691cca, 'sub', 'edx, 1'), (0x140691ccd, 'je', '0x140691cdb'),
        (0x140691ccf, 'cmp', 'edx, 1'), (0x140691cd2, 'jne', '0x140691cfd'),
        (0x140691cd4, 'mov', 'edx, 8'), (0x140691cd9, 'jmp', '0x140691ce7'),
        (0x140691cdb, 'mov', 'edx, 0x14'), (0x140691ce0, 'jmp', '0x140691ce7'),
        (0x140691ce2, 'mov', 'edx, 0xe'),
        (0x140691ce7, 'mov', 'rcx, qword ptr [rcx + 0x68]'),
        (0x140691ceb, 'lea', 'r8, [rsp + 0x30]'), (0x140691cf0, 'mov', 'r9d, 1'),
        (0x140691cf6, 'call', 'qword ptr [r10 + 0x98]'),
        # Getter independently uses the same order and normalizes raw zero.
        (0x140691c38, 'mov', 'byte ptr [rsp + 0x30], 1'),
        (0x140691c3f, 'test', 'edi, edi'), (0x140691c41, 'je', '0x140691c59'),
        (0x140691c43, 'sub', 'eax, 1'), (0x140691c46, 'je', '0x140691c52'),
        (0x140691c48, 'cmp', 'eax, 1'), (0x140691c4d, 'lea', 'edx, [rax + 7]'),
        (0x140691c52, 'mov', 'edx, 0x14'), (0x140691c59, 'mov', 'edx, 0xe'),
        (0x140691c5e, 'mov', 'r9d, 1'), (0x140691c64, 'lea', 'r8, [rsp + 0x30]'),
        (0x140691c69, 'mov', 'rcx, qword ptr [rbx + 0x68]'),
        (0x140691c6d, 'call', 'qword ptr [rbx + 0x90]'),
        (0x140691c73, 'cmp', 'byte ptr [rsp + 0x30], 0'), (0x140691c78, 'sete', 'dl'),
        (0x140691c8e, 'inc', 'edi'), (0x140691c94, 'cmp', 'edi, 3'),
        (0x140691c97, 'jl', '0x140691c31'),
        # Notification permutation: slot 0 reads byte 1, slot 1 byte 2, slot 2 byte 0.
        (0x140691d25, 'cmp', 'byte ptr [rcx + 1], 0'), (0x140691d29, 'sete', 'dl'),
        (0x140691d4b, 'cmp', 'byte ptr [rbx + 2], 0'), (0x140691d4f, 'sete', 'dl'),
        (0x140691d71, 'cmp', 'byte ptr [rbx], 0'), (0x140691d74, 'sete', 'dl'),
        # Upstream owner retains the actual factory-returned DriverAPI at +f8.
        (0x140420ae1, 'call', '0x140680270'), (0x140420ae9, 'mov', 'rax, qword ptr [rax]'),
        (0x140420af7, 'mov', 'qword ptr [rdi + 0xf8], rax')]:
        at(address, op, operands)

    # Leaf lacks unwind metadata; require the entire bounded instruction sequence.
    leaf_start, leaf_end = 0x140422200, 0x140422256
    leaf = list(old.dis.disasm(old.data(leaf_start, leaf_end - leaf_start), leaf_start))
    require(leaf and leaf[-1].address + leaf[-1].size == leaf_end, 'Leaf extent differs')
    expected_leaf = [
        ('mov', 'rax, qword ptr [rip + 0x4a17cf1]'), ('test', 'rax, rax'), ('je', '0x140422255'),
        ('mov', 'rcx, qword ptr [rcx + 0xf8]'), ('test', 'rcx, rcx'), ('je', '0x140422255'),
        ('mov', 'r9, qword ptr [rax + 0x398]'), ('mov', 'rax, qword ptr [rax + 0x3a0]'),
        ('sub', 'rax, r9'), ('sar', 'rax, 2'), ('cmp', 'edx, eax'), ('jge', '0x140422246'),
        ('test', 'edx, edx'), ('js', '0x140422246'), ('movsxd', 'rax, edx'),
        ('mov', 'edx, dword ptr [r9 + rax*4]'), ('mov', 'rax, qword ptr [rcx]'),
        ('jmp', 'qword ptr [rax + 0xb0]'), ('mov', 'rax, qword ptr [rcx]'),
        ('mov', 'edx, 0xffffffff'), ('jmp', 'qword ptr [rax + 0xb0]'), ('ret', '')]
    require([(r.mnemonic, r.op_str) for r in leaf] == expected_leaf, 'Upstream remap leaf differs')
    require(old.rip(leaf[0]) == 0x144e39ef8, 'Descriptor/global source differs')

    for address, glob in [(0x140691d19, 0x144d379d0), (0x140691d3f, 0x144d379f8), (0x140691d65, 0x144d37a20)]:
        require(old.rip(old.at(address, 'mov')) == glob, 'Notification callback slot differs')
    require(old.rip(old.at(0x140691b2e, 'lea')) == 0x140691d10, 'Registered notification target differs')
    at(0x140691b19, 'mov', 'rax, qword ptr [rcx + 0x68]')
    at(0x140691b1d, 'mov', 'r8, qword ptr [rcx + 0xa0]')
    at(0x140691b26, 'mov', 'rcx, rax')
    at(0x140691b35, 'call', 'r8')

    # Derive control-table groups from the original UI table, rather than calling
    # Serato's slot number a physical jack/deck number or changing captured PCM.
    fields = [list(struct.unpack('<3I', driver.data(0x1801b5b00 + group * 0x30, 12))) for group in range(3)]
    require(fields == [[0, 3, 8], [1, 9, 14], [2, 15, 20]], 'Original control table differs')
    offsets = [14, 20, 8]
    permutation = [next(group for group, row in enumerate(fields) if row[2] == offset) for offset in offsets]
    require(permutation == [1, 2, 0], 'Logical slot permutation differs')
    reports = []
    for name in ('serato255-sl3-api-lifecycle.json', 'serato255-sl3-thru-callback.json', 'serato255-thru-owner.json'):
        path = ROOT / 'analysis' / name
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        require(value['binary_sha256'] == old.sha and all(f.get('complete') for f in value['functions']),
                'Focused report identity/completion differs')
        require(all((int(f['start'], 16), int(f['end_exclusive'], 16)) in old.spans for f in value['functions']),
                'Focused report unwind range differs')
        reports.append({'path': str(path.relative_to(ROOT)).replace('\\', '/'), 'sha256': sha(path),
                        'functions': [{'start': f['start'], 'endExclusive': f['end_exclusive']} for f in value['functions']]})
    result = {'scope': 'Historical 2.5.5 original-byte SL3 control contract; no vendor execution, USB write or current Serato admission',
              'seratoSha256': old.sha, 'raneAsioSha256': driver.sha, 'exporterSha256': sha(Path(__file__)),
              'imageHelperSha256': sha(ROOT / 'scripts/export-serato-clock-handshake-evidence.py'),
              'rtti': {'name': '.?AVRaneSL3API@driver@device@serato@@', 'vtableVa': hex(table), 'locatorVa': hex(locator)},
              'logicalSlotToControlGroup': permutation, 'logicalSlotToTableOffset': offsets,
              'booleanWrite': {'false': 1, 'true': 0, 'length': 1, 'rawOperation': 'input byte XOR 1'},
              'readAndNotificationFlag': 'raw byte equals zero', 'notificationInputByteForSlot': permutation,
              'notificationFourthByteInterpreted': False,
              'upstreamRemap': {'entryVa': hex(leaf_start), 'endExclusive': hex(leaf_end),
                  'ownerDriverApiOffset': '0xf8', 'globalVa': '0x144e39ef8',
                  'vectorBeginOffset': '0x398', 'vectorEndOffset': '0x3a0', 'elementBytes': 4,
                  'invalidIndexForwarded': -1, 'runtimeVectorCaptured': False,
                  'assembly': [f'{r.address:x}: {r.mnemonic} {r.op_str}' for r in leaf]},
              'instructionChecks': checks, 'focusedReports': reports,
              'limits': ['Logical API slots are not proven physical jacks or user-visible deck numbers.',
                        'The upstream remapping vector is runtime state and has not been captured.',
                        'Boolean inversion is established for Boolean arguments; arbitrary input bytes use XOR, not logical negation.',
                        'The historical getter initializes its byte to 1 and consumes a void-style getter; unchanged data cannot prove successful I/O.',
                        'Current control transactions must retain explicit success/error/read-back evidence rather than copy historical fallback behavior.',
                        'The fourth notification byte is not consumed by these three callbacks.',
                        'Current 5.0.0 lacks a demonstrated SL3 DriverAPI/descriptor/handshake integration; this does not restore it.',
                        'No driver, application resource, account check, physical routing, security policy or firmware changed.']}
    output = ROOT / 'docs/evidence/serato255-sl3-through-contract.json'
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Verified original SL3 logical-slot order 1/2/0, inverted Boolean controls, notification mapping and upstream remap')


if __name__ == '__main__':
    main()
