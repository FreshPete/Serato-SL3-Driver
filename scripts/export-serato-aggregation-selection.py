"""Verify static aggregation registration/selection, without executing Serato."""
import hashlib
import importlib.util
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sl3_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def rtti(image, table, expected):
    locator = struct.unpack('<Q', image.data(table - 8, 8))[0]
    signature, offset, _, descriptor, _, own = struct.unpack('<6I', image.data(locator, 24))
    h.require(signature == 1 and image.base + own == locator and offset == 0, 'Invalid complete-object locator')
    name = image.data(image.base + descriptor + 16, 160).split(b'\0', 1)[0].decode('ascii')
    h.require(name == expected, 'RTTI type changed')
    return {'table': hex(table), 'locator': hex(locator), 'type': name}


def main():
    a = h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', h.CURRENT_SHA)
    h.require(hashlib.sha256(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe').read_bytes()).hexdigest() == a.sha, 'Installed image differs')
    reports = {}
    for name in ('serato500-usb-connection-01.json', 'serato500-usb-connection-02.json', 'serato500-usb-connection-03.json', 'serato500-usb-connection-04.json'):
        p = ROOT/'analysis'/name
        report = json.loads(p.read_text(encoding='utf-8-sig'))
        h.require(report['binary_sha256'] == a.sha, 'Wrong focused image')
        for row in report['functions']:
            h.require(row['complete'] and (int(row['start'], 16), int(row['end_exclusive'], 16)) in a.spans, 'Incomplete range')
        reports[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    leaves = {
        0x140505470: '488d81d8000000c3',
        0x140c01c30: '0fb74104c3',
        0x140c01c40: '0fb74102c3',
        0x140c01c50: '0fb701c3',
    }
    for va, raw in leaves.items():
        h.require(a.data(va, len(bytes.fromhex(raw))) == bytes.fromhex(raw), 'Leaf bytes changed')
    checks = (
        (0x14213c695, 'call', '0x1421bc060'),
        (0x1421bc1f1, 'call', 'qword ptr [rax + 0x30]'),
        (0x1421bc1f4, 'mov', 'rdi, qword ptr [rax + 0x10]'),
        (0x1421bc238, 'test', 'rdi, rdi'),
        (0x1421bc23b, 'je', '0x1421bc2ca'),
        (0x1421bc2ac, 'add', 'qword ptr [r12 + 8], 0x10'),
        (0x1421bf074, 'call', '0x140c01c30'),
        (0x1421bf08f, 'mov', 'word ptr [rsp + 0x20], si'),
        (0x1421bf0a4, 'call', '0x1421bffa0'),
        (0x1421c0020, 'mov', 'r13, qword ptr [rdi + 0x48]'),
        (0x1421c00ca, 'cmp', 'ax, word ptr [rsp + 0x100]'),
        (0x1421c00d2, 'je', '0x1421c0256'),
        (0x1421c00f5, 'jae', '0x1421c01b4'),
        (0x1421c0155, 'cmp', 'bx, ax'),
        (0x1421c0158, 'cmovbe', 'r15, rcx'),
        (0x1421bf59c, 'je', '0x1421bf5b5'),
        (0x1421bf5b0, 'jle', '0x1421bf5c6'),
        (0x1421bf5c0, 'call', '0x140b1a3c0'),
        (0x140b1a3dd, 'mov', 'dword ptr [rax + 0x10], ebx'),
        (0x140b1a3f3, 'mov', 'dword ptr [rax + 0x10], ebx'),
    )
    assembly = []
    for va, opcode, operands in checks:
        row = a.at(va, opcode, operands)
        assembly.append(f'{va:x}: {row.mnemonic} {row.op_str}')
    calls = [i for i in a.function(0x14213be40) if i.mnemonic == 'call' and i.op_str == '0x140505470']
    h.require(len(calls) == 1, 'Primary vector acquisition changed')
    out = {
        'scope': 'Static DeviceAggregator registration and USB-side numeric selection; no runtime integration',
        'binarySha256': a.sha, 'installedIdentityMatches': True, 'focusedReports': reports,
        'types': [rtti(a, 0x1431d4560, '.?AVDeviceAggregator@composite@device@serato@@'),
                  rtti(a, 0x1431c3ed8, '.?AVDeviceManager@@')],
        'primaryVectorGetterCall': hex(calls[0].address),
        'leafBytes': {hex(k): v for k, v in leaves.items()}, 'assembly': assembly,
        'registration': 'Ordered primary descriptors are supplied as +0x10 interfaces; an existing same VID/PID/revision entry with an empty name suppresses later insertion',
        'numericSelection': 'First exact revision; otherwise highest strictly older revision, later ties win, within the separately populated aggregation vector',
        'revisionReconciliation': 'For matching VID/PID, replace zero or a larger composite revision with the USB-side revision; writes application memory only',
        'limits': ['No provider injection/configuration established', 'Conditional insertion consequences are not an observed SL3 connection',
                   'USB identity-record construction and live revision values remain unverified', 'No application, USB identity, driver, account or firmware changes'],
        'vendorCodeExecuted': False,
    }
    destination = ROOT/'docs/evidence/serato500-aggregation-selection.json'
    destination.write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
    print(destination)


if __name__ == '__main__':
    main()
