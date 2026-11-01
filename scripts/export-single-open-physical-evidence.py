"""Validate retained real bridge/prerequisite records and export metadata only."""
import importlib.util
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'tests/results/local'
CHECKPOINT = ROOT/'artifacts/build/checkpoints/single-open-20261030'
SOURCE_COMMIT = '13fd6c4950053f37f2aeef9d03e4f7699e4ff3b8'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


prior = module('physical', 'validate-historical-usbdk-run.py')
timing = module('timing', 'analyse-callback-timing.py')
statuses = module('statuses', 'summarise-usbdk-packet-status.py')
require, read, digest = prior.require, prior.read, prior.digest


def recorded_source(name, expected):
    path = ROOT/name
    if path.exists() and digest(path).lower() == expected.lower():
        return 'current-file'
    result = subprocess.run(['git', 'show', SOURCE_COMMIT+':'+name], cwd=ROOT, capture_output=True, timeout=10)
    require(result.returncode == 0, 'Historical source unavailable: '+name)
    # Git normalises tracked text; require an exact recorded byte hash after
    # either LF or CRLF reconstruction, not a fuzzy source comparison.
    lf = result.stdout.replace(b'\r\n', b'\n')
    require(any(hashlib.sha256(raw).hexdigest() == expected.lower() for raw in (result.stdout, lf, lf.replace(b'\n', b'\r\n'))),
            'Recorded source differs from archived commit: '+name)
    return 'git:'+SOURCE_COMMIT


def recorded_runner(name, expected):
    path = CHECKPOINT/'scripts'/name
    require(path.exists() and digest(path).lower() == expected.lower(), 'Historical runner changed: '+name)


