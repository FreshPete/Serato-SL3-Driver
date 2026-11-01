"""Actual controls-probe executables: simulated positives, native safe negatives."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def execute(args, expected):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=40)
    require(result.returncode == expected, f'Unexpected exit {result.returncode}, expected {expected}: {result.stderr}')
    return result


def main():
    require(len(sys.argv) == 5, 'Four reviewed executable paths required')
    native, simulated, fixture, worker = [Path(a).resolve() for a in sys.argv[1:]]
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('controls_validation', root/'scripts/validate-controls-host-probe.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    for exe, kind in ((native, False), (simulated, True)):
        plan = json.loads(execute([exe, '--plan'], 0).stdout)
        require(plan['device_access'] is False and plan['simulated'] is kind and plan['controls_inspection'] == {
            'mode': '--controls', 'audio': False, 'maximum_reads': 4}, 'Wrong controls plan')
    parent = root/'tests/results/local'
    parent.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='controls-probe-software-', dir=parent))
    helper = folder/'asserted-absent-helper.dll'
    require(not helper.exists(), 'Native negative helper must not exist')
    sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    options = ['--worker', fixture, '--worker-sha256', sha, '--helper', helper, '--output']
    invalid = folder/'invalid'
    for exe in (native, simulated):
        for tail in (['--intervals', '8'], ['--intervals', '64'], ['--fixture-mode', 'unknown']):
            execute([exe, '--controls', *options, invalid, *tail], 2)
        execute([exe, '--controls', '--worker', 'relative.exe', *options[2:], invalid], 2)
        require(not invalid.exists(), 'Rejected CLI created evidence')
    execute([native, '--controls', *options, invalid, '--fixture-mode', 'normal'], 2)
    output = folder/'simulation'
    execute([simulated, '--controls', *options, output], 0)
    result = validator.probe(output, sha, True)
    require(result['valid'] is True and result['receivedFrames'] == 4 and result['rawControls'] == list(range(17, 39)), 'Simulated controls IPC/record failed')
    before = hashlib.sha256((output/'probe.json').read_bytes()).hexdigest()
    execute([simulated, '--controls', *options, output], 1)
    require(hashlib.sha256((output/'probe.json').read_bytes()).hexdigest() == before, 'Existing evidence was overwritten')
    for mode in ('fail-controls', 'bad-controls', 'hang-controls', 'invalid-clock'):
        failed = folder/mode
        execute([simulated, '--controls', *options, failed, '--fixture-mode', mode], 1)
        record = json.loads((failed/'probe.json').read_text())
        require(record['successful'] is False and record['sample_present'] is False and record['raw_controls'] is None
                and record['received_frames'] is None and record['inputs'] is None and record['audio_start_attempts'] == 0,
                'Failed inspection invented a sample or started audio')
        require(record['finished'] is (mode != 'hang-controls'), 'Failed query cleanup certainty was lost')
        if mode == 'hang-controls':
            require(record['final']['io_retired'] is False and record['final']['device_released'] is False,
                    'Old idle cleanup flags reused after stalled inspection')
    wrong = folder/'wrong-kind'
    for mode in ('hang-device-close', 'fail-device-close'):
        failed = folder/mode
        execute([simulated, '--controls', *options, failed, '--fixture-mode', mode], 1)
        record = json.loads((failed/'probe.json').read_text())
        require(record['successful'] is False and record['finished'] is False and record['sample_present'] is True
                and record['received_frames'] == 4 and record['raw_controls'] == list(range(17, 39))
                and record['final']['device_released'] is False and record['error'] != '',
                'An observed table was lost or promoted to successful final cleanup')
    execute([native, '--controls', *options, wrong], 1)
    record = json.loads((wrong/'probe.json').read_text())
    require(record['acquisition_verified'] is False and record['query_attempts'] == 0 and record['sample_present'] is False,
            'Simulated worker impersonated native controls')
    absent = folder/'native-absent-helper'
    execute([native, '--controls', '--worker', worker, '--worker-sha256', hashlib.sha256(worker.read_bytes()).hexdigest(),
             '--helper', helper, '--output', absent], 1)
    record = json.loads((absent/'probe.json').read_text())
    require(record['successful'] is False and record['acquisition_verified'] is False and record['query_attempts'] == 0
            and record['finished'] is True and record['final']['device_released'] is True and record['final']['worker_exited'] is True,
            'Native negative did not reject absent helper before hardware')
    print('Controls probe plan/CLI, simulated sample/failure/stall, no overwrite, kind and native absent-helper checks passed; no physical USB')


if __name__ == '__main__':
    main()
