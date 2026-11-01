import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

spec = importlib.util.spec_from_file_location('source_runner', Path(__file__).parents[1]/'scripts/test-hub-image-source.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SourceObservationTests(unittest.TestCase):
    def setUp(self):
        self.active = {'sourceActive': True, 'properties': {'systemLoggerModePresent': True, 'clockType': 1, 'logFileMode': 0x02000001,
                       'eventsLost': 0, 'logBuffersLost': 0, 'realTimeBuffersLost': 0}}
        self.absent = {'sourceActive': False, 'properties': None}

    def test_absence_alone_never_establishes_start_or_stop(self):
        for rows in ([], [self.absent], [self.absent, self.absent]):
            self.assertFalse(any(module.evaluate_observations(rows).values()))

    def test_live_then_absent_is_observation_not_timer_proof(self):
        result = module.evaluate_observations([self.absent, self.active, self.absent])
        self.assertTrue(all(result.values()))
        self.assertNotIn('independentStopValidated', result)
        self.assertNotIn('timedExpiryCauseVerified', result)

    def test_return_to_active_invalidates_disappearance(self):
        result = module.evaluate_observations([self.active, self.absent, self.active])
        self.assertFalse(result['sourceDisappearanceObserved'])

    def test_any_observed_wrong_mode_or_clock_fails_flags(self):
        for key, value in (('systemLoggerModePresent', False), ('clockType', 2),
                           ('logFileMode', 0x02000101), ('logFileMode', 0x02000801), ('logFileMode', 0x02000003)):
            row = copy.deepcopy(self.active)
            row['properties'][key] = value
            result = module.evaluate_observations([self.active, row, self.absent])
            self.assertFalse(result['runtimeFlagForwardingVerified'])

    def test_any_loss_is_retained_as_failure(self):
        for key in ('eventsLost', 'logBuffersLost', 'realTimeBuffersLost'):
            row = copy.deepcopy(self.active)
            row['properties'][key] = 1
            self.assertFalse(module.evaluate_observations([row, self.absent])['sampledLossCountersZero'])


class DirectQueryProcessTests(unittest.TestCase):
    def test_direct_interpreter_exit_and_timeout_retirement(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for label,script,timeout in (('exit','import sys; print("query-child"); sys.exit(7)',5),
                                         ('timeout','import time; time.sleep(30)',0.2)):
                log=root/(label+'.log');record=root/(label+'.json')
                if label=='exit':
                    self.assertEqual(module.query_process(['-c',script],timeout,log,record),7)
                    self.assertIn('query-child',log.read_text())
                else:
                    with self.assertRaisesRegex(ValueError,'timed out'):
                        module.query_process(['-c',script],timeout,log,record)
                saved=json.loads(record.read_text())
                self.assertTrue(saved['retired'])
                self.assertEqual(saved['timedOut'],label=='timeout')
                self.assertIsInstance(saved['pid'],int)
                self.assertIsInstance(saved['exitCode'],int)
                self.assertEqual(saved['baseInterpreter'],str(Path(sys._base_executable).resolve()))


@unittest.skipUnless(os.name == 'nt', 'Controller requires Windows; all child actions here are simulated')
class SourceControllerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='sl3-source-controller-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.context = self.root/'context'
        self.capture = self.root/'capture'
        scripts = self.root/'scripts'
        scripts.mkdir()
        self.inputs = {}
        for name in ('inspect-image-source-session.py', 'hub-image-source-action.ps1'):
            # These bytes only bind simulated child reports. They are never executed.
            path = scripts/name
            path.write_text('# simulation-only placeholder', encoding='utf-8')
            self.inputs[name] = module.sha(path)
        preparation = self.root/'preparation.json'
        preparation.write_text('{"simulationOnly":true}', encoding='utf-8')
        self.experiment = {'planOnly': True, 'sourceStarted': False, 'readinessAdmission': False,
                           'queryTimeoutSeconds':3,
                           'queryBaseInterpreter':str(Path(sys._base_executable).resolve()),
                           'queryBaseInterpreterSha256':module.sha(Path(sys._base_executable).resolve()),
                           'inputs': self.inputs, 'preparation': str(preparation),
                           'preparationSha256': module.sha(preparation), 'contextDirectory': str(self.context),
                           'captureRoot': str(self.capture), 'sessionName': 'SL3Image-'+'b'*32,
                           'sessionGuid': '47144616-f8c8-49ef-933d-4eb9c4d77435', 'watchSeconds': 13}
        self.calls = []

    def exercise(self, fault=None, policy='configured'):
        self.experiment['nativeIdentityPolicy'] = policy
        def fake_child(arguments, *, stdout, stderr, timeout, creationflags, cwd):
            self.assertEqual(creationflags, subprocess.CREATE_NO_WINDOW)
            self.assertEqual(cwd, self.root)
            if '-Action' in arguments:
                kind = arguments[arguments.index('-Action')+1]
                self.calls.append(kind)
                self.assertEqual(timeout, 12)
                output = Path(arguments[arguments.index('-Output')+1])
                if fault == 'start-timeout' and kind == 'Start':
                    raise subprocess.TimeoutExpired(arguments, timeout)
                value = {'successful': not (fault == 'cleanup-failure' and kind == 'Cleanup'),
                         'sourceSha256': self.inputs['hub-image-source-action.ps1'],
                         'preparationSha256': self.experiment['preparationSha256'],
                         'sourceCommitted':kind=='Start',
                         'startRequested': kind == 'Start', 'stopRequested': fault == 'cleanup-stop' and kind == 'Cleanup'}
                if fault=='native-uncommitted' and kind=='Start':value['sourceCommitted']=False
                if kind == 'Start' and fault != 'missing-configuration':
                    snapshot_path=output.with_name(output.name+'.committed.json')
                    snapshot={'querySucceeded':True,'status':0,'configurationMatchesExpected':fault!='rejected-configuration',
                              'mismatches':['TraceDataCollector/Guid'] if fault=='rejected-configuration' else [],
                              'error':None,'sourceStarted':False,'readinessAdmission':False,
                              'preparationSha256':self.experiment['preparationSha256'],
                              'collectorName':'[Service]'+self.experiment['sessionName']}
                    snapshot_path.write_text(json.dumps(snapshot),encoding='utf-8')
                    value['committedConfiguration']={'file':snapshot_path.name,'sha256':module.sha(snapshot_path),
                                                     'configurationMatchesExpected':True}
                    if fault=='configuration-hash':value['committedConfiguration']['sha256']='0'*64
                    if fault=='configuration-escape':value['committedConfiguration']['file']='../foreign.json'
                    if fault=='start-timeout-after-snapshot':
                        raise subprocess.TimeoutExpired(arguments,timeout)
                if kind == 'Start' and fault != 'missing-etl':
                    self.capture.mkdir()
                    (self.capture/'images.etl').write_bytes(b'SIMULATED ARTIFACT; NOT AN ETL')
                output.write_text(json.dumps(value), encoding='utf-8')
                return SimpleNamespace(returncode=0 if value['successful'] else 1)
            self.assertEqual(timeout, 3)
            output = Path(arguments[arguments.index('--output')+1])
            label = output.stem
            self.calls.append(label)
            expected_guid=arguments[arguments.index('--session-guid')+1]
            native_fault=isinstance(fault,str) and fault.startswith('native-')
            active = label == 'sample-0' or (label=='sample-0-native-recheck' and fault!='native-gone') or (label == 'before' and fault in ('preexisting-source','native-preexisting')) or (label=='sample-1' and fault=='native-changed-later')
            properties = {'systemLoggerModePresent': True, 'clockType': 1, 'logFileMode': 0x02000001, 'enableFlags':4,
                          'eventsLost': int(fault == 'loss'), 'logBuffersLost': 0, 'realTimeBuffersLost': 0,
                          'logFileName': str(self.capture/'images.etl')} if active else None
            if properties is not None:
                actual_guid='25f55b3e-fb86-44d6-9d12-3d9b9b98e01b' if native_fault else self.experiment['sessionGuid']
                if native_fault and ((fault=='native-changed' and label=='sample-0-native-recheck') or
                                     (fault=='native-changed-later' and label=='sample-1')):actual_guid='2dc60f78-c751-4ec5-a93c-2ee3556da0d1'
                if native_fault and fault=='native-zero':actual_guid='00000000-0000-0000-0000-000000000000'
                if native_fault and fault=='native-version-one':actual_guid='9e814aad-3204-11d2-9a82-006008a86939'
                properties.update(sessionName=self.experiment['sessionName'],sessionGuid=actual_guid,
                                  sessionGuidMatchesExpected=actual_guid==expected_guid,sessionNameMatchesExpected=True)
                if fault=='contradictory-guid':properties['sessionGuid']='00000000-0000-0000-0000-000000000001'
                if fault=='native-name':properties.update(sessionName='FOREIGN',sessionNameMatchesExpected=False)
                if fault=='native-mode':properties['logFileMode']=0x02000100
                if fault=='native-provider':properties['enableFlags']=8
                if fault=='native-path':properties['logFileName']=str(self.root/'foreign.etl')
                if fault=='native-loss':properties['eventsLost']=1
            if active and fault == 'escaped-output':
                properties['logFileName'] = str(self.root/'foreign.etl')
            value = {'sourceSha256': self.inputs['inspect-image-source-session.py'], 'controlCode': 0,
                     'sourceActive': active, 'properties': properties, 'diagnosticAccepted':True,'validationError':None,
                     'win32Status':0 if active else 4201,'sessionName':self.experiment['sessionName'],
                     'expectedSessionGuid':expected_guid}
            if active and native_fault and properties['sessionGuid']!=expected_guid:
                value['diagnosticAccepted']=False
                value['validationError']=f"Session GUID differs from expected source (expected {expected_guid}, returned {properties['sessionGuid']})"
                if fault=='native-extra-error':value['validationError']+='; OTHER ERROR'
                if fault=='native-api':value.update(win32Status=5,sourceActive=None,properties=None,validationError='Trace query failed with Windows error 5')
            rejected=(fault in ('guid-rejected','rejected-with-success-exit') and label=='sample-0') or (fault=='rejected-before' and label=='before')
            if rejected:
                value['diagnosticAccepted']=False
                value['validationError']='Synthetic rejected query metadata'
                if fault=='rejected-before':value.update(win32Status=5,sourceActive=None,properties=None)
            output.write_text(json.dumps(value), encoding='utf-8')
            return SimpleNamespace(returncode=1 if (rejected and fault!='rejected-with-success-exit') or (native_fault and value['diagnosticAccepted'] is False) else 0)

        clock = iter([0, 0, 14]) if fault == 'late-query' else None
        def fake_query(arguments,timeout,log,record):
            with log.open('xb') as stream:
                return fake_child([sys._base_executable,*arguments],stdout=stream,stderr=subprocess.STDOUT,
                                  timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW,cwd=self.root).returncode
        with mock.patch.object(module, 'ROOT', self.root), \
             mock.patch.object(module, 'own_token', return_value={'queried': True, 'elevated': True}), \
             mock.patch.object(module.shutil, 'which', return_value='SIMULATED-POWERSHELL'), \
             mock.patch.object(module.subprocess, 'run', side_effect=fake_child), \
             mock.patch.object(module, 'query_process', side_effect=fake_query), \
             mock.patch.object(module.time, 'sleep'), \
             mock.patch.object(module.time, 'monotonic', side_effect=(lambda: next(clock)) if clock else None,
                               return_value=0):
            result = module.run(self.experiment)
        saved = json.loads((self.context/'run.json').read_text(encoding='utf-8'))
        self.assertEqual(saved, result)
        self.assertFalse(result['independentStopValidated'])
        self.assertFalse(result['imageRundownObserved'])
        self.assertFalse(result['readinessAdmission'])
        return result

    def test_complete_simulated_flow_does_not_claim_timer_or_rundown(self):
        result = self.exercise()
        self.assertTrue(result['successful'])
        self.assertTrue(result['sourceStarted'])
        self.assertFalse(result['timedExpiryCauseVerified'])
        self.assertEqual(self.calls, ['before','Start','sample-0','sample-1','Cleanup','after'])

    def test_distinct_native_guid_still_fails_default_policy(self):
        result=self.exercise('native-valid')
        self.assertFalse(result['successful'])
        self.assertNotIn('nativeGuidDiscovery',result)
        self.assertNotIn('sample-0-native-recheck',self.calls)

    def test_explicit_native_policy_rechecks_and_retains_failed_discovery(self):
        result=self.exercise('native-valid','observed-rechecked')
        self.assertTrue(result['successful'])
        self.assertTrue(result['nativeGuidDiscovery']['recheckAccepted'])
        self.assertNotEqual(result['sessionGuid'],result['nativeSessionGuid'])
        self.assertEqual(len(result['queryRejections']),1)
        self.assertEqual(result['observations'][0]['expectedSessionGuid'],result['nativeSessionGuid'])
        self.assertEqual(self.calls,['before','Start','sample-0','sample-0-native-recheck','sample-1','Cleanup','after'])
        self.assertFalse(json.loads((self.context/'sample-0.json').read_text())['diagnosticAccepted'])

    def test_native_guid_change_during_recheck_is_not_adopted(self):
        result=self.exercise('native-changed','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertFalse(result['nativeGuidDiscovery']['recheckAccepted'])
        self.assertNotIn('nativeSessionGuid',result)
        self.assertIsNone(result['sourceStarted'])
        self.assertEqual(len(result['queryRejections']),2)

    def test_native_guid_change_later_is_not_rediscovered(self):
        result=self.exercise('native-changed-later','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertTrue(result['nativeGuidDiscovery']['recheckAccepted'])
        self.assertEqual(len(result['queryRejections']),2)
        self.assertEqual(self.calls.count('sample-0-native-recheck'),1)
        self.assertNotIn('sample-1-native-recheck',self.calls)

    def test_native_recheck_absence_does_not_establish_start(self):
        result=self.exercise('native-gone','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertIsNone(result['sourceStarted'])
        self.assertFalse(result['nativeGuidDiscovery']['recheckAccepted'])

    def test_native_candidate_with_wrong_name_is_refused(self):
        result=self.exercise('native-name','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertNotIn('sample-0-native-recheck',self.calls)

    def test_native_candidate_with_wrong_output_is_refused(self):
        result=self.exercise('native-path','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertNotIn('sample-0-native-recheck',self.calls)

    def test_native_candidate_with_unreviewed_mode_is_refused(self):
        result=self.exercise('native-mode','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertNotIn('sample-0-native-recheck',self.calls)

    def test_native_candidate_loss_is_not_hidden_by_recheck(self):
        result=self.exercise('native-loss','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertIn('observed loss',result['error'])
        self.assertNotIn('sample-0-native-recheck',self.calls)

    def test_native_zero_guid_is_refused(self):
        result=self.exercise('native-zero','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertNotIn('sample-0-native-recheck',self.calls)

    def test_native_candidate_extra_rejection_is_refused(self):
        result=self.exercise('native-extra-error','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertIn('another cause',result['error'])

    def test_native_preexisting_source_is_never_adopted_or_cleaned(self):
        result=self.exercise('native-preexisting','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertEqual(self.calls,['before'])

    def test_native_reserved_version_one_guid_is_refused(self):
        result=self.exercise('native-version-one','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertNotIn('sample-0-native-recheck',self.calls)

    def test_native_provider_flags_are_constrained(self):
        result=self.exercise('native-provider','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertNotIn('sample-0-native-recheck',self.calls)

    def test_native_api_failure_cannot_start_discovery(self):
        result=self.exercise('native-api','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertNotIn('sample-0-native-recheck',self.calls)

    def test_native_discovery_requires_actual_committed_start_evidence(self):
        result=self.exercise('native-uncommitted','observed-rechecked')
        self.assertFalse(result['successful'])
        self.assertIn('admitted committed start',result['error'])
        self.assertNotIn('sample-0-native-recheck',self.calls)

    def test_start_timeout_preserves_unknown_start_and_attempts_cleanup(self):
        result = self.exercise('start-timeout')
        self.assertFalse(result['successful'])
        self.assertIsNone(result['sourceStarted'])
        self.assertIsNotNone(result['error'])
        self.assertIn('Cleanup', self.calls)

    def test_missing_committed_configuration_refuses_observation(self):
        result=self.exercise('missing-configuration')
        self.assertFalse(result['successful'])
        self.assertIsNone(result['sourceStarted'])
        self.assertIn('Missing accepted committed configuration',result['error'])
        self.assertEqual(self.calls,['before','Start','Cleanup','after'])

    def test_start_timeout_can_leave_snapshot_without_admitting_start(self):
        result=self.exercise('start-timeout-after-snapshot')
        self.assertFalse(result['successful'])
        self.assertIsNone(result['sourceStarted'])
        self.assertTrue((self.context/'start.json.committed.json').is_file())
        self.assertFalse((self.context/'start.json').exists())
        self.assertEqual(self.calls,['before','Start','Cleanup','after'])

    def test_changed_committed_configuration_hash_refuses_observation(self):
        result=self.exercise('configuration-hash')
        self.assertFalse(result['successful'])
        self.assertIn('Committed configuration hash differs',result['error'])
        self.assertEqual(self.calls,['before','Start','Cleanup','after'])

    def test_rejected_committed_configuration_refuses_claimed_success(self):
        result=self.exercise('rejected-configuration')
        self.assertFalse(result['successful'])
        self.assertIn('Committed configuration observation differs',result['error'])
        self.assertEqual(self.calls,['before','Start','Cleanup','after'])
        snapshot=json.loads((self.context/'start.json.committed.json').read_text())
        self.assertFalse(snapshot['configurationMatchesExpected'])

    def test_escaped_committed_configuration_refuses_read(self):
        result=self.exercise('configuration-escape')
        self.assertFalse(result['successful'])
        self.assertIn('Missing accepted committed configuration',result['error'])
        self.assertEqual(self.calls,['before','Start','Cleanup','after'])

    def test_preexisting_source_never_admits_start_or_cleanup(self):
        result = self.exercise('preexisting-source')
        self.assertFalse(result['successful'])
        self.assertEqual(self.calls, ['before'])

    def test_failed_cleanup_preserves_primary_observations_and_child_report(self):
        result = self.exercise('cleanup-failure')
        self.assertFalse(result['successful'])
        self.assertTrue(result['sourceDisappearanceObserved'])
        self.assertIn('cleanupError', result)
        self.assertFalse(json.loads((self.context/'cleanup.json').read_text())['successful'])

    def test_supervisor_stop_does_not_pass_independent_disappearance(self):
        result = self.exercise('cleanup-stop')
        self.assertFalse(result['successful'])
        self.assertTrue(result['cleanup']['stopRequested'])

    def test_loss_produces_explicit_failure(self):
        result = self.exercise('loss')
        self.assertFalse(result['successful'])
        self.assertIn('loss counters', result['error'])

    def test_missing_etl_preserves_report_with_artifact_error(self):
        result = self.exercise('missing-etl')
        self.assertFalse(result['successful'])
        self.assertIn('No bounded ETL', result['artifactError'])

    def test_late_query_is_not_accepted_and_cleanup_still_runs(self):
        result = self.exercise('late-query')
        self.assertFalse(result['successful'])
        self.assertIn('deadline', result['error'])
        self.assertFalse(result['observations'][0]['receivedWithinWatchDeadline'])
        self.assertIn('Cleanup', self.calls)

    def test_escaped_live_output_is_refused_and_cleanup_still_runs(self):
        result = self.exercise('escaped-output')
        self.assertFalse(result['successful'])
        self.assertIn('outside', result['error'])
        self.assertIn('Cleanup', self.calls)

    def test_rejected_query_metadata_is_bound_and_not_admitted(self):
        result=self.exercise('guid-rejected')
        self.assertFalse(result['successful'])
        self.assertIsNone(result['sourceStarted'])
        rejection=result['queryRejections'][0]
        self.assertEqual(rejection['exitCode'],1)
        self.assertEqual(rejection['sha256'],module.sha(self.context/rejection['file']))
        self.assertEqual(result['observations'],[])
        self.assertIn('Cleanup',self.calls)

    def test_rejected_flag_fails_even_if_child_exit_is_zero(self):
        result=self.exercise('rejected-with-success-exit')
        self.assertFalse(result['successful'])
        self.assertEqual(result['queryRejections'][0]['exitCode'],0)
        self.assertEqual(result['observations'],[])

    def test_before_query_error_does_not_admit_start_or_cleanup(self):
        result=self.exercise('rejected-before')
        self.assertFalse(result['successful'])
        self.assertEqual(self.calls,['before'])
        self.assertEqual(result['queryRejections'][0]['win32Status'],5)

    def test_success_exit_and_acceptance_flag_cannot_override_foreign_guid(self):
        result=self.exercise('contradictory-guid')
        self.assertFalse(result['successful'])
        self.assertEqual(result['observations'],[])
        self.assertIn('Contradictory',result['queryRejections'][0]['validationError'])
        self.assertIn('Cleanup',self.calls)


if __name__ == '__main__':
    unittest.main()
