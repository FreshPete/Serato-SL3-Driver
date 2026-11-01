"""Scope collector composition and plan inspection; no source/device is started."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from tests import test_controls_image_collection as fixtures
from tests import test_controls_image_window as window_fixtures

v=fixtures.v
ROOT=fixtures.ROOT


class ScopeImageTests(unittest.TestCase):
    def image(self,seconds):
        return {'jobs':[{'durationSeconds':seconds}],'nativeIdentityPolicy':'observed-rechecked',
                'runtime':{'powershell':'pwsh.exe'}}

    def test_fixed_scope_window_and_normal_user_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'batch.json';path.write_text('{}')
            with patch.object(v,'runtime',return_value={'tested':'scope'}):
                plan=v.plan_value(path,self.image(120),scope=True)
            self.assertEqual(plan['schema'],'sl3.scope-image-collector.v1')
            self.assertEqual(plan['traceSeconds'],60)
            self.assertEqual(plan['scenario'],'Scope')
            self.assertTrue(plan['contextDirectory'].endswith('-scope'))
            self.assertEqual(plan['normalUserCommand'][-2:],['-Scenario','Scope'])
            self.assertFalse(plan['launchesProbe']);self.assertFalse(plan['readinessAdmission'])
            self.assertFalse(Path(plan['contextDirectory']).exists())

    def test_shortened_or_unbounded_image_window_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'batch.json';path.write_text('{}')
            for seconds in (60,119,121):
                with self.subTest(seconds=seconds),self.assertRaises(ValueError):
                    v.plan_value(path,self.image(seconds),scope=True)

    def test_long_window_cannot_be_mixed_or_use_configured_only_identity(self):
        for durations,policy in (([120,5],'observed-rechecked'),([120],'configured'),([61],'observed-rechecked')):
            path=ROOT/'analysis'/('logging-batch-invalid-scope-'+uuid.uuid4().hex)
            with self.subTest(durations=durations,policy=policy),self.assertRaises(ValueError):
                v.batch.prepare(path,durations,policy)
            self.assertFalse(path.exists())

    def test_scope_plan_cannot_be_relabelled_as_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'controls-image.json';batch_path=path.with_name('batch.json');batch_path.write_text('{}')
            with patch.object(v,'runtime',return_value={'tested':'scope'}):
                plan=v.plan_value(batch_path,self.image(120),scope=True)
                plan['schema']='sl3.controls-image-collector.v1';path.write_text(json.dumps(plan))
                with patch.object(v.batch,'validate',return_value=self.image(120)):
                    with self.assertRaises(ValueError):v.validate(path)

    def test_scope_execution_collects_sixty_seconds_without_launching_probe(self):
        fixture=fixtures.CombinedTests();fixture.setUp()
        with tempfile.TemporaryDirectory() as tmp:
            path,plan,image,source,collector,candidate=fixture.execute_fixture(tmp)
            plan.update(schema='sl3.scope-image-collector.v1',scenario='Scope',traceSeconds=60)
            def query_run(*args,**kwargs):Path(tmp,'pre-usb-image-query.json').write_text(json.dumps(fixture.query))
            with patch.object(v,'validate',return_value=(plan,image)),patch.object(v.batch,'source_runner') as runner,\
                 patch.object(v,'wait_candidate',return_value=(candidate,fixture.native)),patch.object(v,'committed_start'),\
                 patch.object(v,'runtime',return_value=plan['runtime']),patch.object(v,'now',return_value=fixture.checked),\
                 patch.object(v.subprocess,'run',side_effect=query_run),\
                 patch.object(v.subprocess,'Popen',side_effect=[source,collector]) as spawn,\
                 patch.object(v,'sha',side_effect=lambda p:'b'*64 if p.name=='batch.json' else 'a'*64):
                runner.return_value.own_token.return_value={'queried':True,'elevated':True}
                result=v.execute(path,'a'*64)
            self.assertTrue(result['collectionCompleted']);self.assertIsNone(result['error'])
            self.assertEqual(result['schema'],'sl3.scope-image-collection.v1')
            self.assertFalse(result['sameWindowVerified']);self.assertFalse(result['launchesProbe'])
            command=spawn.call_args_list[1].args[0]
            self.assertEqual(command[command.index('-TraceSeconds')+1],'60')
            self.assertNotIn('test-controls-user-probe.ps1',command)
            source.wait.assert_called_once_with(timeout=190)

    def test_scope_image_failure_never_starts_usb_or_kills_owner(self):
        fixture=fixtures.CombinedTests();fixture.setUp()
        with tempfile.TemporaryDirectory() as tmp:
            path,plan,image,source,collector,candidate=fixture.execute_fixture(tmp)
            plan.update(schema='sl3.scope-image-collector.v1',scenario='Scope',traceSeconds=60)
            with patch.object(v,'validate',return_value=(plan,image)),patch.object(v.batch,'source_runner') as runner,\
                 patch.object(v,'wait_candidate',side_effect=ValueError('no image admission')),\
                 patch.object(v.subprocess,'Popen',return_value=source) as spawn:
                runner.return_value.own_token.return_value={'queried':True,'elevated':True}
                result=v.execute(path,v.sha(path))
            self.assertFalse(result['collectionCompleted']);self.assertEqual(spawn.call_count,1)
            source.wait.assert_called_once_with(timeout=190)
            source.kill.assert_not_called();source.terminate.assert_not_called()


class ScopeImageActualPlans(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=ROOT/'analysis'/('logging-batch-scope-image-test-'+uuid.uuid4().hex)
        result=subprocess.run([sys.executable,str(ROOT/'scripts/collect-controls-with-images.py'),
                               '--prepare',str(cls.directory),'--scenario','Scope'],capture_output=True,text=True,timeout=35)
        if result.returncode:raise RuntimeError(result.stderr)
        cls.plan=json.loads(result.stdout)

    def test_actual_scope_plan_and_default_launcher_do_not_start(self):
        path=self.directory/'controls-image.json'
        child=subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'scripts/start-controls-image-capture.ps1'),
                              '-Plan',str(path)],capture_output=True,text=True,timeout=30)
        self.assertEqual(child.returncode,0,child.stderr)
        self.assertEqual(json.loads(child.stdout),self.plan)
        batch=v.read(self.directory/'batch.json');job=batch['jobs'][0]
        self.assertEqual(job['durationSeconds'],120)
        self.assertEqual(self.plan['traceSeconds'],60)
        self.assertFalse(Path(self.plan['contextDirectory']).exists())
        self.assertFalse(Path(job['captureRoot']).exists())
        self.assertFalse((self.directory/'controls-image-started.json').exists())
        self.assertFalse((self.directory/'execution-started.json').exists())

    def test_middle_duration_and_overlong_preparation_refused(self):
        for duration in (61,119,121):
            child=subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'scripts/prepare-hub-image-source.ps1'),
                                  '-DurationSeconds',str(duration)],capture_output=True,text=True,timeout=15)
            self.assertNotEqual(child.returncode,0)

    def test_actual_long_window_validation_commits_nothing(self):
        job=v.read(self.directory/'batch.json')['jobs'][0]
        output=self.directory/'validate-120.json'
        child=subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'scripts/validate-hub-image-source.ps1'),
                              '-PreparationRecord',job['preparation'],'-Output',str(output)],
                             capture_output=True,text=True,timeout=25)
        self.assertEqual(child.returncode,0,child.stderr)
        result=json.loads(output.read_text(encoding='utf-8-sig'))
        self.assertTrue(result['valid']);self.assertEqual(result['commitMode'],0x1000)
        self.assertFalse(result['sourceStarted']);self.assertFalse(result['prospectiveDirectoryExists'])


class ScopeQualificationTests(unittest.TestCase):
    """Real record/window checks, with native validation and ETL decoding mocked."""
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.directory=Path(temporary.name);self.window=window_fixtures.v
        self.path=self.directory/'controls-image.json';self.output=self.directory/'qualified.json'
        self.context=self.directory/'scope';self.source_context=self.directory/'image-source'
        self.etl=self.directory/'capture/images.etl';self.etl.parent.mkdir();self.etl.write_bytes(b'synthetic inspector input')
        self.fixture=window_fixtures.ImageWindowTests();self.fixture.setUp()
        self.report=copy.deepcopy(self.fixture.report)
        self.report['headers'][0]['EndTime']=self.window.clock.filetime('2026-11-01T14:02:00Z')
        self.report['kernelImages'][0]['observations'][1]['time']='2026-11-01T14:02:00Z'
        self.report.update(sourceEtlSha256=self.window.sha(self.etl),
                           inspectorSha256=self.window.sha(ROOT/'scripts/inspect-kernel-image-rundown.py'))
        trace=copy.deepcopy(self.fixture.trace);trace['stoppedUtc']='2026-11-01T14:01:05Z'
        run=copy.deepcopy(self.fixture.run);run['probeCompletedUtc']='2026-11-01T14:00:35Z'
        self.save(self.context/'trace/capture.json',trace);self.save(self.context/'run.json',run)
        source={'successful':True,'sourceDisappearanceObserved':True,'sampledLossCountersZero':True,
                'cleanup':{'successful':True,'stopRequested':False,'collectorDeleted':True},'after':{'sourceActive':False},
                'etlFiles':[{'path':str(self.etl),'sha256':self.window.sha(self.etl),'bytes':self.etl.stat().st_size}]}
        self.source_path=self.source_context/'run.json';self.save(self.source_path,source)
        batch={'jobs':[{'durationSeconds':120,'contextDirectory':str(self.source_context),'captureRoot':str(self.etl.parent)}],
               'nativeIdentityPolicy':'observed-rechecked'}
        self.save(self.directory/'batch.json',batch)
        self.plan={'schema':'sl3.scope-image-collector.v1','scenario':'Scope','traceSeconds':60,'runtime':{'tested':'scope'},
                   'imageBatch':str(self.directory/'batch.json'),'imageBatchSha256':self.window.sha(self.directory/'batch.json'),
                   'contextDirectory':str(self.context)}
        self.save(self.path,self.plan)
        digest=self.window.sha(self.path)
        self.save(self.directory/'controls-image-started.json',{'planSha256':digest})
        self.result={'schema':'sl3.scope-image-collection.v1','planSha256':digest,'collectionCompleted':True,
                     'error':None,'imageControllerExitCode':0,'usbCollectorExitCode':0}
        self.save(self.directory/'controls-image-result.json',self.result)
        self.save(self.directory/'batch-result.json',{'successful':True,'planSha256':self.window.sha(self.directory/'batch.json'),
                  'jobs':[{'sourceRunSha256':self.window.sha(self.source_path)}]})

    def save(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),encoding='utf-8')

    def qualify(self):
        def inspect(arguments,**kwargs):
            self.save(Path(arguments[arguments.index('--output')+1]),self.report)
        with patch.object(self.window,'module',return_value=v),patch.object(v,'runtime',return_value=self.plan['runtime']),\
             patch.object(self.window.controls,'validate',return_value={'valid':True}) as probe,\
             patch.object(self.window.subprocess,'run',side_effect=inspect),\
             patch.object(self.window.images,'image_metadata',return_value=self.fixture.expected):
            result=self.window.validate(self.path,self.output)
        return result,probe

    def test_scope_qualification_selects_scope_image_and_validator(self):
        result,probe=self.qualify()
        build=v.read(ROOT/'artifacts/build/native/native-build-Release.json')
        probe.assert_called_once_with(self.context,build['usbdk']['executableSha256'],build['scopeProbe']['executableSha256'],scope=True)
        self.assertEqual(result['scenario'],'Scope');self.assertTrue(result['imageMetadataCoversUsbWindow'])
        self.assertFalse(result['readinessAdmission']);self.assertFalse(result['physicalDeviceIdentityVerified'])

    def test_controls_result_cannot_qualify_as_scope(self):
        self.result['schema']='sl3.controls-image-collection.v1'
        self.save(self.directory/'controls-image-result.json',self.result)
        with self.assertRaisesRegex(ValueError,'scenario'):self.qualify()
        self.assertFalse(self.output.exists())

    def test_short_image_job_refused_even_with_matching_frozen_hashes(self):
        batch=v.read(self.directory/'batch.json');batch['jobs'][0]['durationSeconds']=60
        self.save(self.directory/'batch.json',batch)
        self.plan['imageBatchSha256']=self.window.sha(self.directory/'batch.json');self.save(self.path,self.plan)
        digest=self.window.sha(self.path);self.result['planSha256']=digest
        self.save(self.directory/'controls-image-started.json',{'planSha256':digest})
        self.save(self.directory/'controls-image-result.json',self.result)
        with self.assertRaisesRegex(ValueError,'window differs'):self.qualify()
        self.assertFalse(self.output.exists())


if __name__=='__main__':unittest.main()
