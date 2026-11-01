"""Verify output stereo-pair graph wiring in the unchanged current Serato PE."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
image = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image)
require = image.require


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    app = image.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', image.CURRENT_SHA)
    reports, code = {}, {}
    for filename in ('serato500-endpoint-mixer-03.json', 'serato500-output-builders-08.json',
                     'serato500-output-router-07.json', 'serato500-output-enum-edge-09.json',
                     'serato500-output-connection-10.json'):
        path = ROOT/'analysis'/filename
        report = json.loads(path.read_text(encoding='utf-8-sig'))
        require(report['binary_sha256'] == app.sha, 'Focused image differs')
        for row in report['functions']:
            require(row['complete'] and (int(row['start'], 16), int(row['end_exclusive'], 16)) in app.spans,
                    'Incomplete or mismatched unwind range')
            code[row['start']] = row['pseudocode'].replace('\r', '')
        reports[filename] = digest(path)
    enums = []
    for name, value, literal, store in (
        ('Deck1Out', 3, 0x1405c3fbd, 0x1405c3fcf),
        ('Deck2Out', 4, 0x1405c409d, 0x1405c40af),
        ('Deck3Out', 5, 0x1405c40f2, 0x1405c4104),
    ):
        row = app.at(literal, 'movabs')
        require(struct.pack('<Q', row.operands[1].imm) == name.encode('ascii'), 'Inline endpoint string differs')
        app.at(store, 'mov', f'dword ptr [rbp + 0xf], {value}')
        require(f'uStack_50 = {value};' in code['1405c3c10'], 'Enum store missing from focused initializer')
        enums.append({'name': name, 'value': value, 'assembly': app.window(literal, 0, 7)})
    for address, label in ((0x1405cadb9, 'output_endpoints'), (0x1405cadd1, 'mixer_out'),
                           (0x1405cadf5, 'hw_dest'), (0x14143ecd3, 'FromPort'), (0x14143ed0b, 'ToPort')):
        require(app.text(app.rip(app.at(address))) == label, 'Wrong parser/port label')
    checks = (
        (0x14020c40b, 'call', '0x1405c3c10'),
        (0x1405cab7d, 'xor', 'r15d, r15d'),
        (0x1405cadf0, 'mov', 'dword ptr [rsp + 0x34], r15d'),
        (0x1405cae11, 'call', '0x141b19d10'),
        (0x1405caeee, 'inc', 'r15d'),
        (0x14214a707, 'mov', 'r13, qword ptr [rdi + 0x188]'),
        (0x14214a733, 'mov', 'r12d, dword ptr [rbx + 0x20]'),
        (0x14214a737, 'mov', 'r14, qword ptr [rbp + 0xf8]'),
        (0x14214a7ed, 'mov', 'dword ptr [rcx + 0x20], r12d'),
        (0x14214ad77, 'lea', 'r8, [rbp + 0xf0]'),
        (0x14214ad8c, 'call', '0x1422901d0'),
        (0x1422901e5, 'mov', 'r14, r8'),
        (0x14229026d, 'mov', 'rdx, r14'),
        (0x142290273, 'call', '0x14228e2a0'),
        (0x14228e2c2, 'mov', 'r13, rdx'),
        (0x14228e415, 'mov', 'rbx, qword ptr [r13 + 8]'),
        (0x14228e5fe, 'mov', 'eax, dword ptr [rbx + 0x20]'),
        (0x14228e601, 'lea', 'r15d, [rax + rax]'),
        (0x14228e648, 'mov', 'dword ptr [rsp + 0x28], r15d'),
        (0x14228e664, 'call', '0x1414db7f0'),
        (0x14228e669, 'lea', 'eax, [r15 + 1]'),
        (0x14228e66d, 'mov', 'dword ptr [rsp + 0x28], eax'),
        (0x14228e683, 'call', '0x1414db7f0'),
        (0x14143ece2, 'mov', 'qword ptr [rbx + 0x280], rax'),
        (0x14143ed1a, 'mov', 'qword ptr [rbx + 0x288], rax'),
        (0x1414db9ad, 'mov', 'edx, dword ptr [rsp + 0xb0]'),
        (0x1414db9b4, 'mov', 'rcx, qword ptr [r14 + 0x280]'),
        (0x1414db9d0, 'mov', 'edx, dword ptr [rsp + 0xb8]'),
        (0x1414db9d7, 'mov', 'rcx, qword ptr [r14 + 0x288]'),
    )
    for address, mnemonic, operands in checks:
        app.at(address, mnemonic, operands)
    require(app.rip(app.at(0x14020c404)) == 0x143ebeb28, 'Wrong output enum map initializer')
    require(app.text(0x142f3e2c8) == 'graphOut'
            and app.text(0x143b76920+16) == '.?AVGraphOutNode@model@audio@serato@@', 'Graph output identity differs')
    builder = code['14228e2a0']
    require('iVar5 = (int)plVar12[4] * 2;' in builder
            and 'FUN_1414db7f0(param_1,lStack_a8,lStack_a0,0,iVar7,iVar5);' in builder
            and 'iVar7 + 1,iVar5 + 1' in builder and '0x143b76920' in builder,
            'Focused output wiring differs')
    edge = code['1414db7f0']
    require('FUN_1406af4e0(plVar6[0x50],param_5' in edge
            and 'FUN_1406af4e0(plVar6[0x51],param_6' in edge, 'Connection port ABI differs')
    legacy_path = ROOT/'docs/evidence/serato-legacy-sl3-descriptors.json'
    legacy = json.loads(legacy_path.read_text(encoding='utf-8-sig'))
    require(len(legacy['targets']) == 2 and all(target['outputsInDeclaredOrder'] == ['Deck3Out', 'Deck1Out', 'Deck2Out']
                                             for target in legacy['targets']), 'Historical output order differs')
    result = {
        'scope': 'Static descriptor-to-GraphOut stereo port routing; no physical audio or current SL3 integration',
        'binarySha256': app.sha, 'focusedReportSha256': reports, 'outputEnums': enums,
        'outputMap': {'mixerCompleteOffset': '0x188', 'builderConfigurationOffset': '0x8',
                      'builder': '0x14228E2A0', 'graphNode': 'serato::audio::model::GraphOutNode'},
        'graphOutputPorts': '2*hw_dest and 2*hw_dest+1',
        'routeAssembly': app.window(0x14228e5fe, 0, 35),
        'toPortPropertyAssembly': app.window(0x14143ed00, 0, 7),
        'connectionPortAssignmentAssembly': app.window(0x1414db9ad, 0, 12),
        'legacyEvidenceSha256': digest(legacy_path),
        'historicalOrderInference': [{'endpoint': name, 'hardwarePair': index, 'graphOutputPorts': [index*2, index*2+1]}
                                    for index, name in enumerate(['Deck3Out', 'Deck1Out', 'Deck2Out'])],
        'limits': ['The current discontinued SL3 stub does not supply this full historical configuration',
                   'Graph ports do not prove final backend channel conversion, physical sockets or analogue output',
                   'Account/product/handshake requirements remain independent and unchanged'],
    }
    output = ROOT/'docs/evidence/serato500-output-routing.json'
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified output enum, configuration forwarding, stereo graph ports and ToPort assignment')


if __name__ == '__main__':
    main()
