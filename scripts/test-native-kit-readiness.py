"""Check native readiness and preservation of owned residue fixtures; never Start."""
import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def exercise(kit, expected, application):
    test_root = ROOT / 'artifacts/build/kit-readiness-tests'
    test_root.mkdir(exist_ok=True)
    cases = []
    with tempfile.TemporaryDirectory(prefix='Readiness 会话 spaces ', dir=test_root) as temporary:
        copied = Path(temporary) / 'release'
        shutil.copytree(kit, copied)
        launcher = copied / 'SL3_Rebuild_Development_x64.exe'
        arguments = [str(launcher), '--check-kit', '--kit-manifest', str(copied / 'kit-manifest.json'),
                     '--expected-kit-manifest-sha256', expected, '--app', str(application)]
        environment = os.environ.copy(); environment['PATH'] = ''

        def call(arguments):
            return subprocess.run(arguments, cwd=copied, env=environment, capture_output=True, text=True,
                                  encoding='utf-8', timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)

        result = call(arguments)
        if result.returncode not in (0, 3):
            raise AssertionError(f'Native readiness: {result.returncode}: {result.stdout} {result.stderr}')
        observed = json.loads(result.stdout)
        assert observed['schema'] == 'sl3.session-readiness.v1'
        assert observed['readyForAttempt'] == (result.returncode == 0)
        assert observed['deviceOpened'] is False and observed['packageBinaryLoaded'] is False
        assert observed['elevationRequested'] is False and observed['filesWritten'] is False
        assert {row['id'] for row in observed['checks']} == {'platform', 'application', 'filter', 'device', 'state', 'dependencies'}
        assert not (copied / 'analysis').exists()
        cases.append({'name': 'native-readiness-relocated-empty-path-no-session-state', 'passed': True,
                      'observedReadyForAttempt': observed['readyForAttempt'], 'exitCode': result.returncode})
        source = copied / 'scripts/inspect-sl3-session-readiness.py'
        original = source.read_bytes()
        try:
            source.write_bytes(original + b'\nraise RuntimeError("must not execute")\n')
            rejected = call(arguments)
            assert rejected.returncode == 1 and not rejected.stdout
            assert 'Reviewed launcher input differs: inspect-sl3-session-readiness.py' in rejected.stderr
            assert not (copied / 'analysis').exists()
            cases.append({'name': 'changed-readiness-code-refused-before-python', 'passed': True})
        finally:
            source.write_bytes(original)
        incomplete = call([str(launcher), '--check-kit'])
        assert incomplete.returncode == 2 and not incomplete.stdout and not (copied / 'analysis').exists()
        cases.append({'name': 'incomplete-check-context-refused', 'passed': True})
        # Exercise a real file-residue query in an owned temporary directory,
        # without creating global pointers, registration or a fake installation.
        api = runpy.run_path(str(ROOT / 'scripts/inspect-sl3-session-readiness.py'))
        pointer = Path(temporary) / 'owned-pointer.txt'
        pointer.write_bytes(b'owned fixture; never a global session pointer')
        state = api['residue'](Path(temporary) / 'absent-installation', pointer, application)
        assert 'sessionPointer' in state['occupiedPaths'] and pointer.read_bytes().startswith(b'owned fixture')
        assert api['classify']('state', state)[0] is False
        cases.append({'name': 'existing-pointer-fixture-preserved-and-blocked', 'passed': True})
        return {'schema': 'sl3.native-kit-readiness-tests.v1', 'cases': cases, 'actualHostObservation': observed,
                'kitManifestSha256': expected, 'globalPathEmpty': True, 'spacesAndUnicodeInPath': True,
                'persistentSessionStateCreated': False, 'packageBinaryLoaded': False, 'deviceOpened': False,
                'driverChanged': False, 'globalPointerWritten': False, 'elevationRequested': False,
                'startupAttempted': False, 'audioStarted': False, 'physicalAudioValidated': False}


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