def main():
    build = read(CHECKPOINT/'native-build-Release.json')
    worker_sha, probe_sha = build['usbdk']['executableSha256'], build['hostProbe']['executableSha256']
    require(digest(CHECKPOINT/'sl3_usbdk.exe').lower() == worker_sha.lower(), 'Archived worker binary changed')
    require(digest(CHECKPOINT/'sl3_host_probe.exe').lower() == probe_sha.lower(), 'Archived probe binary changed')
    for name, expected in build['inputs'].items():
        recorded_source(name, expected)
    sequence_dir = LOCAL/'single-open-sequence-20261030-02'
    sequence = read(sequence_dir/'sequence.json')
    require(sequence['completed'] is True and sequence['error'] is None
            and all(sequence[key] is True for key in ('capturePassed', 'duplexPassed', 'bridgePassed')),
            'Sequence did not pass all gates')
    require(sequence['workerSha256'] == worker_sha and sequence['probeSha256'] == probe_sha, 'Sequence build binding differs')
    for name, expected in sequence['scriptHashes'].items():
        recorded_runner(name, expected)
    capture_dir = LOCAL/'input-after-babble-20261030-01'
    cap_run, cap_evidence = prior.validate_run(capture_dir, 'Capture', worker_sha,
                                            runner_directory=CHECKPOINT/'scripts', source_commit=SOURCE_COMMIT)
    require(digest(capture_dir/'run.json').lower() == sequence['captureRunRecordSha256'].lower(), 'Capture prerequisite binding differs')
    capture = prior.capture_validator.validate(capture_dir, worker_sha)
    duplex_dir = sequence_dir/'duplex-run'
    duplex_run, duplex_evidence = prior.validate_run(duplex_dir, 'DuplexSilence', worker_sha,
                                                   runner_directory=CHECKPOINT/'scripts', source_commit=SOURCE_COMMIT)
    d = read(duplex_dir/'duplex/duplex.json')
    require(digest(duplex_dir/'duplex/duplex.json').lower() == duplex_run['nativeRecordSha256'].lower(), 'Duplex payload record differs')
    require(all(d[key] is True for key in ('duplex_succeeded', 'transfers_succeeded', 'buffer_cleanup_complete',
                                          'redirect_and_alternates_cleanup_succeeded')), 'Duplex failed')
    require(all(d[key] == 4 for key in ('submitted_input_requests', 'completed_input_requests',
                                       'submitted_output_requests', 'completed_output_requests')), 'Unexpected finite duplex workload')
    require(d['output_payload'] == 'zero PCM only', 'Unexpected output policy')
    output_buffers, output_bytes = [], 0
    for pair in range(4):
        incoming = sorted((p for p in d['packets'] if p['pair'] == pair and p['direction'] == 'IN'), key=lambda p: p['packet'])
        outgoing = sorted((p for p in d['packets'] if p['pair'] == pair and p['direction'] == 'OUT'), key=lambda p: p['packet'])
        require(len(incoming) == len(outgoing) == 64, 'Missing duplex packet layout')
        offset = 0
        for i, o in zip(incoming, outgoing):
            require(all(p['request_submitted'] is True and p['request_terminal'] is True and
                        p['status'] == p['completion_win32_error'] == p['request_usbd_status'] == 0 for p in (i, o)), 'Nonterminal/error duplex packet')
            require(0 < i['returned_length'] <= 126 and i['returned_length'] % 18 == 0
                    and o['requested_length'] == i['returned_length'] and o['offset'] == offset, 'Duplex OUT differs from real IN layout')
            offset += o['requested_length']
        slots = {p['slot'] for p in outgoing}
        require(len(slots) == 1 and all(p['reported_request_bytes'] == offset for p in outgoing), 'Ambiguous output storage/byte count')
        name = f'registered-{slots.pop()}.bin'
        path = duplex_dir/'duplex'/name
        raw = path.read_bytes()
        require(len(raw) == 8064 and not any(raw), 'Finite output is not zero PCM')
        output_buffers.append({'name': name, 'sha256': digest(path), 'allZero': True})
        output_bytes += offset
    bridge_dir = sequence_dir/'bridge-run'
    run = read(bridge_dir/'run.json')
    require(run['completed'] is True and run['error'] is None and run['probeExitCode'] == run['traceExitCode'] == 0
            and all(run[key] is True for key in ('traceCleanupConfirmed', 'secureBootBefore', 'secureBootAfter', 'recoveryConfirmed')),
            'Bridge trace/security/recovery gate failed')
    require(run['workerSha256'] == worker_sha and run['probeSha256'] == probe_sha
            and run['priorCaptureRunSha256'].lower() == digest(capture_dir/'run.json')
            and run['priorDuplexRunSha256'].lower() == digest(duplex_dir/'run.json'), 'Bridge prerequisite binding differs')
    for name, expected in run['runnerInputs'].items():
        recorded_runner(name, expected)
    for stem in ('before', 'after'):
        path = bridge_dir/f'{stem}-state.json'
        require(digest(path).lower() == run[f'{stem}StateSha256'].lower(), 'Bridge state hash differs')
    require(prior.state_contract(read(bridge_dir/'before-state.json')) == prior.state_contract(read(bridge_dir/'after-state.json')),
            'Bridge selected-state recovery differs')
    stats = prior.capture_validator.trace_statistics(bridge_dir/'events.xml')
    require(stats == run['traceStats'] and stats['eventsLost'] == stats['buffersLost'] == 0, 'Bridge trace differs or is lossy')
    trace = read(bridge_dir/'trace/capture.json')
    require(stats['session'] == trace['session'] and prior.capture_validator.utc(trace['startedUtc'])
            <= prior.capture_validator.utc(run['probeStartedUtc']) <= prior.capture_validator.utc(run['probeCompletedUtc'])
            <= prior.capture_validator.utc(trace['stoppedUtc']), 'Bridge probe outside trace')
    etls = list((bridge_dir/'trace').glob('*.etl'))
    require(len(etls) == 1 and digest(etls[0]).lower() == run['etlSha256'].lower(), 'Bridge ETL binding differs')
    path = bridge_dir/'probe/probe.json'
    p = read(path)
    require(digest(path).lower() == run['probeRecordSha256'].lower(), 'Bridge report differs')
    require(all(p[key] is True for key in ('successful', 'finished', 'single_open', 'stream_started', 'io_retired', 'device_released',
                                          'audio_thread_retired', 'worker_exited', 'private_job_empty', 'buffers_disposed')),
            'Native bridge did not succeed and retire')
    require(all(p[key] is False for key in ('simulated', 'inspect_only', 'inspection_succeeded', 'callback_contract_failed', 'forced_termination',
                                           'analogue_signal_verified', 'latency_measured', 'asio_com_registered')), 'Unexpected bridge claim')
    require(p['completed_inspections'] == 0 and p['expected_rate_hz'] == p['reported_rate_hz'] == sequence['expectedRateHz']
            and p['requested_stream_ms'] == 1000 and p['observed_stream_ms'] >= 1000 and p['bank_frames'] == 128 and p['intervals'] == 64,
            'Single-open mode/rate/time mismatch')
    require(p['callbacks'] == p['callbacks_started'] == p['callbacks_completed'] > 0
            and p['active_callbacks'] == p['host_failure'] == p['worker_failure'] == p['stream_fault'] == p['pending_mask'] == p['retained_mask'] == 0
            and p['input_frames'] > 0 and p['output_submissions'] >= p['output_completions'] > 0, 'Bridge counters/failure fields inconsistent')
    callback_timing = timing.analyse(p)
    callback_timing['probeRecordSha256'] = digest(path)
    failed_dir = LOCAL/'single-open-sequence-20261030-01'
    failed_sequence = read(failed_dir/'sequence.json')
    failed_duplex_path = failed_dir/'duplex-run/duplex/duplex.json'
    failed = read(failed_duplex_path)
    require(failed_sequence['completed'] is False and failed_sequence['bridgePassed'] is False
            and failed['submitted_output_requests'] == failed['completed_output_requests'] == 0, 'Failed gate was bypassed')
    failed_status = statuses.summarise(failed)
    failed_status['recordSha256'] = digest(failed_duplex_path)
    failed_status['sdkHeaderSha256'] = statuses.verify_sdk_header(statuses.SDK_HEADER)
    result = {'scope': 'First verified real single-open one-second callback bridge; earlier packet failure retained; no full ASIO/Serato/DVS claim',
              'workerSha256': worker_sha, 'probeSha256': probe_sha, 'sequenceRecordSha256': digest(sequence_dir/'sequence.json'),
              'capture': {**cap_evidence, 'rateHz': capture['reportedRateHz'], 'frames': capture['frames']},
              'silentDuplex': {**duplex_evidence, 'outputBytesAcceptedByApi': output_bytes, 'zeroOutputBuffers': output_buffers},
              'bridge': {'runRecordSha256': digest(bridge_dir/'run.json'), 'probeRecordSha256': digest(path),
                         'startedUtc': run['probeStartedUtc'], 'completedUtc': run['probeCompletedUtc'],
                         'traceStats': stats, 'etlSha256': digest(etls[0]), 'probe': p, 'callbackTiming': callback_timing},
              'earlierFailedGate': {'sequenceRecordSha256': digest(failed_dir/'sequence.json'), 'packetStatusSummary': failed_status},
              'limits': ['One second at 44.1 kHz, 64 intervals and 128-frame banks is not production eight-interval validation',
                         'Output submission/completion counters differ at stop; final masks and independent ownership domains retired normally',
                         'Software callback batching/rate is not physical clock or sample-continuity proof',
                         'No analogue loopback, timing profile, ASIO registration, current Serato/DVS or sustained stability result']}
    # Retain timing observations locally; exported evidence needs only summary.
    del result['bridge']['probe']['callback_timings']
    output = ROOT/'docs/evidence/first-real-single-open-bridge-20261030.json'
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified real capture, zero duplex buffers, one-second native bridge, trace/retirement and preserved failed gate')


if __name__ == '__main__':
    main()
