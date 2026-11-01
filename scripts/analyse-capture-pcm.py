"""Analyse saved finite SL3 PCM and optionally export it unchanged as a six-channel WAV.

No device access or playback. Packet indices identify retained sample order,
not proven USB continuity, physical jacks, analogue quality or latency.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

CHANNELS, WIDTH, FRAME_BYTES, FULL_SCALE = 6, 3, 18, 1 << 23


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def integer(value):
    return type(value) is int and value >= 0


def decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 256 * 126 and len(raw) % FRAME_BYTES == 0,
            'Expected bounded, complete six-channel packed-24 frames')
    return [tuple(int.from_bytes(raw[i+c*WIDTH:i+(c+1)*WIDTH], 'little', signed=True)
                  for c in range(CHANNELS)) for i in range(0, len(raw), FRAME_BYTES)]


def dbfs(rms):
    return 20 * math.log10(rms / FULL_SCALE) if rms else None


def statistics(frames):
    require(bool(frames), 'No retained frames for statistics')
    count = len(frames)
    result = []
    for channel in range(CHANNELS):
        values = [frame[channel] for frame in frames]
        total, squares = sum(values), sum(x*x for x in values)
        peak = max(abs(x) for x in values)
        rms = math.sqrt(squares / count)
        # Exact integer centred energy avoids cancellation near a large DC.
        ac_rms = math.sqrt(squares * count - total * total) / count
        result.append({'streamChannel': channel, 'minimumCode': min(values), 'maximumCode': max(values),
                       'maximumMagnitudeCode': peak, 'firstMaximumMagnitudeFrame': next(n for n,x in enumerate(values) if abs(x) == peak),
                       'meanCode': total / count, 'rmsCode': rms, 'acRmsCode': ac_rms,
                       'rmsDbfs': dbfs(rms), 'acRmsDbfs': dbfs(ac_rms), 'zeroSamples': values.count(0),
                       'railSamples': sum(x in (-FULL_SCALE, FULL_SCALE-1) for x in values),
                       'distinctCodes': len(set(values))})
    return {'retainedFrames': count, 'channels': result}


def analyse(metadata, raw, prefix_packets=0):
    require(type(metadata) is dict and type(prefix_packets) is int and 0 <= prefix_packets < 256,
            'Invalid capture or descriptive prefix selection')
    for flag in ('capture_succeeded', 'transfers_succeeded', 'buffer_cleanup_complete',
                 'redirect_and_alternates_cleanup_succeeded'):
        require(metadata.get(flag) is True, 'Capture does not record success/cleanup: ' + flag)
    require(metadata.get('transport') == 'UsbDk 1.0.22' and metadata.get('error') == '', 'Unsupported or failed capture')
    rate = metadata.get('reported_rate_hz')
    require(type(rate) is int and rate in (44100, 48000), 'Unsupported recorded rate')
    for key, expected in (('planned_intervals', 256), ('planned_ms', 32), ('submitted_requests', 4),
                          ('completed_requests', 4), ('zero_packets', 0), ('audio_output_submissions', 0)):
        require(type(metadata.get(key)) is int and metadata[key] == expected, 'Unsupported finite capture geometry: ' + key)
    require(type(metadata.get('continuity_verified')) is bool, 'Missing recorded continuity claim')
    frames = decode(raw)
    require(integer(metadata.get('frames')) and len(frames) == metadata['frames'], 'PCM/record frame count differs')
    packets = metadata.get('packets')
    require(type(packets) is list and len(packets) == 256, 'Expected all 256 packet records')
    rows, cursor = [], 0
    for ordinal, packet in enumerate(packets):
        require(type(packet) is dict, 'Malformed packet record')
        for key, expected in (('request', ordinal//64), ('packet', ordinal%64), ('offset', (ordinal%64)*126),
                              ('status', 0), ('completion_win32_error', 0), ('request_usbd_status', 0)):
            require(type(packet.get(key)) is int and packet[key] == expected, 'Packet order/status differs: ' + key)
        for flag in ('request_attempted', 'request_submitted', 'request_terminal'):
            require(packet.get(flag) is True, 'Packet request not recorded retired: ' + flag)
        length = packet.get('length')
        require(integer(length) and 0 < length <= 126 and length % FRAME_BYTES == 0, 'Invalid returned packet length')
        count = length // FRAME_BYTES
        require(cursor + count <= len(frames), 'Packet slices exceed PCM')
        part = frames[cursor:cursor+count]
        rows.append({'packetOrdinal': ordinal, 'request': ordinal//64, 'packet': ordinal%64,
                     'firstRetainedFrame': cursor, 'retainedFrames': count,
                     'maximumMagnitudeByStreamChannel': [max(abs(f[c]) for f in part) for c in range(CHANNELS)]})
        cursor += count
    require(cursor == len(frames), 'Packet lengths do not cover the PCM exactly')
    result = {'schema': 'sl3.saved-pcm-analysis.v1', 'scope': __doc__, 'reportedRateHz': rate,
              'pcmBytes': len(raw), 'pcmSha256': digest(raw), 'channels': CHANNELS, 'sampleBytes': WIDTH,
              'sampleFormat': 'signed packed 24-bit little endian, interleaved stream channels 0..5',
              'nominalRetainedDurationMs': len(frames)*1000/rate, 'plannedUsbWindowMs': 32,
              'captureClaimsContinuity': metadata['continuity_verified'], 'fullCapture': statistics(frames),
              'packetPeaks': rows, 'descriptivePrefixPackets': prefix_packets,
              'samplesDiscarded': 0, 'samplesReplaced': 0, 'samplesNormalised': False,
              'physicalJackMappingVerified': False, 'analogueSignalVerified': False,
              'roundTripLatencyVerified': False, 'continuityIndependentlyVerified': False}
    if prefix_packets:
        boundary = rows[prefix_packets]['firstRetainedFrame']
        result['descriptiveSplit'] = {'boundaryRetainedFrame': boundary, 'selectionIsPostHoc': True,
                                     'prefix': statistics(frames[:boundary]), 'remainder': statistics(frames[boundary:]),
                                     'authorisesDiscardOrWarmupPolicy': False}
    result['limits'] = ['Statistics describe retained PCM values, not the source wiring or a measured oscillator.',
                        'Packet status success does not establish analogue sample validity or absence of startup artefacts.',
                        'A prefix split is descriptive; every sample remains in the full statistics and optional WAV.',
                        'WAV nominal timing cannot restore unknown capture gaps or prove callback/loopback latency.',
                        'Rail hits and distinct codes do not establish analogue clipping or converter precision.']
    return result


def wav_bytes(raw, rate):
    decode(raw)
    require(type(rate) is int and rate in (44100, 48000), 'Unsupported WAV rate')
    # WAVE_FORMAT_EXTENSIBLE, PCM subtype, valid bits 24, unspecified channel
    # mask. These stream channels are not declared to be 5.1 speaker positions.
    subtype = struct.pack('<IHH8s', 1, 0, 0x10, bytes.fromhex('800000aa00389b71'))
    fmt = struct.pack('<HHIIHHHHI', 0xfffe, CHANNELS, rate, rate*FRAME_BYTES,
                      FRAME_BYTES, 24, 22, 24, 0) + subtype
    body = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(raw)) + raw
    return b'RIFF' + struct.pack('<I', len(body)) + body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New directory in an existing parent')
    parser.add_argument('--describe-prefix-packets', type=int, default=0)
    parser.add_argument('--wav', action='store_true', help='Write an unchanged multichannel WAV; never play it')
    args = parser.parse_args()
    require(not args.output.exists() and args.output.parent.is_dir(), 'Expected a fresh output directory')
    record_path, pcm_path = args.capture/'capture.json', args.capture/'capture.pcm'
    require(0 < record_path.stat().st_size <= 1024*1024 and 0 < pcm_path.stat().st_size <= 256*126,
            'Capture evidence exceeds finite bounds')
    record_raw, raw = record_path.read_bytes(), pcm_path.read_bytes()
    result = analyse(json.loads(record_raw.decode('utf-8-sig')), raw, args.describe_prefix_packets)
    result.update(captureRecordSha256=digest(record_raw), analyserSha256=digest(Path(__file__).read_bytes()))
    require(record_path.read_bytes() == record_raw and pcm_path.read_bytes() == raw, 'Capture changed during analysis')
    args.output.mkdir()
    if args.wav:
        wave = wav_bytes(raw, result['reportedRateHz'])
        with (args.output/'capture.wav').open('xb') as stream:
            stream.write(wave)
        result['wave'] = {'file': 'capture.wav', 'sha256': digest(wave), 'channelMask': 0,
                          'pcmPayloadSha256': digest(raw), 'playbackRequested': False}
    with (args.output/'analysis.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'retainedFrames': result['fullCapture']['retainedFrames'],
                      'reportedRateHz': result['reportedRateHz'], 'samplesDiscarded': 0,
                      'analogueSignalVerified': False, 'playbackRequested': False}))


if __name__ == '__main__':
    main()
