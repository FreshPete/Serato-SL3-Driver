"""Exercise a relocated kit with its own interpreter and no global tools on PATH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def exercise(kit, expected, application):
    test_root = ROOT / 'artifacts/build/kit-relocation-tests'
    test_root.mkdir(exist_ok=True)
    cases = []
    with tempfile.TemporaryDirectory(prefix='Moved kit 会话 spaces ', dir=test_root) as temporary:
        moved = Path(temporary) / 'release'
        shutil.copytree(kit, moved)
        assert not (moved / 'analysis').exists()
        environment = os.environ.copy()
        environment['PATH'] = ''
        python = moved / 'runtime/python/python.exe'
        manifest = moved / 'kit-manifest.json'
        assert sha(manifest) == expected
        command = [str(python), '-I', '-B', str(moved / 'scripts/prepare-portable-serato-kit.py'),
                   '--kit-manifest', str(manifest), '--expected-kit-manifest-sha256', expected]

        def call(name, arguments, expected_code=0, message=None):
            result = subprocess.run(arguments, cwd=moved, env=environment, capture_output=True,
                                    text=True, encoding='utf-8', timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode != expected_code:
                raise AssertionError(f'{name}: {result.returncode}: {result.stdout} {result.stderr}')
            if message is not None:
                assert message in result.stderr
            cases.append({'name': name, 'passed': True, 'exitCode': result.returncode})
            return result

        verified = json.loads(call('relocated-kit-inventory-private-interpreter-empty-path', command).stdout)
        assert verified['kitVerified'] is True and not (moved / 'analysis').exists()
        selected = [*command, '--app', str(application)]
        planned = json.loads(call('relocated-kit-read-only-application-plan', selected).stdout)
        assert planned['filesWritten'] is False and not (moved / 'analysis').exists()
        preparation = json.loads(call('relocated-kit-complete-offline-preparation', [*selected, '--prepare']).stdout)
        assert preparation['projectRoot'] == str(moved) and preparation['applicationStarted'] is False
        assert preparation['nativePackageRebound'] is True and preparation['nativeBinariesUnchanged'] is True
        plan = json.loads(Path(preparation['sessionPlan']).read_bytes())
        assert Path(plan['nativeBundle']['path']) != moved / 'native-package'
        assert plan['nativeBundle']['sha256'] == preparation['reboundBundleSha256'] != preparation['originBundleSha256']
        origin = json.loads((moved / 'native-package/bundle-manifest.json').read_bytes())
        rebound = json.loads((Path(plan['nativeBundle']['path']) / 'bundle-manifest.json').read_bytes())
        for name in ('sl3_asio.dll', 'sl3_broker_controller.exe', 'sl3_usbdk.exe', 'UsbDkHelper.dll'):
            assert rebound['files'][name] == origin['files'][name]
        assert Path(plan['projectRoot']) == moved and Path(plan['python']['path']) == python
        for name in ('capsule', 'preparedShim', 'nativeBundle', 'archiveSource', 'installerResource', 'launcher'):
            assert Path(plan[name]['path']).is_relative_to(moved)
        for name in ('fridaDirectory', 'hostOutput'):
            assert Path(plan[name]).is_relative_to(moved)
        assert Path(plan['application']['path']) == application
        checked = call('relocated-kit-native-complete-session-plan', preparation['planArguments'])
        assert 'Complete session plan passed; no application, broker or elevation started' in checked.stdout
        call('kit-static-inventory-still-valid-after-preparation', command)
        before = {path.name for path in (moved / 'analysis').iterdir()}
        bad = [*command]
        bad[bad.index('--expected-kit-manifest-sha256') + 1] = '0' * 64
        call('wrong-kit-hash-refused', bad, 1, 'Kit manifest differs')
        script = moved / 'scripts/serato-session-installer.py'
        original = script.read_bytes()
        try:
            script.write_bytes(original + b'\nraise RuntimeError("must not execute")\n')
            call('changed-kit-helper-refused-before-preparation', [*selected, '--prepare'], 1, 'Kit file differs:')
            call('native-entry-refuses-changed-kit-helper', preparation['planArguments'], 1,
                 'Reviewed launcher input differs: serato-session-installer.py')
        finally:
            script.write_bytes(original)
        runtime = moved / 'runtime/powershell/pwsh.runtimeconfig.json'
        original = runtime.read_bytes()
        try:
            runtime.write_bytes(original + b'changed')
            call('changed-kit-runtime-refused-before-preparation', [*selected, '--prepare'], 1, 'Kit file differs:')
        finally:
            runtime.write_bytes(original)
        extra = moved / 'unexpected.ps1'
        try:
            extra.write_bytes(b'not executed')
            call('unexpected-static-kit-file-refused', command, 1, 'Unexpected kit files')
        finally:
            extra.unlink()
        assert {path.name for path in (moved / 'analysis').iterdir()} == before
        assert not list((moved / 'analysis').glob('*/session-run.lock'))
        assert not list((moved / 'analysis').glob('*/install-receipt.json'))
        result = {'schema': 'sl3.portable-kit-relocation-tests.v1', 'cases': cases,
                  'kitManifestSha256': expected, 'generatedSessionPlanSha256': preparation['sessionPlanSha256'],
                  'archiveSha256': preparation['archiveSha256'], 'globalPathEmpty': True,
                  'kitInterpreterAndPowerShellUsed': True, 'preparedPathsReboundToMovedKit': True,
                  'spacesAndUnicodeInKitPath': True, 'deploymentScope': preparation['deploymentScope'],
                  'differentWindowsAccountTested': False, 'secondPcTested': False,
                  'applicationStarted': False, 'elevationRequested': False, 'registryWritten': False,
                  'deviceAccess': False, 'liveValidated': False}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit', type=Path, required=True)
    parser.add_argument('--expected-kit-manifest-sha256', required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = exercise(args.kit.absolute(), args.expected_kit_manifest_sha256, args.app.absolute())
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps(result, indent=2))
