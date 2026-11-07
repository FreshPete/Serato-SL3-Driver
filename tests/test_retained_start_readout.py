from pathlib import Path
import runpy
import unittest

API = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/read-retained-start-result.py'))
PROCESS = {'pid':100,'creationFileTimeUtc':'134385369433350121','imagePath':'C:/fixture.exe',
           'elevated':False,'tokenQueried':True}
OBSERVER = {'schema':'sl3.asio-module-observation.v1','process':PROCESS,'applicationSha256':'1'*64,
            'moduleFileSha256':'2'*64,'completedModuleSamples':1,'modulePathObserved':'C:/driver.dll',
            'asioCallsObserved':False,'moduleAbsenceProved':False}
CLIENT = {'pid':100,'creationFileTimeUtc':PROCESS['creationFileTimeUtc'],
          'admissionReplySent':True,'streamStartReplies':0,'detachAcknowledged':True}
BROKER = {'schema':'sl3.broker-controller-result.v1','kind':'simulated','published':True,
          'nativeDeviceAcquired':False,'clientObservations':[CLIENT],'clientObservationsTruncated':False,
          'failed':False,'terminationRequested':False,'ioRetiredVerified':True,
          'deviceReleasedVerified':True,'processExited':True,'jobEmpty':True}


class ReadoutTests(unittest.TestCase):
    def test_enumeration_and_streaming_are_separate(self):
        broker = {**BROKER,'clientObservations':[CLIENT,{**CLIENT,'streamStartReplies':2}]}
        result = API['summarize'](OBSERVER,broker)
        self.assertTrue(result['moduleLoadObserved'])
        self.assertEqual(result['matchingAdmissionReplies'],2)
        self.assertEqual(result['matchingStreamStartReplies'],2)
        self.assertFalse(result['applicationCallbacksVerified'])
        self.assertFalse(result['nativeAcquisitionReported'])

    def test_pid_reuse_and_unknown_creation_do_not_match(self):
        broker = {**BROKER,'clientObservations':[{**CLIENT,'creationFileTimeUtc':'1'},
                                                {**CLIENT,'creationFileTimeUtc':'0'}]}
        result = API['summarize'](OBSERVER,broker)
        self.assertTrue(result['moduleLoadObserved'])
        self.assertEqual(result['matchingChallengedConnections'],0)
        self.assertFalse(result['absenceProved'])

    def test_module_load_can_be_missed_and_broker_match_retained(self):
        observer = {**OBSERVER,'modulePathObserved':None}
        result = API['summarize'](observer,BROKER)
        self.assertFalse(result['moduleLoadObserved'])
        self.assertEqual(result['matchingAdmissionReplies'],1)

    def test_module_disappearance_requires_a_later_same_process_sample(self):
        observer = {**OBSERVER,'completedModuleSamples':3,'followUpModuleSamples':2,'moduleDisappearanceSampled':True}
        result = API['summarize'](observer,BROKER)
        self.assertTrue(result['moduleDisappearanceSampled'])
        self.assertEqual(result['followUpModuleSamples'],2)
        self.assertFalse(result['applicationCallbacksVerified'])
        self.assertIsNone(API['summarize'](OBSERVER,BROKER)['moduleDisappearanceSampled'])
        for invalid in ({**observer,'followUpModuleSamples':0},{**observer,'modulePathObserved':None},
                        {**observer,'completedModuleSamples':2}):
            with self.subTest(observer=invalid), self.assertRaises(ValueError):
                API['summarize'](invalid,BROKER)

    def test_interrupted_client_and_worker_release_are_separate(self):
        broker = {**BROKER,'failed':True,'clientObservations':[{**CLIENT,'detachAcknowledged':False}]}
        result = API['summarize'](OBSERVER,broker)
        self.assertTrue(result['brokerFailureReported'])
        self.assertTrue(result['workerRetirementReported'])
        self.assertEqual(result['matchingDetachAcknowledgements'],0)

    def test_truncation_preserves_only_positive_observations(self):
        broker = {**BROKER,'clientObservations':[CLIENT]+[{**CLIENT,'pid':200}]*15,
                  'clientObservationsTruncated':True}
        result = API['summarize'](OBSERVER,broker)
        self.assertTrue(result['brokerObservationsTruncated'])
        self.assertEqual(result['matchingAdmissionReplies'],1)
        self.assertFalse(result['absenceProved'])

    def test_restore_must_be_successful_and_observe_original_state(self):
        restore = {'schema':'sl3.on-demand-test-action.v1','action':'restore','successful':True,'after':API['CLEAN']}
        self.assertTrue(API['summarize'](OBSERVER,BROKER,restore)['originalSetupReportedByRestore'])
        self.assertFalse(API['summarize'](OBSERVER,BROKER,{**restore,'successful':False})['originalSetupReportedByRestore'])
        self.assertIsNone(API['summarize'](OBSERVER,BROKER)['originalSetupReportedByRestore'])

    def test_malformed_identity_and_contradictory_rows_refused(self):
        for bad in ({**CLIENT,'pid':True},{**CLIENT,'creationFileTimeUtc':'01'},
                    {**CLIENT,'streamStartReplies':1,'admissionReplySent':False}):
            with self.subTest(row=bad), self.assertRaises(ValueError):
                API['summarize'](OBSERVER,{**BROKER,'clientObservations':[bad]})


if __name__=='__main__':
    unittest.main()
