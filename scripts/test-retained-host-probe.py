"""Plan/CLI checks, simulated positive lifecycle and native absent-helper negative."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def require(value, message):
    if not value:
        raise ValueError(message)


def execute(args, code):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=50)
    require(result.returncode == code, f'Unexpected exit {result.returncode}: {result.stderr[-1000:]}')
    return result


def main():
    require(len(sys.argv) == 5, 'Native/simulated probe, retained fixture and native worker required')
    native, simulated, fixture, worker = [Path(a).resolve() for a in sys.argv[1:]]
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('retained_validation', root/'scripts/validate-retained-host-probe.py')
    validation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validation)
    for exe, is_simulated in ((native, False), (simulated, True)):
        plan = json.loads(execute([exe, '--plan'], 0).stdout)
        require(plan['device_access'] is False and plan['simulated'] is is_simulated and plan['retained_lifecycle'] == {
            'streams': 2, 'stream_ms': 1000, 'intervals': 8, 'bank_frames': 128}, 'Retained plan differs')
    parent = root/'tests/results/local'
    parent.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='retained-probe-software-', dir=parent))
    helper = folder/'asserted-absent-helper.dll'
    require(not helper.exists(), 'Negative helper must be absent')
    sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    options = ['--worker', fixture, '--worker-sha256', sha, '--helper', helper, '--output']
    invalid = folder/'invalid'
    for tail in (['--intervals', '8'], ['--intervals', '64'], ['--intervals', '8x']):
        execute([native, '--retained-48000', *options, invalid, *tail], 2)
        require(not invalid.exists(), 'Retained mode accepted a variable block shape')
    execute([native, '--retained-96000', *options, invalid], 2)
    execute([native, '--retained-48000', '--worker', 'relative.exe', *options[2:], invalid], 2)
    require(not invalid.exists(), 'Malformed CLI created evidence')
    output = folder/'simulation'
    execute([simulated, '--retained-48000', *options, output], 0)
    result = validation.probe(output, sha, 48000, True)
    require(result['valid'] is True and result['simulated'] is True and len(result['streams']) == 2, 'Simulated retained lifetime failed')
    mismatch = folder/'clock-mismatch'
    execute([simulated, '--retained-44100', *options, mismatch], 1)
    record = json.loads((mismatch/'probe.json').read_text())
    require(record['successful'] is False and record['acquisition_verified'] is True and record['reported_rate_hz'] == 48000
            and record['completed_streams'] == 0 and record['finished'] is True and record['device_released'] is True
            and not list(mismatch.glob('stream-*.json')), 'Expected-rate mismatch started audio or invented an observed rate')
    wrong = folder/'wrong-kind'
    execute([native, '--retained-48000', *options, wrong], 1)
    record = json.loads((wrong/'probe.json').read_text())
    require(record['successful'] is False and record['acquisition_verified'] is False and record['completed_streams'] == 0
            and record['host_failure'] == 2, 'Simulated fixture impersonated native readiness')
    absent = folder/'native-absent-helper'
    execute([native, '--retained-48000', '--worker', worker, '--worker-sha256', hashlib.sha256(worker.read_bytes()).hexdigest(),
             '--helper', helper, '--output', absent], 1)
    record = json.loads((absent/'probe.json').read_text())
    require(record['successful'] is False and record['acquisition_verified'] is False and record['completed_streams'] == 0
            and record['finished'] is True and record['device_released'] is True and record['worker_exited'] is True,
            'Native absent-helper gate did not safely reject before hardware access')
    print('Retained probe plan/CLI, two simulated silent sessions with buffer recreation, clock/kind rejection and native absent-helper passed; no physical USB')


if __name__ == '__main__':
    main()
