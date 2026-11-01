"""Collector composition and failure containment; all trace/process operations mocked."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('combined_controls',ROOT/'scripts/collect-controls-with-images.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class CombinedTests(unittest.TestCase):
    def setUp(self):
        self.native='a7fee275-7ec3-4a51-8783-2d2399466015'
        self.job={'sessionName':'SL3Image-'+'a'*32,'captureRoot':str(ROOT/'tests/results/local'/('SL3Image-'+'a'*32)),
                  'contextDirectory':'unused','inputs':{'inspect-image-source-session.py':'a'*64}}
        self.query={'sourceSha256':'a'*64,'sessionName':self.job['sessionName'],'expectedSessionGuid':self.native,
                    'controlCode':0,'win32Status':0,'sourceActive':True,'diagnosticAccepted':True,
                    'validationError':None,'readinessAdmission':False,'queryStartedUtc':'2026-11-01T14:00:00+00:00',
                    'queryFinishedUtc':'2026-11-01T14:00:00.001+00:00',
                    'properties':{'sessionName':self.job['sessionName'],'sessionGuid':self.native,
                                  'sessionNameMatchesExpected':True,'sessionGuidMatchesExpected':True,
                                  'logFileName':str(Path(self.job['captureRoot'])/'images.etl'),
                                  'logFileMode':0x02800000,'systemLoggerModePresent':True,'clockType':1,'enableFlags':4,
                                  'eventsLost':0,'logBuffersLost':0,'realTimeBuffersLost':0}}
        self.checked='2026-11-01T14:00:00.1+00:00'

    def test_strict_live_image_query(self):
        self.assertEqual(v.live_query(self.query,self.job,self.checked),self.native)

    def test_rejected_stale_or_wrong_private_source(self):
        mutations=[('diagnosticAccepted',False),('sourceActive',False),('sourceSha256','b'*64),
                   ('validationError','mismatch'),('readinessAdmission',True),('win32Status',True),
                   ('controlCode',False),('queryStartedUtc','2026-11-01T13:59:57+00:00'),
                   ('queryFinishedUtc','2026-11-01T14:00:01+00:00')]
        for key,value in mutations:
            query=copy.deepcopy(self.query);query[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.live_query(query,self.job,self.checked)
        for key,value in [('logFileName',str(ROOT/'different.etl')),('sessionGuid','b'*32),
                          ('sessionGuidMatchesExpected',False),('enableFlags',5),('clockType',True),
                          ('logFileMode',2),('eventsLost',1),('logBuffersLost',True),('realTimeBuffersLost',1)]:
            query=copy.deepcopy(self.query);query['properties'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.live_query(query,self.job,self.checked)

    def test_rejected_initial_query_cannot_gate_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.job['contextDirectory']=tmp
            query=copy.deepcopy(self.query);query['diagnosticAccepted']=False
            Path(tmp,'sample-0.json').write_text(json.dumps(query))
            source=Mock();source.poll.return_value=None
            with patch.object(v.time,'monotonic',side_effect=[0,0,26]),patch.object(v.time,'sleep'):
                with self.assertRaisesRegex(ValueError,'No fresh strict'):v.wait_candidate(source,self.job)

    def test_strict_recheck_is_selected_without_relabelling_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.job['contextDirectory']=tmp
            failed=copy.deepcopy(self.query);failed['diagnosticAccepted']=False
            rejection=Path(tmp,'sample-0.json');rejection.write_text(json.dumps(failed))
            recheck=Path(tmp,'sample-0-native-recheck.json');recheck.write_text(json.dumps(self.query))
            source=Mock();source.poll.return_value=None
            with patch.object(v,'now',return_value=self.checked):
                path,native=v.wait_candidate(source,self.job)
            self.assertEqual(path,recheck);self.assertEqual(native,self.native)
            self.assertFalse(json.loads(rejection.read_text())['diagnosticAccepted'])

    def test_source_exit_prevents_gate(self):
        source=Mock();source.poll.return_value=1
        with self.assertRaisesRegex(ValueError,'exited'):v.wait_candidate(source,self.job)

    def test_wait_timeout_never_kills_cleanup_owner(self):
        child=Mock();child.wait.side_effect=subprocess.TimeoutExpired('owned',1)
        with self.assertRaisesRegex(ValueError,'still running'):v.wait_owned(child,1,'collector')
        child.kill.assert_not_called();child.terminate.assert_not_called()

    def execute_fixture(self,tmp):
        path=Path(tmp)/'controls-image.json';path.write_text('{}')
        plan={'imageBatch':str(Path(tmp)/'batch.json'),'imageBatchSha256':'b'*64,
              'runtime':{'fixed':True},'contextDirectory':str(Path(tmp)/'controls')}
        image={'jobs':[self.job],'runtime':{'powershell':'pwsh.exe'}}
        source=Mock(pid=123);source.poll.return_value=None;source.wait.return_value=0
        collector=Mock(pid=456);collector.wait.return_value=0
        candidate=Path(tmp)/'candidate.json';candidate.write_text('{}')
        return path,plan,image,source,collector,candidate

    def test_success_collects_only_and_keeps_window_claim_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,plan,image,source,collector,candidate=self.execute_fixture(tmp)
            def query_run(*args,**kwargs):
                Path(tmp,'pre-usb-image-query.json').write_text(json.dumps(self.query))
            with patch.object(v,'validate',return_value=(plan,image)),patch.object(v.batch,'source_runner') as runner,\
                 patch.object(v,'wait_candidate',return_value=(candidate,self.native)),\
                 patch.object(v,'committed_start'),\
                 patch.object(v,'runtime',return_value=plan['runtime']),patch.object(v,'now',return_value=self.checked),\
                 patch.object(v.subprocess,'run',side_effect=query_run),\
                 patch.object(v.subprocess,'Popen',side_effect=[source,collector]) as spawn,\
                 patch.object(v,'sha',side_effect=lambda p:'b'*64 if p.name=='batch.json' else 'a'*64):
                runner.return_value.own_token.return_value={'queried':True,'elevated':True}
                result=v.execute(path,'a'*64)
            self.assertTrue(result['collectionCompleted']);self.assertIsNone(result['error'])
            self.assertFalse(result['launchesProbe']);self.assertFalse(result['sameWindowVerified'])
            self.assertFalse(result['readinessAdmission']);self.assertEqual(spawn.call_count,2)
            command=spawn.call_args_list[1].args[0]
            self.assertIn('-WithStateObserver',command);self.assertIn('20',command)
            self.assertNotIn('test-controls-user-probe.ps1',command)
            self.assertTrue(Path(tmp,'controls-image-started.json').exists())
            self.assertTrue(Path(tmp,'controls-image-result.json').exists())

    def test_gate_failure_waits_image_cleanup_and_never_starts_usb(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,plan,image,source,collector,candidate=self.execute_fixture(tmp)
            with patch.object(v,'validate',return_value=(plan,image)),patch.object(v.batch,'source_runner') as runner,\
                 patch.object(v,'wait_candidate',side_effect=ValueError('gate failed')),\
                 patch.object(v.subprocess,'Popen',return_value=source) as spawn:
                runner.return_value.own_token.return_value={'queried':True,'elevated':True}
                result=v.execute(path,v.sha(path))
            self.assertFalse(result['collectionCompleted']);self.assertEqual(result['error'],'gate failed')
            self.assertEqual(spawn.call_count,1);source.wait.assert_called_once_with(timeout=130)
            source.kill.assert_not_called()

    def test_second_query_runtime_usb_and_image_failures(self):
        for fault in ('query','runtime','usb','image'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                path,plan,image,source,collector,candidate=self.execute_fixture(tmp)
                if fault=='usb':collector.wait.return_value=1
                if fault=='image':source.wait.return_value=1
                def query_run(*args,**kwargs):
                    query=copy.deepcopy(self.query)
                    if fault=='query':query['diagnosticAccepted']=False
                    Path(tmp,'pre-usb-image-query.json').write_text(json.dumps(query))
                with patch.object(v,'validate',return_value=(plan,image)),patch.object(v.batch,'source_runner') as runner,\
                     patch.object(v,'wait_candidate',return_value=(candidate,self.native)),patch.object(v,'committed_start'),\
                     patch.object(v,'runtime',return_value={} if fault=='runtime' else plan['runtime']),\
                     patch.object(v,'now',return_value=self.checked),patch.object(v.subprocess,'run',side_effect=query_run),\
                     patch.object(v.subprocess,'Popen',side_effect=[source,collector]) as spawn,\
                     patch.object(v,'sha',side_effect=lambda p:'b'*64 if p.name=='batch.json' else 'a'*64):
                    runner.return_value.own_token.return_value={'queried':True,'elevated':True}
                    result=v.execute(path,'a'*64)
                self.assertTrue(result['error'] or result.get('imageCleanupError'))
                self.assertEqual(spawn.call_count,1 if fault in ('query','runtime') else 2)
                source.wait.assert_called_once_with(timeout=130);source.kill.assert_not_called()

    def test_non_elevated_refused_before_marker_or_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,plan,image,*_=self.execute_fixture(tmp)
            with patch.object(v,'validate',return_value=(plan,image)),patch.object(v.batch,'source_runner') as runner,\
                 patch.object(v.subprocess,'Popen') as spawn:
                runner.return_value.own_token.return_value={'queried':True,'elevated':False}
                with self.assertRaisesRegex(ValueError,'elevated'):v.execute(path,v.sha(path))
            spawn.assert_not_called();self.assertFalse(Path(tmp,'controls-image-started.json').exists())

    def test_real_saved_committed_start_read_only(self):
        context=ROOT/'tests/results/local/logging-batch-20261101-native-recheck-1'
        if not context.exists():self.skipTest('Local recorded logging job unavailable')
        saved=v.read(context/'run.json')
        v.committed_start(saved)


if __name__=='__main__':unittest.main()
