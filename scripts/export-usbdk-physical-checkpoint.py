"""Validate saved real-device runs and export metadata only; no live USB calls."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'tests/results/local'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    require(path.stat().st_size <= 1024*1024, 'Oversized JSON evidence')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture_validator = load_module('capture_validator', ROOT/'scripts/validate-usbdk-capture.py')


def state_contract(state):
    selected = {key: state[key] for key in ('secureBoot', 'deviceGuard', 'hvciRegistry', 'devices', 'asio', 'application')}
    selected['devices'] = sorted(selected['devices'], key=lambda row: row['device']['InstanceId'])
    for row in selected['devices']:
        row['properties'] = sorted(row['properties'], key=lambda prop: prop['KeyName'])
    return selected


def validate_run(folder, mode, native_sha):
    record = read(folder/'run.json')
    require(record['mode'] == mode and record['completed'] is True and record['error'] is None, 'Incomplete scenario: '+folder.name)
    require(record['nativeExitCode'] == 0 and record['traceExitCode'] == 0 and record['traceCleanupConfirmed'] is True
            and record['recoveryConfirmed'] is True and record['driverChanges'] is False, 'Scenario/cleanup failed')
    require(record['nativeSha256'].lower() == native_sha.lower() and record['secureBootBefore'] is True
            and record['secureBootAfter'] is True, 'Build/security mismatch')
    for name, expected in record['runnerInputs'].items():
        require(digest(ROOT/'scripts'/name).lower() == expected.lower(), 'Runner source changed: '+name)
    before = read(folder/'before-state.json')
    after = read(folder/'after-state.json')
    require(digest(folder/'before-state.json').lower() == record['beforeStateSha256'].lower()
            and digest(folder/'after-state.json').lower() == record['afterStateSha256'].lower(), 'Snapshot hashes differ')
    require(before['secureBoot'] is True and after['secureBoot'] is True
            and state_contract(before) == state_contract(after), 'Recovery state changed')
    stats = capture_validator.trace_statistics(folder/'events.xml')
    require(stats == record['traceStats'] and stats['eventsLost'] == 0 and stats['buffersLost'] == 0, 'Trace statistics differ or are lossy')
    trace = read(folder/'trace/capture.json')
    require(stats['session'] == trace['session'], 'Trace session differs')
    require(capture_validator.utc(trace['startedUtc']) <= capture_validator.utc(record['nativeStartedUtc'])
            <= capture_validator.utc(record['nativeCompletedUtc']) <= capture_validator.utc(trace['stoppedUtc']), 'Native operation outside trace')
    etls = list((folder/'trace').glob('*.etl'))
    require(len(etls) == 1 and digest(etls[0]).lower() == record['etlSha256'].lower(), 'ETL binding differs')
    return record, {'runRecordSha256': digest(folder/'run.json'), 'beforeStateSha256': digest(folder/'before-state.json'),
                    'afterStateSha256': digest(folder/'after-state.json'), 'traceStats': stats,
                    'etlSha256': digest(etls[0]), 'secureBootBeforeAndAfter': True, 'recoveryConfirmed': True}


def main():
    build_path = ROOT/'artifacts/build/native/native-build-Release.json'
    build = read(build_path)
    native_sha = build['usbdk']['executableSha256']
    require(digest(ROOT/'artifacts/build/native/Release/sl3_usbdk.exe').lower() == native_sha.lower(), 'Native executable changed')
    for name, expected in build['inputs'].items():
        require(digest(ROOT/name).lower() == expected.lower(), 'Native source changed: '+name)
    listing = LOCAL/'usbdk-list-postrestart-20261030-01'
    _, list_result = validate_run(listing, 'List', native_sha)
    info = json.loads((listing/'native-output.txt').read_text())
    require(info == {'matched_sl3': 1, 'descriptor_fixture_matches': True, 'high_speed': True, 'device_redirected': False}, 'Unexpected descriptor-only result')
    list_result.update(info)
    capture = LOCAL/'usbdk-capture-postrestart-20261030-01'
    _, capture_result = validate_run(capture, 'Capture', native_sha)
    validation = capture_validator.validate(capture, native_sha)
    require(validation['valid'] is True, 'Capture consistency did not validate')
    data = read(capture/'capture/capture.json')
    capture_result.update({'reportedRateHz': data['reported_rate_hz'], 'frames': data['frames'],
                           'packetCount': len(data['packets']), 'plannedIntervals': data['planned_intervals'],
                           'packetLengthHistogram': dict(Counter(p['length'] for p in data['packets'])),
                           'pcmBytes': (capture/'capture/capture.pcm').stat().st_size,
                           'pcmSha256': digest(capture/'capture/capture.pcm'),
                           'nativeRecordSha256': digest(capture/'capture/capture.json'),
                           'audioOutputSubmissions': data['audio_output_submissions'],
                           'continuityVerified': data['continuity_verified']})
    duplex = LOCAL/'usbdk-duplex-postrestart-20261030-01'
    run, duplex_result = validate_run(duplex, 'DuplexSilence', native_sha)
    d = read(duplex/'duplex/duplex.json')
    require(digest(duplex/'duplex/duplex.json').lower() == run['nativeRecordSha256'].lower(), 'Duplex record hash differs')
    require(all(d[key] is True for key in ('duplex_succeeded', 'transfers_succeeded', 'buffer_cleanup_complete',
                                          'redirect_and_alternates_cleanup_succeeded', 'audio_output_submissions_known')), 'Duplex transfer failed')
    require(d['output_payload'] == 'zero PCM only' and d['audio_output_submissions'] == 4
            and d['submitted_input_requests'] == d['completed_input_requests'] == 4
            and d['submitted_output_requests'] == d['completed_output_requests'] == 4, 'Unexpected duplex workload')
    require(len(d['packets']) == 512, 'Incomplete duplex packets')
    output_buffers = []
    total_output = 0
    for pair in range(4):
        incoming = sorted((p for p in d['packets'] if p['pair'] == pair and p['direction'] == 'IN'), key=lambda p: p['packet'])
        outgoing = sorted((p for p in d['packets'] if p['pair'] == pair and p['direction'] == 'OUT'), key=lambda p: p['packet'])
        require(len(incoming) == len(outgoing) == 64, 'Missing duplex pair')
        offset = 0
        for number, (i, o) in enumerate(zip(incoming, outgoing)):
            for p in (i, o):
                require(p['packet'] == number and p['status'] == p['completion_win32_error'] == p['request_usbd_status'] == 0
                        and p['request_attempted'] is True and p['request_submitted'] is True and p['request_terminal'] is True,
                        'Failed/nonterminal physical packet')
            require(i['offset'] == number*126 and i['requested_length'] == 126 and 0 < i['returned_length'] <= 126
                    and i['returned_length'] % 18 == 0, 'Malformed IN packet')
            require(o['requested_length'] == i['returned_length'] and o['offset'] == offset, 'OUT layout differs from observed IN')
            offset += o['requested_length']
        slots = {p['slot'] for p in outgoing}
        require(len(slots) == 1, 'Ambiguous output buffer')
        slot = slots.pop()
        buffer_path = duplex/f'duplex/registered-{slot}.bin'
        raw = buffer_path.read_bytes()
        require(len(raw) == 8064 and not any(raw), 'Output buffer contains nonzero data')
        require(all(p['reported_request_bytes'] == offset for p in outgoing), 'OUT accepted-byte result differs')
        output_buffers.append({'slot': slot, 'bytes': len(raw), 'sha256': digest(buffer_path), 'allZero': True})
        total_output += offset
    require(total_output == d['output_bytes_requested'] == d['output_bytes_accepted_by_api'], 'Output totals differ')
    duplex_result.update({'reportedRateHz': d['reported_rate_hz'], 'inputRequestsCompleted': 4, 'outputRequestsCompleted': 4,
                          'inputPackets': 256, 'outputPackets': 256, 'outputBytesRequestedAndAcceptedByApi': total_output,
                          'outputBuffers': output_buffers, 'nativeRecordSha256': digest(duplex/'duplex/duplex.json'),
                          'continuityVerified': d['continuity_verified'], 'sampleClockValidated': d['sample_clock_validated'],
                          'analogOutputVerified': d['analog_output_verified']})
    rate_folder = LOCAL/'usbdk-rate48-postrestart-20261030-01'
    rate_validator = load_module('rate_validator', ROOT/'scripts/validate-usbdk-rate.py')
    rate_validation = rate_validator.validate(rate_folder, native_sha, 48000)
    require(rate_validation['valid'] is True, 'Rate evidence failed')
    _, rate_result = validate_run(rate_folder, 'Rate', native_sha)
    rate_data = read(rate_folder/'rate/rate.json')
    require(rate_data['initial_rate_hz'] == 44100 and rate_data['verified_rate_hz'] == 48000
            and rate_data['audio_submissions'] == 0 and rate_data['alternate_changes'] == 0, 'Unexpected rate transaction')
    rate_result.update({'initialRateHz': 44100, 'targetAndReadbackHz': 48000,
                        'nativeRecordSha256': digest(rate_folder/'rate/rate.json'),
                        'audioSubmissions': 0, 'rateRestorationAttempted': False})
    capture48 = LOCAL/'usbdk-capture48-postrestart-20261030-01'
    _, capture48_result = validate_run(capture48, 'Capture', native_sha)
    validation48 = capture_validator.validate(capture48, native_sha)
    require(validation48['valid'] is True and validation48['reportedRateHz'] == 48000, '48 kHz capture did not validate')
    c48 = read(capture48/'capture/capture.json')
    capture48_result.update({'reportedRateHz': 48000, 'frames': c48['frames'], 'packetCount': len(c48['packets']),
                             'packetLengthHistogram': dict(Counter(p['length'] for p in c48['packets'])),
                             'nativeRecordSha256': digest(capture48/'capture/capture.json'),
                             'pcmBytes': (capture48/'capture/capture.pcm').stat().st_size,
                             'pcmSha256': digest(capture48/'capture/capture.pcm'), 'audioOutputSubmissions': 0})
    duplex48 = LOCAL/'usbdk-duplex48-postrestart-20261030-01'
    r48, duplex48_result = validate_run(duplex48, 'DuplexSilence', native_sha)
    d48 = read(duplex48/'duplex/duplex.json')
    require(digest(duplex48/'duplex/duplex.json').lower() == r48['nativeRecordSha256'].lower(), '48 kHz duplex record changed')
    require(all(d48[k] is True for k in ('duplex_succeeded', 'transfers_succeeded', 'buffer_cleanup_complete',
                                        'redirect_and_alternates_cleanup_succeeded')) and d48['reported_rate_hz'] == 48000
            and d48['output_payload'] == 'zero PCM only' and len(d48['packets']) == 512, '48 kHz duplex did not pass')
    ins = {(p['pair'], p['packet']): p for p in d48['packets'] if p['direction'] == 'IN'}
    outs = {(p['pair'], p['packet']): p for p in d48['packets'] if p['direction'] == 'OUT'}
    require(len(ins) == len(outs) == 256 and ins.keys() == outs.keys(), '48 kHz duplex packet pairing differs')
    for p in d48['packets']:
        require(p['status'] == p['request_usbd_status'] == p['completion_win32_error'] == 0
                and p['request_submitted'] is True and p['request_terminal'] is True, '48 kHz packet failed')
    for pair in range(4):
        offset = 0
        for number in range(64):
            i, o = ins[(pair, number)], outs[(pair, number)]
            require(0 < i['returned_length'] <= 126 and i['returned_length'] % 18 == 0
                    and o['requested_length'] == i['returned_length'] and o['offset'] == offset, '48 kHz output layout mismatch')
            offset += o['requested_length']
    slots48 = {p['slot'] for p in outs.values()}
    require(len(slots48) == 4 and d48['completed_input_requests'] == d48['completed_output_requests'] == 4, '48 kHz request count differs')
    zeros48 = []
    for slot in sorted(slots48):
        path = duplex48/f'duplex/registered-{slot}.bin'
        raw = path.read_bytes()
        require(len(raw) == 8064 and not any(raw), '48 kHz output contains nonzero data')
        zeros48.append({'slot': slot, 'sha256': digest(path), 'allZero': True})
    output48 = sum(p['requested_length'] for p in outs.values())
    require(output48 == d48['output_bytes_requested'] == d48['output_bytes_accepted_by_api'], '48 kHz output totals differ')
    duplex48_result.update({'reportedRateHz': 48000, 'inputRequestsCompleted': 4, 'outputRequestsCompleted': 4,
                            'outputBytesRequestedAndAcceptedByApi': output48, 'outputBuffers': zeros48,
                            'nativeRecordSha256': digest(duplex48/'duplex/duplex.json'),
                            'continuityVerified': d48['continuity_verified'], 'analogOutputVerified': d48['analog_output_verified']})
    report = {'generatedUtc': datetime.now(timezone.utc).isoformat(), 'scope': 'Observed bounded SL3 USB input and zero-PCM output with saved trace consistency',
              'nativeSha256': native_sha, 'buildManifestSha256': digest(build_path), 'listing': list_result,
              'capture': capture_result, 'silentDuplex': duplex_result, 'rateChange48k': rate_result,
              'capture48k': capture48_result, 'silentDuplex48k': duplex48_result,
              'limits': ['Input signal identity, physical channel mapping and analogue output remain unverified',
                         'Planned intervals and sample count do not prove continuous clocking or latency',
                         'No Windows audio/ASIO application or current Serato/DVS integration tested',
                         'The original Rane binding is restored to its code-39 baseline after redirection',
                         'Raw USB traces, buffers and PCM remain local and are not exported']}
    output = ROOT/'docs/evidence/usbdk-physical-checkpoint-20261030.json'
    output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
