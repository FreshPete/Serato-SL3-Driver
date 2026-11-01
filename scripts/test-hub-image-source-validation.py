"""Actual local PLA validate-only CLI checks. No trace source or device test."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('preparation', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    assert not args.report.exists() and args.report.parent.is_dir()
    original = json.loads(args.preparation.read_text(encoding='utf-8-sig'))
    source = ROOT / 'scripts/validate-hub-image-source.ps1'
    outcomes = []
    with tempfile.TemporaryDirectory(prefix='sl3-image-validation-') as folder:
        temp = Path(folder)

        def run(name, record, expected, creates_report=False):
            input_path, output = temp / (name + '-input.json'), temp / (name + '-output.json')
            input_path.write_text(json.dumps(record), encoding='utf-8')
            process = subprocess.run(['pwsh', '-NoProfile', '-File', str(source), '-PreparationRecord', str(input_path),
                                      '-Output', str(output)], capture_output=True, text=True, timeout=20)
            assert process.returncode == expected, (name, process.stdout, process.stderr)
            assert output.exists() == creates_report, (name, process.stdout, process.stderr)
            value = json.loads(output.read_text(encoding='utf-8-sig')) if creates_report else None
            if value is not None:
                assert value['commitMode'] == 4096 and value['sourceStarted'] is False and value['readinessAdmission'] is False
                assert value['before']['error']['hresult'] == value['after']['error']['hresult'] == '0x80300002'
                assert not value['prospectiveDirectoryExists']
                assert value['valid'] == (expected == 0)
            outcomes.append({'case': name, 'exitCode': process.returncode, 'reportCreated': creates_report,
                             'valid': value['valid'] if value else None,
                             'validationItems': value['validationItems'] if value else None})
            return value

        positive = run('valid', original, 0, True)
        assert positive['knownInactiveWarningsAccepted'] and positive['producer']['tokenQueried']
        for name, key, value in [('stale-source', 'sourceSha256', '0' * 64),
                                  ('unsafe-name', 'sessionName', 'NT Kernel Logger'),
                                  ('committed-role', 'sourceCommitted', True),
                                  ('false-string-role', 'sourceStarted', 'false'),
                                  ('oversized-record', 'extra', 'x' * 131073),
                                  ('dtd', 'xml', '<!DOCTYPE DataCollectorSet><DataCollectorSet/>')]:
            record = copy.deepcopy(original)
            record[key] = value
            run(name, record, 1)
        for name, xpath, value in [('wrong-provider', 'TraceDataCollector/TraceDataProvider/Guid', '{00000000-0000-0000-0000-000000000000}'),
                                   ('wrong-mode', 'TraceDataCollector/ExtendedModes', '0'),
                                   ('circular-mode', 'TraceDataCollector/LogCircular', '1'),
                                   ('output-path', 'TraceDataCollector/FileName', '../escape'),
                                   ('extra-filter', 'TraceDataCollector/TraceDataProvider/KeywordsAll/Value', '4096'),
                                   ('task-not-empty', 'Task', 'validation-only-no-execution')]:
            record = copy.deepcopy(original)
            xml = ET.fromstring(record['xml'])
            xml.find(xpath).text = value
            record['xml'] = ET.tostring(xml, encoding='unicode')
            run(name, record, 1)
        # Nonempty TaskArguments reaches commit-time warning handling. This
        # host rejects the inactive nonempty pattern earlier during SetXml.
        for field in ('TaskArguments', 'SubdirectoryFormatPattern'):
            record = copy.deepcopy(original)
            xml = ET.fromstring(record['xml'])
            xml.find(field).text = 'validation-only-nonempty'
            record['xml'] = ET.tostring(xml, encoding='unicode')
            value = run('nonempty-' + field, record, 1, field == 'TaskArguments')
            if value is not None:
                assert value['validationCallSucceeded'] and not value['knownInactiveWarningsAccepted']
        existing = temp / 'existing.json'
        existing.write_text('preserve this', encoding='utf-8')
        process = subprocess.run(['pwsh', '-NoProfile', '-File', str(source), '-PreparationRecord', str(args.preparation.resolve()),
                                  '-Output', str(existing)], capture_output=True, text=True, timeout=20)
        assert process.returncode == 1 and existing.read_text() == 'preserve this'
        outcomes.append({'case': 'existing-output', 'exitCode': 1, 'existingOutputPreserved': True})
    result = {'scope': 'Actual PLA validation-only CLI tests; no operational commit/start/device request',
              'validatorSha256': sha(source), 'testSourceSha256': sha(Path(__file__)),
              'preparationSha256': sha(args.preparation), 'positiveProducer': positive['producer'],
              'checks': outcomes, 'sourceStarted': False, 'readinessAdmission': False}
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(f'Passed {len(outcomes)} actual validate-only CLI cases; no source persisted or started')


if __name__ == '__main__':
    main()
