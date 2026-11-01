"""Exercise plan/rejection modes and an explicitly simulated probe only."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def require(value, message):
    if not value:
        raise ValueError(message)


def execute(arguments, code):
    result = subprocess.run([str(a) for a in arguments], capture_output=True, text=True, timeout=35)
    require(result.returncode == code, f'Unexpected exit {result.returncode}; {result.stdout[-1000:]} {result.stderr[-1000:]}')
    return result


def main():
    require(len(sys.argv) == 4, 'Production probe, simulated probe and session fixture paths required')
    native, simulated, fixture = [Path(p).resolve() for p in sys.argv[1:]]
    for executable, expected_simulation in ((native, False), (simulated, True)):
        for arguments in ([], ['--plan']):
            report = json.loads(execute([executable, *arguments], 0).stdout)
            require(report['plan_only'] is True and report['device_access'] is False
                    and report['simulated'] is expected_simulation and report['output_payload'] == 'zero PCM only', 'Plan contract mismatch')
        for arguments in (['--run'], ['--run', '--plan'], ['--unknown'], ['--plan', '--helper', 'x']):
            execute([executable, *arguments], 2)
    root = Path(__file__).resolve().parents[1]
    parent = root/'tests/results/local'
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='host-probe-software-', dir=parent))
    output = temporary/'simulation'
    helper = Path('C:/deliberately-missing-sl3-session-helper.dll')
    require(not helper.exists(), 'Simulation must use the deliberately absent helper')
    fixture_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
    options = ['--run', '--worker', fixture, '--worker-sha256', fixture_hash, '--helper', helper]
    # Bad hashes/relative paths must reject before creating the output folder.
    execute([native, '--run', '--worker', fixture, '--worker-sha256', 'wrong', '--helper', helper, '--output', output], 2)
    execute([native, '--run', '--worker', 'relative.exe', '--worker-sha256', fixture_hash, '--helper', helper, '--output', output], 2)
    require(not output.exists(), 'Malformed run created evidence before rejection')
    for mode, shape in (('--run', '8'), ('--inspect-reopen', '8'), ('--single-open-48000', '16'), ('--single-open-48000', '8x')):
        execute([native, mode, *options[1:], '--output', output, '--intervals', shape], 2)
        require(not output.exists(), 'Rejected block shape created evidence')
    execute([simulated, *options, '--output', output], 0)
    report = json.loads((output/'probe.json').read_text())
    require(report['simulated'] is True and report['successful'] is True and report['finished'] is True
            and report['callbacks'] > 0 and report['observed_stream_ms'] >= 1000 and report['output_completions'] > 0
            and report['io_retired'] and report['device_released'] and report['audio_thread_retired']
            and report['private_job_empty'] and report['worker_exited'] and report['buffers_disposed']
            and report['callback_contract_failed'] is False and report['forced_termination'] is False
            and report['latency_measured'] is False and report['asio_com_registered'] is False, 'Simulated lifecycle did not retire normally')
    timings = report['callback_timings']
    require(0 < len(timings) <= 2048 and len(timings) + report['timing_records_dropped'] == report['callbacks']
            and report['callback_counter_frequency'] > 0, 'Incomplete bounded callback instrumentation')
    for index, row in enumerate(timings):
        require(len(row) == 3 and row[0] == report['first_frame'] + index * 128
                and row[1] >= 0 and row[2] > 0, 'Malformed timing observation')
        if index:
            require(row[1] >= timings[index-1][1] and row[2] >= timings[index-1][2], 'Timing clock regressed')
    # The production probe must reject this truthful simulated worker identity.
    inspection = temporary/'inspection-only'
    execute([simulated, '--inspect-reopen', *options[1:], '--output', inspection], 0)
    inspected = json.loads((inspection/'probe.json').read_text())
    require(inspected['inspect_only'] is True and inspected['successful'] is True
            and inspected['completed_inspections'] == 2 and inspected['callbacks'] == 0 and inspected['initial_reported_rate_hz'] == 48000
            and inspected['stream_started'] is False and inspected['requested_stream_ms'] == 0
            and inspected['output_submissions'] == 0 and inspected['input_frames'] == 0
            and inspected['buffers_disposed'] is False and inspected['finished'] is True,
            'Inspection-only diagnostic created audio or failed ownership retirement')
    single = temporary/'single-open'
    execute([simulated, '--single-open-48000', *options[1:], '--output', single], 0)
    checked = json.loads((single/'probe.json').read_text())
    require(checked['single_open'] is True and checked['successful'] is True and checked['stream_started'] is True
            and checked['completed_inspections'] == 0 and checked['inspection_succeeded'] is False
            and checked['initial_reported_rate_hz'] == 0
            and checked['reported_rate_hz'] == checked['expected_rate_hz'] == 48000 and checked['callbacks'] > 0,
            'Single-open factory verification was confused with a prior inspection')
    small = temporary/'single-open-eight-intervals'
    execute([simulated, '--single-open-48000', *options[1:], '--output', small, '--intervals', '8'], 0)
    small_report = json.loads((small/'probe.json').read_text())
    require(small_report['successful'] is True and small_report['simulated'] is True and small_report['intervals'] == 8
            and small_report['callbacks'] > 0 and small_report['output_completions'] > 0 and small_report['pending_mask'] == small_report['retained_mask'] == 0
            and small_report['worker_exited'] and small_report['private_job_empty'] and small_report['buffers_disposed'],
            'Eight-interval probe failed SDK callbacks or retirement')
    mismatch = temporary/'single-open-mismatch'
    execute([simulated, '--single-open-44100', *options[1:], '--output', mismatch], 1)
    wrong_rate = json.loads((mismatch/'probe.json').read_text())
    require(wrong_rate['successful'] is False and wrong_rate['stream_started'] is False
            and wrong_rate['callbacks'] == 0 and wrong_rate['output_submissions'] == 0
            and wrong_rate['reported_rate_hz'] == 0 and wrong_rate['finished'] is True,
            'Factory clock mismatch generated audio or false observed metadata')
    wrong = temporary/'wrong-kind'
    execute([native, *options, '--output', wrong], 1)
    rejected = json.loads((wrong/'probe.json').read_text())
    require(rejected['successful'] is False and rejected['inspection_succeeded'] is False
            and rejected['stream_started'] is False and rejected['callbacks'] == 0
            and rejected['host_failure'] == 2, 'Simulation impersonated physical streaming or did not reach kind rejection')
    # Evidence is retained under the ignored results tree; no recursive cleanup.
    print('Host probe plan/argument gates, simulated callbacks/counters/retirement and wrong-kind rejection passed; no physical USB')


if __name__ == '__main__':
    main()
