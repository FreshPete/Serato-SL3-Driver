"""Split-role admission/token guards; no device test or elevated child."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('user_probe_validator', ROOT/'scripts/validate-controls-user-probe.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class UserControlsTests(unittest.TestCase):
    def setUp(self):
        self.now = '2026-10-30T23:00:05+00:00'
        self.process = {'pid': 1234, 'creationFileTimeUtc': '134379600000000000', 'imagePath': r'C:\Program Files\PowerShell\7\pwsh.exe',
                        'alive': True, 'tokenQueried': False, 'elevated': None, 'elevationType': None}
        session = 'SL3Startup-'+'a'*32
        self.trace = {'collectorPid': 1234, 'collectorCreationFileTimeUtc': self.process['creationFileTimeUtc'],
                      'collectorImagePath': self.process['imagePath'], 'status': 'recording', 'session': session,
                      'startedUtc': '2026-10-30T23:00:00+00:00', 'plan': {'durationSeconds': 60, 'withUsbDkLifecycle': True},
                      'commands': [{'arguments': ['update', 'trace', '-n', session, '-p', '{88e1661f-48b6-410f-b096-ba84e9f0656f}', '0x650', '4'], 'exitCode': 0},
                                   {'arguments': ['start', '-n', session], 'exitCode': 0}]}
        self.context = {'schema': 'sl3.controls-user.context.v1', 'completed': False, 'error': None, 'administratorToken': True,
                        'probeLaunched': False, 'securityChanges': False, 'testProcessesBefore': [], 'startedUtc': '2026-10-30T22:59:50+00:00'}
        self.before = {'collectedUtc': '2026-10-30T22:59:55+00:00', 'secureBoot': True,
                       'devices': [{'device': {'InstanceId': r'USB\VID_1CC5&PID_0001\SL3.01.00'}}]}

    def admit(self):
        return v.admission_values(self.trace, self.context, self.before, self.process, self.now)

    def test_live_collector_is_admitted(self):
        self.admit()

    def test_explicit_short_duration_and_tighter_admission(self):
        self.context['traceSeconds'] = 20
        self.trace['plan']['durationSeconds'] = 20
        self.admit()
        self.now = '2026-10-30T23:00:05.001+00:00'
        with self.assertRaises(ValueError):self.admit()

    def test_duration_requires_explicit_matching_integer_contract(self):
        for duration in (19,61,True,20.0,'20'):
            self.context['traceSeconds'] = duration
            self.trace['plan']['durationSeconds'] = duration
            with self.subTest(duration=duration),self.assertRaises(ValueError):self.admit()
        self.context['traceSeconds'] = 20;self.trace['plan']['durationSeconds'] = 21
        with self.assertRaises(ValueError):self.admit()

    def test_stale_reused_or_exited_collector_rejected(self):
        original = copy.deepcopy(self.process)
        for key, value in [('pid', 1235), ('creationFileTimeUtc', '134379600000000001'), ('alive', False),
                           ('imagePath', r'C:\other.exe'), ('tokenQueried', True), ('creationFileTimeUtc', '0')]:
            self.process = copy.deepcopy(original);self.process[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):self.admit()

    def test_trace_time_status_mode_and_provider_order(self):
        original = copy.deepcopy(self.trace)
        for at in ('2026-10-30T22:59:59+00:00', '2026-10-30T23:00:11+00:00'):
            self.now = at
            with self.assertRaises(ValueError):self.admit()
        self.now = '2026-10-30T23:00:05+00:00'
        for mode in ('stopped', 'duration', 'provider', 'order', 'failed'):
            self.trace = copy.deepcopy(original)
            if mode == 'stopped':self.trace['status'] = 'window completed'
            if mode == 'duration':self.trace['plan']['durationSeconds'] = 30
            if mode == 'provider':self.trace['commands'][0]['arguments'][6] = '0x640'
            if mode == 'order':self.trace['commands'].reverse()
            if mode == 'failed':self.trace['commands'][1]['exitCode'] = 1
            with self.subTest(mode=mode), self.assertRaises(ValueError):self.admit()

    def test_security_baseline_and_collector_role(self):
        original = copy.deepcopy(self.context)
        for key, value in [('completed', True), ('administratorToken', False), ('probeLaunched', True),
                           ('securityChanges', True), ('error', 'failed'), ('testProcessesBefore', [123])]:
            self.context = copy.deepcopy(original);self.context[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):self.admit()
        self.context = original;self.before['secureBoot'] = False
        with self.assertRaises(ValueError):self.admit()
        self.before['secureBoot'] = True;self.before['devices'] = []
        with self.assertRaises(ValueError):self.admit()

    def token_record(self):
        record = {'probeStartedUtc': '2026-10-30T23:00:06+00:00', 'probeCompletedUtc': '2026-10-30T23:00:09+00:00', 'probePid': 2001,
                  'parentImagePath': self.process['imagePath'], 'probeImagePath': r'C:\probe.exe', 'workerImagePath': r'C:\worker.exe', 'userProcesses': {}}
        created = int((datetime(2026,10,30,23,0,6,tzinfo=timezone.utc)-datetime(1601,1,1,tzinfo=timezone.utc)).total_seconds()*10**7)
        for n, role in enumerate(('parent','probe','worker')):
            evidence = dict(self.process, pid=2000+n, imagePath=record[role+'ImagePath'], tokenQueried=True,
                            elevated=False, elevationType=3, creationFileTimeUtc=str(created))
            record['userProcesses'][role] = {'process': evidence, 'checkedUtc': '2026-10-30T23:00:07+00:00'}
        return record

    def test_all_three_non_elevated_tokens(self):
        record = self.token_record();v.tokens(record, 2002)
        record['userProcesses']['worker']['process']['elevationType'] = 1
        v.tokens(record, 2002)

    def test_missing_elevated_or_unqueried_tokens(self):
        for role in ('parent','probe','worker'):
            for key, value in [('elevated', True), ('elevated', None), ('tokenQueried', False), ('elevationType', True), ('alive', False)]:
                record = self.token_record();record['userProcesses'][role]['process'][key] = value
                with self.subTest(role=role,key=key), self.assertRaises(ValueError):v.tokens(record, 2002)
            record = self.token_record();del record['userProcesses'][role]
            with self.assertRaises(ValueError):v.tokens(record, 2002)

    def test_wrong_worker_image_pid_or_query_window(self):
        for key, value in [('pid', 2003), ('imagePath', r'C:\unrelated.exe'), ('creationFileTimeUtc', '134379600000000000')]:
            record = self.token_record();record['userProcesses']['worker']['process'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):v.tokens(record, 2002)
        record = self.token_record();record['userProcesses']['worker']['checkedUtc'] = '2026-10-30T23:00:10+00:00'
        with self.assertRaises(ValueError):v.tokens(record, 2002)

    def test_plans_create_no_directory_and_launch_no_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            for script, seconds in ((s,t) for s in ('capture-controls-user-context.ps1', 'test-controls-user-probe.ps1') for t in (20,60)):
                target = Path(temporary)/script
                child = subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'scripts'/script),'-ContextDirectory',str(target),'-TraceSeconds',str(seconds)],
                                       capture_output=True,text=True,timeout=15)
                self.assertEqual(child.returncode,0,child.stderr)
                plan = json.loads(child.stdout)
                self.assertTrue(plan['planOnly']);self.assertFalse(plan['deviceAccess'])
                self.assertFalse(plan['selfElevates']);self.assertFalse(plan['securityChanges']);self.assertFalse(target.exists())
                self.assertEqual(plan['traceSeconds'],seconds)

    def test_invalid_duration_refused_before_context_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            for script in ('capture-controls-user-context.ps1','test-controls-user-probe.ps1'):
                target=Path(temporary)/script
                child=subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'scripts'/script),'-ContextDirectory',str(target),'-TraceSeconds','19'],
                                     capture_output=True,text=True,timeout=15)
                self.assertNotEqual(child.returncode,0);self.assertFalse(target.exists())

    def test_real_self_process_query_without_usb(self):
        path = str(ROOT/'scripts/inspect-process.psm1').replace("'", "''")
        child = subprocess.run(['pwsh','-NoProfile','-Command',
                                f"Import-Module '{path}'; Get-Sl3ProcessEvidence -ProcessId $PID -WithToken | ConvertTo-Json"],
                               capture_output=True,text=True,timeout=20)
        self.assertEqual(child.returncode,0,child.stderr)
        evidence = json.loads(child.stdout)
        self.assertTrue(evidence['alive']);self.assertTrue(evidence['tokenQueried'])
        self.assertIs(type(evidence['elevated']),bool)
        self.assertIn(evidence['elevationType'],(1,2,3))
        self.assertEqual(Path(evidence['imagePath']).name.casefold(),'pwsh.exe')
        self.assertRegex(evidence['creationFileTimeUtc'],r'^[1-9][0-9]{16,17}$')

    def saved_fixture(self, folder):
        def save(name, value):
            (folder/name).parent.mkdir(parents=True, exist_ok=True)
            (folder/name).write_text(json.dumps(value), encoding='utf-8')
        self.context.update(producerSha256=v.digest(ROOT/'scripts/capture-controls-user-context.ps1'))
        save('before-state.json', self.before)
        self.context['beforeStateSha256'] = v.digest(folder/'before-state.json')
        self.trace['producerSha256'] = v.digest(ROOT/'scripts/capture-usb-startup.ps1')
        save('admitted-trace.json', self.trace);save('admitted-context.json', self.context)
        save('collector-process.json', {'process': self.process, 'checkedUtc': self.now})
        trace = copy.deepcopy(self.trace);trace['status'] = 'window completed'
        save('trace/capture.json', trace)
        after = copy.deepcopy(self.before);after['collectedUtc'] = '2026-10-30T23:01:01+00:00'
        save('after-state.json', after)
        context = copy.deepcopy(self.context)
        context.update(completed=True, completedUtc='2026-10-30T23:01:02+00:00', testProcessesAfter=[],
                       afterStateSha256=v.digest(folder/'after-state.json'), traceRecordSha256=v.digest(folder/'trace/capture.json'))
        save('context.json', context)
        build_path = ROOT/'artifacts/build/native/native-build-Release.json'
        build = v.read(build_path);record = self.token_record()
        record.update(splitUserContext=True, buildManifestSha256=v.digest(build_path), runnerInputs=build['hostProbe']['controls']['scriptInputs'])
        for role, filename in (('probe','sl3_host_probe.exe'),('worker','sl3_usbdk.exe')):
            path = ROOT/'artifacts/build/native/Release'/filename
            record[role+'ImagePath'] = str(path)
            record['userProcesses'][role]['process']['imagePath'] = str(path)
        for name, key in (('context.json','contextSha256'), ('admitted-trace.json','admittedTraceSha256'),
                          ('admitted-context.json','admittedContextSha256'),('collector-process.json','collectorProcessSha256'),
                          ('before-state.json','beforeStateSha256'),('after-state.json','afterStateSha256'),('trace/capture.json','traceRecordSha256')):
            record[key] = v.digest(folder/name)
        save('run.json',record)
        return record, build['usbdk']['executableSha256'], build['hostProbe']['executableSha256']

    def test_final_bindings_compose_with_existing_native_trace_validator(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary);record, worker, probe = self.saved_fixture(folder)
            with patch.object(v.base, 'traced', return_value={'valid':True,'probe':{'nativeJournal':{'workerPid':2002}}}) as underlying:
                self.assertTrue(v.validate(folder,worker,probe)['nonElevatedParentProbeAndWorker'])
                underlying.assert_called_once_with(folder,worker,probe)

    def test_scope_selects_its_own_image_pins_and_trace_validator(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);record,worker,_=self.saved_fixture(folder)
            build=v.read(ROOT/'artifacts/build/native/native-build-Release.json')
            image=str(ROOT/'artifacts/build/native/Release/sl3_scope_probe.exe')
            record.update(scenario='Scope',traceSeconds=60,schema='sl3.scope-host.traced-run.v1',
                          probeImagePath=image,runnerInputs=build['scopeProbe']['scriptInputs'])
            record['userProcesses']['probe']['process']['imagePath']=image
            (folder/'run.json').write_text(json.dumps(record),encoding='utf-8')
            probe=build['scopeProbe']['executableSha256']
            with patch.object(v.base,'traced',return_value={'valid':True,'probe':{'nativeJournal':{'workerPid':2002}}}) as underlying:
                self.assertTrue(v.validate(folder,worker,probe,scope=True)['nonElevatedParentProbeAndWorker'])
                underlying.assert_called_once_with(folder,worker,probe,scope=True)
            for key,value in [('scenario','Controls'),('traceSeconds',20),('runnerInputs',build['hostProbe']['controls']['scriptInputs'])]:
                bad=copy.deepcopy(record);bad[key]=value
                (folder/'run.json').write_text(json.dumps(bad),encoding='utf-8')
                with patch.object(v.base,'traced',return_value={'valid':True,'probe':{'nativeJournal':{'workerPid':2002}}}):
                    with self.subTest(key=key),self.assertRaises(ValueError):v.validate(folder,worker,probe,scope=True)

    def test_broker_scope_selects_own_image_and_binds_server_creation_identity(self):
        # Synthetic surrounding records; the component trace validator is mocked here.
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);record,worker,_=self.saved_fixture(folder)
            build=v.read(ROOT/'artifacts/build/native/native-build-Release.json')
            image=str(ROOT/'artifacts/build/native/Release/sl3_broker_scope_probe.exe')
            record.update(scenario='BrokerScope',traceSeconds=60,schema='sl3.broker-scope.traced-run.v1',
                          probeImagePath=image,runnerInputs=build['brokerScopeProbe']['scriptInputs'])
            record['userProcesses']['probe']['process']['imagePath']=image
            (folder/'run.json').write_text(json.dumps(record),encoding='utf-8')
            (folder/'probe').mkdir()
            process=record['userProcesses']['probe']['process']
            session=['SL3-BROKER-SESSION-1','endpoint=fixture','server_pid='+str(process['pid']),
                     'server_created='+process['creationFileTimeUtc'],'worker_sha256='+worker.lower()]
            path=folder/'probe/broker-session.txt'
            def save_session(value):path.write_text('\n'.join(value)+'\n',encoding='ascii')
            save_session(session);probe=build['brokerScopeProbe']['executableSha256']
            with patch.object(v.base,'traced',return_value={'valid':True,'probe':{'nativeJournal':{'workerPid':2002}}}) as underlying:
                self.assertTrue(v.validate(folder,worker,probe,broker_scope=True)['nonElevatedParentProbeAndWorker'])
                underlying.assert_called_once_with(folder,worker,probe,broker_scope=True)
            for index,value in [(2,'server_pid=4000'),(3,'server_created=134379600000000001')]:
                bad=session.copy();bad[index]=value;save_session(bad)
                with patch.object(v.base,'traced',return_value={'valid':True,'probe':{'nativeJournal':{'workerPid':2002}}}):
                    with self.subTest(index=index),self.assertRaisesRegex(ValueError,'observed probe'):
                        v.validate(folder,worker,probe,broker_scope=True)
            save_session(session)
            for key,value in [('scenario','Scope'),('traceSeconds',20),('runnerInputs',build['scopeProbe']['scriptInputs'])]:
                bad=copy.deepcopy(record);bad[key]=value;(folder/'run.json').write_text(json.dumps(bad),encoding='utf-8')
                with patch.object(v.base,'traced',return_value={'valid':True,'probe':{'nativeJournal':{'workerPid':2002}}}):
                    with self.subTest(key=key),self.assertRaises(ValueError):v.validate(folder,worker,probe,broker_scope=True)

    def test_input_record_selects_own_image_pins_and_component(self):
        # Synthetic surrounding records; component validation is mocked only here.
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);record,worker,_=self.saved_fixture(folder)
            build=v.read(ROOT/'artifacts/build/native/native-build-Release.json')
            image=str(ROOT/'artifacts/build/native/Release/sl3_input_record_probe.exe')
            record.update(scenario='InputRecord',traceSeconds=60,schema='sl3.input-record.traced-run.v1',
                          expectedRateHz=44100,probeImagePath=image,runnerInputs=build['inputRecordProbe']['scriptInputs'])
            record['userProcesses']['probe']['process']['imagePath']=image
            def save(value):(folder/'run.json').write_text(json.dumps(value),encoding='utf-8')
            save(record);probe=build['inputRecordProbe']['executableSha256']
            component={'valid':True,'probe':{'nativeJournal':{'workerPid':2002}}}
            with patch.object(v.base,'traced',return_value=component) as underlying:
                result=v.validate(folder,worker,probe,input_record=True)
                self.assertTrue(result['nonElevatedParentProbeAndWorker'])
                underlying.assert_called_once_with(folder,worker,probe,input_record=True)
            for key,value in [('scenario','Controls'),('traceSeconds',20),('runnerInputs',build['scopeProbe']['scriptInputs'])]:
                bad=copy.deepcopy(record);bad[key]=value;save(bad)
                with patch.object(v.base,'traced',return_value=component):
                    with self.subTest(key=key),self.assertRaises(ValueError):v.validate(folder,worker,probe,input_record=True)

    def test_final_record_mutations_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary);record, worker, probe = self.saved_fixture(folder)
            for key, value in [('contextSha256','a'*64),('collectorProcessSha256','b'*64),('buildManifestSha256','c'*64),
                               ('probeTimedOut',True),('probeContainmentRequested',True),('tokenQueryError','denied'),
                               ('probeStartedUtc','2026-10-30T23:00:08+00:00'),('runnerInputs',{}),('traceSeconds',20)]:
                bad = copy.deepcopy(record);bad[key] = value
                (folder/'run.json').write_text(json.dumps(bad),encoding='utf-8')
                with patch.object(v.base, 'traced', return_value={'valid':True,'probe':{'nativeJournal':{'workerPid':2002}}}):
                    with self.subTest(key=key), self.assertRaises(ValueError):v.validate(folder,worker,probe)

    def test_short_capture_requires_post_release_interval(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary);self.context['traceSeconds']=20
            self.trace['plan']['durationSeconds']=20
            record, worker, probe = self.saved_fixture(folder)
            record['traceSeconds']=20
            (folder/'run.json').write_text(json.dumps(record),encoding='utf-8')
            trace=v.read(folder/'trace/capture.json')
            context=v.read(folder/'context.json')
            for stop,valid in [('2026-10-30T23:00:21+00:00',True),('2026-10-30T23:00:20.999+00:00',False)]:
                trace['stoppedUtc']=stop
                (folder/'trace/capture.json').write_text(json.dumps(trace),encoding='utf-8')
                context['traceRecordSha256']=v.digest(folder/'trace/capture.json')
                (folder/'context.json').write_text(json.dumps(context),encoding='utf-8')
                record.update(contextSha256=v.digest(folder/'context.json'),traceRecordSha256=context['traceRecordSha256'])
                (folder/'run.json').write_text(json.dumps(record),encoding='utf-8')
                with patch.object(v.base,'traced',return_value={'valid':True,'probe':{'nativeJournal':{'workerPid':2002}}}):
                    if valid:self.assertTrue(v.validate(folder,worker,probe)['nonElevatedParentProbeAndWorker'])
                    else:
                        with self.assertRaises(ValueError):v.validate(folder,worker,probe)

    def test_cold_verifier_requires_fresh_independent_launch_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.now='2026-10-30T23:00:02+00:00'
            folder=Path(temporary);record,worker,probe=self.saved_fixture(folder)
            launch={'trace':copy.deepcopy(self.trace),'process':copy.deepcopy(self.process),
                    'checkedUtc':'2026-10-30T23:00:05.5+00:00'}
            def save(value):
                path=folder/'launch-admission.json';path.write_text(json.dumps(value),encoding='utf-8')
                record['launchAdmissionSha256']=v.digest(path)
                (folder/'run.json').write_text(json.dumps(record),encoding='utf-8')
            save(launch)
            with patch.object(v.base,'traced',return_value={'valid':True,'probe':{'nativeJournal':{'workerPid':2002}}}):
                self.assertTrue(v.validate(folder,worker,probe)['nonElevatedParentProbeAndWorker'])
                original=copy.deepcopy(launch)
                for fault in ('old','future','reused','changed','stopped','hash'):
                    launch=copy.deepcopy(original)
                    if fault=='old':launch['checkedUtc']='2026-10-30T23:00:03.9+00:00'
                    if fault=='future':launch['checkedUtc']='2026-10-30T23:00:06.1+00:00'
                    if fault=='reused':launch['process']['creationFileTimeUtc']='134379600000000001'
                    if fault=='changed':launch['trace']['session']='SL3Startup-'+'b'*32
                    if fault=='stopped':launch['trace']['status']='window completed'
                    save(launch)
                    if fault=='hash':
                        (folder/'launch-admission.json').write_text('{}',encoding='utf-8')
                    with self.subTest(fault=fault),self.assertRaises(ValueError):v.validate(folder,worker,probe)
                del record['launchAdmissionSha256']
                (folder/'run.json').write_text(json.dumps(record),encoding='utf-8')
                with self.assertRaises(ValueError):v.validate(folder,worker,probe)


if __name__ == '__main__':
    unittest.main()
