"""Host enumeration cadence interpretation; no native library or USB calls."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('identity_cadence', Path(__file__).resolve().parents[1]/'scripts/export-usb-identity-baseline.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def pair(start, end, complete=True):
    return [{'event': 'snapshot_enter', 'elapsed_seconds': start},
            {'event': 'sample', 'elapsed_seconds': end, 'snapshot': {'complete': complete}}]


class CadenceTests(unittest.TestCase):
    def test_measured_gaps_are_distinct_from_requested_sleep(self):
        result = m.cadence(pair(0, .6)+pair(.85, 1.4), .25)
        self.assertAlmostEqual(result['sampleReturnGapSeconds']['maximum'], .8)
        self.assertAlmostEqual(result['hostEnumerationDurationSeconds']['minimum'], .55)
        self.assertIsNone(result['guaranteedTransientDetectionSeconds'])
        self.assertFalse(result['physicalAudioClockMeasured'])

    def test_single_sample_cannot_supply_a_gap_or_rate(self):
        result = m.cadence(pair(0, 1), .05)
        self.assertEqual(result['sampleReturnGapSeconds'], {'count': 0, 'minimum': None, 'maximum': None, 'mean': None})

    def test_failed_snapshot_still_counts_in_timing(self):
        result = m.cadence(pair(0, 1, False)+pair(1.1, 2), .1)
        self.assertEqual(result['samples'], 2); self.assertEqual(result['completeSamples'], 1)

    def test_invalid_regressing_overlapping_or_incomplete_inputs_rejected(self):
        for rows in [[], pair(0, 1)[:1], pair(1, .5), pair(0, 1)+pair(.5, 2),
                     pair(0, float('nan')), pair(0, float('inf')), pair(0, True)]:
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    m.cadence(rows, .1)
        with self.assertRaises(ValueError):
            m.cadence(pair(0, 1), -1)


if __name__ == '__main__':
    unittest.main()
