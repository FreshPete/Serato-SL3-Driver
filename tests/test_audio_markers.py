import importlib.util
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location('markers', Path(__file__).parents[1]/'scripts/analyse-audio-markers.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AudioMarkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='sl3-offline-marker-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.reference = self.root/'reference.wav'
        self.reference.write_bytes(module.wav_bytes(module.stimulus(44100), 44100))

    def analyse(self, data, rate=44100):
        capture = self.root/'capture.wav'
        capture.write_bytes(module.wav_bytes(data, rate))
        return module.analyse(self.reference, capture)

    def test_fft_correlation_agrees_with_independent_direct_windows(self):
        x = np.array([0.7, -0.8, 0.1, 0.4, 0.5, -0.6, 0.3])
        y = np.array([-0.4, 0.7, 0.3])
        expected = []
        for i in range(len(x)-len(y)+1):
            left = x[i:i+len(y)]-np.mean(x[i:i+len(y)])
            right = y-np.mean(y)
            expected.append(float(left@right/np.sqrt((left@left)*(right@right))))
        np.testing.assert_allclose(module.correlate_valid(x, y), expected, atol=1e-12)

    def test_permuted_delayed_polarity_inverted_pcm24_candidates(self):
        source = module.stimulus(44100)
        permutation = [5, 2, 0, 4, 1, 3]
        capture = np.zeros((len(source)+347, 6))
        capture[347:] = source[:, permutation]*0.4
        capture[:, 2] *= -1
        result = self.analyse(capture)
        self.assertEqual([r['candidateOutputIndex'] for r in result['channels']], permutation)
        self.assertEqual([r['relativeFileOffsetFrames'] for r in result['channels']], [347]*6)
        self.assertLess(result['channels'][2]['bestMatch']['signedPeakCorrelation'], -0.999)
        self.assertFalse(result['physicalChannelMappingVerified'])
        self.assertFalse(result['measuredLatencyAvailable'])

    def test_silence_produces_no_mapping(self):
        result = self.analyse(np.zeros((10000, 2)))
        self.assertTrue(all(row['candidateOutputIndex'] is None for row in result['channels']))
        self.assertTrue(all('weak_correlation' in row['rejectionReasons'] for row in result['channels']))
        self.assertTrue(all(row['relativeFileOffsetFrames'] is None for row in result['channels']))

    def test_unrelated_noise_produces_no_mapping(self):
        result = self.analyse(np.random.default_rng(17).normal(0, 0.01, (15000, 1)))
        self.assertIsNone(result['channels'][0]['candidateOutputIndex'])

    def test_mixed_output_markers_are_ambiguous(self):
        source = module.stimulus(44100)
        result = self.analyse((source[:, 0]+source[:, 1]).reshape(-1, 1))
        self.assertIn('ambiguous_reference', result['channels'][0]['rejectionReasons'])
        self.assertIsNone(result['channels'][0]['candidateOutputIndex'])

    def test_repeated_marker_has_no_unique_position(self):
        data = np.zeros((18000, 1))
        data[100:100+module.MARKER_FRAMES, 0] = module.marker(0)
        data[9000:9000+module.MARKER_FRAMES, 0] = module.marker(0)
        result = self.analyse(data)
        self.assertIn('repeated_or_ambiguous_position', result['channels'][0]['rejectionReasons'])

    def test_full_scale_rails_prevent_candidate_acceptance(self):
        data = module.stimulus(44100)[:, :1]
        data[0, 0] = -1
        result = self.analyse(data)
        self.assertEqual(result['channels'][0]['fullScaleRailSampleCount'], 1)
        self.assertIn('full_scale_samples', result['channels'][0]['rejectionReasons'])

    def test_rate_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'rate/duration'):
            self.analyse(np.zeros((10000, 1)), 48000)

    def test_arbitrary_reference_rejected(self):
        self.reference.write_bytes(module.wav_bytes(np.zeros((10000, 6)), 44100))
        with self.assertRaisesRegex(ValueError, 'canonical'):
            self.analyse(np.zeros((10000, 1)))

    def test_truncated_payload_rejected(self):
        capture = self.root/'truncated.wav'
        capture.write_bytes(module.wav_bytes(np.zeros((10000, 2)), 44100)[:-3])
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            module.analyse(self.reference, capture)

    def test_48khz_generation_and_analysis(self):
        self.reference.write_bytes(module.wav_bytes(module.stimulus(48000), 48000))
        result = self.analyse(module.stimulus(48000)[:, 4:5], 48000)
        self.assertEqual(result['channels'][0]['candidateOutputIndex'], 4)

    def test_pcm_boundaries_and_nonfinite_values(self):
        capture = self.root/'boundary.wav'
        capture.write_bytes(module.wav_bytes(np.array([[-1.0], [0.0], [1.0]]), 44100))
        _, rate, integers = module.read_wav(capture)
        self.assertEqual(rate, 44100)
        self.assertEqual(integers[:, 0].tolist(), [-8388607, 0, 8388607])
        for value in (float('nan'), float('inf'), 1.1):
            with self.assertRaises(ValueError):
                module.pcm24_bytes(np.array([[value]]))

    def test_cli_refuses_overwrite(self):
        before = self.reference.read_bytes()
        result = subprocess.run([sys.executable, str(Path(module.__file__)), 'generate', '--rate', '48000',
                                 '--output', str(self.reference)], capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.reference.read_bytes(), before)

    def test_declared_frame_count_is_bounded_before_read(self):
        import struct
        raw = bytearray(module.wav_bytes(np.zeros((10000, 1)), 44100))
        struct.pack_into('<I', raw, 40, 0xffffff00)
        capture = self.root/'oversized-count.wav'
        capture.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'frame count'):
            module.analyse(self.reference, capture)


if __name__ == '__main__':
    unittest.main()
