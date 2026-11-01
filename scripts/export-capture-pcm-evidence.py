"""Recheck saved capture content and byte-exact WAVs; no live audio/device access."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import wave

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    (44100, 'usbdk-capture-postrestart-20261030-01', 'capture',
     '22aa87a0aced608d783879532b49649aeb4e9714a4ee74eeb0a00c73c1422d6a',
     '2c2e8d18e31de9ca72fb202a330d44897ac3b74d98ab0ef5722cd124afb6c6ac'),
    (48000, 'usbdk-capture48-postrestart-20261030-01', 'capture48k',
     '9a88d9b240204cfdadca9e284aa72e1b6290c0901e6b06154a48ac9feae60827',
     '302aa53d94e5169c2eb0223f9cc5cd08c47790cb1a0192a9c19b2128669ab8c0'),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def require(value, reason):
    if not value:
        raise ValueError(reason)


def main():
    spec = importlib.util.spec_from_file_location('capture_pcm', ROOT/'scripts/analyse-capture-pcm.py')
    analyser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyser)
    physical_path = ROOT/'docs/evidence/usbdk-physical-checkpoint-20261030.json'
    historical = read(physical_path)
    rows = []
    for rate, name, key, pcm_sha, record_sha in CASES:
        source = ROOT/'tests/results/local'/name
        record_path, pcm_path = source/'capture/capture.json', source/'capture/capture.pcm'
        old = historical[key]
        require(sha(source/'run.json') == old['runRecordSha256']
                and sha(record_path) == old['nativeRecordSha256'] == record_sha
                and sha(pcm_path) == old['pcmSha256'] == pcm_sha, 'Historical capture binding differs')
        metadata, raw = read(record_path), pcm_path.read_bytes()
        output = ROOT/f'analysis/capture-pcm-{rate}-20261101'
        result_path = output/'analysis.json'
        result = read(result_path)
        recomputed = analyser.analyse(metadata, raw, 2)
        require(all(result[k] == value for k, value in recomputed.items())
                and result['captureRecordSha256'] == record_sha
                and result['analyserSha256'] == sha(ROOT/'scripts/analyse-capture-pcm.py'), 'Saved analysis differs')
        wav_path = output/'capture.wav'
        require(sha(wav_path) == result['wave']['sha256'] and result['wave']['channelMask'] == 0
                and result['wave']['pcmPayloadSha256'] == pcm_sha
                and result['wave']['playbackRequested'] is False, 'WAV result binding differs')
        require(wav_path.read_bytes() == analyser.wav_bytes(raw, rate), 'WAV header/payload differs')
        with wave.open(str(wav_path), 'rb') as stream:
            require((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes()) ==
                    (6, 3, rate, metadata['frames']) and stream.readframes(stream.getnframes()) == raw,
                    'Independent WAV reader did not preserve raw PCM')
        split = result['descriptiveSplit']
        full = result['fullCapture']
        prefix, remainder = split['prefix'], split['remainder']
        require(split['selectionIsPostHoc'] is True and split['authorisesDiscardOrWarmupPolicy'] is False
                and prefix['retainedFrames'] + remainder['retainedFrames'] == full['retainedFrames']
                and result['samplesDiscarded'] == result['samplesReplaced'] == 0, 'Prefix comparison discarded samples')
        ranked = sorted(result['packetPeaks'], key=lambda x:max(x['maximumMagnitudeByStreamChannel']), reverse=True)
        rows.append({'reportedRateHz': rate, 'frames': metadata['frames'], 'pcmBytes': len(raw), 'pcmSha256': pcm_sha,
                     'captureRecordSha256': record_sha, 'analysisSha256': sha(result_path), 'wavSha256': sha(wav_path),
                     'packetFrameCountHistogram': dict(sorted(Counter(x['retainedFrames'] for x in result['packetPeaks']).items())),
                     'nominalRetainedDurationMs': result['nominalRetainedDurationMs'],
                     'fullMaximumMagnitudeByStreamChannel': [x['maximumMagnitudeCode'] for x in full['channels']],
                     'fullFirstMaximumMagnitudeFrameByStreamChannel': [x['firstMaximumMagnitudeFrame'] for x in full['channels']],
                     'postHocPrefixPackets': 2, 'postHocBoundaryFrame': split['boundaryRetainedFrame'],
                     'remainingMaximumMagnitudeByStreamChannel': [x['maximumMagnitudeCode'] for x in remainder['channels']],
                     'remainingAcRmsByStreamChannel': [x['acRmsCode'] for x in remainder['channels']],
                     'largestFourPacketPeaks': ranked[:4], 'railSamples': sum(x['railSamples'] for x in full['channels']),
                     'captureClaimsContinuity': result['captureClaimsContinuity'], 'wiringKnown': False})
    tests_path = ROOT/'analysis/capture-pcm-20261101-tests.log'
    tests = tests_path.read_text()
    require('Ran 12 tests' in tests and tests.rstrip().endswith('OK'), 'PCM tests did not pass')
    result = {'scope': __doc__, 'captures': rows, 'focusedSoftwareTestsPassed': 12,
              'testLogSha256': sha(tests_path), 'testSourceSha256': sha(ROOT/'tests/test_capture_pcm.py'),
              'analyserSha256': sha(ROOT/'scripts/analyse-capture-pcm.py'),
              'exporterSha256': sha(Path(__file__)), 'historicalPhysicalSummarySha256': sha(physical_path),
              'historicalCaptureWorkerSha256': historical['nativeSha256'], 'newDeviceOperation': False,
              'playbackRequested': False, 'samplesDiscarded': 0, 'warmupOrDiscardPolicyValidated': False,
              'analogueSignalVerified': False, 'physicalJackMappingVerified': False,
              'currentWorkerAudioVerified': False, 'loopbackLatencyVerified': False,
              'limits': ['The high-magnitude early samples are real saved values; their physical/firmware/transport cause is unproved.',
                         'Input wiring and intended signal were not recorded for these captures.',
                         'Both records explicitly lack verified continuity; WAV timestamps cannot recreate it.',
                         'These earlier finite captures do not validate the current worker or a stream-start suppression policy.']}
    (ROOT/'docs/evidence/capture-pcm-20261101.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print('Verified two original PCM captures, byte-exact six-channel WAVs and descriptive startup differences; no new hardware/audio test')


if __name__ == '__main__':
    main()
