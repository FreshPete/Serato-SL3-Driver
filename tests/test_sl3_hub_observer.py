"""Observer timing, collector identity and direct-process containment without USB."""
import copy
from contextlib import redirect_stdout
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('port_observer',ROOT/'scripts/observe-sl3-hub-port.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class FakeClock:
    def __init__(self):self.value=0
    def monotonic(self):return self.value
    def sleep(self,seconds):self.value+=seconds


class ObserverTests(unittest.TestCase):
    def test_prepare_cli_returns_zero_without_starting_worker(self):
        with patch.object(v.sys,'argv',['observer','--prepare','unused','--context','unused']),\
             patch.object(v,'prepare',return_value={'startsTrace':False}) as prepare,\
             patch.object(v,'supervise') as supervise,patch.object(v,'worker') as worker,redirect_stdout(io.StringIO()):
            self.assertEqual(v.main(),0)
        prepare.assert_called_once();supervise.assert_not_called();worker.assert_not_called()

    def test_default_inspection_cli_returns_zero_without_starting_worker(self):
        with patch.object(v.sys,'argv',['observer','--job','unused']),\
             patch.object(v,'validate',return_value={'startsTrace':False}) as validate,\
             patch.object(v,'supervise') as supervise,patch.object(v,'worker') as worker,redirect_stdout(io.StringIO()):
            self.assertEqual(v.main(),0)
        validate.assert_called_once();supervise.assert_not_called();worker.assert_not_called()

    def test_execution_cli_preserves_failed_and_successful_status(self):
        for successful in (False,True):
            with self.subTest(successful=successful),patch.object(v.sys,'argv',['observer','--job','unused','--run']),\
                 patch.object(v,'supervise',return_value={'successful':successful}),redirect_stdout(io.StringIO()):
                self.assertEqual(v.main(),0 if successful else 1)

    def setUp(self):
        self.settings={'createdUtc':'2026-11-01T14:00:00Z','waitSeconds':90,'sampleSeconds':18,
                       'devnodeInstance':r'USB\VID_1CC5&PID_0001\SL3.01.00',
                       'intervalSeconds':.25,'maximumSamples':128,'query':{},
                       'runtime':{'sources':{'capture-usb-startup.ps1':'a'*64}}}
        self.trace={'status':'recording','session':'SL3Startup-'+'a'*32,'producerSha256':'A'*64,
                    'startedUtc':'2026-11-01T14:00:01Z','plan':{'durationSeconds':20,'withStateObserver':True},
                    'collectorPid':42,'collectorCreationFileTimeUtc':'134380000000000000','collectorImagePath':r'C:\pwsh.exe'}
        self.process={'pid':42,'creationFileTimeUtc':'134380000000000000','imagePath':r'C:\pwsh.exe','alive':True}
        node=patch.object(v,'devnode_status',return_value={'complete':True});node.start();self.addCleanup(node.stop)

    def test_fresh_exact_collector(self):v.admit(self.trace,self.process,self.settings,'2026-11-01T14:00:02Z')

    def test_stale_reused_exited_or_changed_source_rejected(self):
        for fault in ('stale','reused','exited','source','old','terminal','mode'):
            trace=copy.deepcopy(self.trace);process=copy.deepcopy(self.process);at='2026-11-01T14:00:02Z'
            if fault=='stale':at='2026-11-01T14:00:06.000001Z'
            if fault=='reused':process['creationFileTimeUtc']='134380000000000001'
            if fault=='exited':process['alive']=False
            if fault=='source':trace['producerSha256']='b'*64
            if fault=='old':trace['startedUtc']='2026-10-31T14:00:01Z'
            if fault=='terminal':trace['status']='window completed'
            if fault=='mode':trace['plan']['durationSeconds']=60
            with self.subTest(fault=fault),self.assertRaises(ValueError):v.admit(trace,process,self.settings,at)

    def query_result(self):
        return {'successful':True,'error':None,'handleClosed':True,
                'producerToken':{'pid':os.getpid(),'elevated':False}}

    def test_sampling_respects_duration_and_measured_cadence(self):
        clock=FakeClock();rows=[]
        def query(settings):clock.value+=.1;return self.query_result()
        with patch.object(v.time,'monotonic',clock.monotonic),patch.object(v.time,'sleep',clock.sleep),\
             patch.object(v.query,'run',side_effect=query):
            result=v.samples(self.settings,rows.append)
        self.assertEqual(result['samples'],len(rows));self.assertGreater(len(rows),1)
        self.assertLess(len(rows),72);self.assertGreaterEqual(result['elapsedSeconds'],18)
        self.assertGreater(rows[1]['elapsedSeconds']-rows[0]['elapsedSeconds'],.25)

    def test_query_failure_no_retry(self):
        result=self.query_result();result['successful']=False;rows=[]
        with patch.object(v.query,'run',return_value=result) as query:
            with self.assertRaisesRegex(ValueError,'without retry'):v.samples(self.settings,rows.append)
        query.assert_called_once();self.assertEqual(len(rows),1)

    def test_zero_index_enumeration_gap_preserves_later_samples(self):
        clock=FakeClock();rows=[]
        raw=bytes(31)+b'\x09'+bytes(355)
        gap={**self.query_result(),'successful':False,'error':'Hub response connection index differs',
             'queryWin32Error':0,'bytesReturned':35,'responseEvidence':v.query.response_evidence(raw,35)}
        with patch.object(v.time,'monotonic',clock.monotonic),patch.object(v.time,'sleep',clock.sleep),\
             patch.object(v.query,'run',side_effect=[self.query_result(),gap,self.query_result()]),\
             patch.object(v,'devnode_status',return_value={'complete':True}) as devnode:
            result=v.samples({**self.settings,'sampleSeconds':.75},rows.append)
        self.assertEqual(result['samples'],3)
        self.assertEqual(result['enumerationGaps'],1)
        self.assertIsNone(rows[1]['devnode'])
        self.assertIs(rows[1]['query'],gap)
        self.assertEqual(devnode.call_count,2)

    def test_slow_query_crossing_deadline_is_not_success(self):
        clock=FakeClock()
        def query(settings):clock.value=19;return self.query_result()
        with patch.object(v.time,'monotonic',clock.monotonic),patch.object(v.query,'run',side_effect=query):
            with self.assertRaisesRegex(ValueError,'crossed'):v.samples(self.settings,lambda row:None)

    def test_other_process_cannot_produce_sample(self):
        result=self.query_result();result['producerToken']['pid']+=1
        with patch.object(v.query,'run',return_value=result):
            with self.assertRaisesRegex(ValueError,'observer process'):v.samples(self.settings,lambda row:None)

    def test_actual_self_identity_query_without_usb(self):
        result=v.process_identity(os.getpid())
        self.assertTrue(result['alive']);self.assertEqual(result['pid'],os.getpid())
        self.assertGreater(int(result['creationFileTimeUtc']),0)

    def test_devnode_problem_only_valid_when_flag_is_set(self):
        self.assertEqual(v.devnode_fields(0,0,0x400,39)['problemCode'],39)
        self.assertIsNone(v.devnode_fields(0,0,8,999)['problemCode'])
        self.assertTrue(v.devnode_fields(0,0,8,999)['started'])
        self.assertTrue(v.devnode_fields(13,0,0,0)['complete'])
        self.assertFalse(v.devnode_fields(13,0,0,0)['present'])
        self.assertFalse(v.devnode_fields(5,0,0,0)['complete'])

    def test_terminal_trace_prevents_queries(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.settings['contextDirectory']=temporary;path=Path(temporary)/'trace';path.mkdir()
            (path/'capture.json').write_text(json.dumps({'status':'failed'}))
            with self.assertRaisesRegex(ValueError,'terminal'):v.await_trace(self.settings)

    def supervise_fixture(self,temporary):
        path=Path(temporary)
        settings={'runtime':{'baseInterpreter':r'C:\Python313\python.exe'},'supervisorDeadlineSeconds':115}
        (path/'plan.json').write_text('{}')
        rows=[{'record':'header','producerToken':{'pid':123}}, {'record':'summary','successful':True}]
        (path/'observations.ndjson').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        return path,settings

    def test_supervisor_uses_base_executable_and_exact_producer(self):
        with tempfile.TemporaryDirectory() as temporary:
            path,settings=self.supervise_fixture(temporary);child=Mock(pid=123);child.wait.return_value=0;child.poll.return_value=0
            with patch.object(v,'validate',return_value=settings),patch.object(v.query,'own_token',return_value={'queried':True,'elevated':False}),\
                 patch.object(v.subprocess,'Popen',return_value=child) as spawn:
                result=v.supervise(path)
            self.assertTrue(result['successful']);self.assertTrue(result['directProducerRetired'])
            self.assertEqual(spawn.call_args.args[0][0],settings['runtime']['baseInterpreter'])

    def test_timeout_is_failure_even_after_process_termination(self):
        with tempfile.TemporaryDirectory() as temporary:
            path,settings=self.supervise_fixture(temporary);child=Mock(pid=123)
            child.wait.side_effect=[subprocess.TimeoutExpired('observer',115),-1];child.poll.return_value=-1
            with patch.object(v,'validate',return_value=settings),patch.object(v.query,'own_token',return_value={'queried':True,'elevated':False}),\
                 patch.object(v.subprocess,'Popen',return_value=child):result=v.supervise(path)
            self.assertTrue(result['timedOut']);self.assertFalse(result['successful']);child.kill.assert_called_once()

    def test_pid_mismatch_and_single_use_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path,settings=self.supervise_fixture(temporary);child=Mock(pid=124);child.wait.return_value=0;child.poll.return_value=0
            with patch.object(v,'validate',return_value=settings),patch.object(v.query,'own_token',return_value={'queried':True,'elevated':False}),\
                 patch.object(v.subprocess,'Popen',return_value=child) as spawn:
                result=v.supervise(path);self.assertFalse(result['successful']);self.assertIn('PID differs',result['error'])
                with self.assertRaises(FileExistsError):v.supervise(path)
                self.assertEqual(spawn.call_count,1)


if __name__=='__main__':unittest.main()
