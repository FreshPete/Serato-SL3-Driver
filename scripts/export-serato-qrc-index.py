"""Preserve bounded Qt-index findings and parser checks; no vendor execution."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('qrc_inspection', ROOT/'scripts/inspect-serato-qrc-resources.py')
qrc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qrc)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    result = qrc.inspect()
    all_indexes = list(result['bundles'].values())+result['embedded']
    qrc.require(sum(row['files'] for row in result['bundles'].values()) == 7844 and
                sum(row['files'] for row in result['embedded']) == 332, 'Checked index inventory differs')
    qrc.require(all(not row['deviceFolderPaths'] and not row['sl3NamedPaths'] for row in all_indexes),
                'Device-folder/SL3 name result changed; review integration candidates')
    log = ROOT/'analysis/qrc-index-tests.log'
    text = log.read_text(encoding='utf-8-sig')
    qrc.require('Ran 6 tests' in text and text.rstrip().endswith('OK'), 'Parser checks did not pass')
    result['parserChecks'] = {'testsPassed': 6, 'logSha256': sha(log),
                              'testSourceSha256': sha(ROOT/'tests/test_qrc_index.py'),
                              'inspectorSha256': sha(ROOT/'scripts/inspect-serato-qrc-resources.py')}
    result['finding'] = 'No indexed member under userio/userio_partner/userio_hidden_from_partners and no SL3-named file within these checked inputs'
    (ROOT/'docs/evidence/serato500-qrc-indexes.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified 7844 external and 332 embedded Qt file entries, exact original registration sites, six parser checks; no device folders or SL3 filenames in this scope')


if __name__ == '__main__':
    main()
