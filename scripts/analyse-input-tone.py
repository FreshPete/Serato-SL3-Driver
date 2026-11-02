"""Fit a declared input tone to saved finite PCM; no device, playback or profile."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re

import numpy as np

_spec = importlib.util.spec_from_file_location('sl3_tone_saved_pcm', Path(__file__).with_name('analyse-capture-pcm.py'))
pcm = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(pcm)
require = pcm.require


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pairs(items):
    value = {}
    for key, item in items:
        require(key not in value, 'Duplicate JSON field')
        value[key] = item
    return value


def parse(raw, limit):
    require(type(raw) is bytes and 0 < len(raw) <= limit, 'Bounded JSON bytes required')
    def invalid(value):
        raise ValueError('Nonfinite JSON number: '+value)
    value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=invalid)
    require(type(value) is dict, 'JSON object required')
    return value


def declaration(raw, record_raw, audio, rate):
    value = parse(raw, 16384)
    require(set(value) == {'schema', 'evidenceKind', 'rateHz', 'toneHz', 'sourceDescription', 'wiringDescription',
                           'controlStateDescription', 'captureRecordSha256', 'pcmSha256'}, 'Exact test declaration fields required')
    require(value['schema'] == 'sl3.input-tone-declaration.v1' and
            value['evidenceKind'] in ('synthetic', 'operator_declared'), 'Explicit synthetic/operator-declared evidence kind required')
    require(type(value['rateHz']) is int and value['rateHz'] == rate, 'Declared/getter rates differ')
    frequency = value['toneHz']
    require(type(frequency) in (int, float) and 0 < frequency <= rate/4 and math.isfinite(frequency),
            'Finite positive declared tone at or below rate/4 required')
    for key in ('sourceDescription', 'wiringDescription', 'controlStateDescription'):
        text = value[key]
        require(type(text) is str and 0 < len(text.strip()) <= 512 and all(c.isprintable() for c in text),
                'Bounded nonempty printable source/wiring/control descriptions required')
    for key, data in [('captureRecordSha256', record_raw), ('pcmSha256', audio)]:
        require(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]) and value[key] == digest(data),
                'Declaration does not bind actual input bytes: '+key)
    return value


def fit(frames, rate, frequency, first, end):
    count = end-first
    cycles = count*frequency/rate
    result = {'firstRetainedFrame': first, 'endRetainedFrameExclusive': end, 'frames': count,
              'nominalCycles': cycles, 'eligible': False}
    if count < 32 or cycles < 3:
        result['reason'] = 'At least 32 frames and three nominal cycles required'
        return result
    positions = np.arange(first, end, dtype=np.float64)
    angles = positions*(2*math.pi*frequency/rate)
    design = np.column_stack((np.ones(count), np.sin(angles), np.cos(angles)))
    values = np.asarray(frames[first:end], dtype=np.float64)
    coefficients, _, rank, singular = np.linalg.lstsq(design, values, rcond=None)
    require(rank == 3 and np.all(np.isfinite(coefficients)) and singular[-1] > 0 and
            singular[0]/singular[-1] <= 100, 'Tone fit is rank-deficient or poorly conditioned')
    predicted = design @ coefficients; residual = values-predicted
    channels = []
    for channel in range(6):
        actual = values[:, channel]; remainder = residual[:, channel]
        centred = actual-float(np.mean(actual)); energy = float(np.dot(centred, centred))
        error_energy = float(np.dot(remainder, remainder))
        dc, sine, cosine = (float(x) for x in coefficients[:, channel])
        amplitude = math.hypot(sine, cosine)
        residual_rms = math.sqrt(error_energy/count)
        channels.append({'streamChannel': channel, 'fittedDcCode': dc, 'sineAmplitudeCode': amplitude,
                         'sinePeakDbfs': pcm.dbfs(amplitude),
                         'phaseAtRetainedFrameZeroRadians': math.atan2(cosine, sine) if amplitude else None,
                         'residualRmsCode': residual_rms, 'residualRmsDbfs': pcm.dbfs(residual_rms),
                         'observedAcRmsCode': math.sqrt(energy/count),
                         'explainedCentredEnergyFraction': min(1.0, max(0.0, 1-error_energy/energy)) if energy else None})
    result.update(eligible=True, matrixRank=int(rank), matrixCondition=float(singular[0]/singular[-1]), channels=channels)
    return result


def analyse(record_raw, audio, declaration_raw):
    record = parse(record_raw, 1024*1024)
    base = pcm.analyse(record, audio)
    declared = declaration(declaration_raw, record_raw, audio, base['reportedRateHz'])
    frames = pcm.decode(audio); rate = base['reportedRateHz']; frequency = declared['toneHz']
    full = fit(frames, rate, frequency, 0, len(frames))
    require(full['eligible'], 'Full capture has insufficient declared cycles/frames for this fit')
    request_windows = []
    for request in range(4):
        first = base['packetPeaks'][request*64]['firstRetainedFrame']
        last_packet = base['packetPeaks'][request*64+63]
        end = last_packet['firstRetainedFrame']+last_packet['retainedFrames']
        request_windows.append(dict(fit(frames, rate, frequency, first, end), request=request))
    result = {'schema': 'sl3.saved-input-tone-analysis.v1', 'evidenceKind': declared['evidenceKind'],
              'declaration': declared, 'declarationSha256': digest(declaration_raw),
              'captureRecordSha256': digest(record_raw), 'pcmSha256': digest(audio),
              'numpyVersion': np.__version__, 'reportedRateHz': rate, 'declaredToneHz': frequency,
              'sampleFormat': base['sampleFormat'], 'fullCaptureStatistics': base['fullCapture'],
              'fullCaptureFit': full, 'requestWindowFits': request_windows,
              'samplesDiscarded': 0, 'samplesReplaced': 0, 'samplesNormalised': False,
              'deviceAccess': False, 'playbackRequested': False, 'timingProfileGenerated': False,
              'physicalJackMappingVerified': False, 'analogueSignalVerified': False,
              'physicalClockVerified': False, 'usbContinuityVerified': False, 'latencyMeasured': False,
              'limits': ['Source/wiring/control descriptions are declarations, not independently verified physical evidence.',
                         'The fixed-frequency DC/sine/cosine fit uses retained sample order and the nominal recorded rate.',
                         'Phase is relative to retained frame zero; periodic phase is not a unique delay or round-trip measurement.',
                         'Full statistics include every sample; request windows are predetermined and do not authorize trimming.',
                         'A good fit does not prove analogue wiring, gain in volts, continuity, clock accuracy or DVS.',
                         'No physical pass/fail decision, ASIO timing profile or deployment approval is generated.']}
    json.dumps(result, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--declaration', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Fresh directory in an existing parent')
    args = parser.parse_args()
    require(not args.output.exists() and args.output.parent.is_dir(), 'Fresh output directory required')
    paths = [args.capture/'capture.json', args.capture/'capture.pcm', args.declaration]
    limits = [1024*1024, 256*126, 16384]; raw = []
    for path, limit in zip(paths, limits):
        require(0 < path.stat().st_size <= limit, 'Input file exceeds finite bound')
        data = path.read_bytes(); require(0 < len(data) <= limit, 'Input changed beyond bound'); raw.append(data)
    result = analyse(*raw)
    result['sourceSha256'] = {Path(__file__).name: digest(Path(__file__).read_bytes()),
                              'analyse-capture-pcm.py': digest(Path(__file__).with_name('analyse-capture-pcm.py').read_bytes())}
    require(all(path.read_bytes() == data for path, data in zip(paths, raw)), 'Input changed during analysis')
    args.output.mkdir()
    with (args.output/'analysis.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'output': str(args.output), 'frames': result['fullCaptureFit']['frames'],
                      'evidenceKind': result['evidenceKind'], 'analogueSignalVerified': False,
                      'timingProfileGenerated': False, 'playbackRequested': False}))


if __name__ == '__main__':
    main()
