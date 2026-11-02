"""Broker scope plan reconstruction and actual non-elevating launcher guards; no USB open."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('scope_trace_tests',ROOT/'scripts/prepare-broker-scope-trace.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
REAL_RUNTIME=v.runtime


class PlanTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);(self.root/'analysis').mkdir()
        (self.root/'tests/results/local').mkdir(parents=True)
        self.directory=self.root/'analysis/broker-scope-trace-test';self.directory.mkdir()
        self.path=self.directory/'broker-scope-trace.json'
        for mocker in (patch.object(v,'ROOT',self.root),patch.object(v,'runtime',return_value={'tested':'original'})):
            mocker.start();self.addCleanup(mocker.stop)
        self.plan=v.plan_value(self.directory);self.save(self.plan)

    def save(self,value):self.path.write_text(json.dumps(value),encoding='utf-8')

    def invoke(self,*args):
        with patch.object(sys,'argv',['prepare-broker-scope-trace.py',*map(str,args)]),contextlib.redirect_stdout(io.StringIO()) as output:
            v.main()
        return json.loads(output.getvalue())

    def test_fixed_roles_and_no_output_context(self):
        self.assertEqual(v.validate(self.path),self.plan)
        self.assertEqual(self.plan['normalRole']['arguments'][:5],['-Run','-Scenario','BrokerScope','-TraceSeconds','60'])
        self.assertEqual(self.plan['redirectsRequested'],1)
        self.assertEqual(self.plan['audioStarts'],0)
        self.assertEqual(self.plan['clientProcesses'],3)
        self.assertEqual(self.plan['clockReads'],7)
        self.assertEqual(self.plan['schema'],'sl3.broker-scope-trace.plan.v1')
        self.assertEqual(self.plan['postRetirementTraceSecondsRequired'],12)
        self.assertFalse(Path(self.plan['contextDirectory']).exists())

    def test_plan_changes_cannot_expand_roles_or_operations(self):
        changes=[('traceSeconds',20),('audioStarts',1),('automaticRetry',True),('imageWindowQualified',True),
                 ('contextDirectory',str(self.root/'elsewhere')),('normalRole',{'script':'unreviewed.ps1'}),
                 ('collectorRole',{'script':'unreviewed.ps1'}),('runtime',{'tested':'changed'})]
        for key,value in changes:
            with self.subTest(key=key):
                bad=copy.deepcopy(self.plan);bad[key]=value;self.save(bad)
                with self.assertRaisesRegex(ValueError,'changed'):v.validate(self.path)

    def test_changed_runtime_invalidates_saved_plan(self):
        with patch.object(v,'runtime',return_value={'tested':'rebuilt'}):
            with self.assertRaisesRegex(ValueError,'changed'):v.validate(self.path)

    def test_consumed_plan_and_existing_context_refused(self):
        (self.directory/'attempted.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'already attempted'):v.validate(self.path)
        Path(self.plan['contextDirectory']).mkdir()
        with self.assertRaisesRegex(ValueError,'fresh'):v.validate(self.path,claimed=True)

    def test_unsafe_output_and_wrong_filename_refused(self):
        for path in (self.root/'broker-scope-trace-test',self.root/'analysis/not-scope',self.directory/'nested'):
            with self.subTest(path=path),self.assertRaises(ValueError):v.plan_value(path)
        with self.assertRaisesRegex(ValueError,'filename'):v.validate(self.directory/'other.json')

    def test_collector_requires_matching_single_use_claim(self):
        ident='a'*32;digest=v.sha(self.path)
        args=('--collector-check',self.path,'--expected-sha256',digest,'--launch-id',ident)
        with self.assertRaises(FileNotFoundError):self.invoke(*args)
        claim={'launchId':ident,'planSha256':digest}
        for name in ('attempted.json','normal-started.json'):
            (self.directory/name).write_text(json.dumps(claim))
        self.assertEqual(self.invoke(*args),self.plan)
        bad={**claim,'launchId':'b'*32}
        (self.directory/'normal-started.json').write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,'matching'):self.invoke(*args)
        (self.directory/'normal-started.json').write_text(json.dumps(claim))
        (self.directory/'collector-started.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'already attempted'):self.invoke(*args)

    def test_wrong_hash_and_internal_arguments_refused(self):
        with self.assertRaisesRegex(ValueError,'binding'):
            self.invoke('--collector-check',self.path,'--expected-sha256','0'*64,'--launch-id','a'*32)
        with self.assertRaisesRegex(ValueError,'Internal arguments'):
            self.invoke('--plan',self.path,'--launch-id','a'*32)

    def test_launcher_dependency_set_cannot_be_empty_or_substituted(self):
        manifest={'buildScriptSha256':'a'*64,'inputs':{},'brokerScopeProbe':{
            'scriptInputs':{f'fixture-{i}':'a'*64 for i in range(19)},'traceLauncherInputs':{}}}
        # Exercise the real runtime checker, stopping before it resolves images or PowerShell.
        with patch.object(v,'runtime',wraps=REAL_RUNTIME):
            for pins in ({},{'other.py':'a'*64,'start-broker-scope-trace.ps1':'a'*64}):
                manifest['brokerScopeProbe']['traceLauncherInputs']=pins
                with patch.object(v,'read',return_value=manifest),patch.object(v,'sha',return_value='a'*64):
                    with self.subTest(pins=pins),self.assertRaisesRegex(ValueError,'launcher dependencies missing'):v.runtime()

    def test_trace_schemas_cannot_cross_qualify(self):
        module_spec=importlib.util.spec_from_file_location('scope_trace_schema_test',ROOT/'scripts/validate-controls-host-probe.py')
        validator=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(validator)
        for schema,scope in (('sl3.controls-host.traced-run.v1',True),('sl3.broker-scope.traced-run.v1',False)):
            (self.directory/'run.json').write_text(json.dumps({'schema':schema,'completed':True,'error':None}))
            with self.subTest(schema=schema),self.assertRaisesRegex(ValueError,'Incomplete traced'):
                validator.traced(self.directory,'a'*64,'b'*64,broker_scope=scope)


class ActualLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=ROOT/'analysis'/('broker-scope-trace-test-'+uuid.uuid4().hex)
        result=subprocess.run([sys.executable,str(ROOT/'scripts/prepare-broker-scope-trace.py'),'--prepare',str(cls.directory)],
                              capture_output=True,text=True,timeout=20)
        if result.returncode:raise RuntimeError(result.stderr)
        cls.plan=json.loads(result.stdout);cls.path=cls.directory/'broker-scope-trace.json'

    def invoke(self,*args):
        return subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'scripts/start-broker-scope-trace.ps1'),
                               '-Plan',str(self.path),*args],capture_output=True,text=True,timeout=25)

    def test_default_inspection_creates_no_launch_or_context(self):
        before={p.name for p in self.directory.iterdir()}
        child=self.invoke();self.assertEqual(child.returncode,0,child.stderr)
        self.assertEqual(json.loads(child.stdout),self.plan)
        self.assertEqual({p.name for p in self.directory.iterdir()},before)
        self.assertFalse(Path(self.plan['contextDirectory']).exists())

    def test_normal_collector_role_denied_and_cannot_overwrite_evidence(self):
        module=str(ROOT/'scripts/inspect-process.psm1').replace("'","''")
        token=subprocess.run(['pwsh','-NoProfile','-Command',
                              f"Import-Module '{module}'; Get-Sl3ProcessEvidence -ProcessId $PID -WithToken | ConvertTo-Json"],
                             capture_output=True,text=True,timeout=20)
        self.assertEqual(token.returncode,0,token.stderr)
        observed=json.loads(token.stdout)
        if observed['elevated']:self.skipTest('Requires ordinary token for direct denial check')
        self.assertTrue(observed['tokenQueried'])
        ident=uuid.uuid4().hex
        args=('-Execute','-ExpectedSha256',v.sha(self.path),'-LaunchId',ident)
        child=self.invoke(*args);self.assertNotEqual(child.returncode,0)
        output=self.directory/f'collector-{ident}-exit.json'
        saved=json.loads(output.read_text(encoding='utf-8-sig'))
        self.assertEqual(saved['exitCode'],1)
        self.assertIn('requires elevation',saved['error'])
        before=v.sha(output)
        retry=self.invoke(*args);self.assertNotEqual(retry.returncode,0)
        self.assertEqual(v.sha(output),before)
        self.assertFalse((self.directory/'collector-started.json').exists())
        self.assertFalse((self.directory/'attempted.json').exists())
        self.assertFalse(Path(self.plan['contextDirectory']).exists())

    def test_internal_arguments_never_launch(self):
        child=self.invoke('-ExpectedSha256','a'*64)
        self.assertNotEqual(child.returncode,0)
        self.assertIn('Internal arguments',child.stderr)
        self.assertFalse((self.directory/'attempted.json').exists())
        self.assertFalse(Path(self.plan['contextDirectory']).exists())

    def test_normal_role_plan_stays_offline_and_describes_broker_reads(self):
        target=self.directory/'must-not-be-created'
        child=subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'scripts/test-controls-user-probe.ps1'),
                              '-Scenario','BrokerScope','-ContextDirectory',str(target)],
                             capture_output=True,text=True,timeout=20)
        self.assertEqual(child.returncode,0,child.stderr);plan=json.loads(child.stdout)
        self.assertEqual(plan['scenario'],'BrokerScope');self.assertTrue(plan['planOnly'])
        self.assertFalse(plan['deviceAccess']);self.assertFalse(plan['selfElevates'])
        self.assertEqual(plan['redirectsRequested'],1);self.assertEqual(plan['audioStartAttempts'],0)
        self.assertEqual(plan['probeDeadlineSeconds'],30)
        self.assertIn('seven rate',str(plan['getters']));self.assertFalse(target.exists())

    def test_scope_short_window_rejected_before_run(self):
        child=subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'scripts/test-controls-user-probe.ps1'),
                              '-Scenario','BrokerScope','-TraceSeconds','20'],capture_output=True,text=True,timeout=20)
        self.assertNotEqual(child.returncode,0)
        self.assertIn('sixty-second trace',child.stderr)


if __name__=='__main__':unittest.main()
