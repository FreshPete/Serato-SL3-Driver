"""Check the offline SL3 candidate against recorded USB identity and original selection bytes."""
import argparse
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('selection_candidate', ROOT/'scripts/prepare-serato-sl3-candidate.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
EXPECTED = {
    'serato500-descriptor-precedence.json': '90aa41ffa9f65fdf4f4f8a4061771a74cc2c978db6cc77365e6dbab34d465613',
    'serato500-aggregation-selection.json': 'b9762f6ab4096387858f26517d484e55a6774d6687ba7a6cf7112007d36225c2',
    'serato500-usb-discovery.json': '45e91ca74e7716a99018948e0a4fd502b4453d45557bb453bf0aeecdd8390029',
    'usb-identity-baseline-20261030.json': '9863fbe585c5f63f58900ee41ea6b60cc07da5748b3ce2c3acd6ca2fe8d649b5',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        c.require(not args.output.exists(), 'Fresh evidence output required')
    reports = {}
    for name, sha in EXPECTED.items():
        raw = c.read(ROOT/'docs/evidence'/name)
        c.require(c.digest(raw) == sha, 'Prior evidence changed: '+name)
        reports[name] = c.parsed(raw)
    context = c.source_context()
    folder = ROOT/'analysis/sl3-descriptor-candidate-20261102'
    xml = c.read(folder/c.XML_NAME, 65536)
    expected_xml = c.candidate_bytes(context['history'], c.schema_device_order(context['schemaBytes']))
    c.require(xml == expected_xml, 'Candidate XML differs')
    validation = c.validate_schema(xml, context['schemaBytes'])
    c.require(c.parsed(c.read(folder/'candidate.json')) == c.manifest(context, xml, validation), 'Candidate manifest differs')
    device = ET.fromstring(xml).find('native_pro_device')
    c.require(device.find('bcd_device') is None and device.find('midi_name') is None, 'Candidate selection fields differ')
    c.require(device.find('win_audio_device_name').get('value') == c.NAME, 'Candidate ASIO name differs')
    h = c.module('selection_image', 'export-serato-clock-handshake-evidence.py')
    a = h.Image('artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe', h.CURRENT_SHA)
    inherited = []
    for name, field in [('serato500-descriptor-precedence.json', 'checkedInstructions'),
                        ('serato500-aggregation-selection.json', 'assembly')]:
        for text in reports[name][field]:
            match = re.fullmatch(r'([0-9a-f]+): (\S+)(?: (.*))?', text)
            c.require(match is not None, 'Instruction evidence shape differs')
            a.at(int(match[1], 16), match[2], match[3] or '')
            inherited.append(text)
    for row in reports['serato500-usb-discovery.json']['instructions']:
        va = int(row['va'], 16)
        c.require(a.data(va, len(bytes.fromhex(row['bytes']))).hex() == row['bytes'], 'Discovery instruction bytes differ')
    for va, raw in reports['serato500-aggregation-selection.json']['leafBytes'].items():
        c.require(a.data(int(va, 16), len(bytes.fromhex(raw))).hex() == raw, 'Identity getter differs')
    # Parser defaults/absence branches and the shared identity-interface name getter.
    checks = [(0x1405c8365, 'xor', 'edi, edi'),
              (0x1405c83b1, 'mov', 'word ptr [rsi + 0xac], di'),
              (0x1405c83b8, 'lea', 'rdx, [rip + 0x22550a9]'),
              (0x1405c83c2, 'call', '0x141b17da0'),
              (0x1405c83c7, 'test', 'rax, rax'),
              (0x1405c83ca, 'je', '0x1405c83f3'),
              (0x1405c83f3, 'lea', 'rdx, [rip + 0x2237d6e]'),
              (0x1405c83fa, 'lea', 'rcx, [rsi + 0xb0]'),
              (0x1405c8401, 'call', '0x1404a8080'),
              (0x1405c8406, 'lea', 'rdx, [rip + 0x225506b]'),
              (0x1405c8410, 'call', '0x141b17da0'),
              (0x1405c8415, 'test', 'rax, rax'),
              (0x1405c8418, 'je', '0x1405c843b'),
              (0x1405c842f, 'lea', 'rcx, [rsi + 0xb0]'),
              (0x1405c8436, 'call', '0x1404a8080'),
              (0x1405c6ec9, 'lea', 'rdx, [rcx - 0x688]'),
              (0x1405c6ed3, 'call', '0x1404a3300')]
    facts = []
    for va, op, operands in checks:
        i = a.at(va, op, operands)
        facts.append({'va': hex(va), 'bytes': i.bytes.hex(), 'instruction': op+' '+operands})
    c.require(a.text(a.rip(a.at(0x1405c83b8))) == 'bcd_device', 'Revision key differs')
    c.require(a.text(a.rip(a.at(0x1405c8406))) == 'midi_name', 'Identity name key differs')
    c.require(a.text(a.rip(a.at(0x1405c83f3))) == '', 'Name default differs')
    c.require(struct.unpack('<2i', a.data(a.rip(a.at(0x1405beae9)), 8)) == (-8, 0x730), 'Interface base differs')
    c.require(struct.unpack('<Q', a.data(0x14281cbe8+0x30, 8))[0] == 0x1405c6ec0 and 8+0x730-0x688 == 0xb0, 'Name slot/field differs')
    supervisor = c.module('selection_saved_observer', 'supervise-usb-identity.py')
    baseline = ROOT/'tests/results/local/usb-identity-baseline-20261030-01'
    saved = supervisor.validate_supervised_run(baseline)
    old = reports['usb-identity-baseline-20261030.json']
    for name, sha in old['files'].items():
        c.require(c.digest(c.read(baseline/name)) == sha, 'Saved baseline file differs')
    rows = [c.parsed(line.encode()) for line in (baseline/'observations.jsonl').read_text(encoding='utf-8').splitlines()]
    samples = [r['snapshot'] for r in rows if r['event'] == 'sample']
    identity = old['sampledIdentity']
    c.require(identity == {'vendor': 0x1cc5, 'product': 1, 'revision': 0, 'bus': 3, 'address': 1}, 'Recorded identity differs')
    c.require(len(samples) == 4 and all(s['complete'] is True and s['identities'] == [identity] for s in samples), 'Four complete stable samples required')
    sources = ['scripts/export-serato-sl3-selection.py', 'scripts/supervise-usb-identity.py', 'scripts/observe-sl3-usb-identity.py',
               'scripts/prepare-serato-sl3-candidate.py', 'scripts/export-serato-clock-handshake-evidence.py']
    report = {'schema': 'sl3.candidate-selection-analysis.v1', 'status': 'conditional_static_prediction',
              'applicationSha256': a.sha, 'candidateSha256': c.digest(xml), 'priorEvidenceSha256': EXPECTED,
              'sources': {p: {'localSha256': c.digest(c.read(ROOT/p)), 'gitLfSha256': c.digest(c.read(ROOT/p).replace(b'\r\n', b'\n'))} for p in sources},
              'newInstructionFacts': facts, 'inheritedSelectionInstructionChecks': len(inherited),
              'inheritedDiscoveryByteChecks': len(reports['serato500-usb-discovery.json']['instructions']),
              'savedObservationValidation': saved, 'recordedUsbIdentity': identity, 'newPhysicalObservation': False,
              'parserProjection': {'bcd_device': 0, 'midi_name': '', 'identityNameSlot': '0x30', 'identityNameCompleteOffset': '0xb0',
                                   'asioDriverName': c.NAME, 'asioNameIsIdentityName': False},
              'conditionalPrediction': {'primaryNumericLookupAtRecordedRevision': 'First parsed candidate exact match before later stub',
                                        'aggregationRegistration': 'Earlier same-triple candidate with empty midi_name suppresses later stub',
                                        'aggregationLookupAtRecordedRevision': 'Candidate exact match if registered as projected',
                                        'identityChangeNeededForRecordedRevision': False},
              'conditions': ['Resource must load and full native descriptor parse must succeed', 'Default fields must remain unmodified at runtime',
                             'Resource-before-stub registration and matching stub identity must apply',
                             'Actual lookup must use the recorded revision and checked numeric/aggregation route'],
              'counterexample': 'For nonzero requested revision and both entries at zero in the primary vector, later stub wins an older-fallback tie; do not generalize this result',
              'firmwareVersionInferred': False, 'currentRevisionAttested': False, 'actualChosenDescriptorObserved': False,
              'applicationExecuted': False, 'installedApplicationModified': False, 'deviceAccess': False,
              'currentSeratoAdmissionVerified': False, 'twoDeckDvsVerified': False, 'deploymentApproved': False,
              'remaining': ['Runtime trust/parsing/provider load and actual selection', 'NONE control semantics and service readiness',
                            'Measured ASIO profile/deployment, physical audio and legitimate current DVS']}
    raw = json.dumps(report, indent=2)+'\n'
    if args.output:
        with args.output.open('x', encoding='utf-8', newline='\n') as f:
            f.write(raw)
    else:
        print(raw, end='')


if __name__ == '__main__':
    main()
