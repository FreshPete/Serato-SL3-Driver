"""Exercise native kit Plan/preparation and pre-execution refusals; never Start."""
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
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def exercise(kit, expected, application):
    test_root = ROOT / 'artifacts/build/native-kit-entry-tests'
    test_root.mkdir(exist_ok=True)
    cases = []
    with tempfile.TemporaryDirectory(prefix='Native kit 会话 spaces ', dir=test_root) as temporary:
        moved = Path(temporary) / 'release'
        shutil.copytree(kit, moved)
        launcher = moved / 'SL3_Rebuild_Development_x64.exe'
        manifest = moved / 'kit-manifest.json'
        assert sha(manifest) == expected and not (moved / 'analysis').exists()
        environment = os.environ.copy()
        environment['PATH'] = ''
        command = [str(launcher), '--plan-kit', '--kit-manifest', str(manifest),
                   '--expected-kit-manifest-sha256', expected, '--app', str(application)]

        def call(name, arguments, expected_code=0, message=None, pre_execution=False):
            result = subprocess.run(arguments, cwd=moved, env=environment, capture_output=True,
                                    text=True, encoding='utf-8', timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode != expected_code:
                raise AssertionError(f'{name}: {result.returncode}: {result.stdout} {result.stderr}')
            if message is not None:
                assert message in result.stderr, (name, result.stderr)
            if pre_execution:
                assert not result.stdout
            cases.append({'name': name, 'passed': True, 'exitCode': result.returncode})
            return result

        first = json.loads(call('native-kit-plan-relocated-empty-path', command).stdout)
        assert first['filesWritten'] is False and not (moved / 'analysis').exists()
        prepare = [*command]
        prepare[1] = '--prepare-kit'
        prepared = json.loads(call('native-kit-complete-offline-preparation', prepare).stdout)
        assert prepared['projectRoot'] == str(moved) and prepared['applicationStarted'] is False
        assert prepared['nativePackageRebound'] is True and prepared['nativeBinariesUnchanged'] is True
        assert prepared['originBundleSha256'] != prepared['reboundBundleSha256']
        assert prepared['stopArguments'][1] == '--stop-session'
        assert prepared['stopArguments'][2:] == prepared['planArguments'][2:]
        checked = call('native-prepared-kit-complete-session-plan', prepared['planArguments'])
        assert 'Complete session plan passed; no application, broker or elevation started' in checked.stdout
        status = json.loads(call('native-prepared-session-status', prepared['statusArguments']).stdout)
        assert status['schema'] == 'sl3.session-status.v1' and status['phase'] == 'prepared'
        assert status['originalSetupCurrentlyClean'] is True and status['completionEvidenceConsistent'] is False
        assert status['repairAttempted'] is False and status['deviceOpened'] is False
        assert json.loads(Path(prepared['sessionPlan']).read_bytes())['asioPrivateTrace'] is False
        status_source = moved / 'scripts/inspect-serato-session-status.py'
        status_original = status_source.read_bytes()
        try:
            status_source.write_bytes(status_original + b'changed')
            call('changed-status-helper-refused-before-python', prepared['statusArguments'], 1,
                 'Reviewed launcher input differs: inspect-serato-session-status.py', True)
        finally:
            status_source.write_bytes(status_original)
        call('native-kit-plan-after-preparation', command)
        before = {path.name for path in (moved / 'analysis').iterdir()}
        wrong = [*prepare]
        wrong[5] = '0' * 64
        call('wrong-kit-identity-refused-before-python', wrong, 1, 'Reviewed launcher input differs: kit-manifest.json', True)
        for name, label in (
            ('scripts/prepare-portable-serato-kit.py', 'changed-kit-preparer'),
            ('docs/evidence/serato-legacy-sl3-descriptors.json', 'changed-specification-evidence'),
            ('runtime/python/python315.zip', 'changed-private-standard-library'),
            ('runtime/powershell/pwsh.runtimeconfig.json', 'changed-powershell-runtime'),
        ):
            path = moved / name
            original = path.read_bytes()
            try:
                path.write_bytes(original + b'changed')
                call(label + '-refused-before-python', prepare, 1,
                     'Reviewed launcher input differs: ' + path.name, True)
            finally:
                path.write_bytes(original)
        original_manifest = manifest.read_bytes()
        try:
            row = json.loads(original_manifest)
            row['launcherSha256'] = '0' * 64
            manifest.write_text(json.dumps(row), encoding='utf-8')
            wrong_release = [*prepare]
            wrong_release[5] = sha(manifest)
            call('foreign-launcher-release-refused-before-python', wrong_release, 1,
                 'Reviewed launcher input differs: SL3_Rebuild_Development_x64.exe', True)
        finally:
            manifest.write_bytes(original_manifest)
        # No need to copy the large original image: a bounded, differently
        # hashed local file must be rejected before any helper or PE load.
        other = moved / 'analysis/Serato DJ Pro.exe'
        try:
            other.write_bytes(b'not a reviewed executable; never executed')
            wrong_application = [*prepare]
            wrong_application[7] = str(other)
            call('unreviewed-application-refused-before-python', wrong_application, 1,
                 'Reviewed launcher input differs: Serato DJ Pro.exe', True)
        finally:
            other.unlink()
        unsupported_path = [*prepare]
        unsupported_path[3] = str(Path(temporary) / 'semicolon; unsupported/kit-manifest.json')
        call('semicolon-kit-path-refused-before-python', unsupported_path, 1,
             'Kit directory cannot contain a semicolon', True)
        call('incomplete-start-context-refused', [str(launcher), '--start-kit'], 2, pre_execution=True)
        assert {path.name for path in (moved / 'analysis').iterdir()} == before
        assert not list((moved / 'analysis').glob('*/session-run.lock'))
        assert not list((moved / 'analysis').glob('*/install-receipt.json'))
        return {'schema': 'sl3.native-kit-entry-tests.v1', 'cases': cases, 'kitManifestSha256': expected,
                'launcherSha256': sha(launcher), 'generatedSessionPlanSha256': prepared['sessionPlanSha256'],
                'globalPathEmpty': True, 'spacesAndUnicodeInKitPath': True,
                'onlyPlanPreparationOrRefusalInvocations': True, 'liveStartAttempted': False,
                'applicationStarted': False, 'brokerStarted': False, 'elevationRequested': False,
                'registryWritten': False, 'deviceAccess': False, 'liveValidated': False}


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
