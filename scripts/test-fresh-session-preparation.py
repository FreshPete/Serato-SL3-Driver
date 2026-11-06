"""Exercise fresh preparation and complete Plans only; never start Serato."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def exercise(launcher, powershell, template):
    original_hash = sha(template)
    original = json.loads(template.read_bytes())
    python = original['python']['path']
    cases = []
    generated = []

    def fresh_directories():
        return set((ROOT / 'analysis').glob('sl3-session-capsule-fresh-*'))

    def call(name, arguments, expected=0):
        result = subprocess.run(arguments, capture_output=True, text=True, encoding='utf-8',
                                timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode != expected:
            raise AssertionError(f'{name}: {result.returncode}: {result.stdout} {result.stderr}')
        cases.append({'name': name, 'passed': True, 'exitCode': result.returncode})
        return result

    before = fresh_directories()
    direct = [python, '-I', '-B', str(ROOT / 'scripts/prepare-fresh-serato-session.py'),
              '--session-plan', str(template), '--expected-session-plan-sha256', original_hash]
    default = json.loads(call('default-read-only-preparation-plan', direct).stdout)
    assert default['filesWritten'] is False and fresh_directories() == before
    arguments = [str(launcher), '--prepare-session', '--session-plan', str(template),
                 '--expected-session-plan-sha256', original_hash, '--powershell-directory', str(powershell)]
    for number in (1, 2):
        result = json.loads(call(f'fresh-preparation-{number}', arguments).stdout)
        directory = Path(result['sessionDirectory'])
        assert directory.parent == ROOT / 'analysis' and directory not in before
        assert result['captureOutput'] is False and result['launcherRecompiled'] is False
        assert result['installerResourceRepacked'] is False and result['applicationStarted'] is False
        assert result['recoveryArguments'][1]=='--recover-session'
        assert result['recoveryArguments'][2:]==result['planArguments'][2:]
        assert {path.name for path in directory.iterdir()} == {
            'preparation-started.json', 'preparation-complete.json', 'session-capsule.json', 'session-plan.json'}
        plan = json.loads(Path(result['sessionPlan']).read_bytes())
        capsule = json.loads(Path(result['capsule']).read_bytes())
        assert sha(Path(result['sessionPlan'])) == result['sessionPlanSha256']
        assert capsule['sessionDirectory'] == str(directory)
        assert plan['launcher'] == original['launcher'] and plan['installerResource'] == original['installerResource']
        assert plan['asioPrivateTrace'] is original['asioPrivateTrace']
        assert plan['preparedShim']==original['preparedShim']
        assert result['asioPrivateTrace'] is original['asioPrivateTrace']
        assert plan['nativeBundle'] == original['nativeBundle'] and plan['hostOutput'] != original['hostOutput']
        assert all(not (directory / name).exists() for name in ('session-run.lock', 'install-receipt.json', 'broker-session'))
        checked = call(f'fresh-complete-wrapper-plan-{number}', result['planArguments'])
        assert 'Complete session plan passed; no application, broker or elevation started' in checked.stdout
        generated.append({'capsuleSha256': result['capsuleSha256'], 'sessionPlanSha256': result['sessionPlanSha256']})
    assert len({item['sessionPlanSha256'] for item in generated}) == 2
    before = fresh_directories()
    wrong = [*arguments]
    wrong[5] = '0' * 64
    refused = call('wrong-reviewed-plan-hash-writes-no-session', wrong, 1)
    assert 'Reviewed launcher input differs:' in refused.stderr and fresh_directories() == before
    with tempfile.TemporaryDirectory(prefix='sl3-session-capsule-preparation-test-', dir=ROOT / 'analysis') as temporary:
        # tempfile's suffix may contain underscores; keep the actual capsule
        # leaf within the production tag grammar instead of weakening it.
        directory = Path(temporary) / 'sl3-session-capsule-preparation-test'
        directory.mkdir()
        bad = directory / 'session-plan.json'
        altered = json.loads(json.dumps(original))
        altered['launcher']['sha256'] = '0' * 64
        bad.write_text(json.dumps(altered), encoding='utf-8')
        wrong_release = [*arguments]
        wrong_release[3] = str(bad)
        wrong_release[5] = sha(bad)
        result = call('other-launcher-release-refused-before-preparation', wrong_release, 1)
        assert 'Reviewed launcher input differs:' in result.stderr and fresh_directories() == before
        source_capsule = json.loads(Path(original['capsule']['path']).read_bytes())
        source_capsule['captureOutput'] = True
        source_capsule['sessionDirectory'] = str(directory)
        capsule = directory / 'session-capsule.json'
        capsule.write_text(json.dumps(source_capsule), encoding='utf-8')
        api = runpy.run_path(str(ROOT / 'scripts/prepare-serato-session-plan.py'))
        recording_plan = api['construct'](capsule, sha(capsule), original['preparedShim']['path'],
                                          original['preparedShim']['sha256'], original['archiveSource']['path'],
                                          original['installerResource']['path'], original['launcher']['path'],
                                          original['fridaDirectory'])
        bad.write_text(json.dumps(recording_plan), encoding='utf-8')
        denied = [python, '-I', '-B', str(ROOT / 'scripts/prepare-fresh-serato-session.py'),
                  '--session-plan', str(bad), '--expected-session-plan-sha256', sha(bad), '--prepare']
        result = call('recording-template-refused-before-session-creation', denied, 1)
        assert 'Fresh interactive sessions require recording disabled' in result.stderr
        assert fresh_directories() == before
    assert sha(template) == original_hash
    return {'schema': 'sl3.fresh-session-preparation-tests.v1', 'cases': cases, 'sessions': generated,
            'sameLauncherAndResourceReused': True, 'preparedSessionsRetainedForReview': True,
            'applicationStarted': False, 'deviceAccess': False, 'registryWritten': False,
            'elevationRequested': False, 'liveValidated': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--powershell', type=Path, required=True)
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = exercise(args.launcher.absolute(), args.powershell.absolute(), args.template.absolute())
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps(result, indent=2))
