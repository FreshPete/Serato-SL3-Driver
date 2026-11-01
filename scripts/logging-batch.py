"""Prepare/validate a fixed logging-only batch; execution requires an elevated token."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('prepare-hub-image-source.ps1', 'validate-hub-image-source.ps1', 'inspect-process.psm1',
           'inspect-image-source-session.py', 'hub-image-source-action.ps1', 'test-hub-image-source.py',
           'inspect-loaded-hub.py', 'logging-batch.py', 'start-logging-batch.ps1')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    require(path.stat().st_size <= 131072, 'Oversized batch record')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def source_runner():
    spec = importlib.util.spec_from_file_location('source_runner', ROOT/'scripts/test-hub-image-source.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def runtime():
    powershell = shutil.which('pwsh')
    require(powershell is not None, 'PowerShell 7 is required')
    python = Path(sys.executable).resolve()
    powershell = Path(powershell).resolve()
    return {'scripts': {name: sha(ROOT/'scripts'/name) for name in SOURCES},
            'python': str(python), 'pythonSha256': sha(python),
            'powershell': str(powershell), 'powershellSha256': sha(powershell)}


def job_plan(runner, preparation, context, policy):
    require(policy in ('configured','observed-rechecked'), 'Unknown native identity policy')
    return runner.plan(preparation, context) if policy == 'configured' else runner.plan(preparation, context, policy)


def prepare(directory, durations, native_identity_policy='configured'):
    require(native_identity_policy in ('configured','observed-rechecked'), 'Unknown native identity policy')
    directory = directory.resolve()
    require(directory.parent == (ROOT/'analysis').resolve() and not directory.exists()
            and re.fullmatch(r'logging-batch-[a-zA-Z0-9-]{1,64}', directory.name), 'Expected a fresh direct analysis/logging-batch-* folder')
    require(1 <= len(durations) <= 3 and all(type(d) is int and 1 <= d <= 60 for d in durations),
            'Expected one to three durations of 1..60 seconds')
    pinned = runtime()
    directory.mkdir()
    runner = source_runner()
    jobs = []
    for number, duration in enumerate(durations, 1):
        preparation = directory/f'preparation-{number}.json'
        context = ROOT/'tests/results/local'/f'{directory.name}-{number}'
        subprocess.run([pinned['powershell'], '-NoProfile', '-File', str(ROOT/'scripts/prepare-hub-image-source.ps1'),
                        '-DurationSeconds', str(duration), '-Output', str(preparation)],
                       check=True, capture_output=True, text=True, timeout=20)
        jobs.append(job_plan(runner, preparation, context, native_identity_policy))
    result = {'schema': 'sl3.logging-batch.v1', 'batchDirectory': str(directory), 'runtime': pinned,
              'scope': 'Fixed source-only diagnostics; no USB/audio, driver, security or firmware operations',
              'administratorApprovalsExpectedAtMost': 1, 'stopOnFailure': True, 'deviceAccess': False,
              'nativeIdentityPolicy': native_identity_policy, 'jobs': jobs, 'sourceStarted': False, 'readinessAdmission': False}
    write_new(directory/'batch.json', result)
    return result


def validate(plan_path):
    plan_path = plan_path.resolve()
    require(plan_path.name == 'batch.json' and plan_path.parent.parent == (ROOT/'analysis').resolve()
            and re.fullmatch(r'logging-batch-[a-zA-Z0-9-]{1,64}', plan_path.parent.name), 'Unexpected batch location')
    batch = read(plan_path)
    require(batch['schema'] == 'sl3.logging-batch.v1' and batch['batchDirectory'] == str(plan_path.parent)
            and batch['stopOnFailure'] is True and batch['deviceAccess'] is False
            and batch['sourceStarted'] is False and batch['readinessAdmission'] is False,
            'Unexpected batch role or policy')
    require(batch['runtime'] == runtime(), 'Reviewed runtime changed; prepare a new batch')
    require(isinstance(batch['jobs'], list) and 1 <= len(batch['jobs']) <= 3, 'Invalid batch length')
    require(not (plan_path.parent/'execution-started.json').exists(), 'Batch execution was already attempted')
    runner = source_runner()
    policy = batch.get('nativeIdentityPolicy', 'configured')
    for number, job in enumerate(batch['jobs'], 1):
        preparation = plan_path.parent/f'preparation-{number}.json'
        context = ROOT/'tests/results/local'/f'{plan_path.parent.name}-{number}'
        require(job == job_plan(runner, preparation, context, policy), 'Job differs from its fixed reviewed source plan')
    return batch


def execute(plan_path, expected_sha):
    require(sha(plan_path) == expected_sha, 'Batch changed after administrator launch')
    batch = validate(plan_path)
    runner = source_runner()
    token = runner.own_token()
    require(token['queried'] is True and token['elevated'] is True,
            'Execution requires an already elevated process; this function never prompts')
    directory = plan_path.resolve().parent
    result = {'schema': 'sl3.logging-batch-result.v1', 'planSha256': expected_sha, 'producerToken': token,
              'startedUtc': datetime.now(timezone.utc).isoformat(), 'successful': False, 'jobs': [],
              'error': None, 'attemptedJobs': 0, 'remainingJobsSkipped': len(batch['jobs']), 'readinessAdmission': False}
    write_new(directory/'execution-started.json', {'startedUtc': result['startedUtc'], 'planSha256': expected_sha})
    try:
        for number, job in enumerate(batch['jobs'], 1):
            require(batch['runtime'] == runtime(), 'Reviewed runtime changed between jobs')
            require(job == job_plan(runner, Path(job['preparation']), Path(job['contextDirectory']),
                                    batch.get('nativeIdentityPolicy','configured')), 'Source plan changed before execution')
            result['attemptedJobs'] = number
            result['remainingJobsSkipped'] = len(batch['jobs'])-number
            result['lastAttemptedContextDirectory'] = job['contextDirectory']
            observed = runner.run(job)
            row = {'number': number, 'contextDirectory': job['contextDirectory'], 'successful': observed['successful'],
                   'sourceRunSha256': sha(Path(job['contextDirectory'])/'run.json'),
                   'error': observed.get('error'), 'cleanupError': observed.get('cleanupError')}
            result['jobs'].append(row)
            if observed['successful'] is not True:
                result['error'] = 'Source diagnostic failed; remaining jobs were not started'
                break
        result['successful'] = result['error'] is None and result['remainingJobsSkipped'] == 0
    except Exception as failure:
        result['error'] = str(failure)
    finally:
        result['completedUtc'] = datetime.now(timezone.utc).isoformat()
        write_new(directory/'batch-result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', type=Path)
    modes.add_argument('--plan', type=Path)
    parser.add_argument('--durations', nargs='+', type=int, default=[5])
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--expected-sha256')
    parser.add_argument('--native-identity-policy', choices=('configured','observed-rechecked'), default='configured')
    args = parser.parse_args()
    require(not args.execute or (args.plan is not None and args.expected_sha256 is not None), 'Execution needs a frozen plan hash')
    if args.prepare:
        result = prepare(args.prepare, args.durations, args.native_identity_policy)
    elif args.execute:
        result = execute(args.plan, args.expected_sha256)
    else:
        result = validate(args.plan)
    print(json.dumps(result, indent=2))
    return 0 if not args.execute or result['successful'] else 1


if __name__ == '__main__':
    sys.exit(main())
