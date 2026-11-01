"""Verify conditional USB/composite removal through DeviceManager list publication."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = importlib.util.spec_from_file_location('removal_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    app = h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', h.CURRENT_SHA)
    h.require(hashlib.sha256(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe').read_bytes()).hexdigest()
              == app.sha, 'Installed application differs')
    checks = [
        (0x1421c0aa7, 'call', '0x14080e0a0'), (0x1421c0ab2, 'test', 'al, al'),
        (0x1421c0ab4, 'je', '0x1421c0c2f'),
        (0x1421c0ad0, 'mov', 'dword ptr [rbp - 0x71], 1'),
        (0x1421c0b1c, 'lea', 'r9, [rbp - 0x71]'), (0x1421c0b2b, 'call', '0x1421de6b0'),
        (0x1421c0be4, 'call', '0x1421de0a0'),
        (0x1421de6c5, 'lea', 'rax, [rip + 0xff8274]'),
        (0x1421de71b, 'mov', 'eax, dword ptr [rsi]'), (0x1421de722, 'mov', 'dword ptr [rbx + 0x28], eax'),
        (0x1421de935, 'movsxd', 'rax, dword ptr [r14 + 0x28]'), (0x1421de939, 'cmp', 'eax, 0xe'),
        (0x1421de942, 'lea', 'rcx, [rip - 0x21de949]'),
        (0x1421de949, 'mov', 'edx, dword ptr [rcx + rax*4 + 0x21debe4]'),
        (0x1421de950, 'add', 'rdx, rcx'), (0x1421de953, 'jmp', 'rdx'),
        (0x1421de968, 'mov', 'rbx, qword ptr [rax + 0x10]'), (0x1421de970, 'jmp', '0x1421deb7f'),
        (0x142140072, 'lea', 'rax, [rip + 0x87]'),
        (0x142140091, 'lea', 'r8, [rcx - 0x88]'), (0x142140098, 'add', 'rcx, 0x18'),
        (0x1421400a4, 'call', '0x14213ae20'),
        (0x142140e75, 'call', '0x140bff5c0'), (0x142140e7a, 'mov', 'rbx, qword ptr [rsi + 0x150]'),
        (0x142140ed4, 'lea', 'rcx, [rsi + 0x160]'), (0x142140edb, 'call', '0x142141ba0'),
        (0x140c00a49, 'lea', 'rdx, [rcx + 0x40]'), (0x140c00a50, 'call', '0x1404a3300'),
        (0x140bff674, 'call', '0x140c00a40'), (0x140bff6d9, 'call', '0x140bff860'),
        (0x142141c76, 'call', '0x14213b850'),
        (0x142141c8d, 'mov', 'r10, qword ptr [rdx + 0x60]'), (0x142141cb1, 'call', 'r10'),
        (0x14213bf98, 'lea', 'rdi, [rsi + 0x160]'),
        (0x14213c1f4, 'movdqa', 'xmm0, xmmword ptr [rip + 0x1088274]'),
        (0x14213c1fc, 'movdqu', 'xmmword ptr [rbp - 0x18], xmm0'),
        (0x14213c2b2, 'mov', 'eax, dword ptr [rbp - 0x18]'),
        (0x14213c2b5, 'mov', 'dword ptr [rdi + 0x18], eax'),
        (0x14213b8e6, 'lea', 'rax, [rip + 0x10887a3]'), (0x14213b8ed, 'mov', 'qword ptr [r15], rax'),
    ]
    evidence = []
    for va, op, operands in checks:
        i = app.at(va, op, operands)
        evidence.append({'va': hex(va), 'bytes': i.bytes.hex(), 'instruction': op+' '+operands})
    leaf = list(app.dis.disasm(app.data(0x14080e0a0, 5), 0x14080e0a0))
    h.require([(i.bytes.hex(), i.mnemonic, i.op_str) for i in leaf] ==
              [('0fb64160', 'movzx', 'eax, byte ptr [rcx + 0x60]'), ('c3', 'ret', '')], 'Composite flag getter differs')
    h.require(app.base+struct.unpack('<I', app.data(0x1421debe4+4, 4))[0] == 0x1421de965,
              'Action 1 jump-table target differs')
    h.require(app.rip(app.at(0x142140072)) == 0x142140100, 'Wrong manager callback')
    h.require(app.rip(app.at(0x14213c1f4)) == 0x1431c4470 and
              struct.unpack('<4I', app.data(0x1431c4470, 16)) == (0x2df, 0, 0, 0), 'Device-list message constants differ')
    classes = []
    for table, offset, name, slots in [
        (0x1431d6940, 0, '.?AVDispatchDeviceDeferredAction@composite@device@serato@@', {8: 0x1421de890}),
        (0x1431c3f28, 0x88, '.?AVDeviceManager@@', {0x10: 0x142140060}),
        (0x1431c4090, 0, '.?AV?$UserIO_TemplateMessageData@VDeviceList@@@data@message@serato@@', {})]:
        col_va = struct.unpack('<Q', app.data(table-8, 8))[0]
        col = struct.unpack('<6I', app.data(col_va, 24))
        h.require(col[0] == 1 and col[1] == offset and col[5]+app.base == col_va and
                  app.text(app.base+col[3]+16) == name, 'Removal dispatch RTTI differs')
        for slot, target in slots.items():
            h.require(struct.unpack('<Q', app.data(table+slot, 8))[0] == target, 'Removal dispatch slot differs')
        classes.append({'type': name, 'vtable': hex(table), 'locator': hex(col_va), 'objectOffset': offset,
                        'checkedSlots': {hex(k): hex(v) for k, v in slots.items()}})
    reports = {}
    for file, starts in [
        ('serato500-usb-removal-dispatch-01.json', ['1421c0970']),
        ('serato500-usb-removal-dispatch-02.json', ['142140060']),
        ('serato500-usb-removal-dispatch-03.json', ['142140100']),
        ('serato500-usb-removal-dispatch-04.json', ['140bff5c0', '142141ba0'])]:
        path = ROOT/'analysis'/file; report = json.loads(path.read_text(encoding='utf-8-sig'))
        h.require(report['binary_sha256'] == app.sha, 'Wrong removal report image')
        ranges = []
        for start in starts:
            f = next(f for f in report['functions'] if f['start'] == start)
            span = (int(start, 16), int(f['end_exclusive'], 16))
            h.require(f['complete'] and span in app.spans, 'Incomplete removal report/range')
            ranges.append(f'{start}:{f["end_exclusive"]}')
        reports[file] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'selectedRanges': ranges}
    result = {
        'scope': 'Conditional static removal notification and ordinary DeviceManager list-update path',
        'applicationSha256': app.sha, 'classes': classes, 'instructions': evidence, 'reports': reports,
        'conditionalDispatch': {'compositeFlagOffset': 0x60, 'whenNonzero': 'Queue action 1',
                                'actionObserverSlot': 0x10, 'managerReceiverOffset': 0x88,
                                'scheduledCallback': '0x142140100'},
        'ordinaryCallbackPath': {'collectionOffset': 0x150, 'compositeKeyStringOffset': 0x40,
                                 'publicationStateOffset': 0x160, 'messageId': 0x2df,
                                 'payloadType': 'UserIO_TemplateMessageData<DeviceList>'},
        'audioCloseProven': False, 'actualSL3RemovalDispatchCaptured': False,
        'limits': ['Composite flag +0x60 is a raw checked predicate; its full lifecycle semantics are not established here',
                   'Callback has earlier conditional paths/returns; ordinary collection removal is not universal',
                   'Collection publication is not a direct IASIO stop/dispose/Release call',
                   'No exhaustive subscriber recovery, runtime observer proof or scheduling deadline',
                   'Current SL3 admission and UsbDk identity churn remain unverified; no application/resource/security change']}
    (ROOT/'docs/evidence/serato500-usb-removal-dispatch.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified conditional action 1, DeviceManager callback and ordinary DeviceList publication; audio close remains unproved')


if __name__ == '__main__':
    main()
