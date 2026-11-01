"""Read-only consistency gate for a completed traced UsbDk capture run.

This verifies recorded evidence, not hardware attestation, analogue audio,
continuous timing or permission to execute a later scenario.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    if path.stat().st_size > 1024 * 1024:
        raise ValueError(f'JSON evidence exceeds the bounded record size: {path.name}')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    return type(value) is int and value >= 0


def utc(value):
    require(isinstance(value, str), 'Missing UTC timestamp')
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, 'Timestamp needs an explicit timezone')
    return parsed.astimezone(dt.timezone.utc)


def reject_circular_overwrite(header):
    # Lost-event counters do not count intentional circular-file replacement.
    # Old synthetic fixtures omit mode; real tracerpt headers carry geometry.
    if 'LogFileMode' not in header:
        return
    mode = int(header['LogFileMode'], 0)
    if not mode & 2:
        return
    for field in ('BufferSize', 'BuffersWritten', 'MaxFileSize'):
        require(header.get(field, '').isdigit(), 'Missing circular trace geometry: '+field)
    size, written, maximum = (int(header[field]) for field in ('BufferSize', 'BuffersWritten', 'MaxFileSize'))
    require(size > 0 and maximum > 0 and written*size < maximum*1024*1024,
            'Circular trace reached/overwrote file capacity; zero loss counters do not establish full coverage')


def trace_statistics(path):
    path = Path(path)
    require(path.stat().st_size <= 512 * 1024 * 1024, 'Decoded trace exceeds the bounded size')
    ns = '{http://schemas.microsoft.com/win/2004/08/events/event}'
    count, header = 0, None
    for _, event in ET.iterparse(path, events=['end']):
        if event.tag != ns + 'Event':
            continue
        if count == 0:
            provider = event.find(ns + 'System/' + ns + 'Provider')
            require(provider is not None and provider.get('Guid', '').lower() ==
                    '{9e814aad-3204-11d2-9a82-006008a86939}', 'Missing ETW system header')
            header = {item.get('Name'): (item.text or '').strip()
                      for item in event.findall(ns + 'EventData/' + ns + 'Data')}
        count += 1
        require(count <= 2000000, 'Decoded trace exceeds the bounded event count')
        event.clear()
    require(header is not None, 'Empty decoded trace')
    reject_circular_overwrite(header)
    for field in ['EventsLost', 'BuffersLost']:
        require(header.get(field, '').isdigit(), f'Missing ETW loss counter: {field}')
    return {'eventsLost': int(header['EventsLost']), 'buffersLost': int(header['BuffersLost']),
            'eventCount': count, 'session': header.get('SessionNameString'), 'xmlSha256': digest(path)}


def validate(run_directory, expected_native_sha256=None):
    folder = Path(run_directory).resolve(strict=True)
    run = read_json(folder / 'run.json')
    require(run.get('schema') == 'sl3.usbdk.traced-run.v1' and run.get('mode') == 'Capture',
            'A capture-mode record from the traced UsbDk runner is required')
    require(run.get('completed') is True and integer(run.get('nativeExitCode')) and run['nativeExitCode'] == 0 and run.get('error') is None,
            'Prior capture run did not finish successfully')
    require(run.get('secureBootBefore') is True and run.get('secureBootAfter') is True,
            'Prior run does not confirm Secure Boot before/after')
    require(run.get('recoveryConfirmed') is True, 'Prior run does not confirm baseline recovery')
    for name, field in [('before-state.json', 'beforeStateSha256'), ('after-state.json', 'afterStateSha256')]:
        require(digest(folder / name).lower() == str(run.get(field, '')).lower(), 'Recovery snapshot hash changed')
    require(integer(run.get('traceExitCode')) and run['traceExitCode'] == 0 and run.get('traceCleanupConfirmed') is True,
            'Prior trace did not finish/clean up successfully')
    stats = run.get('traceStats', {})
    require(stats == trace_statistics(folder / 'events.xml'), 'Decoded trace statistics or hash changed')
    trace = read_json(folder / 'trace/capture.json')
    require(trace.get('status') == 'window completed' and not trace.get('deleteError') and
            stats.get('session') == trace.get('session') and
            trace.get('startedUtc') == run.get('traceStartedUtc') and
            trace.get('stoppedUtc') == run.get('traceStoppedUtc'), 'Trace session/cleanup record is inconsistent')
    require(integer(stats.get('eventsLost')) and stats['eventsLost'] == 0 and
            integer(stats.get('buffersLost')) and stats['buffersLost'] == 0 and
            integer(stats.get('eventCount')) and stats['eventCount'] > 0, 'Missing or lossy trace evidence')
    native_sha = run.get('nativeSha256', '')
    require(isinstance(native_sha, str) and len(native_sha) == 64 and all(c in '0123456789abcdefABCDEF' for c in native_sha),
            'Missing native executable identity')
    if expected_native_sha256:
        require(native_sha.lower() == expected_native_sha256.lower(), 'Capture used a different native executable; capture again with the tested build')
    record = folder / 'capture/capture.json'
    require(digest(record).lower() == str(run.get('nativeRecordSha256', '')).lower(), 'Native capture record hash changed')
    capture = read_json(record)
    require(capture.get('transport') == 'UsbDk 1.0.22', 'A capture through this UsbDk backend is required')
    for field in ['capture_succeeded', 'transfers_succeeded', 'buffer_cleanup_complete',
                  'redirect_and_alternates_cleanup_succeeded', 'offline_playback_layout_validated']:
        require(capture.get(field) is True, f'Capture prerequisite is not confirmed: {field}')
    for field, expected in [('submitted_requests', 4), ('completed_requests', 4),
                            ('planned_intervals', 256), ('planned_ms', 32),
                            ('zero_packets', 0), ('audio_output_submissions', 0)]:
        require(integer(capture.get(field)) and capture[field] == expected, f'Unexpected capture count: {field}')
    rate = capture.get('reported_rate_hz')
    require(type(rate) is int and rate in [44100, 48000], 'Unrecognized device-reported rate')
    packets = capture.get('packets')
    require(isinstance(packets, list) and len(packets) == 256, 'Exactly 256 packet records are required')
    trace_start, trace_end = utc(run.get('traceStartedUtc')), utc(run.get('traceStoppedUtc'))
    native_start, native_end = utc(capture.get('started_utc')), utc(capture.get('completed_utc'))
    require(trace_start <= native_start <= native_end <= trace_end, 'Native capture is not covered by the trace window')
    require((native_end - native_start).total_seconds() <= 20, 'Prior native run exceeded its bounded window')
    by_key = {}
    for packet in packets:
        request, index = packet.get('request'), packet.get('packet')
        require(integer(request) and 0 <= request < 4 and integer(index) and 0 <= index < 64, 'Invalid packet identity')
        require((request, index) not in by_key, 'Duplicate packet identity')
        for field in ['request_attempted', 'request_submitted', 'request_terminal']:
            require(packet.get(field) is True, f'Packet request is not confirmed: {field}')
        for field in ['status', 'completion_win32_error', 'request_usbd_status']:
            require(integer(packet.get(field)) and packet[field] == 0, f'Packet/request error: {field}')
        require(integer(packet.get('offset')) and packet['offset'] == index * 126, 'IN packet offset is not the prepared stride')
        length = packet.get('length')
        require(integer(length) and 0 < length <= 126 and length % 18 == 0, 'Invalid/empty six-channel packet length')
        submitted, completed = utc(packet.get('submitted_utc')), utc(packet.get('completed_utc'))
        require(native_start <= submitted <= completed <= native_end, 'Packet timestamps fall outside native capture')
        by_key[request, index] = packet
    packed = bytearray()
    evidence_files = [folder / name for name in ['run.json', 'events.xml', 'trace/capture.json', 'before-state.json', 'after-state.json']]
    evidence_files.append(record)
    for request in range(4):
        source = folder / f'capture/registered-{request}.bin'
        raw = source.read_bytes()
        require(len(raw) == 64 * 126, 'Unexpected registered-buffer size')
        evidence_files.append(source)
        for index in range(64):
            packet = by_key[request, index]
            packed.extend(raw[packet['offset']:packet['offset'] + packet['length']])
    pcm = folder / 'capture/capture.pcm'
    require(pcm.read_bytes() == packed, 'Packed PCM does not match recorded packet slices (including padding exclusion)')
    evidence_files.append(pcm)
    frames = len(packed) // 18
    require(integer(capture.get('frames')) and capture['frames'] == frames, 'Reported frame count does not match packet data')
    # A conservative prerequisite for the next experiment, not oscillator or
    # gap-free-stream validation. A mismatch requires investigation first.
    require(abs(frames - rate * 0.032) <= 2, 'Frame count is not plausible for 256 planned intervals at the reported rate')
    return {'valid': True, 'scope': 'Recorded capture consistency and prerequisites only',
            'nativeSha256': native_sha, 'reportedRateHz': rate, 'frames': frames,
            'packetCount': len(packets), 'unusedPaddingExcluded': True,
            'files': [{'path': str(path.relative_to(folder)), 'sha256': digest(path)} for path in evidence_files],
            'limits': ['Not hardware attestation or execution approval', 'Analogue signal/channel mapping unverified',
                       'Actual sample clock, USB continuity and latency unverified']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory', nargs='?')
    parser.add_argument('--trace-xml')
    parser.add_argument('--expected-native-sha256')
    args = parser.parse_args()
    try:
        require(bool(args.run_directory) != bool(args.trace_xml), 'Choose one capture directory or --trace-xml')
        result = trace_statistics(args.trace_xml) if args.trace_xml else validate(args.run_directory, args.expected_native_sha256)
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as error:
        print(json.dumps({'valid': False, 'error': str(error)}))
        raise SystemExit(1)
    print(json.dumps(result, indent=2))
