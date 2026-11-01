import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

spec = importlib.util.spec_from_file_location('batch', Path(__file__).parents[1]/'scripts/logging-batch.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LoggingBatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='sl3-batch-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root/'analysis/logging-batch-test'
        self.directory.mkdir(parents=True)
        self.plan = self.directory/'batch.json'
        self.pinned = {'simulationOnly': True}
        self.calls = []
        self.policies = []
        self.fail = None
        self.elevated = True
        self.runner = SimpleNamespace(plan=self.source_plan, run=self.source_run,
                                      own_token=lambda: {'queried': True, 'elevated': self.elevated})
        jobs = [self.source_plan(self.directory/f'preparation-{n}.json',
                                self.root/'tests/results/local'/f'logging-batch-test-{n}') for n in (1, 2)]
        module.write_new(self.plan, {'schema': 'sl3.logging-batch.v1', 'batchDirectory': str(self.directory),
                                    'runtime': self.pinned, 'stopOnFailure': True, 'deviceAccess': False,
                                    'sourceStarted': False, 'readinessAdmission': False, 'jobs': jobs})
        self.patches = [mock.patch.object(module, 'ROOT', self.root),
                        mock.patch.object(module, 'runtime', return_value=self.pinned),
                        mock.patch.object(module, 'source_runner', return_value=self.runner)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def source_plan(self, preparation, context, policy='configured'):
        # An offline placeholder; never invokes a real source or a child process.
        if context.exists():
            raise ValueError('Already used context')
        value={'preparation': str(preparation), 'contextDirectory': str(context)}
        if policy!='configured':value['nativeIdentityPolicy']=policy
        return value

    def source_run(self, job):
        self.calls.append(job['contextDirectory'])
        self.policies.append(job.get('nativeIdentityPolicy','configured'))
        if self.fail == 'exception':
            raise RuntimeError('Simulated source failure')
        context = Path(job['contextDirectory'])
        context.mkdir(parents=True)
        result = {'successful': self.fail != 'result', 'error': 'Simulated failure' if self.fail else None}
        module.write_new(context/'run.json', result)
        return result

    def execute(self):
        return module.execute(self.plan, module.sha(self.plan))

    def test_default_validation_does_not_execute_or_create_contexts(self):
        module.validate(self.plan)
        self.assertEqual(self.calls, [])
        self.assertFalse((self.directory/'execution-started.json').exists())
        self.assertFalse((self.root/'tests').exists())

    def test_successful_simulated_batch_uses_one_elevated_owner(self):
        result = self.execute()
        self.assertTrue(result['successful'])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result['remainingJobsSkipped'], 0)
        self.assertFalse(result['readinessAdmission'])

    def test_first_failure_skips_following_job(self):
        self.fail = 'result'
        result = self.execute()
        self.assertFalse(result['successful'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['remainingJobsSkipped'], 1)
        self.assertIn('remaining jobs', result['error'])

    def test_exception_is_recorded_and_never_retries(self):
        self.fail = 'exception'
        result = self.execute()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['error'], 'Simulated source failure')
        self.assertEqual(result['attemptedJobs'], 1)
        self.assertEqual(result['remainingJobsSkipped'], 1)
        self.assertTrue((self.directory/'batch-result.json').is_file())

    def test_normal_token_cannot_execute(self):
        self.elevated = False
        with self.assertRaisesRegex(ValueError, 'already elevated'):
            self.execute()
        self.assertEqual(self.calls, [])
        self.assertFalse((self.directory/'execution-started.json').exists())

    def test_plan_hash_change_prevents_execution(self):
        with self.assertRaisesRegex(ValueError, 'changed after'):
            module.execute(self.plan, '0'*64)
        self.assertEqual(self.calls, [])

    def test_runtime_change_prevents_execution(self):
        with mock.patch.object(module, 'runtime', return_value={'changed': True}):
            with self.assertRaisesRegex(ValueError, 'runtime changed'):
                self.execute()
        self.assertEqual(self.calls, [])

    def test_job_argument_change_cannot_add_an_operation(self):
        batch = module.read(self.plan)
        batch['jobs'][0]['operation'] = 'UNSUPPORTED'
        self.plan.write_text(json.dumps(batch), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'fixed reviewed'):
            self.execute()
        self.assertEqual(self.calls, [])

    def test_batch_is_single_use(self):
        self.execute()
        with self.assertRaisesRegex(ValueError, 'already attempted'):
            self.execute()
        self.assertEqual(len(self.calls), 2)

    def test_more_than_three_jobs_is_rejected(self):
        batch = module.read(self.plan)
        batch['jobs'] *= 2
        self.plan.write_text(json.dumps(batch), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'batch length'):
            self.execute()

    def test_runtime_change_between_jobs_stops_before_second_source(self):
        with mock.patch.object(module, 'runtime', side_effect=[self.pinned, self.pinned, {'changed': True}]):
            result = self.execute()
        self.assertFalse(result['successful'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['remainingJobsSkipped'], 1)
        self.assertIn('runtime changed between', result['error'])

    def test_unexpected_plan_location_is_rejected(self):
        foreign = self.root/'foreign.json'
        foreign.write_bytes(self.plan.read_bytes())
        with self.assertRaisesRegex(ValueError, 'batch location'):
            module.execute(foreign, module.sha(foreign))
        self.assertEqual(self.calls, [])

    def test_explicit_native_identity_policy_reaches_each_fixed_job(self):
        batch=module.read(self.plan)
        batch['nativeIdentityPolicy']='observed-rechecked'
        for job in batch['jobs']:job['nativeIdentityPolicy']='observed-rechecked'
        self.plan.write_text(json.dumps(batch),encoding='utf-8')
        self.assertTrue(self.execute()['successful'])
        self.assertEqual(self.policies,['observed-rechecked','observed-rechecked'])

    def test_unknown_native_identity_policy_is_refused(self):
        batch=module.read(self.plan);batch['nativeIdentityPolicy']='UNREVIEWED'
        self.plan.write_text(json.dumps(batch),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Unknown native identity policy'):
            self.execute()
        self.assertEqual(self.calls,[])


if __name__ == '__main__':
    unittest.main()
