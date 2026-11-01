"""Synthetic split-role rate qualification and actual inert/refusal CLI checks; no USB or elevation."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch
from tests import test_selection_user_probe as selection_fixtures
from tests import test_rate_probe_evidence as rate_fixtures
save=selection_fixtures.save

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
v=module('rate_user_test_validator',ROOT/'scripts/validate-rate-user-probe.py')
p=module('rate_user_test_planner',ROOT/'scripts/prepare-rate-trace.py')

class RateUserTests(unittest.TestCase):
    def test_actual_plan_only_and_invalid_run_do_not_create_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            context=Path(temporary)/'must-not-exist'
            command=['pwsh','-NoProfile','-File',str(ROOT/'scripts/test-rate-user-probe.ps1'),'-ContextDirectory',str(context)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr);plan=json.loads(result.stdout)
            self.assertTrue(plan['planOnly']);self.assertFalse(plan['deviceAccess']);self.assertFalse(plan['selfElevates'])
            self.assertEqual(plan['maximumRateSetters'],1);self.assertEqual(plan['traceSeconds'],60);self.assertEqual(plan['probeDeadlineSeconds'],30)
            for extra in (['-TargetHz','048000'],['-Run'],['-Run','-TargetHz','44100'],['-ExpectedInitialHz','48000 ']):
                result=subprocess.run(command+extra,capture_output=True,text=True,timeout=15)
                self.assertNotEqual(result.returncode,0,result.stdout)
            self.assertFalse(context.exists())

    def test_planner_target_runtime_context_and_single_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'analysis').mkdir();(root/'tests/results/local').mkdir(parents=True)
            directory=root/'analysis/rate-trace-unit';directory.mkdir();path=directory/'rate-trace.json'
            with patch.object(p,'ROOT',root),patch.object(p,'runtime',return_value={'synthetic':True}):
                value=p.plan_value(directory,44100,48000);save(directory,'rate-trace.json',value)
                self.assertEqual(p.validate(path),value);self.assertEqual(value['normalRole']['arguments'][1:5],['-TargetHz','44100','-ExpectedInitialHz','48000'])
                for field,new in [('targetHz',48000),('expectedInitialHz',44100),('traceSeconds',20),('maximumRateSetters',2),('automaticRollback',True)]:
                    bad=copy.deepcopy(value);bad[field]=new;save(directory,'rate-trace.json',bad)
                    if field in ('targetHz','expectedInitialHz'):
                        # A pre-launch saved target is reviewable plan data; its
                        # SHA binds it at claim. Both role arguments must match.
                        with self.assertRaises(ValueError):p.validate(path)
                    else:
                        with self.assertRaises(ValueError):p.validate(path)
                save(directory,'rate-trace.json',value);save(directory,'attempted.json',{'status':'consumed'})
                with self.assertRaises(ValueError):p.validate(path)
                self.assertEqual(p.validate(path,claimed=True),value)
                for target in (0,True,'44100',96000):
                    with self.assertRaises(ValueError):p.plan_value(directory,target,48000)

    def fixture(self,root):
        folder,_,_,_,record,worker,probe=selection_fixtures.SelectionUserTests().fixture(root)
        bound={'buildManifestSha256':v.digest(v.BUILD),'runnerInputs':{n:v.digest(ROOT/'scripts'/n) for n in v.RUNNER_INPUTS}}
        with patch.object(v,'build_contract',return_value=bound):intent=v.intent_value(44100,48000,worker,probe)
        save(folder,'intent.json',intent)
        result,request=rate_fixtures.records()
        for obj in (result,request):obj.update(simulated=False,worker_sha256=worker.lower())
        save(folder,'probe/probe.json',result);save(folder,'probe/request.json',request)
        native=rate_fixtures.RateProbeEvidenceTests().native();native['utc']='2026-10-30T23:00:07+00:00'
        save(folder,'probe/worker-1.tsv.rate/rate.json',native)
        (folder/'probe/worker-1.tsv').write_text(''.join(f'{i+100}\t2002\t{s}\n' for i,s in enumerate(rate_fixtures.stages())),encoding='ascii')
        save(folder,'probe-validation.json',v.selected.probe(folder/'probe',worker))
        for name in ('context.json','admitted-context.json'):
            context=v.read(folder/name);context['traceSeconds']=60;save(folder,name,context)
        launch={'trace':v.read(folder/'admitted-trace.json'),'process':v.read(folder/'collector-process.json')['process'],
            'checkedUtc':v.read(folder/'collector-process.json')['checkedUtc']}
        save(folder,'launch-admission.json',launch)
        record.update(schema='sl3.rate-user.traced-run.v1',targetHz=44100,expectedInitialHz=48000,traceSeconds=60,rateRestorationVerified=False,**bound)
        for name,key in [('intent.json','intentRecordSha256'),('context.json','contextSha256'),('admitted-context.json','admittedContextSha256'),
            ('launch-admission.json','launchAdmissionSha256'),('probe/request.json','requestRecordSha256'),('probe/probe.json','probeRecordSha256'),
            ('probe-validation.json','probeValidationSha256'),('probe/worker-1.tsv.rate/rate.json','nativeRateRecordSha256')]:record[key]=v.digest(folder/name)
        save(folder,'run.json',record)
        return folder,bound,record,worker,probe

    def test_complete_synthetic_rate_envelope_qualifies_only_its_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder,bound,record,worker,probe=self.fixture(Path(temporary))
            with patch.object(v,'build_contract',return_value=bound):result=v.validate(folder,worker,probe)
            self.assertTrue(result['valid']);self.assertTrue(result['nonElevatedParentProbeAndWorker'])
            self.assertFalse(result['rateRestorationVerified']);self.assertFalse(result['usbPayloadCorrelationVerified'])
            self.assertFalse(result['audioStreamingVerified'])

    def test_intent_and_runtime_mutations_refuse_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder,bound,record,worker,probe=self.fixture(Path(temporary));intent=v.read(folder/'intent.json')
            for key,value in [('targetHz',True),('expectedInitialHz','48000'),('runnerInputs',{}),('valid',False),('schema','other')]:
                bad=copy.deepcopy(intent);bad[key]=value;save(folder,'intent.json',bad)
                with patch.object(v,'build_contract',return_value=bound),self.subTest(key=key),self.assertRaises(ValueError):v.admission(folder)
            save(folder,'intent.json',intent)
            with patch.object(v,'build_contract',side_effect=ValueError('changed source')),self.assertRaises(ValueError):v.admission(folder)

    def test_trace_retirement_target_clock_and_cleanup_failures_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder,bound,record,worker,probe=self.fixture(Path(temporary))
            for key,value in [('rateRestorationVerified',True),('targetHz',48000),('expectedInitialHz',44100),('traceSeconds',20),
                ('probeCompletedUtc','2026-10-30T23:00:49+00:00'),('probeStartedUtc','2026-10-30T23:00:09+00:00'),
                ('traceCleanupConfirmed',False),('probeTimedOut',True),('nativeRateRecordSha256','0'*64),('launchAdmissionSha256','0'*64)]:
                bad=copy.deepcopy(record);bad[key]=value;save(folder,'run.json',bad)
                with patch.object(v,'build_contract',return_value=bound),self.subTest(key=key),self.assertRaises(ValueError):v.validate(folder,worker,probe)
            save(folder,'run.json',record)
            native=v.read(folder/'probe/worker-1.tsv.rate/rate.json');native['utc']='2026-10-30T22:00:00+00:00'
            save(folder,'probe/worker-1.tsv.rate/rate.json',native);record['nativeRateRecordSha256']=v.digest(folder/'probe/worker-1.tsv.rate/rate.json');save(folder,'run.json',record)
            with patch.object(v,'build_contract',return_value=bound),self.assertRaises(ValueError):v.validate(folder,worker,probe)

    def test_current_build_and_actual_inert_launcher_then_disarm(self):
        build=v.read(v.BUILD);worker=build['usbdk']['executableSha256'];probe=build['hostProbe']['executableSha256']
        bound=v.build_contract(worker,probe);self.assertEqual(set(bound['runnerInputs']),set(v.RUNNER_INPUTS));self.assertEqual(len(v.RUNNER_INPUTS),23)
        for mutation in ('missing-pin','wrong-source','unprepared'):
            bad=copy.deepcopy(build)
            if mutation=='missing-pin':bad['hostProbe']['rateSelection']['traceScriptInputs'].pop('test-rate-user-probe.ps1')
            if mutation=='wrong-source':bad['inputs']['src/windows/host_probe_main.cpp']='0'*64
            if mutation=='unprepared':bad['hostProbe']['rateSelection']['traceRunnerPrepared']=False
            with patch.object(v,'read',return_value=bad),self.assertRaises(ValueError):v.build_contract(worker,probe)
        directory=ROOT/'analysis'/('rate-trace-unit-'+uuid.uuid4().hex)
        result=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'scripts/prepare-rate-trace.py'),'--prepare',str(directory),
            '--target','44100','--expected-initial','48000'],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        plan=directory/'rate-trace.json';value=json.loads(result.stdout);context=Path(value['contextDirectory'])
        command=['pwsh','-NoProfile','-File',str(ROOT/'scripts/start-rate-trace.ps1'),'-Plan',str(plan)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout),value)
        self.assertFalse(context.exists());self.assertFalse((directory/'normal-started.json').exists());self.assertFalse((directory/'collector-started.json').exists())
        # These unit-test plans must never become attended launch candidates.
        save(directory,'attempted.json',{'status':'disarmed_without_execution','sourceStarted':False,'deviceAccess':False})
        result=subprocess.run(command,capture_output=True,text=True,timeout=15)
        self.assertNotEqual(result.returncode,0);self.assertFalse(context.exists())

    def test_powershell_source_parses_and_keeps_fixed_roles(self):
        for name in ('test-rate-user-probe.ps1','start-rate-trace.ps1'):
            source=str(ROOT/'scripts'/name).replace("'","''")
            code=f"$e=$null;$t=$null;[void][Management.Automation.Language.Parser]::ParseFile('{source}',[ref]$t,[ref]$e);if($e.Count){{$e;exit 1}}"
            result=subprocess.run(['pwsh','-NoProfile','-Command',code],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
        normal=(ROOT/'scripts/test-rate-user-probe.ps1').read_text(encoding='utf-8')
        self.assertNotIn('-Verb RunAs',normal);self.assertIn('Preserve-ProbeFiles',normal);self.assertIn('launch-admission.json',normal)
        launcher=(ROOT/'scripts/start-rate-trace.ps1').read_text(encoding='utf-8')
        self.assertEqual(launcher.count('-Verb RunAs'),1);self.assertIn('[IO.FileMode]::CreateNew',launcher)

if __name__=='__main__':unittest.main()
