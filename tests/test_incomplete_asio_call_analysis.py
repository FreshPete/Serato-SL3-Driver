import importlib.util
from pathlib import Path
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('partial_analysis', ROOT / 'scripts/inspect-incomplete-asio-call-log.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
event = runpy.run_path(str(ROOT / 'tests/test_asio_call_analysis.py'))['event']


class IncompleteAnalysisTest(unittest.TestCase):
    def test_complete_observed_pairs_do_not_become_complete_session(self):
        result = p.analyze([event(1,7,'begin'), event(1,7,'end')], 42)
        self.assertTrue(result['observedPairsComplete'])
        self.assertFalse(result['completionMarkerUsed'])
        self.assertFalse(result['sessionMetadataComplete'])
        self.assertFalse(result['shutdownVerified'])
        for name in ('sessionStopStatus','reportedEventsLost','reportedBuffersLost'):
            self.assertIsNone(result[name])
        self.assertTrue(result['matchingEventsObserved'])
        self.assertFalse(result['sourceHostIdentityVerified'])
        self.assertFalse(result['wholeHostSequenceVerified'])

    def test_missing_stop_terminal_identifies_observation_not_deadlock(self):
        result = p.analyze([event(9,7,'begin')], 42)
        self.assertEqual(result['unterminatedBegins'], [9])
        self.assertEqual(result['unterminatedBeginDetails'],
                         [{'call':9,'operation':'stop','object':1,'thread':7}])
        self.assertFalse(result['missingTerminalProvesBlockedCall'])
        self.assertEqual(result['completedCalls'], 0)

    def test_empty_log_does_not_claim_matching_calls_or_shutdown(self):
        result = p.analyze([], 42)
        self.assertFalse(result['matchingEventsObserved'])
        self.assertFalse(result['observedPairsComplete'])
        self.assertFalse(result['shutdownVerified'])
        self.assertEqual(result['unterminatedBeginDetails'], [])

    def test_shared_schema_and_pair_validation_still_refuse_mixed_data(self):
        for rows in ([event(1,7,'begin')]*2,
                     [event(1,7,'begin'),event(1,7,'end',tid=8)],
                     [{**event(1,7,'begin'),'pid':43}]):
            with self.assertRaises(ValueError): p.analyze(rows,42)

    def test_empty_rows_still_require_exact_bounded_pid(self):
        for pid in (True,0,-1,2**32,'42'):
            with self.assertRaises(ValueError): p.analyze([],pid)


if __name__ == '__main__': unittest.main()
