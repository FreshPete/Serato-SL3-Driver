"""Report the generated tone in a saved SL3 loopback recording."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy


def envelope_offsets(frames, rate, length, origin, frequencies):
    import numpy as np

    position = np.arange(length)
    fade = rate // 100
    ramp = np.minimum(np.minimum(position, length - 1 - position), fade) / fade
    # Correlate the smoothed onset and end ramps. Carrier phase alone can
    # select another whole cycle, even in a clean recording.
    kernel = np.ones(rate * 4 // 1000)
    measured = np.sqrt(np.apply_along_axis(lambda channel: np.convolve(channel**2, kernel, mode='same'),
                                          0, frames.astype(np.float64)))
    lags = len(frames) - length + 1
    fft_size = 1 << (len(frames) + length - 2).bit_length()
    energy = np.vstack((np.zeros((1, measured.shape[1])), np.cumsum(measured**2, axis=0)))
    window_energy = np.maximum(0, energy[length:] - energy[:-length])
    transformed = np.fft.rfft(measured, fft_size, axis=0)
    observations = []
    for frequency in frequencies:
        samples = np.trunc(265271 * ramp * np.sin(position * (6.283185307179586 * frequency / rate)))
        reference = np.sqrt(np.convolve(samples**2, kernel, mode='same'))
        dot = np.fft.irfft(transformed * np.conj(np.fft.rfft(reference, fft_size))[:, None],
                           fft_size, axis=0)[:lags]
        denominator = np.sqrt(np.dot(reference, reference) * window_energy)
        score = np.divide(dot, denominator, out=np.zeros_like(dot), where=denominator > 0)
        channels = []
        for index in range(measured.shape[1]):
            if not np.any(denominator[:, index] > 0):
                channels.append({'streamChannel': index, 'returnStartFrame': None, 'logicalOffsetFrames': None,
                                 'envelopeSimilarity': None})
                continue
            start = int(np.argmax(score[:, index]))
            channels.append({'streamChannel': index, 'returnStartFrame': start, 'logicalOffsetFrames': start - origin,
                             'envelopeSimilarity': float(np.clip(score[start, index], 0, 1))})
        observations.append({'frequencyHz': frequency, 'channels': channels})
    return observations


def analyse(folder, challenge):
    scripts = Path(__file__).resolve().parent
    timer = runpy.run_path(str(scripts/'validate-driver-timer.py'))
    with (folder/'timer.json').open('rb') as stream:
        checked = timer['validate'](stream.read(8193), challenge, True, False, True)
    length = checked['loopbackPcmBytes']
    with (folder/'loopback.pcm').open('rb') as stream:
        audio = stream.read(length + 1)
    if len(audio) != length:
        raise ValueError('Saved loopback PCM length differs')
    rate = checked['rateHz']
    tone = runpy.run_path(str(scripts/'analyse-input-tone.py'))
    frames = tone['decode_recording'](audio)
    windows = []
    step = rate // 20
    marker_hz = checked.get('stereoMarkerHz')
    for first in range(0, len(frames), step):
        end = min(first + step, len(frames))
        fit = tone['fit'](frames, rate, 997, first, end)
        if marker_hz:
            fit['rightMarkerFit'] = tone['fit'](frames, rate, marker_hz[1], first, end)
        windows.append(fit)
    result = {'schema': 'sl3.timer-loopback-analysis.v1', 'recordSha256': checked['recordSha256'],
              'pcmSha256': hashlib.sha256(audio).hexdigest(), 'rateHz': rate, 'frames': len(frames),
              'toneHz': 997, 'windows': windows, 'physicalWiringVerified': False, 'latencyMeasured': False}
    if marker_hz:
        origin = checked['toneFirstLogicalFrame']
        result.update(stereoMarkerHz=marker_hz, toneFirstLogicalFrame=origin,
                      logicalEnvelopeOffsets=envelope_offsets(frames, rate, checked['toneFramesStaged'], origin, marker_hz))
    return result


def host_marker_returns(frames, origin, count, frequencies, fit):
    rate = 44100
    fade = rate // 100
    candidates = envelope_offsets(frames, rate, count, origin, frequencies)
    returns = []
    for channel, marker in zip((2, 3), candidates):
        candidate = marker['channels'][channel]
        first = candidate['returnStartFrame']
        result = {'streamChannel': channel, 'frequencyHz': marker['frequencyHz'],
                  'envelopeSimilarity': candidate['envelopeSimilarity'], 'acceptedOffsetFrames': None}
        if first is None:
            result['rejection'] = 'No return signal'
        else:
            tone_fit = fit(frames, rate, marker['frequencyHz'], first + fade, first + count - fade)
            result['toneFit'] = tone_fit
            channels = tone_fit['channels']
            expected = channels[channel]
            amplitude = expected['sineAmplitudeCode']
            strongest_other = max(item['sineAmplitudeCode'] for i, item in enumerate(channels) if i != channel)
            if first < origin or candidate['envelopeSimilarity'] < 0.90:
                result['rejection'] = 'Return starts too early or envelope does not match'
            elif amplitude < 1000 or (expected['explainedCentredEnergyFraction'] or 0) < 0.80:
                result['rejection'] = 'Expected marker is weak or poorly fitted'
            elif amplitude < 4 * strongest_other:
                result['rejection'] = 'Marker is not isolated on the expected channel'
            elif (abs(frames[first:first + count, channel]) >= 8388607).any():
                result['rejection'] = 'Return contains clipped samples'
            else:
                result['acceptedOffsetFrames'] = first - origin
        returns.append(result)
    return returns


def analyse_host(folder, worker_sha):
    validator = runpy.run_path(str(Path(__file__).with_name('validate-input-record-probe.py')))
    checked = validator['validate'](folder, worker_sha, host_loopback=True)
    raw = validator['read'](folder/'result.json', 256 * 1024)
    record = json.loads(raw)
    audio = validator['read'](folder/'input.pcm', 8 * 1024 * 1024)
    digest = hashlib.sha256(audio).hexdigest()
    if hashlib.sha256(raw).hexdigest() != checked['resultSha256'] or digest != checked['pcmSha256']:
        raise ValueError('Host evidence changed after validation')
    tone = runpy.run_path(str(Path(__file__).with_name('analyse-input-tone.py')))
    frames = tone['decode_recording'](audio)
    origin, count, frequencies = (record[key] for key in ('markerFirstFrame', 'markerFrames', 'markerHz'))
    returns = host_marker_returns(frames, origin, count, frequencies, tone['fit'])
    result = {'schema': 'sl3.host-loopback-analysis.v2', 'recordSha256': checked['resultSha256'],
            'workerSha256': worker_sha, 'nativeJournal': checked['nativeJournal'],
            'pcmSha256': digest, 'rateHz': 44100, 'markerReturns': returns,
            'bothMarkersAccepted': all(item['acceptedOffsetFrames'] is not None for item in returns),
            'timingProfileWritten': False,
            'directionalLatencyMeasured': False}
    if 'markerOutputChannels' in record:
        result['markerOutputChannels'] = record['markerOutputChannels']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--challenge')
    mode.add_argument('--host-callback', action='store_true')
    parser.add_argument('--worker-sha256')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.host_callback != bool(args.worker_sha256):
        parser.error('--worker-sha256 is required with --host-callback')
    result = analyse_host(args.folder, args.worker_sha256) if args.host_callback else analyse(args.folder, args.challenge)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
