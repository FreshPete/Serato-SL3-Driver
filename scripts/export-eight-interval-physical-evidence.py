"""Verify the real eight-interval bridge against its immutable tested checkpoint."""
import hashlib
import json
import subprocess
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('first_bridge', ROOT/'scripts/export-single-open-physical-evidence.py')
first = importlib.util.module_from_spec(spec)
spec.loader.exec_module(first)
require, read, digest = first.require, first.read, first.digest


def main():
    # Includes exact same-worker capture and duplex records, successful packet
    # statuses, independently zero output buffers and the earlier failed gate.
    first.main()
    checkpoint = ROOT/'artifacts/build/checkpoints/eight-interval-probe-20261030'
    build = read(checkpoint/'native-build-Release.json')
    worker_sha, probe_sha = build['usbdk']['executableSha256'], build['hostProbe']['executableSha256']
    for filename, expected in [('sl3_usbdk.exe', worker_sha), ('sl3_host_probe.exe', probe_sha)]:
        require(digest(checkpoint/filename).lower() == expected.lower(), 'Archived eight-interval binary differs')
    source_commit = subprocess.run(['git', 'rev-parse', '525c472^{commit}'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    for name, expected in build['inputs'].items():
        path = ROOT/name
        if path.exists() and digest(path).lower() == expected.lower():
            continue
        result = subprocess.run(['git', 'show', source_commit+':'+name], cwd=ROOT, capture_output=True, timeout=10)
        require(result.returncode == 0, 'Eight-interval source unavailable: '+name)
        lf = result.stdout.replace(b'\r\n', b'\n')
        require(any(hashlib.sha256(raw).hexdigest() == expected.lower() for raw in (result.stdout, lf, lf.replace(b'\n', b'\r\n'))),
                'Eight-interval source byte identity differs: '+name)
    folder = ROOT/'tests/results/local/single-open-eight-intervals-20261030-01'
    run = read(folder/'run.json')
    require(run['completed'] is True and run['error'] is None and run['probeExitCode'] == run['traceExitCode'] == 0
            and all(run[k] is True for k in ('traceCleanupConfirmed', 'secureBootBefore', 'secureBootAfter', 'recoveryConfirmed')),
            'Eight-interval trace/security/recovery gate failed')
    baseline = read(ROOT/'docs/evidence/first-real-single-open-bridge-20261030.json')
    require(worker_sha == baseline['workerSha256'] == run['workerSha256'] and probe_sha == run['probeSha256'], 'Worker/probe binding differs')
    require(run['priorCaptureRunSha256'].lower() == baseline['capture']['runRecordSha256'].lower()
            and run['priorDuplexRunSha256'].lower() == baseline['silentDuplex']['runRecordSha256'].lower(), 'Prerequisite binding differs')
    for name, expected in run['runnerInputs'].items():
        require(digest(checkpoint/'scripts'/name).lower() == expected.lower(), 'Archived eight-interval runner differs: '+name)
    for stem in ('before', 'after'):
        require(digest(folder/f'{stem}-state.json').lower() == run[f'{stem}StateSha256'].lower(), 'State snapshot hash differs')
    require(first.prior.state_contract(read(folder/'before-state.json')) == first.prior.state_contract(read(folder/'after-state.json')),
            'Selected recovery contract differs')
    stats = first.prior.capture_validator.trace_statistics(folder/'events.xml')
    require(stats == run['traceStats'] and stats['eventsLost'] == stats['buffersLost'] == 0, 'Trace differs or is lossy')
    trace = read(folder/'trace/capture.json')
    utc = first.prior.capture_validator.utc
    require(stats['session'] == trace['session'] and utc(trace['startedUtc']) <= utc(run['probeStartedUtc'])
            <= utc(run['probeCompletedUtc']) <= utc(trace['stoppedUtc']), 'Probe outside trace window')
    etls = list((folder/'trace').glob('*.etl'))
    require(len(etls) == 1 and digest(etls[0]).lower() == run['etlSha256'].lower(), 'ETL hash differs')
    path = folder/'probe/probe.json'
    require(digest(path).lower() == run['probeRecordSha256'].lower(), 'Probe record hash differs')
    p = read(path)
    require(all(p[k] is True for k in ('successful', 'finished', 'single_open', 'stream_started', 'io_retired', 'device_released',
                                      'audio_thread_retired', 'worker_exited', 'private_job_empty', 'buffers_disposed')), 'Bridge success/retirement failed')
    require(all(p[k] is False for k in ('simulated', 'inspect_only', 'inspection_succeeded', 'callback_contract_failed', 'forced_termination',
                                       'analogue_signal_verified', 'latency_measured', 'asio_com_registered')), 'Unexpected bridge claim')
    require(p['intervals'] == run['blockIntervals'] == 8 and p['bank_frames'] == 128 and p['completed_inspections'] == 0
            and p['expected_rate_hz'] == p['reported_rate_hz'] == run['singleOpenExpectedRateHz'] == 44100
            and p['requested_stream_ms'] == 1000 and p['observed_stream_ms'] >= 1000 and p['output_payload'] == 'zero PCM only', 'Requested shape/rate differs')
    require(p['callbacks'] == p['callbacks_started'] == p['callbacks_completed'] > 0
            and all(p[k] == 0 for k in ('active_callbacks', 'host_failure', 'worker_failure', 'stream_fault', 'pending_mask', 'retained_mask')),
            'Callback/fault contract failed')
    require(p['input_frames'] == p['audio_input_frames'] == p['published_output_frames'] > 0
            and p['input_blocks'] >= p['output_submissions'] >= p['output_completions'] > 0
            and 0 < p['output_frames_submitted'] <= p['published_output_frames']
            and p['callbacks']*p['bank_frames'] <= p['input_frames'], 'Frame/submission counters inconsistent')
    timing = first.timing.analyse(p)
    del p['callback_timings']
    result = {'scope': 'One real one-second 44.1 kHz eight-interval bridge; no production ASIO/Serato/DVS claim',
              'sourceCommit': source_commit, 'workerSha256': worker_sha, 'probeSha256': probe_sha,
              'runRecordSha256': digest(folder/'run.json'), 'probeRecordSha256': digest(path),
              'startedUtc': run['probeStartedUtc'], 'completedUtc': run['probeCompletedUtc'],
              'traceStats': stats, 'etlSha256': digest(etls[0]), 'probe': p, 'callbackTiming': timing,
              'limits': ['One second does not establish sustained stability, physical clock accuracy or gap-free samples',
                         'Stop counters differ: not every submitted/published block has a successful OUT-completion claim',
                         'Native error is preserved; terminal masks and independent retirement are checked separately',
                         'No analogue signal, measured latency profile, retained-device hardware run, production ASIO or Serato/DVS result']}
    (ROOT/'docs/evidence/eight-interval-physical-20261030.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified eight-interval real bridge, pinned prerequisites, complete trace and independent retirement')


if __name__ == '__main__':
    main()
