"""Synthetic timing analysis only; no USB, driver or analogue proof."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('callback_timing', Path(__file__).resolve().parents[1]/'scripts/analyse-callback-timing.py')
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


def fixture():
    # 44.1 kHz: exactly 128 frames per 128 QPC ticks at 44,100 ticks/sec.
    return {'schema': 'sl3.host-probe.v1', 'simulated': True, 'successful': True,
            'reported_rate_hz': 44100, 'bank_frames': 128, 'callback_counter_frequency': 44100,
            'callbacks': 4, 'first_frame': 0, 'last_frame': 384, 'timing_records_dropped': 0,
            'callback_timings': [[i*128, i*128*1_000_000_000//44100, 1000+i*128] for i in range(4)]}


class CallbackTimingTests(unittest.TestCase):
    def test_nominal(self):
        result = timing.analyse(fixture())
        self.assertEqual(result['softwareDeliveryFramesPerSecond'], 44100)
        self.assertTrue(result['completeCallbackCoverage'])
        self.assertTrue(result['simulated'])
        self.assertFalse(result['latencyMeasured'])
        self.assertFalse(result['physicalClockVerified'])
        self.assertFalse(result['usbContinuityVerified'])

    def test_batched_publication_and_callback_stall(self):
        data = fixture()
        data['callback_timings'][1][1] = 0
        data['callback_timings'][-1][2] += 44100
        result = timing.analyse(data)
        self.assertEqual(result['repeatedPublicationTimestamps'], 1)
        self.assertGreater(result['callbackSpacingNs']['maximum'], 1_000_000_000)
        self.assertLess(result['softwareDeliveryFramesPerSecond'], 44100)

    def test_regression_and_frame_gaps(self):
        for column in range(3):
            data = fixture()
            data['callback_timings'][2][column] = 0
            with self.assertRaises(ValueError):
                timing.analyse(data)

    def test_numeric_validation(self):
        for key in ('callback_counter_frequency', 'callbacks', 'last_frame', 'timing_records_dropped'):
            for value in (-1, True, 1.5, None, 1 << 64):
                data = fixture()
                data[key] = value
                with self.assertRaises(ValueError):
                    timing.analyse(data)

    def test_truncated_coverage_is_explicit(self):
        data = fixture()
        data['callbacks'] = 2051
        data['last_frame'] = 2050*128
        data['callback_timings'] = [[i*128, i*100, i+1000] for i in range(2048)]
        data['timing_records_dropped'] = 3
        result = timing.analyse(data)
        self.assertFalse(result['completeCallbackCoverage'])
        self.assertEqual(result['recordsDropped'], 3)

    def test_short_inconsistent_and_zero_span(self):
        for change in ({'callback_timings': []}, {'callbacks': 5}, {'last_frame': 385},
                       {'timing_records_dropped': 1, 'callbacks': 5, 'last_frame': 512},
                       {'callback_counter_frequency': 0}):
            data = fixture()
            data.update(change)
            with self.assertRaises(ValueError):
                timing.analyse(data)
        data = copy.deepcopy(fixture())
        for row in data['callback_timings']:
            row[2] = 1000
        with self.assertRaises(ValueError):
            timing.analyse(data)


if __name__ == '__main__':
    unittest.main()
