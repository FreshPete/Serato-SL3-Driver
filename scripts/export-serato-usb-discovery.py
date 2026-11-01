"""Verify current Serato's USB identity discovery and record selection, offline."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
APP = 'artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe'


def main():
    spec = importlib.util.spec_from_file_location('usb_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    app = h.Image(APP, h.CURRENT_SHA)
    h.require(hashlib.sha256(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe').read_bytes()).hexdigest()
              == app.sha, 'Installed application differs')
    app.pe.parse_data_directories(directories=[1])
    imports = {e.address: (d.dll.decode(), e.name.decode() if e.name else '')
               for d in app.pe.DIRECTORY_ENTRY_IMPORT for e in d.imports}
    usb_imports = {va: name for va, (dll, name) in imports.items() if dll.lower() == 'libusb-1.0.dll'}
    expected = {
        0x142737560: 'libusb_free_config_descriptor', 0x142737568: 'libusb_get_device_address',
        0x142737570: 'libusb_get_bus_number', 0x142737578: 'libusb_get_config_descriptor',
        0x142737580: 'libusb_get_device_descriptor', 0x142737588: 'libusb_init',
        0x142737590: 'libusb_exit', 0x142737598: 'libusb_get_device_list',
        0x1427375a0: 'libusb_free_device_list'}
    h.require(usb_imports == expected, 'Direct libusb import inventory differs')
    instructions = []

    def check(va, op, operands):
        i = app.at(va, op, operands)
        instructions.append({'va': hex(va), 'bytes': i.bytes.hex(), 'instruction': op+' '+operands})

    def leaf(va, expected_rows):
        rows = list(app.dis.disasm(app.data(va, sum(len(bytes.fromhex(b)) for b, _, _ in expected_rows)), va))
        h.require([(i.bytes.hex(), i.mnemonic, i.op_str) for i in rows] == expected_rows, 'Leaf differs')
        instructions.extend({'va': hex(i.address), 'bytes': i.bytes.hex(), 'instruction': i.mnemonic+' '+i.op_str} for i in rows)

    thunks = {}
    for va, name in ((0x140c24b00, 'libusb_get_device_list'), (0x140c24b10, 'libusb_free_device_list'),
                     (0x140c24b20, 'libusb_get_device_descriptor'), (0x1422152a0, 'libusb_get_bus_number'),
                     (0x1422152b0, 'libusb_get_device_address')):
        rows = list(app.dis.disasm(app.data(va, 6), va))
        h.require(len(rows) == 1 and rows[0].mnemonic == 'jmp' and
                  imports[app.rip(rows[0])] == ('libusb-1.0.dll', name), 'Import thunk differs')
        thunks[hex(va)] = name
    # Exact descriptor storage, not decompiler-inferred parameter types.
    for va, op, operands in [
        (0x1421e4e48, 'call', '0x140c24b00'),
        (0x1421e4fd2, 'lea', 'rdx, [rbp + 0xe0]'), (0x1421e4fdc, 'call', '0x140c24b20'),
        (0x1421e4fe3, 'test', 'eax, eax'), (0x1421e4fe5, 'jns', '0x1421e5074'),
        (0x1421e5077, 'call', '0x1422152a0'), (0x1421e507c, 'movzx', 'ebx, al'),
        (0x1421e5082, 'call', '0x1422152b0'), (0x1421e5087, 'movzx', 'edi, al'),
        (0x1421e5129, 'movzx', 'edx, word ptr [rbp + 0xe8]'),
        (0x1421e5148, 'movzx', 'edx, word ptr [rbp + 0xea]'),
        (0x1421e5167, 'movzx', 'edx, word ptr [rbp + 0xec]'),
        (0x1421e5186, 'mov', 'edx, ebx'), (0x1421e51a0, 'mov', 'edx, edi'),
        (0x1421e53fe, 'mov', 'ecx, 0x28'), (0x1421e5403, 'call', '0x142117f10'),
        (0x1421e5439, 'movzx', 'r9d, word ptr [rbp + 0xec]'),
        (0x1421e5441, 'movzx', 'r8d, word ptr [rbp + 0xea]'),
        (0x1421e5449, 'movzx', 'edx, word ptr [rbp + 0xe8]'),
        (0x1421e5453, 'call', '0x140c01bc0'),
        (0x140c01beb, 'mov', 'word ptr [rcx], dx'),
        (0x140c01bee, 'mov', 'word ptr [rcx + 2], r8w'),
        (0x140c01bf3, 'mov', 'word ptr [rcx + 4], r9w'),
        (0x140c01bf8, 'add', 'rcx, 8'), (0x140c01bff, 'call', '0x1404a3300'),
        (0x1421e568b, 'mov', 'edx, 1'), (0x1421e5690, 'call', '0x140c24b10'),
        (0x1421e2168, 'movzx', 'ebp, r9w'), (0x1421e216c, 'movzx', 'r15d, r8w'),
        (0x1421e219a, 'mov', 'rax, qword ptr [rsi + 8]'),
        (0x1421e21aa, 'call', '0x140c01c50'), (0x1421e21af, 'cmp', 'ax, r15w'),
        (0x1421e21b9, 'call', '0x140c01c40'), (0x1421e21be, 'cmp', 'ax, bp'),
        (0x1421e21c1, 'je', '0x1421e2227'),
        (0x1421e21cc, 'mov', 'qword ptr [r14], 0'), (0x1421e21d3, 'mov', 'qword ptr [r14 + 8], 0'),
        (0x1421e226b, 'call', '0x1421e2730'),
        (0x1421e2270, 'mov', 'qword ptr [r14], r15'), (0x1421e2273, 'mov', 'qword ptr [r14 + 8], rbp'),
        (0x1421e2750, 'cmp', 'qword ptr [rdx + 0x10], rcx'),
        (0x1421e27bb, 'mov', 'qword ptr [r8], rax'),
        (0x1421e27c5, 'mov', 'qword ptr [r8 + 8], rax'),
        (0x1421e27c9, 'dec', 'qword ptr [r9 + 8]'),
        (0x1421dc68a, 'call', 'qword ptr [rax + 0x20]'),
        (0x1421dc6b6, 'call', 'qword ptr [rax + 0x18]'),
        (0x1421dc6b9, 'movzx', 'r9d, bx'), (0x1421dc6bd, 'movzx', 'r8d, ax'),
        (0x1421dc6cc, 'call', '0x1421e2150')]:
        check(va, op, operands)
    # Discovery/list removal path: virtual slots are bound by the RTTI below.
    for va, op, operands in [
        (0x1421c2132, 'mov', 'rax, qword ptr [rdx + 8]'), (0x1421c213e, 'call', 'rax'),
        (0x1421c22d4, 'call', '0x1421e0df0'), (0x1421c22e5, 'call', '0x1421c08e0'),
        (0x1421c22ed, 'call', '0x1421bc440'),
        (0x1421e1009, 'call', '0x1404f8f90'),
        (0x1404f8f99, 'lea', 'rdx, [rcx + 8]'), (0x1404f8fa0, 'call', '0x1404a3300'),
        (0x1421e1118, 'call', '0x1421201f0'), (0x1421e117a, 'call', '0x1421201f0'),
        (0x1421e1794, 'mov', 'rbx, qword ptr [rcx + 0x10]'), (0x1421e17c0, 'call', 'rbx'),
        (0x1421e1818, 'mov', 'rax, qword ptr [rax + 8]'), (0x1421e1847, 'call', 'rax'),
        (0x1421e2003, 'call', '0x1421e2730'), (0x1421e2008, 'test', 'al, al'),
        (0x1421e200a, 'jne', '0x1421e2019'), (0x1421e200c, 'lea', 'rcx, [rbp + 0x18]'),
        (0x1421e2013, 'call', '0x1421e2830'),
        (0x1421e22fc, 'lea', 'rdx, [rsi + 0x18]'),
        (0x1421e2308, 'mov', 'qword ptr [rdi], rcx'),
        (0x1421e230b, 'mov', 'qword ptr [rdx], rax'),
        (0x1421be7e2, 'call', '0x1421e22a0'),
        (0x1421be869, 'call', '0x140be1d00'), (0x1421be879, 'call', '0x1404f8f90'),
        (0x1421be891, 'call', '0x140c00a60'), (0x1421be8a8, 'call', '0x1404f8f90'),
        (0x1421be8d1, 'cmp', 'r8, rcx'), (0x1421be8d4, 'jne', '0x1421be8ef'),
        (0x1421be8e1, 'call', '0x1421201f0'), (0x1421be8e6, 'test', 'eax, eax'),
        (0x1421be8e8, 'jne', '0x1421be8ef'), (0x1421be9e2, 'jne', '0x1421bea98'),
        (0x1421beaeb, 'call', '0x1421bdc90')]:
        check(va, op, operands)
    leaf(0x140be1d00, [('4883792000', 'cmp', 'qword ptr [rcx + 0x20], 0'),
                       ('0f95c0', 'setne', 'al'), ('c3', 'ret', '')])
    leaf(0x140c01c40, [('0fb74102', 'movzx', 'eax, word ptr [rcx + 2]'), ('c3', 'ret', '')])
    leaf(0x140c01c50, [('0fb701', 'movzx', 'eax, word ptr [rcx]'), ('c3', 'ret', '')])
    strings = {}
    for va, literal in ((0x1421e5109, 'Vid=0x'), (0x1421e513c, '&Pid=0x'),
                        (0x1421e515b, '&BcdDevice=0x'), (0x1421e517a, '&Instance='), (0x1421e5194, '#')):
        h.require(app.text(app.rip(app.at(va, 'lea'))) == literal, 'Identity string differs')
        strings[hex(va)] = literal
    classes = []
    for table, locator, name, slots in [
        (0x1431d6f58, 0x1433edd18, '.?AVUsbDeviceDiscoveryWindows@composite@device@serato@@',
         [0x1421e4be0, 0x1421e4d10]),
        (0x1431d6b50, 0x1433eda20, '.?AVUsbConnectionList@composite@device@serato@@',
         [0x1421e1e30, 0x1421e2490, 0x1421e1e70])]:
        h.require(struct.unpack('<Q', app.data(table-8, 8))[0] == locator, 'Wrong locator')
        col = struct.unpack('<6I', app.data(locator, 24))
        h.require(col[0] == 1 and col[1] == 0 and col[5]+app.base == locator and
                  app.text(col[3]+app.base+16) == name, 'Wrong discovery/list RTTI')
        h.require(list(struct.unpack('<'+'Q'*len(slots), app.data(table, 8*len(slots)))) == slots, 'Wrong vtable')
        classes.append({'type': name, 'vtable': hex(table), 'locator': hex(locator), 'slots': list(map(hex, slots))})
    report_path = ROOT/'analysis/serato500-usb-discovery-01.json'
    report = json.loads(report_path.read_text(encoding='utf-8-sig'))
    h.require(report['binary_sha256'] == app.sha, 'Wrong focused report image')
    expected_ranges = {(0x1421e4d10, 0x1421e57c7), (0x1421e2490, 0x1421e272a),
                       (0x1421e1e70, 0x1421e2143), (0x1421e2150, 0x1421e229c)}
    h.require(len(report['functions']) == len(expected_ranges) and
              {(int(f['start'], 16), int(f['end_exclusive'], 16)) for f in report['functions']} == expected_ranges,
              'Focused report coverage differs')
    for f in report['functions']:
        h.require(f['complete'] and (int(f['start'], 16), int(f['end_exclusive'], 16)) in app.spans,
                  'Incomplete or incorrect focused report range')
    lifetime_reports = {}
    for file, ranges in [
        ('serato500-usb-discovery-lifetime-02.json',
         {(0x1421c20e0, 0x1421c231d), (0x1421e0ce0, 0x1421e0d41),
          (0x1421e1a00, 0x1421e1aaf), (0x1421be060, 0x1421bed49)}),
        ('serato500-usb-discovery-lifetime-03.json',
         {(0x1421e0df0, 0x1421e19f5), (0x1421e22a0, 0x1421e2382), (0x1421bdc90, 0x1421be051)})]:
        path = ROOT/'analysis'/file
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        h.require(value['binary_sha256'] == app.sha and len(value['functions']) == len(ranges) and
                  {(int(f['start'], 16), int(f['end_exclusive'], 16)) for f in value['functions']} == ranges and
                  all(f['complete'] and (int(f['start'], 16), int(f['end_exclusive'], 16)) in app.spans
                      for f in value['functions']), 'Lifetime report differs/incomplete')
        lifetime_reports[file] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                  'ranges': [f'{start:x}:{end:x}' for start, end in sorted(ranges)]}
    result = {
        'scope': 'Original-byte static USB identity discovery and list selection; no device/app execution',
        'applicationSha256': app.sha, 'directLibusbImports': {hex(k): v for k, v in usb_imports.items()},
        'importThunks': thunks, 'classes': classes, 'identityStringLiterals': strings,
        'record': {'allocationBytes': 40, 'vendorWordOffset': 0, 'productWordOffset': 2,
                   'revisionWordOffset': 4, 'identityStringOffset': 8,
                   'identityIncludes': ['vendor', 'product', 'revision', 'bus', 'address']},
        'selection': {'function': '0x1421e2150', 'matches': ['vendor', 'product'],
                      'onMatch': 'Take shared record and unlink its list entry', 'onMiss': 'Empty shared pointer'},
        'removal': {'discoveryConsumer': '0x1421c20e0', 'identityDiff': '0x1421e0df0',
                    'observerRemovalSlot': 16, 'observerArrivalSlot': 8,
                    'unusedArrivalRemoval': 'Unlink from available records without queueing a composite removal',
                    'consumedRecordRemoval': 'Queue at list +0x18, later drained by 0x1421e22a0',
                    'compositeMatching': 'Exact identity string length and bytes',
                    'matchingCompositeHelper': '0x1421bdc90',
                    'finalAudioTeardownVerified': False, 'runtimeIdentityChurnVerified': False},
        'instructions': instructions, 'focusedReportSha256': hashlib.sha256(report_path.read_bytes()).hexdigest(),
        'lifetimeReports': lifetime_reports,
        'limits': ['Direct imports do not exclude dynamic or transitive I/O elsewhere',
                   'This discovery record does not establish audio/control/handshake admission',
                   'No runtime UsbDk coexistence, bus/address stability or removal/rearrival behaviour verified',
                   'No descriptor, identity, resource, account, executable or security state changed']}
    (ROOT/'docs/evidence/serato500-usb-discovery.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified original USB discovery, descriptor-only record construction, VID/PID take and direct import inventory')


if __name__ == '__main__':
    main()
