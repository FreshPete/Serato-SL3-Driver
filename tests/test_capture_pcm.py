"""Saved-PCM analysis and WAV export use synthetic bytes only; no audio/device calls."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/analyse-capture-pcm.py'
spec = importlib.util.spec_from_file_location('capture_pcm', SCRIPT)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def packed(frames):
    return b''.join(value.to_bytes(3, 'little', signed=True) for frame in frames for value in frame)


def fixture():
    frames = [(1, -1, 0, 2, -2, 3)] * (256*5)
    record = {'transport': 'UsbDk 1.0.22', 'capture_succeeded': True, 'transfers_succeeded': True,
              'buffer_cleanup_complete': True, 'redirect_and_alternates_cleanup_succeeded': True,
              'error': '', 'reported_rate_hz': 44100, 'planned_intervals': 256, 'planned_ms': 32,
              'submitted_requests': 4, 'completed_requests': 4, 'zero_packets': 0,
              'audio_output_submissions': 0, 'continuity_verified': False, 'frames': len(frames), 'packets': []}
    for ordinal in range(256):
        record['packets'].append({'request': ordinal//64, 'packet': ordinal%64, 'offset': ordinal%64*126,
                                  'status': 0, 'completion_win32_error': 0, 'request_usbd_status': 0,
                                  'request_attempted': True, 'request_submitted': True, 'request_terminal': True,
                                  'length': 90})
    return record, packed(frames)


class PcmTests(unittest.TestCase):
    def test_all_six_signed_channels_and_byte_order(self):
        frames = [(-8388608, 8388607, -1, 0, 1, 0x123456)]
        raw = bytes.fromhex('000080 ffff7f ffffff 000000 010000 563412')
        self.assertEqual(v.decode(raw), frames)

    def test_incomplete_or_empty_frames_refused(self):
        for raw in (b'', bytes(17), bytes(19), bytes(256*126+18)):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                v.decode(raw)

    def test_dc_and_centred_energy(self):
        result = v.statistics([(8388606,)*6, (8388607,)*6])['channels'][0]
        self.assertEqual(result['meanCode'], 8388606.5)
        self.assertEqual(result['acRmsCode'], .5)
        self.assertEqual(result['railSamples'], 1)

    def test_extremes_and_maximum_position(self):
        result = v.statistics([(-8388608,)*6, (8388607,)*6])['channels'][0]
        self.assertEqual(result['maximumMagnitudeCode'], 8388608)
        self.assertEqual(result['firstMaximumMagnitudeFrame'], 0)
        self.assertEqual(result['meanCode'], -.5)
        self.assertEqual(result['acRmsCode'], 8388607.5)
        self.assertEqual(result['railSamples'], 2)

    def test_silence_has_json_null_not_infinity(self):
        result = v.statistics([(0,)*6]*3)
        self.assertIsNone(result['channels'][0]['rmsDbfs'])
        self.assertIsNone(result['channels'][0]['acRmsDbfs'])
        json.dumps(result, allow_nan=False)

    def test_metadata_packet_faults_are_not_analysed_as_success(self):
        record, raw = fixture()
        for field, value in (('status', 1), ('request', 3), ('packet', 1), ('offset', 1),
                             ('length', 89), ('length', 0), ('request_terminal', False),
                             ('completion_win32_error', True), ('request_usbd_status', 1)):
            changed = copy.deepcopy(record)
            changed['packets'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                v.analyse(changed, raw)

    def test_record_failure_frame_count_and_rate_refused(self):
        record, raw = fixture()
        for field, value in (('capture_succeeded', False), ('frames', 1), ('reported_rate_hz', 96000),
                             ('submitted_requests', True), ('continuity_verified', 1), ('audio_output_submissions', 1)):
            changed = copy.deepcopy(record)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                v.analyse(changed, raw)
        with self.assertRaises(ValueError):
            v.analyse(record, raw[:-18])
        with self.assertRaises(ValueError):
            v.analyse(record, raw, 256)

    def test_packet_order_and_full_coverage(self):
        record, raw = fixture()
        record['packets'][0], record['packets'][1] = record['packets'][1], record['packets'][0]
        with self.assertRaises(ValueError):
            v.analyse(record, raw)
        record, raw = fixture()
        record['packets'].pop()
        with self.assertRaises(ValueError):
            v.analyse(record, raw)

    def test_descriptive_split_never_removes_samples(self):
        record, raw = fixture()
        raw = packed([(8388607,)*6]) + raw[18:]
        result = v.analyse(record, raw, 2)
        split = result['descriptiveSplit']
        self.assertEqual(split['boundaryRetainedFrame'], 10)
        self.assertEqual(split['prefix']['retainedFrames']+split['remainder']['retainedFrames'], record['frames'])
        self.assertEqual(result['fullCapture']['channels'][0]['maximumCode'], 8388607)
        self.assertEqual(split['remainder']['channels'][0]['maximumCode'], 1)
        self.assertFalse(split['authorisesDiscardOrWarmupPolicy'])
        self.assertEqual(result['samplesDiscarded'], 0)

    def test_wav_is_interoperable_unspecified_layout_and_byte_exact(self):
        _, raw = fixture()
        encoded = v.wav_bytes(raw, 48000)
        self.assertEqual(struct.unpack_from('<I', encoded, 4)[0], len(encoded)-8)
        self.assertEqual(struct.unpack_from('<I', encoded, 40)[0], 0)
        with wave.open(io.BytesIO(encoded), 'rb') as stream:
            self.assertEqual((stream.getnchannels(), stream.getsampwidth(), stream.getframerate()), (6, 3, 48000))
            self.assertEqual(stream.readframes(stream.getnframes()), raw)

    def test_actual_cli_writes_new_files_and_refuses_reuse(self):
        with tempfile.TemporaryDirectory(prefix='sl3-pcm-cli-') as directory:
            root = Path(directory)
            source, output = root/'capture', root/'analysis'
            source.mkdir()
            record, raw = fixture()
            (source/'capture.json').write_text(json.dumps(record))
            (source/'capture.pcm').write_bytes(raw)
            arguments = [sys.executable, str(SCRIPT), '--capture', str(source), '--output', str(output),
                         '--wav', '--describe-prefix-packets', '2']
            run = subprocess.run(arguments, capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)
            analysis_raw = (output/'analysis.json').read_bytes()
            result = json.loads(analysis_raw)
            self.assertEqual(result['pcmSha256'], hashlib.sha256(raw).hexdigest())
            self.assertFalse(result['wave']['playbackRequested'])
            self.assertEqual(subprocess.run(arguments, capture_output=True, timeout=5).returncode, 1)
            self.assertEqual((output/'analysis.json').read_bytes(), analysis_raw)
            self.assertEqual((source/'capture.pcm').read_bytes(), raw)

    def test_actual_cli_failure_creates_no_output(self):
        with tempfile.TemporaryDirectory(prefix='sl3-pcm-refusal-') as directory:
            root = Path(directory)
            record, raw = fixture()
            record['frames'] += 1
            (root/'capture.json').write_text(json.dumps(record))
            (root/'capture.pcm').write_bytes(raw)
            output = root/'refused'
            run = subprocess.run([sys.executable, str(SCRIPT), '--capture', str(root), '--output', str(output)],
                                 capture_output=True, timeout=5)
            self.assertEqual(run.returncode, 1)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
