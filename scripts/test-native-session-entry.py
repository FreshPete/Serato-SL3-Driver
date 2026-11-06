"""Exercise only the native full-session Plan/refusal entry; never start a session."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def exercise(launcher, powershell, plan_a, plan_b, release):
    cases = []
    identity = sha(launcher)
    source_pins = json.loads(release.read_bytes())['sourcePins']

    def call(name, selected=plan_a, runtime=powershell, expected=0, executable=launcher, digest=None):
        args = [str(executable), '--plan-session', '--session-plan', str(selected),
                '--expected-session-plan-sha256', digest or sha(selected), '--powershell-directory', str(runtime)]
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', timeout=45,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode != expected:
            raise AssertionError(f'{name}: {result.returncode}: {result.stdout} {result.stderr}')
        if expected == 0:
            assert 'Complete session plan passed; no application, broker or elevation started' in result.stdout
            assert '"deviceAccess": false' in result.stdout
        cases.append({'name': name, 'passed': True, 'exitCode': result.returncode})
        return result

    call('complete-plan-private-python-and-powershell')
    call('second-session-same-executable', selected=plan_b)
    call('wrong-plan-hash-refused', digest='0' * 64, expected=1)
    test_root = ROOT / 'artifacts/build/native-session-entry-tests'
    test_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=test_root) as temporary:
        directory = Path(temporary)
        relocated = directory / launcher.name
        shutil.copyfile(launcher, relocated)
        call('executable-relocated', executable=relocated)
        semicolon = directory / 'PowerShell; unsupported'
        result = call('powershell-semicolon-path-refused-clearly', runtime=semicolon, expected=1)
        assert 'PowerShell runtime directory cannot contain a semicolon' in result.stderr
        copied = directory / 'PowerShell spaces dollar$(literal) 会话'
        shutil.copytree(powershell, copied)
        call('powershell-relocated-spaces-unicode-and-dollar-parentheses', runtime=copied)
        for name in ('pwsh.exe', 'pwsh.runtimeconfig.json', 'System.Management.Automation.dll'):
            member = copied / name
            original = member.read_bytes()
            try:
                member.write_bytes(original + b'changed')
                result = call('changed-' + name + '-refused-before-powershell', runtime=copied, expected=1)
                assert 'Reviewed launcher input differs: ' + name in result.stderr
                assert not result.stdout
            finally:
                member.write_bytes(original)
        fixture = directory / 'session-plan.json'
        original_plan = json.loads(plan_a.read_bytes())
        for name, mutate in (
            ('foreign-interpreter', lambda row: row['python'].update(sha256='0' * 64)),
            ('foreign-application', lambda row: row['application'].update(sha256='0' * 64)),
            ('unsupported-schema', lambda row: row.update(schema='unknown')),
        ):
            record = json.loads(json.dumps(original_plan))
            mutate(record)
            fixture.write_text(json.dumps(record), encoding='utf-8')
            result = call(name, selected=fixture, expected=1)
            assert not result.stdout
        copied_sources = directory / 'sources'
        for name in source_pins:
            target = copied_sources / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        wrapper = copied_sources / 'scripts/serato-session.ps1'
        wrapper.write_bytes(wrapper.read_bytes() + b'\nthrow "must never execute changed wrapper"\n')
        record = json.loads(json.dumps(original_plan))
        record['projectRoot'] = str(copied_sources)
        fixture.write_text(json.dumps(record), encoding='utf-8')
        result = call('changed-wrapper-refused-before-powershell', selected=fixture, expected=1)
        assert 'Reviewed launcher input differs: serato-session.ps1' in result.stderr and not result.stdout
    assert sha(launcher) == identity
    return {'schema': 'sl3.native-session-entry-tests.v1', 'launcherSha256': identity, 'cases': cases,
            'onlyPlanOrRefusalInvocations': True, 'applicationStarted': False, 'deviceAccess': False,
            'registrationWritten': False, 'elevationRequested': False, 'liveValidated': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--powershell', type=Path, required=True)
    parser.add_argument('--plan-a', type=Path, required=True)
    parser.add_argument('--plan-b', type=Path, required=True)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = exercise(*(path.absolute() for path in (args.launcher, args.powershell, args.plan_a, args.plan_b, args.release)))
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps(result, indent=2))
