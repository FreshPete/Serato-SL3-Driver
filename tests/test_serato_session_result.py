import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

API = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/inspect-serato-session-result.py'))


class ResultInspectionTest(unittest.TestCase):
    def fixture(self, root):
        host = root/'host'; host.mkdir()
        capsule = root/'capsule'; capsule.mkdir(); (capsule/'broker-session').mkdir()
        records = {
            host/'intent.json': {'schema':'sl3.startup-supervisor-intent.v1', 'applicationSha256':'app',
                                  'preparationSha256':'shim','deploymentManifestSha256':'native'},
            host/'result.json': {'schema':'sl3.startup-supervisor-result.v1','supervisionCompleted':True,
                'asioStartObserved':True,'stagedAsioVerified':True,'tracerDetached':True,'error':None,
                'endReason':'application_exited','process':{'processStarted':True,'processExited':True,
                'jobEmpty':True,'observerForcedTermination':False,'exitCode':0,'closeRequested':False}},
            capsule/'broker-session/result.json': {'schema':'sl3.broker-controller-result.v1','successful':True,
                'failed':False,'ownerFailureCode':'none','processExited':True,'jobEmpty':True,
                'ioRetiredVerified':True,'deviceReleasedVerified':True},
            capsule/'session-final.json': {'restored':True,'registrationAbsent':True,'error':None,'receiptState':'success'},
        }
        records[capsule/'broker-clean.json'] = {**records[capsule/'broker-session/result.json'],'controllerExited':True}
        plan = root/'plan.json'
        plan.write_text(json.dumps({'schema':'sl3.serato-session-plan.v1','capsule':{'path':str(capsule/'capsule.json')},
            'hostOutput':str(host),'application':{'sha256':'app'},'preparedShim':{'sha256':'shim'},'nativeBundle':{'sha256':'native'}}))
        return records, plan, hashlib.sha256(plan.read_bytes()).hexdigest()

    def check(self, records, plan, digest):
        for path, record in records.items():path.write_text(json.dumps(record))
        return API['inspect'](plan,digest)

    def test_consistent_manual_exit_is_reported_without_physical_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            records,plan,digest=self.fixture(Path(temporary)); result=self.check(records,plan,digest)
            self.assertTrue(result['cleanSessionReported'])
            self.assertFalse(result['physicalAudioVerified']);self.assertFalse(result['currentDeviceStateVerified'])

    def test_retired_owner_failure_does_not_become_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            records,plan,digest=self.fixture(Path(temporary))
            for path in list(records):
                if path.name in ('broker-clean.json','result.json') and 'capsule' in path.parts:
                    records[path].update(successful=False,failed=True,ownerFailureCode='client_exited_running')
            result=self.check(records,plan,digest)
            self.assertTrue(result['checks']['workerAndControllerRetirementReported'])
            self.assertFalse(result['cleanSessionReported'])

    def test_forced_exit_and_contradictory_worker_report_fail_independently(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);records,plan,digest=self.fixture(root)
            records[root/'host/result.json']['process']['observerForcedTermination']=True
            records[root/'capsule/broker-session/result.json']['deviceReleasedVerified']=False
            result=self.check(records,plan,digest)
            self.assertFalse(result['checks']['hostShutdownReportedClean'])
            self.assertFalse(result['checks']['workerAndControllerRetirementReported'])

    def test_missing_report_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);records,plan,digest=self.fixture(root)
            records.pop(root/'capsule/session-final.json')
            result=self.check(records,plan,digest)
            self.assertFalse(result['cleanSessionReported']);self.assertEqual(len(result['missingOrInvalidReports']),1)

    def test_wrong_plan_or_wrong_intent_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);records,plan,digest=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'plan differs'):API['inspect'](plan,'0'*64)
            records[root/'host/intent.json']['applicationSha256']='another app'
            result=self.check(records,plan,digest)
            self.assertFalse(result['cleanSessionReported']);self.assertFalse(result['checks']['intentMatchesReviewedPlan'])

    def test_observer_close_is_separate_from_manual_exit_and_boolean_is_not_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);records,plan,digest=self.fixture(root)
            records[root/'host/result.json']['process']['closeRequested']=True
            result=self.check(records,plan,digest)
            self.assertTrue(result['checks']['hostShutdownReportedClean'])
            self.assertFalse(result['checks']['exitPrecededObserverClose'])
            records[root/'host/result.json']['process']['exitCode']=False
            self.assertFalse(self.check(records,plan,digest)['checks']['hostShutdownReportedClean'])


if __name__ == '__main__':unittest.main()
