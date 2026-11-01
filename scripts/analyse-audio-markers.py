"""Generate/analyse bounded PCM files offline; never open or play an audio device."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import wave

import numpy as np

RATES = (44100, 48000)
CHANNELS = 6
MARKER_FRAMES = 4096
PEAK = 0.015  # File-generation peak only; analogue level/gain is unknown.
MAX_SECONDS = 10


def require(ok, message):
    if not ok:
        raise ValueError(message)


def marker(channel):
    require(type(channel) is int and 0 <= channel < CHANNELS, 'Invalid reference channel')
    # Hash-derived chips avoid a random-generator/version-dependent reference.
    raw = b''.join(hashlib.sha256(f'SL3 marker v1/{channel}/{i}'.encode()).digest() for i in range(4))
    chips = np.unpackbits(np.frombuffer(raw, dtype=np.uint8)).astype(np.float64)*2-1
    samples = np.repeat(chips, 4)
    samples *= np.minimum(1, np.minimum(np.arange(MARKER_FRAMES), np.arange(MARKER_FRAMES)[::-1])/64)
    samples -= np.mean(samples)
    return samples*(PEAK/np.max(np.abs(samples)))


def stimulus(rate):
    require(type(rate) is int and rate in RATES, 'Unsupported rate')
    data = np.zeros((2*rate, CHANNELS), dtype=np.float64)
    for channel in range(CHANNELS):
        start = rate//10+channel*(rate//4)
        data[start:start+MARKER_FRAMES, channel] = marker(channel)
    return data


def pcm24_bytes(data):
    data = np.asarray(data, dtype=np.float64)
    require(data.ndim == 2 and 1 <= data.shape[1] <= CHANNELS and np.all(np.isfinite(data))
            and np.max(np.abs(data), initial=0) <= 1, 'Invalid PCM samples')
    values = np.rint(data*8388607).astype(np.int32).reshape(-1)
    return np.column_stack((values & 255, (values >> 8) & 255, (values >> 16) & 255)).astype(np.uint8).tobytes()


def wav_bytes(data, rate):
    require(type(rate) is int and rate in RATES and 0 < len(data) <= rate*MAX_SECONDS, 'Invalid PCM duration/rate')
    payload = pcm24_bytes(data)
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setnchannels(data.shape[1])
        stream.setsampwidth(3)
        stream.setframerate(rate)
        stream.writeframes(payload)
    return output.getvalue()


def read_wav(path):
    limit = 48000*MAX_SECONDS*CHANNELS*3+65536
    require(44 <= path.stat().st_size <= limit, 'WAV file exceeds bounds')
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    require(44 <= len(raw) <= limit, 'WAV file changed or exceeds bounds')
    with wave.open(io.BytesIO(raw), 'rb') as stream:
        rate, channels, count = stream.getframerate(), stream.getnchannels(), stream.getnframes()
        require(rate in RATES and 1 <= channels <= CHANNELS and stream.getsampwidth() == 3
                and stream.getcomptype() == 'NONE', 'Expected 44.1/48 kHz packed PCM24, one to six channels')
        require(0 < count <= rate*MAX_SECONDS, 'WAV frame count exceeds bounds')
        payload = stream.readframes(count+1)
        require(len(payload) == count*channels*3, 'Truncated or inconsistent PCM payload')
    triples = np.frombuffer(payload, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
    integers = triples[:, 0] | triples[:, 1] << 8 | triples[:, 2] << 16
    integers = ((integers ^ 0x800000)-0x800000).reshape(count, channels)
    return raw, rate, integers


def correlate_valid(capture, reference):
    """Normalized, DC-removed, linear full-template correlation at every valid start."""
    capture, reference = np.asarray(capture, dtype=np.float64), np.asarray(reference, dtype=np.float64)
    require(capture.ndim == reference.ndim == 1 and 2 <= len(reference) <= len(capture)
            and np.all(np.isfinite(capture)) and np.all(np.isfinite(reference)), 'Invalid correlation inputs')
    reference = reference-np.mean(reference)
    energy = float(reference@reference)
    require(energy > 0, 'Reference has no varying signal')
    count, size = len(reference), 1 << (len(capture)+len(reference)-2).bit_length()
    numerator = np.fft.irfft(np.fft.rfft(capture, size)*np.fft.rfft(reference[::-1], size), size)
    numerator = numerator[count-1:len(capture)]
    sums = np.concatenate(([0.0], np.cumsum(capture)))
    squares = np.concatenate(([0.0], np.cumsum(capture*capture)))
    variance = np.maximum(0, squares[count:]-squares[:-count]-(sums[count:]-sums[:-count])**2/count)
    scores = np.zeros_like(numerator)
    usable = variance > count*1e-12  # Ignore windows below one-millionth full-scale RMS.
    scores[usable] = numerator[usable]/np.sqrt(variance[usable]*energy)
    return np.clip(scores, -1, 1)


def analyse(reference_path, capture_path):
    reference_raw, rate, reference = read_wav(reference_path)
    require(reference_raw == wav_bytes(stimulus(rate), rate), 'Reference is not the canonical six-channel marker WAV')
    capture_raw, capture_rate, captured = read_wav(capture_path)
    require(rate == capture_rate and len(captured) >= MARKER_FRAMES, 'Capture rate/duration differs')
    rows = []
    for channel in range(captured.shape[1]):
        samples = captured[:, channel].astype(np.float64)/8388608
        matches = []
        for output in range(CHANNELS):
            start = rate//10+output*(rate//4)
            template = reference[start:start+MARKER_FRAMES, output].astype(np.float64)/8388608
            scores = correlate_valid(samples, template)
            peak = int(np.argmax(np.abs(scores)))
            signed = float(scores[peak])
            other = np.abs(scores).copy()
            other[max(0, peak-MARKER_FRAMES//8):peak+MARKER_FRAMES//8+1] = 0
            matches.append({'referenceOutputIndex': output, 'signedPeakCorrelation': signed,
                            'markerStartInCaptureFrames': peak, 'markerStartInReferenceFrames': start,
                            'secondSeparatedPeakCorrelation': float(np.max(other, initial=0))})
        matches.sort(key=lambda row: abs(row['signedPeakCorrelation']), reverse=True)
        best, runner_up = matches[:2]
        score = abs(best['signedPeakCorrelation'])
        rails = int(np.count_nonzero((captured[:, channel] >= 8388607) | (captured[:, channel] <= -8388607)))
        reasons = []
        if score < 0.8: reasons.append('weak_correlation')
        if score-abs(runner_up['signedPeakCorrelation']) < 0.15: reasons.append('ambiguous_reference')
        if best['secondSeparatedPeakCorrelation'] >= 0.8: reasons.append('repeated_or_ambiguous_position')
        if rails: reasons.append('full_scale_samples')
        rows.append({'captureInputIndex': channel, 'candidateOutputIndex': None if reasons else best['referenceOutputIndex'],
                     'rejectionReasons': reasons, 'fullScaleRailSampleCount': rails,
                     'peakFullScale': float(np.max(np.abs(samples))),
                     'bestMatch': best, 'runnerUpMatch': runner_up,
                     'relativeFileOffsetFrames': None if reasons else best['markerStartInCaptureFrames']-best['markerStartInReferenceFrames']})
    return {'schema': 'sl3.offline-marker-analysis.v1', 'scope': 'File correlation candidates; physical provenance is unverified',
            'captureSourceKind': 'unverified_file',
            'rateHz': rate, 'captureFrames': len(captured), 'captureChannels': captured.shape[1], 'channels': rows,
            'referenceSha256': hashlib.sha256(reference_raw).hexdigest(), 'captureSha256': hashlib.sha256(capture_raw).hexdigest(),
            'producerSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'numpyVersion': np.__version__,
            'physicalChannelMappingVerified': False, 'measuredLatencyAvailable': False,
            'limits': ['Channel indexes do not identify physical jacks without recorded wiring and hardware provenance.',
                       'Relative file offsets include arbitrary capture/playback origins and are not ASIO or round-trip latency.',
                       'Correlation thresholds are diagnostic heuristics, not calibrated physical acceptance criteria.',
                       'Filtering, clock drift and analogue noise can reject a real route; no resampling or alignment repair is applied.',
                       'Full-scale rail samples flag a level problem but do not alone prove distortion.',
                       'Marker correlation does not establish level calibration, continuity, sustained audio or DVS.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    generate = sub.add_parser('generate')
    generate.add_argument('--rate', type=int, choices=RATES, required=True)
    generate.add_argument('--output', type=Path, required=True)
    inspect = sub.add_parser('analyse')
    inspect.add_argument('--reference', type=Path, required=True)
    inspect.add_argument('--capture', type=Path, required=True)
    inspect.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists() and args.output.parent.is_dir(), 'Expected a new output in an existing folder')
    result = wav_bytes(stimulus(args.rate), args.rate) if args.action == 'generate' else (
        json.dumps(analyse(args.reference, args.capture), indent=2, allow_nan=False)+'\n').encode('utf-8')
    with args.output.open('xb') as stream:
        stream.write(result)
    print(json.dumps({'action': args.action, 'output': str(args.output), 'deviceAccess': False,
                      'bytes': len(result), 'sha256': hashlib.sha256(result).hexdigest()}))


if __name__ == '__main__':
    main()
