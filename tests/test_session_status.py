from pathlib import Path
import runpy
import tempfile
import unittest

API = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/inspect-serato-session-status.py'))


class SessionStatusTest(unittest.TestCase):
    def fixture(self):
        saved = {'checks': {name: True for name in ('intentMatchesReviewedPlan', 'startupAndDetachReported',
            'hostShutdownReportedClean', 'workerAndControllerRetirementReported', 'brokerSessionReportedSuccessful',
            'restorationReported', 'exitPrecededObserverClose')}, 'missingOrInvalidReports': []}
        host = {'schema': 'sl3.startup-supervisor-result.v1', 'endReason': 'application_exited',
                'process': {'processExited': True, 'jobEmpty': True, 'exitCode': 0, 'observerForcedTermination': False}}
        return {'saved': saved, 'host': host, 'stage': {'restored': True, 'registrationAbsent': True,
                'error': None, 'receiptState': 'success'}, 'owners': {'runner': {'state': 'exited'},
                'supervisor': {'state': 'exited'}}, 'current': {'currentSetupClean': True},
                'stop_valid': False, 'issues': [], 'has_intent': True}

    def test_complete_needs_reports_current_setup_and_retired_owners(self):
        values = self.fixture(); result = API['summarize'](**values)
        self.assertEqual(result['phase'], 'completed')
        self.assertTrue(result['completionEvidenceConsistent'])
        for changed in ({'current': {'currentSetupClean': False}}, {'owners': {'runner': {'state': 'unknown'}}},
                        {'issues': [{'record': 'final', 'message': 'partial'}]}):
            self.assertFalse(API['summarize'](**{**values, **changed})['completionEvidenceConsistent'])

    def test_controlled_stop_is_distinct_from_manual_close_and_deadline(self):
        values = self.fixture(); values['host'].update(endReason='manual_stop', userStopRequested=True)
        values['saved']['checks']['exitPrecededObserverClose'] = False; values['stop_valid'] = True
        result = API['summarize'](**values)
        self.assertTrue(result['completionEvidenceConsistent']); self.assertEqual(result['closeKind'], 'requested_stop')
        values['stop_valid'] = False
        self.assertFalse(API['summarize'](**values)['completionEvidenceConsistent'])
        values['host']['endReason'] = 'viewing_limit'; values['stop_valid'] = True
        self.assertFalse(API['summarize'](**values)['completionEvidenceConsistent'])

    def test_forced_exit_remains_unsuccessful_after_restoration(self):
        values = self.fixture(); values['saved']['checks']['hostShutdownReportedClean'] = False
        values['host']['process'].update(observerForcedTermination=True, exitCode=1)
        values['host']['endReason'] = 'viewing_limit'
        result = API['summarize'](**values)
        self.assertEqual(result['phase'], 'ended_unverified')
        self.assertTrue(result['originalSetupCurrentlyClean']); self.assertFalse(result['completionEvidenceConsistent'])
        self.assertTrue(result['hostOutcome']['observerForcedTermination'])

    def test_broker_failure_is_not_hidden_by_retirement(self):
        values = self.fixture(); values['saved']['checks']['brokerSessionReportedSuccessful'] = False
        result = API['summarize'](**values)
        self.assertFalse(result['completionEvidenceConsistent']); self.assertTrue(result['originalSetupCurrentlyClean'])

    def test_live_owner_prevents_completion_and_shows_cleanup(self):
        values = self.fixture(); values['owners']['runner']['state'] = 'alive'
        result = API['summarize'](**values)
        self.assertEqual(result['phase'], 'stopping'); self.assertFalse(result['completionEvidenceConsistent'])

    def test_startup_progress_requires_detach_event_and_bound_intent(self):
        values = self.fixture(); values.update(host=None, stage=None, owners={'supervisor': {'state': 'alive'}})
        self.assertEqual(API['summarize'](**values)['phase'], 'starting')
        self.assertEqual(API['summarize'](**values, startup_reported=True)['phase'], 'running')
        self.assertEqual(API['summarize'](**{**values, 'stop_valid': True}, startup_reported=True)['phase'], 'stopping')

    def test_unused_broker_cancellation_does_not_claim_completed_audio(self):
        values = self.fixture(); values['host'].update(endReason='manual_stop_during_startup', userStopRequested=True)
        values['stage']['receiptState'] = 'absent'; values['stop_valid'] = True
        values['saved']['checks']['startupAndDetachReported'] = False
        values['saved']['checks']['workerAndControllerRetirementReported'] = False
        values['saved']['checks']['restorationReported'] = False
        values['saved']['missingOrInvalidReports'] = ['worker report absent as expected']
        result = API['summarize'](**values, unused_broker=True)
        self.assertEqual(result['phase'], 'cancelled_restored')
        self.assertTrue(result['cancellationRestorationEvidenceConsistent']); self.assertFalse(result['completionEvidenceConsistent'])
        self.assertTrue(API['summarize'](**values)['recoveryReviewNeeded'])

    def test_prepared_and_unknown_are_separate(self):
        values = self.fixture(); values.update(host=None, stage=None, has_intent=False,
            owners={'runner': {'state': 'not_recorded'}, 'supervisor': {'state': 'not_recorded'}})
        self.assertEqual(API['summarize'](**values)['phase'], 'prepared')
        values['issues'] = [{'record': 'runner', 'message': 'partial'}]
        self.assertEqual(API['summarize'](**values)['phase'], 'unknown')

    def test_missing_retirement_needs_review_even_with_restored_files(self):
        values = self.fixture(); values['saved']['checks']['workerAndControllerRetirementReported'] = False
        result = API['summarize'](**values)
        self.assertTrue(result['recoveryReviewNeeded']); self.assertFalse(result['completionEvidenceConsistent'])

    def test_partial_events_do_not_advance_progress(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'events.jsonl'; issues = []
            path.write_bytes(b'{"event":"trace_ready"}\n{"event":"diagnostic_tracer_detached"}')
            value = API['progress'](path, issues)
            self.assertFalse(value['startupAndDetachEventReported']); self.assertEqual(value['lastCompleteEvent'], 'trace_ready')
            with path.open('ab') as stream: stream.write(b'\n')
            self.assertTrue(API['progress'](path, issues)['startupAndDetachEventReported'])
            self.assertFalse(issues)

    def test_partial_result_is_unknown_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'result.json'; path.write_bytes(b'{'); issues = []
            self.assertIsNone(API['record'](path, issues, 'host'))
            self.assertTrue(issues); self.assertEqual(path.read_bytes(), b'{')


if __name__ == '__main__':
    unittest.main()
