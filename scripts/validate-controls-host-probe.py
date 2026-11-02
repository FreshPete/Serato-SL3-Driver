"""Read-only consistency checks for the bounded no-audio controls probe."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('controls_physical', ROOT/'scripts/export-usbdk-physical-checkpoint.py')
physical = importlib.util.module_from_spec(spec)
spec.loader.exec_module(physical)
require, read, digest = physical.require, physical.read, physical.digest
RUNNER_INPUTS = ('test-controls-host-traced.ps1', 'validate-controls-host-probe.py', 'test-controls-host-probe.py',
                 'read-startup-journal.ps1', 'capture-usb-startup.ps1', 'preflight-usbdk.ps1',
                 'collect-windows-state.ps1', 'export-usbdk-physical-checkpoint.py', 'validate-usbdk-capture.py',
                 'prepare-usbdk-lifecycle-trace.py','observe-sl3-usb-identity.py','supervise-usb-identity.py','controls-usb-identity.py',
            'capture-controls-user-context.ps1','test-controls-user-probe.ps1','inspect-process.psm1','validate-controls-user-probe.py','validate-usb-state-capture.py')


def lifecycle_trace(folder, capture, requested):
    require(type(requested) is bool and capture['plan']['withUsbDkLifecycle'] is requested, 'Lifecycle trace selection differs')
    if not requested:
        require('lifecycle' not in capture['plan'] and 'lifecycleDecoder' not in capture, 'Unexpected lifecycle trace metadata')
        return None
    spec = importlib.util.spec_from_file_location('controls_lifecycle', ROOT/'scripts/prepare-usbdk-lifecycle-trace.py')
    preparer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preparer)
    expected, tmf = preparer.check()
    plan = capture['plan']['lifecycle']
    require(plan == {'provider': expected['providerGuid'], 'flags': expected['flags'], 'level': expected['level'],
                     'driverSha256': expected['driverSha256'], 'selectedTmfSha256': expected['selectedTmfSha256'],
                     'emissionVerified': False} and plan['emissionVerified'] is False, 'Lifecycle provider configuration differs')
    saved = capture['lifecycleDecoder']
    decoder = folder/'lifecycle-decoder'
    require(json.dumps(read(decoder/'plan.json'), sort_keys=True) == json.dumps(expected, sort_keys=True)
            and (decoder/'lifecycle.tmf').read_bytes() == tmf,
            'Prepared lifecycle source/decoder differs')
    for key, path in (('sourceSha256', ROOT/'scripts/prepare-usbdk-lifecycle-trace.py'),
                      ('planSha256', decoder/'plan.json'), ('tmfSha256', decoder/'lifecycle.tmf')):
        require(type(saved[key]) is str and re.fullmatch(r'[0-9a-fA-F]{64}', saved[key]) is not None
                and digest(path).lower() == saved[key].lower(), 'Lifecycle decoder file binding differs')
    update = ['update', 'trace', '-n', capture['session'], '-p', '{'+expected['providerGuid']+'}', expected['flags'], str(expected['level'])]
    commands = capture['commands']
    configured = [n for n, row in enumerate(commands) if row['arguments'] == update and type(row['exitCode']) is int and row['exitCode'] == 0]
    started = [n for n, row in enumerate(commands) if row['arguments'] == ['start', '-n', capture['session']] and type(row['exitCode']) is int and row['exitCode'] == 0]
    require(len(configured) == len(started) == 1 and configured[0] < started[0], 'Lifecycle provider not configured before shared trace start')
    return {'providerConfigured': True, 'sharedSession': capture['session'], 'emissionVerified': False,
            'decodedMessagesVerified': False, 'tmfSha256': expected['selectedTmfSha256']}


def uint(value, limit=2**64):
    return type(value) is int and 0 <= value < limit


def flags(record, yes=(), no=()):
    require(all(record[k] is True for k in yes) and all(record[k] is False for k in no), 'Unexpected probe flags')


def owner(record, released):
    flags(record, ('io_retired', 'audio_thread_retired', 'process_started'), ('running', 'forced_termination'))
    flags(record, ('device_released', 'worker_exited', 'private_job_empty') if released else ('device_held',),
          ('device_held',) if released else ('device_released', 'worker_exited', 'private_job_empty'))
    require(record['rate_hz'] in (44100, 48000) and type(record['rate_hz']) is int, 'Invalid observed rate')
    require(record['worker_phase'] == (6 if released else 1) and type(record['worker_phase']) is int, 'Wrong owner phase')
    for key in ('host_failure', 'active_callbacks', 'callbacks_started', 'callbacks_completed', 'worker_failure', 'stream_fault',
                'audio_input_submissions', 'audio_input_frames', 'audio_input_blocks', 'audio_owner_input_frames', 'published_output_frames',
                'audio_output_submissions', 'audio_output_completions', 'audio_output_frames_submitted', 'pending_mask', 'retained_mask'):
        require(uint(record[key]) and record[key] == 0, 'Audio/failure/ownership counter is nonzero: '+key)
    require(uint(record['native_error'], 2**32), 'Invalid native error field')


def journal(path, received):
    require(0 < path.stat().st_size <= 65536, 'Empty/oversized controls journal')
    raw = path.read_bytes()
    require(raw.endswith(b'\n'), 'Incomplete controls journal suffix')
    rows = []
    for line in raw.decode('ascii').splitlines():
        # The first guarded worker emitted this exact legacy two-dot name.
        # Admit only that spelling, without accepting arbitrary dotted stages.
        match = re.fullmatch(r'([0-9]+)\t([0-9]+)\t((?:[a-z_]+|redirect_owner\.acquire)\.(?:enter|return))', line)
        require(match is not None, 'Malformed journal')
        tick, pid = int(match[1]), int(match[2])
        require(tick < 2**64 and 0 < pid < 2**32 and (not rows or tick >= rows[-1][0]), 'Invalid journal time/PID')
        rows.append((tick, pid, match[3]))
    require(len({r[1] for r in rows}) == 1, 'Multiple controls workers')
    stages = [r[2] for r in rows]
    require(stages[:3] == ['worker.enter', 'helper_load.enter', 'helper_load.return'], 'Invalid worker prefix')
    at = 3
    while stages[at:at+2] == ['enumerate.enter', 'enumerate.return']:
        at += 2
    require(at > 3, 'Missing enumeration')
    guard = []
    for name in ('redirect_owner_acquire', 'redirect_owner.acquire'):
        pair = [name+'.enter', name+'.return']
        if stages[at+2:at+4] == pair:
            guard = pair
    expected = ['configuration.enter', 'configuration.return'] + guard + ['redirect_start.enter', 'redirect_start.return',
                'system_handle.enter', 'system_handle.return', 'clock_getter.enter', 'clock_getter.return',
                'audio_controls.enter', 'audio_controls_write.enter', 'audio_controls_write.return'] + [
                'audio_controls_read.enter', 'audio_controls_read.return']*received + [
                'audio_controls.return', 'redirect_close.enter', 'redirect_close.return', 'helper_unload.enter', 'helper_unload.return']
    require(stages[at:] == expected, 'Expected one acquire/rate/getter/release and exact received-frame count')
    result = {'name': path.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'records': len(rows), 'workerPid': rows[0][1],
              'redirects': 1, 'rateGetters': 1, 'controlsWrites': 1, 'controlsReads': received, 'redirectCloses': 1}
    if guard:
        result['redirectOwnerAcquireMarkers'] = guard
    return result


def probe(folder, worker_sha, simulated=False):
    require(re.fullmatch(r'[0-9a-fA-F]{64}', worker_sha) is not None, 'Invalid expected worker hash')
    data = read(folder/'probe.json')
    require(data['schema'] == 'sl3.controls-host-probe.v1' and data['phase'] == 'finished', 'Wrong probe schema/phase')
    flags(data, ('successful', 'finished', 'acquisition_verified', 'sample_present'),
          ('audio_buffers_created', 'calibration_verified', 'analogue_signal_verified', 'asio_com_registered'))
    require(data['simulated'] is simulated and type(data['worker_sha256']) is str and data['worker_sha256'].lower() == worker_sha.lower(), 'Kind/worker hash mismatch')
    for key, expected in {'device_protocol_version': 3, 'acquisition_attempts': 1, 'query_attempts': 1,
                          'audio_start_attempts': 0, 'alternate_changes_requested': 0, 'rate_changes': 0,
                          'control_setters': 0, 'firmware_requests': 0}.items():
        require(uint(data[key]) and data[key] == expected, 'Wrong controls-only operation count: '+key)
    received = data['received_frames']
    require(uint(received) and 1 <= received <= 4 and data['error'] == '', 'Invalid frame budget/result')
    raw = data['raw_controls']
    require(type(raw) is list and len(raw) == 22 and all(uint(v, 256) for v in raw), 'Invalid complete raw control table')
    inputs = data['inputs']
    require(type(inputs) is list and len(inputs) == 3, 'Missing interpreted control groups')
    for group, (p, s, t) in enumerate(((0, 3, 8), (1, 9, 14), (2, 15, 20))):
        expected = {'group': group, 'phono_raw': raw[p], 'phono_nonzero': raw[p] != 0,
                    'sensitivity_code': raw[s], 'original_ui_sensitivity_tenths_mv': 25+5*raw[s] if raw[s] <= 15 else None,
                    'through_raw': raw[t], 'through_nonzero': raw[t] != 0}
        require(inputs[group] == expected, 'Interpreted fields do not match the raw table')
        require(all(type(inputs[group][k]) is type(v) for k, v in expected.items()), 'Invalid interpreted field types')
    for name, released in (('acquisition', False), ('after_query', False), ('final', True)):
        owner(data[name], released)
    rate = data['acquisition']['rate_hz']
    require(data['after_query']['rate_hz'] == data['final']['rate_hz'] == rate, 'Cached rate identity changed')
    journals = list(folder.glob('worker-*.tsv'))
    if simulated:
        require(not journals, 'Simulated result contains native journal')
        native_journal = None
    else:
        require(len(journals) == 1 and journals[0].name == 'worker-1.tsv', 'Expected one native worker journal')
        native_journal = journal(journals[0], received)
    return {'valid': True, 'scope': 'Recorded controls/ownership consistency only; not calibration, analogue or Serato readiness',
            'simulated': simulated, 'workerSha256': worker_sha.lower(), 'rateHz': rate,
            'receivedFrames': received, 'rawControls': raw, 'inputs': inputs,
            'probeRecordSha256': digest(folder/'probe.json'), 'nativeJournal': native_journal}


def traced(folder, worker_sha, probe_sha, scope=False, broker_scope=False):
    require(not (scope and broker_scope), 'Conflicting trace scenarios')
    require(re.fullmatch(r'[0-9a-fA-F]{64}', worker_sha) is not None and re.fullmatch(r'[0-9a-fA-F]{64}', probe_sha) is not None,
            'Invalid expected executable hashes')
    record = read(folder/'run.json')
    schema='sl3.broker-scope.traced-run.v1' if broker_scope else ('sl3.scope-host.traced-run.v1' if scope else 'sl3.controls-host.traced-run.v1')
    require(record['schema'] == schema and record['completed'] is True and record['error'] is None,
            'Incomplete traced controls run')
    flags(record, ('traceCleanupConfirmed', 'secureBootBefore', 'secureBootAfter', 'recoveryConfirmed'),
          ('driverChanges', 'securityChanges', 'asioRegistration', 'automaticRetry'))
    require(record['probeExitCode'] == record['traceExitCode'] == 0 and type(record['probeExitCode']) is int
            and type(record['traceExitCode']) is int, 'Probe/trace failed')
    require(record['workerSha256'].lower() == worker_sha.lower() and record['probeSha256'].lower() == probe_sha.lower(), 'Executable identities differ')
    inputs=RUNNER_INPUTS+('validate-broker-scope-probe.py',) if broker_scope else (RUNNER_INPUTS+('validate-scope-host-probe.py',) if scope else RUNNER_INPUTS)
    require(set(record['runnerInputs']) == set(inputs), 'Missing/unexpected runner dependencies')
    for name, expected in record['runnerInputs'].items():
        require(type(expected) is str and re.fullmatch(r'[0-9a-fA-F]{64}', expected) is not None, 'Invalid runner hash')
        require(digest(ROOT/'scripts'/name).lower() == expected.lower(), 'Runner source changed: '+name)
    before, after = read(folder/'before-state.json'), read(folder/'after-state.json')
    require(len(before['devices']) == 1 and before['devices'][0]['device']['InstanceId'].upper() == r'USB\VID_1CC5&PID_0001\SL3.01.00',
            'Expected exact resting SL3 fixture in recovery baseline')
    require(digest(folder/'before-state.json').lower() == record['beforeStateSha256'].lower()
            and digest(folder/'after-state.json').lower() == record['afterStateSha256'].lower(), 'Recovery snapshot hashes differ')
    require(before['secureBoot'] is True and after['secureBoot'] is True
            and physical.state_contract(before) == physical.state_contract(after), 'Recovery differs')
    stats = physical.capture_validator.trace_statistics(folder/'events.xml')
    require(stats == record['traceStats'] and stats['eventsLost'] == stats['buffersLost'] == 0, 'USB trace loss/statistics differ')
    trace = read(folder/'trace/capture.json')
    lifecycle = lifecycle_trace(folder/'trace', trace, record['withUsbDkLifecycle'])
    require(digest(folder/'trace/capture.json').lower() == record['traceRecordSha256'].lower(), 'Trace record binding differs')
    require(stats['session'] == trace['session'], 'USB trace session differs')
    require(trace['status'] == 'window completed' and any(command['arguments'] == ['delete', '-n', trace['session']]
            and command['exitCode'] == 0 for command in trace['commands']), 'Trace cleanup was not recorded')
    utc = physical.capture_validator.utc
    require(utc(trace['startedUtc']) <= utc(record['probeStartedUtc']) <= utc(record['probeCompletedUtc']) <= utc(trace['stoppedUtc']),
            'Probe outside USB trace window')
    etls = list((folder/'trace').glob('*.etl'))
    require(len(etls) == 1 and digest(etls[0]).lower() == record['etlSha256'].lower(), 'ETL binding differs')
    if broker_scope:
        spec=importlib.util.spec_from_file_location('broker_scope_component',ROOT/'scripts/validate-broker-scope-probe.py')
        component=importlib.util.module_from_spec(spec);spec.loader.exec_module(component)
        result=component.validate(folder/'probe',worker_sha.lower())
        result['probeRecordSha256']=result['bindings']['result.json']
    elif scope:
        spec=importlib.util.spec_from_file_location('scope_component',ROOT/'scripts/validate-scope-host-probe.py')
        component=importlib.util.module_from_spec(spec);spec.loader.exec_module(component)
        result=component.validate(folder/'probe',worker_sha.lower())
    else:result = probe(folder/'probe', worker_sha)
    require(result['probeRecordSha256'] == record['probeRecordSha256'].lower(), 'Probe record binding differs')
    require(digest(folder/'probe-validation.json').lower() == record['probeValidationSha256'].lower(), 'Saved probe validation binding differs')
    identity_spec = importlib.util.spec_from_file_location('controls_identity_coverage', ROOT/'scripts/controls-usb-identity.py')
    identity = importlib.util.module_from_spec(identity_spec); identity_spec.loader.exec_module(identity)
    identity_result = identity.coverage(folder, record, trace)
    return {'valid': True, 'scope': 'Native controls result, complete USB trace and selected recovery consistency only',
            'probe': result, 'runRecordSha256': digest(folder/'run.json'), 'traceStats': stats,
            'secureBootBeforeAndAfter': True, 'recoveryConfirmed': True, 'lifecycleTrace': lifecycle,
            'usbIdentity': identity_result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--probe', type=Path)
    group.add_argument('--run', type=Path)
    parser.add_argument('--worker-sha256', required=True)
    parser.add_argument('--probe-sha256')
    parser.add_argument('--expect-simulated', action='store_true')
    args = parser.parse_args()
    require(not args.run or (args.probe_sha256 and not args.expect_simulated), 'Native traced run requires probe hash')
    result = traced(args.run, args.worker_sha256, args.probe_sha256) if args.run else probe(args.probe, args.worker_sha256, args.expect_simulated)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as error:
        print(json.dumps({'valid': False, 'error': str(error)}))
        raise SystemExit(1)
