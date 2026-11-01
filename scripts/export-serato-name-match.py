"""Verify a bounded static name-matching checkpoint; execute no vendor code."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sl3_image', ROOT / 'scripts/export-serato-clock-handshake-evidence.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def main():
    app = helper.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', helper.CURRENT_SHA)
    installed = Path('C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe')
    helper.require(hashlib.sha256(installed.read_bytes()).hexdigest() == app.sha, 'Installed application changed')
    reports = {}
    for name in ('serato500-name-match-01.json', 'serato500-name-match-02.json', 'serato500-name-match-03.json'):
        path = ROOT / 'analysis' / name
        report = json.loads(path.read_text(encoding='utf-8-sig'))
        helper.require(report['binary_sha256'] == app.sha, 'Focused image mismatch')
        for row in report['functions']:
            helper.require(row['complete'] and (int(row['start'], 16), int(row['end_exclusive'], 16)) in app.spans, 'Incomplete focused range')
        reports[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    pattern = app.data(0x142e75920, 17)
    helper.require(pattern == rb'(\d+\s*-\s+)?(.+)', 'Name normalization expression changed')
    checks = (
        (0x140b21cb2, 'call', '0x140b220c0'),
        (0x140b21d0e, 'mov', 'dword ptr [rsp + 0x20], 1'),
        (0x140b21d23, 'call', '0x140b1c2c0'),
        (0x140b21d9b, 'xor', 'r8d, r8d'),
        (0x140b21da7, 'call', '0x140b1bc50'),
        (0x140b21dac, 'movzx', 'esi, al'),
        (0x140b21e65, 'movzx', 'eax, sil'),
        (0x140b1bc54, 'or', 'r8d, 0x10'),
        (0x140b1bc71, 'mov', 'byte ptr [rsp + 0x28], 1'),
        (0x140b1bc7e, 'call', '0x140b1b170'),
    )
    assembly = []
    for va, opcode, operands in checks:
        row = app.at(va, opcode, operands)
        assembly.append(f'{va:x}: {row.mnemonic} {row.op_str}')
    out = {
        'scope': 'Static name normalization and matcher call boundary; no runtime matching or integration test',
        'binarySha256': app.sha, 'installedIdentityMatches': True,
        'focusedReports': reports, 'normalizationExpression': pattern.decode('ascii'),
        'normalizationResult': 'Focused code selects capture group 2 after a successful match, otherwise copies original input',
        'descriptorPatternSyntaxArgument': 1, 'matcherAddedFlags': 16, 'matcherFinalBooleanArgument': True,
        'assembly': assembly,
        'limits': ['Regex-library interpretation is static, not execution of the vendor matcher',
                   'Exact engine semantics and exceptional/locale behavior not exhaustively recovered',
                   'No descriptor/provider installation route or physical Serato connection established'],
        'vendorCodeExecuted': False, 'applicationChanges': False,
    }
    destination = ROOT / 'docs/evidence/serato500-name-match.json'
    destination.write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
    print(destination)


if __name__ == '__main__':
    main()
