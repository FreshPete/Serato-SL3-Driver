"""Check Phase archive generation in a copy containing only public recipe files."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
API = runpy.run_path(str(ROOT / 'scripts/prepare-serato-installed-phase-archive.py'))


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def exercise(application, powershell, expected):
    test_root = ROOT / 'artifacts/build/installed-phase-tests'
    test_root.mkdir(exist_ok=True)
    cases = []
    with tempfile.TemporaryDirectory(prefix='public recipe 会话 ', dir=test_root) as temporary:
        directory = Path(temporary)
        for name in API['SOURCES']:
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        (directory / 'analysis').mkdir()
        original_directory = directory / 'Owner installation spaces 会话'
        original_directory.mkdir()
        copied = original_directory / application.name
        archive = copied.with_name('userio_resources.bin')
        shutil.copyfile(application, copied)
        shutil.copyfile(application.with_name('userio_resources.bin'), archive)
        original_hashes = {path.name: sha(path) for path in (copied, archive)}
        command = [sys.executable, '-I', '-B', str(directory / 'scripts/prepare-serato-installed-phase-archive.py'),
                   '--app', str(copied), '--portable-powershell', str(powershell),
                   '--expected-powershell-manifest-sha256', expected]
        output = directory / 'analysis/sl3-archive-candidate-isolated'

        def call(name, arguments, expected_code=0, message=None):
            result = subprocess.run(arguments, capture_output=True, text=True, encoding='utf-8', timeout=60,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode != expected_code:
                raise AssertionError(f'{name}: {result.returncode}: {result.stdout} {result.stderr}')
            if message is not None:
                assert message in result.stderr
            cases.append({'name': name, 'passed': True, 'exitCode': result.returncode})
            return result

        inspected = json.loads(call('public-recipe-only-read-only-plan', command).stdout)
        assert inspected['persistentFilesWritten'] is False and not list((directory / 'analysis').iterdir())
        result = json.loads(call('public-recipe-only-preparation', [*command, '--prepare', str(output)]).stdout)
        assert sha(output / 'userio_resources.bin') == API['PHASE_SHA'] == result['archiveSha256']
        assert result['schemaValidation']['valid'] is True
        assert result['preservation']['allOriginalEncryptedMembersUnchanged'] is True
        assert result['historicalExecutablesRead'] is False and result['intermediateCandidateArchiveRead'] is False
        assert not (directory / 'artifacts').exists() and not (directory / 'src').exists()
        assert {path.name for path in output.iterdir()} == {'userio_resources.bin', 'archive-preparation.json'}
        call('existing-output-preserved', [*command, '--prepare', str(output)], 1, 'Fresh archive output directory required')
        assert sha(output / 'userio_resources.bin') == API['PHASE_SHA']
        absent = directory / 'analysis/sl3-archive-candidate-must-not-exist'
        negative = [*command, '--prepare', str(absent)]
        for path, message, label in (
            (copied, 'Original Serato 5.0.0.1278 executable required', 'changed-original-executable'),
            (archive, 'Original adjacent Serato archive required', 'changed-original-archive'),
            (directory / API['HISTORY'], 'Reviewed historical specification evidence required', 'changed-public-specification-evidence'),
        ):
            length = path.stat().st_size
            try:
                with path.open('ab') as stream:
                    stream.write(b'changed')
                call(label, negative, 1, message)
                assert not absent.exists()
            finally:
                with path.open('r+b') as stream:
                    stream.truncate(length)
        bad_runtime = [*negative]
        bad_runtime[bad_runtime.index('--expected-powershell-manifest-sha256') + 1] = '0' * 64
        call('changed-runtime-manifest-binding', bad_runtime, 1, 'Runtime manifest differs')
        assert not absent.exists()
        assert {path.name: sha(path) for path in (copied, archive)} == original_hashes
        assert {path.name for path in original_directory.iterdir()} == {application.name, 'userio_resources.bin'}
    return {'schema': 'sl3.installed-phase-archive-tests.v1', 'cases': cases,
            'isolatedRecipeFiles': list(API['SOURCES']), 'historicalExecutablesPresent': False,
            'intermediateCandidatePresent': False, 'nativeBuildPresent': False,
            'privateAnalysisInputsPresent': False, 'archiveSha256': API['PHASE_SHA'],
            'originalInputHashesUnchanged': True, 'applicationExecuted': False,
            'registryWritten': False, 'deviceAccess': False, 'liveValidated': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--portable-powershell', type=Path, required=True)
    parser.add_argument('--expected-powershell-manifest-sha256', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = exercise(args.app.absolute(), args.portable_powershell.absolute(), args.expected_powershell_manifest_sha256)
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps(result, indent=2))
