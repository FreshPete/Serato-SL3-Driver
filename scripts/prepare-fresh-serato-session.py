"""Prepare a fresh session from a hash-reviewed complete plan; default is read-only."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise ValueError(message)


def module(name):
    return runpy.run_path(str(ROOT / 'scripts' / name))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_new(path, record):
    raw = (json.dumps(record, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('ascii')
    with path.open('xb') as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def fresh_record(record, directory):
    require(record['captureOutput'] is False, 'Fresh interactive sessions require recording disabled')
    copied = json.loads(json.dumps(record))
    copied['sessionDirectory'] = str(directory)
    return copied


def prepare(reviewed, expected, prepare=False, powershell=None):
    api = module('prepare-serato-session-plan.py')
    saved = api['verify'](Path(reviewed).absolute(), expected)
    capsule_api = module('serato-session-capsule.py')
    record, _, _ = capsule_api['verify'](Path(saved['capsule']['path']), saved['capsule']['sha256'])
    require(record['captureOutput'] is False, 'Fresh interactive sessions require recording disabled')
    if powershell is not None:
        powershell = Path(powershell).absolute()
        require(powershell.is_dir() and ';' not in str(powershell), 'Supported PowerShell directory required')
    if not prepare:
        return {'planOnly': True, 'reviewedInputsVerified': True, 'filesWritten': False,
                'applicationStarted': False, 'deviceAccess': False, 'registryWritten': False}
    parent = ROOT / 'analysis'
    require(parent.is_dir() and not parent.is_symlink() and
            not getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400,
            'Ordinary existing analysis directory required')
    directory = parent / ('sl3-session-capsule-fresh-' + uuid.uuid4().hex)
    # Atomic directory creation claims this session. Never reuse a directory or
    # delete partial results after a later failure; their state remains visible.
    directory.mkdir()
    write_new(directory / 'preparation-started.json', {
        'schema': 'sl3.fresh-session-preparation-started.v1', 'reviewedPlanSha256': expected})
    capsule = directory / 'session-capsule.json'
    capsule_sha = write_new(capsule, fresh_record(record, directory))
    constructed = api['construct'](capsule, capsule_sha, saved['preparedShim']['path'], saved['preparedShim']['sha256'],
                                   saved['archiveSource']['path'], saved['installerResource']['path'],
                                   saved['launcher']['path'], saved['fridaDirectory'], saved['asioPrivateTrace'])
    plan = directory / 'session-plan.json'
    plan_sha = write_new(plan, constructed)
    api['verify'](plan, plan_sha)
    result = {'schema': 'sl3.fresh-session-preparation.v1', 'prepared': True,
              'sessionDirectory': str(directory), 'capsule': str(capsule), 'capsuleSha256': capsule_sha,
              'sessionPlan': str(plan), 'sessionPlanSha256': plan_sha,
              'launcherRecompiled': False, 'installerResourceRepacked': False,
              'captureOutput': False, 'asioPrivateTrace': saved['asioPrivateTrace'], 'applicationStarted': False, 'deviceAccess': False,
              'registryWritten': False, 'liveValidated': False}
    if powershell is not None:
        result['startArguments'] = [saved['launcher']['path'], '--start-session', '--session-plan', str(plan),
                                    '--expected-session-plan-sha256', plan_sha,
                                    '--powershell-directory', str(powershell)]
        result['planArguments'] = [*result['startArguments']]
        result['planArguments'][1] = '--plan-session'
        result['stopArguments'] = [*result['startArguments']]
        result['stopArguments'][1] = '--stop-session'
        result['statusArguments'] = [*result['startArguments']]
        result['statusArguments'][1] = '--status-session'
        result['recoveryCheckArguments'] = [*result['startArguments']]
        result['recoveryCheckArguments'][1] = '--check-recovery'
    write_new(directory / 'preparation-complete.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-plan', type=Path, required=True)
    parser.add_argument('--expected-session-plan-sha256', required=True)
    parser.add_argument('--powershell-directory', type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--start', action='store_true')
    args = parser.parse_args()
    require(not args.start or (args.prepare and args.powershell_directory is not None),
            'Starting requires explicit preparation and PowerShell selection')
    result = prepare(args.session_plan, args.expected_session_plan_sha256, args.prepare, args.powershell_directory)
    print(json.dumps(result, indent=2), flush=True)
    if args.start:
        # Use a fixed argument vector and the selected launcher's own complete
        # verification. The preparation receipt records no hardware validation.
        raise SystemExit(subprocess.run(result['startArguments'], creationflags=subprocess.CREATE_NO_WINDOW).returncode)
