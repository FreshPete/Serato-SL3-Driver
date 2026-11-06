"""Exercise generated activation records with the native passive parser; no USB or installation."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
API = runpy.run_path(str(ROOT / 'scripts/prepare-asio-activation-config.py'))
BASE = API['BASE']
require = BASE['require']
read = BASE['read']
sha = lambda path: BASE['digest'](read(path))


def main():
    build = Path(sys.argv[1]).absolute()
    identity = uuid.uuid4().hex
    bundle = ROOT / 'artifacts/build/deployment-bundles' / ('activation-origin-' + identity)
    output = ROOT / 'artifacts/build/activation-reviews' / ('records with spaces-\u97f3-' + identity)
    installation = Path(os.environ['ProgramFiles']) / 'SL3 Rebuild' / ('activation-review-' + identity)
    pointer = Path(os.environ['LOCALAPPDATA']) / 'SL3Rebuild' / ('unused-' + identity) / 'current-session.txt'
    BASE['prepare'](build, sha(build), ROOT / 'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10', bundle,
                    installation, pointer, True)
    bundle_sha = sha(bundle / 'bundle-manifest.json')
    cases = []

    def good(name, action):
        action()
        cases.append({'name': name, 'passed': True})

    def rejects(name, action):
        try:
            action()
        except (ValueError, FileNotFoundError):
            cases.append({'name': name, 'passed': True})
        else:
            raise AssertionError('Accepted: ' + name)

    result = API['prepare'](bundle, bundle_sha, build, sha(build), output)
    good('native-parser-accepts-generated-records-with-unicode-and-spaces', lambda: require(result['prepared'], 'Prepared records'))
    expected = result['reviewSha256']
    good('repeat-readonly-native-inspection', lambda: API['verify'](output, expected))
    before = {p.name: sha(p) for p in output.iterdir()}
    rejects('existing-output-preserved', lambda: API['prepare'](bundle, bundle_sha, build, sha(build), output))
    require(before == {p.name: sha(p) for p in output.iterdir()}, 'Existing records changed')
    for name, bundle_hash, build_hash in [('wrong-bundle-hash', '0' * 64, sha(build)), ('wrong-build-hash', bundle_sha, '0' * 64)]:
        destination = output.with_name(identity + '-' + name)
        rejects(name, lambda: API['prepare'](bundle, bundle_hash, build, build_hash, destination))
        require(not destination.exists(), 'Refusal must precede review output creation')
    rejects('wrong-review-hash', lambda: API['verify'](output, '0' * 64))
    checker = build.parent / 'Release/sl3_driver_configuration_tests.exe'
    entry = output / 'sl3-asio.conf'
    original = entry.read_bytes()
    for name, data in [('native-rejects-extra-simulation-selector', original + b'kind=simulated\n'),
                       ('native-rejects-incomplete-record', original[:-1]),
                       ('native-rejects-excessive-diagnostic-lifetime', original.replace(b'lifetime_ms=600000', b'lifetime_ms=600001')),
                       ('native-rejects-input-hash-mismatch', original.replace(b'input_sha256=', b'input_sha256=0', 1))]:
        entry.write_bytes(data)
        child = subprocess.run([str(checker), '--inspect-activation', str(entry)], capture_output=True, timeout=15,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        require(child.returncode == 1, name)
        cases.append({'name': name, 'passed': True})
        rejects(name + '-review-refusal', lambda: API['verify'](output, expected))
    entry.write_bytes(original)
    moved = output.with_name(identity + '-moved')
    shutil.copytree(output, moved)
    rejects('copied-location-is-not-silently-rebound', lambda: API['verify'](moved, expected))
    extra = output / 'unexpected.txt'
    extra.write_text('unexpected', encoding='utf-8')
    rejects('unexpected-inventory', lambda: API['verify'](output, expected))
    extra.unlink()
    good('restored-records-pass-native-recheck', lambda: API['verify'](output, expected))
    require(not installation.exists() and not pointer.parent.exists(), 'No planned installation or session pointer created')
    report = {'schema': 'sl3.activation-configuration-review-tests.v1', 'passed': True, 'cases': cases,
              'bundle': str(bundle), 'bundleSha256': bundle_sha, 'output': str(output), 'reviewSha256': expected,
              'buildManifestSha256': sha(build), 'nativeInspectorSha256': sha(checker),
              'sourceSha256': {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in
                              (Path(__file__), ROOT / 'scripts/prepare-asio-activation-config.py')},
              'installed': False, 'deviceAccess': False, 'controllerLaunched': False, 'seratoLaunched': False}
    report_path = ROOT / 'tests/results/local' / ('activation-configuration-review-' + identity + '.json')
    report_path.write_bytes(BASE['encoded'](report))
    print(json.dumps({'passed': True, 'cases': len(cases), 'report': str(report_path), 'output': str(output)}, indent=2))


if __name__ == '__main__':
    main()
