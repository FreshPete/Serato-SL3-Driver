"""Actual timer CLI failure checks using only a nonexistent helper; no DLL/device opened."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / 'artifacts/build/timer-diagnostic/Release/sl3_usbdk.exe'


def require(value, message):
    if not value:
        raise ValueError(message)


def main():
    rows = []
    with tempfile.TemporaryDirectory(prefix='sl3-timer-cli-') as directory:
        folder = Path(directory)
        helper = folder / 'nonexistent-helper.dll'
        require(not helper.exists(), 'Helper must not exist')
        common = ['--timer-query', '--challenge', '0123456789abcdef']
        cases = [
            ('missing challenge', ['--timer-query'], 'Conflicting, missing or unused arguments'),
            ('malformed challenge', ['--timer-query', '--challenge', '0123456789abcdeg'], 'Invalid timer challenge digit'),
            ('duplicate challenge', common + ['--challenge', '0123456789abcdef'], 'Usage:'),
            ('mode conflict', common + ['--capture'], 'Conflicting, missing or unused arguments'),
            ('unused startup log', common + ['--startup-log', str(folder / 'startup.json')], 'Startup journal is only valid'),
        ]
        for number, (name, args, error) in enumerate(cases):
            output = folder / str(number)
            run = subprocess.run([str(EXE), *args, '--helper', str(helper), '--output', str(output)],
                                 capture_output=True, text=True, timeout=5)
            require(run.returncode == 2 and error in run.stderr and not output.exists(), f'Failed guard: {name}')
            rows.append({'case': name, 'exitCode': run.returncode, 'outputCreated': False})
        output = folder / 'missing-explicit-helper'
        run = subprocess.run([str(EXE), *common, '--output', str(output)], capture_output=True, text=True, timeout=5)
        require(run.returncode == 2 and 'explicit pinned helper' in run.stderr and not output.exists(), 'Missing helper guard')
        rows.append({'case': 'missing explicit helper', 'exitCode': run.returncode, 'outputCreated': False})
        output = folder / 'pre-load-failure'
        run = subprocess.run([str(EXE), *common, '--helper', str(helper), '--output', str(output)],
                             capture_output=True, text=True, timeout=5)
        record_path = output / 'timer.json'
        record = json.loads(record_path.read_text())
        require(run.returncode == 1 and record['phase'] == 'failed before timer diagnostic'
                and record['redirect_attempted'] is False and record['write_attempts'] == record['read_attempts'] == 0
                and record['response_parsed'] is False and record['response_verified'] is False
                and record['audio_submissions'] == 0 and record['error'], 'Pre-load failure evidence')
        rows.append({'case': 'nonexistent helper failure', 'exitCode': run.returncode, 'record': record})
        before = record_path.read_bytes()
        run = subprocess.run([str(EXE), *common, '--helper', str(helper), '--output', str(output)],
                             capture_output=True, text=True, timeout=5)
        require(run.returncode == 1 and 'fresh output directory' in run.stderr and record_path.read_bytes() == before,
                'Existing output was not preserved')
        rows.append({'case': 'existing output refusal', 'exitCode': run.returncode, 'recordPreserved': True})
    result = {'scope': __doc__, 'passed': len(rows), 'workerSha256': hashlib.sha256(EXE.read_bytes()).hexdigest(),
              'scriptSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'cases': rows,
              'physicalTimerQueryTested': False}
    destination = ROOT / 'analysis/driver-timer-cli-20261101.json'
    require(not destination.exists(), 'Expected a fresh result')
    destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'{len(rows)} actual CLI guards passed; no helper DLL or SL3 opened')


if __name__ == '__main__':
    main()
