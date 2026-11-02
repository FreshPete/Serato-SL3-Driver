"""Identify the USB helper's actual service receiver, offline; never query authorization."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('authorization_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
CHECKS = [
    (0x14070ffcb, 'call', '0x141960f80'),
    (0x14070ffe0, 'call', 'r8'),
    (0x14070ffe7, 'call', '0x141960f80'),
    (0x14070fffc, 'call', 'r8'),
    (0x141960f89, 'lea', 'rcx, [rip + 0x26cb8d0]'),
    (0x141960f90, 'call', '0x1419605a0'),
    (0x141960f95, 'mov', 'rax, qword ptr [rip + 0x26cb8bc]'),
    (0x1419605a6, 'mov', 'rbx, rcx'),
    (0x1419605b3, 'call', 'qword ptr [rip + 0xdd1d1f]'),
    (0x1419605c4, 'cmp', 'dword ptr [rsp + 0x40], 0'),
    (0x1419605c9, 'je', '0x141960630'),
    (0x1419605dd, 'call', '0x141960a60'),
    (0x1419605e2, 'mov', 'rdx, qword ptr [rax]'),
    (0x1419605e5, 'mov', 'qword ptr [rax], 0'),
    (0x1419605f3, 'mov', 'qword ptr [rip + 0x26cc25e], rdx'),
    (0x141960626, 'call', 'qword ptr [rip + 0xdd1cdc]'),
    (0x141960a6f, 'cmp', 'dword ptr [rip + 0x26cbddb], edi'),
    (0x141960a75, 'jne', '0x141960aa7'),
    (0x141960a77, 'mov', 'ecx, 0xe8'),
    (0x141960a8e, 'call', '0x141984590'),
    (0x141960a93, 'mov', 'rdi, rax'),
    (0x141960a99, 'mov', 'qword ptr [rbx], rdi'),
    (0x141960aa7, 'mov', 'ecx, 0x38'),
    (0x141960abe, 'call', '0x14197fce0'),
    (0x141960ac3, 'mov', 'rdi, rax'),
    (0x141960ac9, 'mov', 'qword ptr [rbx], rdi'),
    (0x1419845aa, 'call', '0x1419606b0'),
    (0x1419845b0, 'lea', 'rax, [rip + 0x164cd01]'),
    (0x1419845b7, 'mov', 'qword ptr [r14], rax'),
    (0x14197fce9, 'call', '0x1419606b0'),
    (0x14197fcee, 'lea', 'rax, [rip + 0x1650cd3]'),
    (0x14197fcf5, 'mov', 'qword ptr [rbx], rax'),
    (0x14197fcf8, 'mov', 'rax, rbx'),
]
RANGES = [(0x141960f80, 0x141960fa1), (0x1419605a0, 0x14196063c),
          (0x141960a60, 0x141960ad7), (0x141984590, 0x141984777), (0x14197fce0, 0x14197fd09)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rtti(a, table, expected):
    locator = struct.unpack('<Q', a.data(table-8, 8))[0]
    sig, offset, _, td, _, own = struct.unpack('<6I', a.data(locator, 24))
    h.require(sig == 1 and offset == 0 and a.base+own == locator, 'Complete-object locator differs')
    h.require(a.text(a.base+td+16) == expected, 'Service RTTI differs')
    return {'vtable': hex(table), 'locator': hex(locator), 'type': expected,
            'slots': {hex(n): hex(struct.unpack('<Q', a.data(table+n, 8))[0]) for n in [0x90, 0xa0]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        h.require(not args.output.exists(), 'Fresh output required')
    a = h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', h.CURRENT_SHA)
    h.require(sha(Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe')) == a.sha, 'Installed executable differs')
    old_path = ROOT/'docs/evidence/serato500-usb-arrival.json'
    h.require(sha(old_path) == '7d018af5beaa3cb0f1111d3f2c79cff3369bdacec7e9e80f828f98794a3d9f50', 'Earlier helper proof differs')
    # Recheck earlier exact helper/message evidence using its original exporter metadata.
    old_spec = importlib.util.spec_from_file_location('authorization_arrival', ROOT/'scripts/export-serato-usb-arrival.py')
    old = importlib.util.module_from_spec(old_spec)
    old_spec.loader.exec_module(old)
    for va, text in old.CHECKS:
        op, _, operands = text.partition(' ')
        a.at(va, op, operands)
    facts = []
    for va, op, operands in CHECKS:
        i = a.at(va, op, operands)
        facts.append({'va': hex(va), 'bytes': i.bytes.hex(), 'instruction': op+' '+operands})
    h.require(a.rip(a.at(0x141960f89)) == 0x14402c860, 'Once state differs')
    h.require(a.rip(a.at(0x141960f95)) == a.rip(a.at(0x1419605f3)) == 0x14402c858, 'Service pointer load/store differs')
    h.require(a.rip(a.at(0x141960a6f)) == 0x14402c850, 'Factory selector differs')
    h.require(a.rip(a.at(0x1419845b0)) == 0x142fd12b8 and a.rip(a.at(0x14197fcee)) == 0x142fd09c8, 'Constructor vtable differs')
    a.pe.parse_data_directories(directories=[1])
    imports = {e.address: (d.dll.decode(), e.name.decode() if e.name else '') for d in a.pe.DIRECTORY_ENTRY_IMPORT for e in d.imports}
    for va, name in [(0x1419605b3, 'InitOnceBeginInitialize'), (0x141960626, 'InitOnceComplete')]:
        h.require(imports[a.rip(a.at(va))] == ('KERNEL32.dll', name), 'Once API import differs')
    types = [rtti(a, 0x142fd12b8, '.?AVRLMAuthorization@authorization@serato@@'),
             rtti(a, 0x142fd09c8, '.?AVJWTAuthorization@authorization@serato@@'),
             rtti(a, 0x142e86360, '.?AVDriverAPI@driver@device@serato@@')]
    h.require(types[0]['slots'] == {'0x90': '0x14198f450', '0xa0': '0x14198a130'} and
              types[1]['slots'] == {'0x90': '0x141983630', '0xa0': '0x141982ba0'} and
              types[2]['slots']['0x90'] == '0x1404a4550', 'Distinct method bindings differ')
    focused_path = ROOT/'analysis/serato500-authorization-service-20261102-decompile.json'
    focused = json.loads(focused_path.read_text(encoding='utf-8-sig'))
    h.require(focused['binary_sha256'] == a.sha and len(focused['functions']) == len(RANGES), 'Focused image/count differs')
    functions = []
    for row, extent in zip(focused['functions'], RANGES):
        h.require(row['complete'] and (int(row['start'], 16), int(row['end_exclusive'], 16)) == extent and extent in a.spans, 'Complete original unwind extent required')
        functions.append({'start': hex(extent[0]), 'endExclusive': hex(extent[1]), 'bytesSha256': hashlib.sha256(a.data(extent[0], extent[1]-extent[0])).hexdigest()})
    sources = ['scripts/export-serato-authorization-service.py', 'scripts/export-serato-usb-arrival.py', 'scripts/export-serato-clock-handshake-evidence.py']
    report = {'schema': 'sl3.usb-helper-service-binding.v1', 'status': 'static_receiver_identification',
              'applicationSha256': a.sha, 'priorUsbArrivalEvidenceSha256': sha(old_path), 'instructionFacts': facts,
              'priorArrivalInstructionChecks': len(old.CHECKS), 'types': types, 'completeFocusedFunctions': functions,
              'privateFocusedReportSha256': sha(focused_path),
              'sources': {p: {'localSha256': sha(ROOT/p), 'gitLfSha256': hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n', b'\n')).hexdigest()} for p in sources},
              'binding': {'accessor': '0x141960f80', 'initializer': '0x1419605a0', 'factory': '0x141960a60',
                          'pointerGlobal': '0x14402c858', 'onceState': '0x14402c860', 'selectorGlobal': '0x14402c850',
                          'zeroSelectorType': 'RLMAuthorization', 'nonzeroSelectorType': 'JWTAuthorization'},
              'conclusion': 'The USB helper calls an authorization-namespace service, not DriverAPI; equal slot offsets do not identify equal receivers or meanings',
              'helperResultBoundary': 'Service slot +0x90 result is sent in 0x693; helper returns stored +0x70 OR +0x71, not the direct service Boolean',
              'actualBackendObserved': False, 'authorizationSemanticsExhausted': False, 'accountOrLicenseQueried': False,
              'authorizationChangedOrEmulated': False, 'historicalRaneControlReplacementEstablished': False,
              'applicationExecuted': False, 'installedApplicationModified': False, 'deviceAccess': False,
              'currentSeratoAdmissionVerified': False, 'twoDeckDvsVerified': False, 'deploymentApproved': False,
              'remaining': ['Actual permitted service result for genuine SL3 and complete state-message delivery',
                            'Source/meaning of all 0x692 updates and any later service-pointer mutation',
                            'Current resource parsing/admission, NONE/control contract, measured native audio/deployment and real DVS'],
              'limits': ['Names establish RTTI identity, not full entitlement semantics or a claim that purchasing a license admits SL3',
                         'Factory branch is static; live selector/account/backend state was not read',
                         'No service response, token, account state, key, identity or policy is substituted']}
    raw = json.dumps(report, indent=2)+'\n'
    if args.output:
        with args.output.open('x', encoding='utf-8', newline='\n') as f:
            f.write(raw)
    else:
        print(raw, end='')


if __name__ == '__main__':
    main()
