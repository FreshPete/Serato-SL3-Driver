"""Read-only retained-probe/prerequisite consistency checks; no device operations."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


physical = module('retained_physical', 'export-usbdk-physical-checkpoint.py')
timing = module('retained_timing', 'analyse-callback-timing.py')
require, read, digest = physical.require, physical.read, physical.digest


def uint(value):
    return type(value) is int and 0 <= value < 2**64


def flags(record, yes=(), no=()):
    require(all(record[k] is True for k in yes) and all(record[k] is False for k in no), 'Unexpected evidence flags')


def zero(record, keys):
    require(all(uint(record[k]) and record[k] == 0 for k in keys), 'Nonzero or invalid failure/ownership counters')


def journal(path, keepalive=False):
    require(0 < path.stat().st_size <= 65536, 'Empty/oversized startup journal')
    raw = path.read_bytes()
    require(raw.endswith(b'\n'), 'Incomplete startup journal suffix')
    rows = []
    for line in raw.decode('ascii').splitlines():
        match = re.fullmatch(r'([0-9]+)\t([0-9]+)\t([a-z_]+\.(?:enter|return))', line)
        require(match is not None, 'Malformed startup journal')
        tick, pid = int(match[1]), int(match[2])
        require(tick < 2**64 and 0 < pid < 2**32 and (not rows or tick >= rows[-1][0]), 'Journal clock/PID invalid')
        rows.append((tick, pid, match[3]))
    require(len({r[1] for r in rows}) == 1, 'Multiple worker PIDs in retained journal')
    stages = [r[2] for r in rows]
    prefix = ['worker.enter', 'helper_load.enter', 'helper_load.return']
    require(stages[:3] == prefix, 'Journal startup prefix differs')
    at = 3
    while stages[at:at+2] == ['enumerate.enter', 'enumerate.return']:
        at += 2
    require(at > 3, 'Missing complete enumeration')
    expected = ['configuration.enter', 'configuration.return']
    if keepalive:
        expected.extend(('redirect_owner_acquire.enter', 'redirect_owner_acquire.return'))
    expected.extend(('redirect_start.enter', 'redirect_start.return', 'system_handle.enter',
                     'system_handle.return', 'clock_getter.enter', 'clock_getter.return'))
    for _ in range(2):
        expected.extend(('clock_getter.enter', 'clock_getter.return'))
        if keepalive:
            expected.extend(('playback_keepalive.enter', 'playback_keepalive.return'))
    expected.extend(('redirect_close.enter', 'redirect_close.return', 'helper_unload.enter', 'helper_unload.return'))
    require(stages[at:] == expected, 'Expected exactly one redirect, three fresh clock getters and one final release')
    result = {'name': path.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'records': len(rows),
              'workerPid': rows[0][1], 'redirects': 1, 'clockGetters': 3, 'redirectCloses': 1}
    if keepalive:
        starts = [tick for tick, _, name in rows if name == 'playback_keepalive.enter']
        stops = [tick for tick, _, name in rows if name == 'playback_keepalive.return']
        require(starts[1] - stops[0] >= 250, 'Missing idle interval between keepalive lifetimes')
        result.update(keepaliveLifetimes=2, idleBetweenKeepaliveMs=starts[1] - stops[0])
    return result


def probe(folder, worker_sha, expected_rate, simulated=False, keepalive=False):
    root = read(folder/'probe.json')
    require(root['schema'] == 'sl3.retained-host-probe.v1' and root['phase'] == 'finished', 'Wrong lifecycle schema/phase')
    flags(root, ('successful', 'finished', 'acquisition_verified', 'acquisition_io_retired', 'acquisition_device_held',
                 'io_retired', 'device_released', 'audio_thread_retired', 'worker_exited', 'private_job_empty'),
          ('acquisition_device_released', 'acquisition_worker_exited', 'device_held', 'forced_termination',
           'analogue_signal_verified', 'latency_measured', 'asio_com_registered'))
    require(root['simulated'] is simulated and root['worker_sha256'].lower() == worker_sha.lower(), 'Worker kind/hash mismatch')
    require(root.get('playback_keepalive', False) is keepalive and not (keepalive and simulated),
            'Unexpected keepalive mode')
    for key, expected in {'acquisition_attempts': 1, 'requested_streams': 2, 'completed_streams': 2, 'buffer_recreations': 1,
                          'requested_stream_ms': 1000, 'bank_frames': 128, 'intervals': 8, 'worker_phase': 6,
                          'expected_rate_hz': expected_rate, 'reported_rate_hz': expected_rate}.items():
        require(uint(root[key]) and root[key] == expected, 'Lifecycle shape/state differs: '+key)
    zero(root, ('host_failure', 'worker_failure', 'stream_fault', 'active_callbacks'))
    require(root['error'] == '' and root['output_payload'] == 'zero PCM only', 'Unexpected lifecycle error/output policy')
    require(type(root['streams']) is list and len(root['streams']) == 2, 'Missing per-stream records')
    streams = []
    for i, entry in enumerate(root['streams'], 1):
        require(entry['file'] == f'stream-{i}.json', 'Unexpected or repeated stream record path')
        flags(entry, ('successful', 'buffers_disposed'))
        path = folder/entry['file']
        s = read(path)
        require(s['schema'] == 'sl3.host-probe.v1' and s['phase'] == 'finished' and s['simulated'] is simulated, 'Wrong per-stream schema/phase/kind')
        flags(s, ('successful', 'finished', 'retained_device', 'stream_started', 'device_held', 'io_retired', 'audio_thread_retired', 'buffers_disposed'),
              ('device_released', 'worker_exited', 'private_job_empty', 'forced_termination', 'single_open', 'inspect_only',
               'inspection_succeeded', 'callback_contract_failed', 'analogue_signal_verified', 'latency_measured', 'asio_com_registered'))
        for key, expected in {'stream_index': i, 'expected_rate_hz': expected_rate, 'reported_rate_hz': expected_rate,
                              'initial_reported_rate_hz': expected_rate, 'intervals': 8, 'bank_frames': 128,
                              'requested_stream_ms': 1000, 'worker_phase': 1, 'audio_exit': 2}.items():
            require(uint(s[key]) and s[key] == expected, 'Per-stream state/shape differs: '+key)
        zero(s, ('host_failure', 'worker_failure', 'stream_fault', 'active_callbacks', 'pending_mask', 'retained_mask', 'completed_inspections', 'first_frame'))
        counters = ('callbacks', 'callbacks_started', 'callbacks_completed', 'input_blocks', 'input_frames', 'audio_input_frames',
                    'published_output_frames', 'output_submissions', 'output_completions', 'output_frames_submitted', 'observed_stream_ms')
        require(all(uint(s[k]) and s[k] > 0 for k in counters), 'Missing/invalid positive stream counters')
        require(s['callbacks'] == s['callbacks_started'] == s['callbacks_completed'] and s['observed_stream_ms'] >= 1000
                and s['input_frames'] >= s['audio_input_frames'] >= s['published_output_frames']
                and s['input_blocks'] >= s['output_submissions'] >= s['output_completions']
                and s['output_frames_submitted'] <= s['published_output_frames'] and s['callbacks']*128 <= s['audio_input_frames'], 'Inconsistent stream counters')
        require(s['error'] == '' and s['output_payload'] == 'zero PCM only', 'Unexpected stream error/output policy')
        observation = timing.analyse(s)
        streams.append({'file': path.name, 'sha256': digest(path), 'callbacks': s['callbacks'], 'inputFrames': s['input_frames'],
                        'outputSubmissions': s['output_submissions'], 'outputCompletions': s['output_completions'],
                        'nativeError': s['native_error'], 'callbackTiming': observation})
    journals = list(folder.glob('worker-*.tsv'))
    require((simulated and not journals) or (not simulated and len(journals) == 1 and journals[0].name == 'worker-1.tsv'), 'Unexpected worker journal count')
    return {'valid': True, 'scope': 'Recorded retained lifecycle consistency only; not hardware attestation or latency approval',
            'simulated': simulated, 'workerSha256': worker_sha.lower(), 'rateHz': expected_rate, 'probeRecordSha256': digest(folder/'probe.json'),
            'streams': streams, 'journal': None if simulated else journal(journals[0], keepalive),
            'limits': ['Submission/completion differences at stop are preserved', 'No analogue audio, physical clock/continuity, production ASIO or Serato/DVS result']}


def prerequisites(capture_folder, duplex_folder, worker_sha, expected_rate):
    capture_run, capture_evidence = physical.validate_run(capture_folder, 'Capture', worker_sha)
    cap = physical.capture_validator.validate(capture_folder, worker_sha)
    duplex_run, duplex_evidence = physical.validate_run(duplex_folder, 'DuplexSilence', worker_sha)
    require(physical.capture_validator.utc(capture_run['nativeCompletedUtc']) <= physical.capture_validator.utc(duplex_run['nativeStartedUtc']), 'Duplex did not follow capture')
    d = read(duplex_folder/'duplex/duplex.json')
    require(digest(duplex_folder/'duplex/duplex.json').lower() == duplex_run['nativeRecordSha256'].lower(), 'Duplex record differs')
    flags(d, ('duplex_succeeded', 'transfers_succeeded', 'buffer_cleanup_complete', 'redirect_and_alternates_cleanup_succeeded'))
    require(cap['reportedRateHz'] == d['reported_rate_hz'] == expected_rate and d['output_payload'] == 'zero PCM only', 'Prerequisite rate/output mismatch')
    require(all(type(d[k]) is int and d[k] == 4 for k in ('submitted_input_requests', 'completed_input_requests', 'submitted_output_requests', 'completed_output_requests')),
            'Incomplete finite duplex requests')
    packets = d['packets']
    require(type(packets) is list and len(packets) == 512, 'Missing/extra duplex packet rows')
    require(all(type(p['pair']) is int and p['pair'] in range(4) and p['direction'] in ('IN', 'OUT') and
                type(p['slot']) is int and p['slot'] == p['pair']*2+(p['direction'] == 'OUT') for p in packets), 'Unexpected packet identity/slot')
    for pair in range(4):
        incoming = sorted((p for p in packets if p['pair'] == pair and p['direction'] == 'IN'), key=lambda p: p['packet'])
        outgoing = sorted((p for p in packets if p['pair'] == pair and p['direction'] == 'OUT'), key=lambda p: p['packet'])
        require(len(incoming) == len(outgoing) == 64, 'Missing duplex pair')
        offset = 0
        for index, (inp, out) in enumerate(zip(incoming, outgoing)):
            for p in (inp, out):
                flags(p, ('request_submitted', 'request_terminal'))
                require(uint(p['packet']) and p['packet'] == index and all(uint(p[k]) and p[k] == 0 for k in ('status', 'completion_win32_error', 'request_usbd_status')), 'Nonterminal/failed/duplicate duplex packet')
            length = inp['returned_length']
            require(uint(length) and 0 < length <= 126 and length % 18 == 0 and out['requested_length'] == length and out['offset'] == offset, 'Duplex output differs from real input layout')
            offset += length
        slots = {p['slot'] for p in outgoing}
        require(len(slots) == 1 and all(p['reported_request_bytes'] == offset for p in outgoing), 'Ambiguous output storage/byte count')
        slot = slots.pop()
        require(type(slot) is int and slot in (1, 3, 5, 7), 'Unexpected output slot')
        raw = (duplex_folder/'duplex'/f'registered-{slot}.bin').read_bytes()
        require(len(raw) == 8064 and not any(raw), 'Finite prerequisite output buffer is not zero PCM')
    return {'valid': True, 'scope': 'Same-worker capture/zero-duplex prerequisites only', 'workerSha256': worker_sha.lower(), 'rateHz': expected_rate,
            'capture': capture_evidence, 'duplex': duplex_evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--probe', type=Path)
    group.add_argument('--prerequisites', nargs=2, type=Path)
    parser.add_argument('--worker-sha256', required=True)
    parser.add_argument('--expected-rate', type=int, choices=(44100, 48000), required=True)
    parser.add_argument('--expect-simulated', action='store_true')
    parser.add_argument('--keepalive', action='store_true')
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-fA-F]{64}', args.worker_sha256) is not None, 'Invalid expected worker SHA256')
    require(not (args.expect_simulated and args.prerequisites), 'Physical prerequisites cannot be simulated')
    require(not args.keepalive or args.probe and not args.expect_simulated, 'Keepalive requires a native probe record')
    result = probe(args.probe, args.worker_sha256, args.expected_rate, args.expect_simulated, args.keepalive) if args.probe else prerequisites(*args.prerequisites, args.worker_sha256, args.expected_rate)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as error:
        print(json.dumps({'valid': False, 'error': str(error)}))
        raise SystemExit(1)
