"""Synthetic split-role setting evidence and actual plan-only invocations; no USB."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('selection_user_validator',ROOT/'scripts/validate-selection-user-probe.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
operation=v.module('selection_operation_fixtures',ROOT/'tests/test_selection_probe_evidence.py')
controls=v.module('selection_role_fixtures',ROOT/'tests/test_controls_user_probe.py')
TARGET={'setting':'through','group':0,'value':1}


def save(folder,name,value):
    path=folder/name;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8')


class SelectionUserTests(unittest.TestCase):
    def test_canonical_target_and_plan_only_no_io(self):
        for text in ('sensitivity:0:0','sensitivity:2:15','through:0:0','through:2:1'):
            v.selected.target(v.target(text))
        for text in ('','through:0:2','through:00:1','Through:0:1','sensitivity:1:16','through:0:1\n',None,True):
            with self.assertRaises(ValueError):v.target(text)
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)/'must-not-exist'
            command=['pwsh','-NoProfile','-File',str(ROOT/'scripts/test-selection-user-probe.ps1'),'-ContextDirectory',str(folder)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr);plan=json.loads(result.stdout)
            self.assertTrue(plan['planOnly']);self.assertFalse(plan['deviceAccess']);self.assertFalse(plan['selfElevates'])
            self.assertEqual(plan['probeDeadlineSeconds'],50);self.assertEqual(plan['maximumControlSetters'],1)
            for extra in (['-Target','through:0:2'],['-Run','-Target','through:0:1'],['-BaselineDirectory','\\\\host\\share']):
                result=subprocess.run(command+extra,capture_output=True,text=True,timeout=15)
                self.assertNotEqual(result.returncode,0,result.stdout)
            self.assertFalse(folder.exists())
            # Execute only the trusted evidence-preservation function, not the runner.
            source=str(ROOT/'scripts/test-selection-user-probe.ps1').replace("'","''")
            context=str(Path(temporary)/'partial-evidence').replace("'","''")
            code=f"""$ErrorActionPreference='Stop';$errors=$null;$tokens=$null
$ast=[Management.Automation.Language.Parser]::ParseFile('{source}',[ref]$tokens,[ref]$errors)
if($errors.Count){{throw 'Runner parse error'}}
$definition=$ast.Find({{param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq 'Preserve-ProbeFiles'}},$true)
. ([scriptblock]::Create($definition.Extent.Text))
$ContextDirectory='{context}';$null=New-Item -ItemType Directory -Path (Join-Path $ContextDirectory 'probe') -Force
[IO.File]::WriteAllText((Join-Path $ContextDirectory 'probe/request.json'),'{{}}')
[IO.File]::WriteAllText((Join-Path $ContextDirectory 'probe/probe.json'),'{{}}')
$record=[ordered]@{{error=$null}};Preserve-ProbeFiles;$successful=$record
$locked=[IO.File]::Open((Join-Path $ContextDirectory 'probe/probe.json'),[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try{{$record=[ordered]@{{error='original operation failure'}};Preserve-ProbeFiles
    [ordered]@{{successful=$successful;failed=$record}}|ConvertTo-Json -Depth 4
}}finally{{$locked.Dispose()}}
"""
            result=subprocess.run(['pwsh','-NoProfile','-Command',code],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr);data=json.loads(result.stdout)
            self.assertIsNone(data['successful']['error']);self.assertEqual(data['successful']['requestRecordSha256'],data['successful']['probeRecordSha256'])
            self.assertEqual(data['failed']['error'],'original operation failure');self.assertTrue(data['failed']['evidencePreservationError'])

    def test_current_build_contract_and_dependency_failures(self):
        build=v.read(v.BUILD);worker=build['usbdk']['executableSha256'];probe=build['hostProbe']['executableSha256']
        result=v.build_contract(worker,probe)
        self.assertEqual(set(result['runnerInputs']),set(v.RUNNER_INPUTS));self.assertEqual(len(v.RUNNER_INPUTS),22)
        for change in ('missing-pin','wrong-pin','unprepared','native-positive','wrong-source'):
            bad=copy.deepcopy(build);feature=bad['hostProbe']['selection']
            if change=='missing-pin':feature['traceScriptInputs'].pop('test-selection-user-probe.ps1')
            if change=='wrong-pin':feature['traceScriptInputs']['test-selection-user-probe.ps1']='0'*64
            if change=='unprepared':feature['supervisedLauncherPrepared']=False
            if change=='native-positive':feature['nativeSettingRunDuringBuild']=True
            if change=='wrong-source':bad['inputs']['src/windows/host_probe_main.cpp']='0'*64
            with patch.object(v,'read',return_value=bad),self.subTest(change=change),self.assertRaises(ValueError):v.build_contract(worker,probe)

    def fixture(self,root):
        baseline=root/'baseline';folder=root/'selection';baseline.mkdir();folder.mkdir()
        source=controls.UserControlsTests();source.setUp();record,worker,probe=source.saved_fixture(folder)
        before=v.read(folder/'before-state.json')
        before.update(deviceGuard={},hvciRegistry={},asio=[],application={})
        before['devices'][0]['properties']=[]
        save(folder,'before-state.json',before)
        after=copy.deepcopy(before);after['collectedUtc']='2026-10-30T23:01:01+00:00';save(folder,'after-state.json',after)
        prior=copy.deepcopy(before);prior['collectedUtc']='2026-10-30T22:59:35+00:00'
        for name in ('before-state.json','after-state.json'):save(baseline,name,prior)
        save(baseline,'run.json',{'schema':'sl3.controls-host.traced-run.v1','splitUserContext':True,'completed':True,
                                'completedUtc':'2026-10-30T22:59:40+00:00'})
        save(baseline,'context.json',{'completedUtc':'2026-10-30T22:59:39+00:00'})
        save(baseline,'probe/probe.json',{'schema':'sl3.controls-host-probe.v1','simulated':False,'successful':True,
             'raw_controls':[0]*22,'acquisition':{'rate_hz':44100}})
        bound={'buildManifestSha256':v.digest(v.BUILD),'runnerInputs':{name:v.digest(ROOT/'scripts'/name) for name in v.RUNNER_INPUTS}}
        intent={'schema':'sl3.selection-user.intent.v1','valid':True,'scope':'synthetic unit-test prerequisite',
                'target':TARGET,'workerSha256':worker.lower(),'probeSha256':probe.lower(),**bound,
                'baselineDirectory':str(baseline.resolve()),'baselineCompletedUtc':'2026-10-30T22:59:40+00:00',
                'baselineFiles':{name:v.digest(baseline/name) for name in ('run.json','probe/probe.json','before-state.json','after-state.json')},
                'reviewedRawControls':[0]*22,'reviewedRateHz':44100}
        save(folder,'intent.json',intent)
        context=v.read(folder/'admitted-context.json');context['beforeStateSha256']=v.digest(folder/'before-state.json')
        save(folder,'admitted-context.json',context)
        trace=v.read(folder/'trace/capture.json');trace['stoppedUtc']='2026-10-30T23:01:00+00:00'
        trace['commands'].append({'arguments':['delete','-n',trace['session']],'exitCode':0})
        preparer=v.module('selection_test_tmf',ROOT/'scripts/prepare-usbdk-lifecycle-trace.py');expected,tmf=preparer.check()
        decoder=folder/'trace/lifecycle-decoder';decoder.mkdir()
        save(decoder,'plan.json',expected);(decoder/'lifecycle.tmf').write_bytes(tmf)
        trace['plan']['lifecycle']={'provider':expected['providerGuid'],'flags':expected['flags'],'level':expected['level'],
             'driverSha256':expected['driverSha256'],'selectedTmfSha256':expected['selectedTmfSha256'],'emissionVerified':False}
        trace['lifecycleDecoder']={'sourceSha256':v.digest(ROOT/'scripts/prepare-usbdk-lifecycle-trace.py'),
             'planSha256':v.digest(decoder/'plan.json'),'tmfSha256':v.digest(decoder/'lifecycle.tmf')}
        save(folder,'trace/capture.json',trace)
        context.update(completed=True,error=None,completedUtc='2026-10-30T23:01:02+00:00',testProcessesAfter=[],
             afterStateSha256=v.digest(folder/'after-state.json'),traceRecordSha256=v.digest(folder/'trace/capture.json'))
        save(folder,'context.json',context)
        (folder/'trace/synthetic.etl').write_bytes(b'Synthetic test bytes; no physical capture or decoding')
        (folder/'events.xml').write_text('<Events xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><Event><System>'
             '<Provider Guid="{9e814aad-3204-11d2-9a82-006008a86939}"/></System><EventData>'
             '<Data Name="EventsLost">0</Data><Data Name="BuffersLost">0</Data>'
             f'<Data Name="SessionNameString">{trace["session"]}</Data></EventData></Event></Events>',encoding='utf-8')
        result,request=operation.records()
        for obj in (result,request):obj.update(simulated=False,worker_sha256=worker.lower(),reviewed_baseline_raw_controls=[0]*22)
        save(folder,'probe/probe.json',result);save(folder,'probe/request.json',request)
        stages=['worker.enter','control_target_through.enter','control_group_zero.enter','control_value_one.enter','helper_load.enter','helper_load.return',
                'enumerate.enter','enumerate.return','configuration.enter','configuration.return','redirect_start.enter','redirect_start.return',
                'system_handle.enter','system_handle.return','clock_getter.enter','clock_getter.return','audio_controls.enter',
                'audio_controls_write.enter','audio_controls_write.return','audio_controls_read.enter','audio_controls_read.return','audio_controls.return',
                'audio_control_selection.enter']
        for stem in ('audio_controls_write','audio_control_selection_set','audio_controls_write'):
            stages += [stem+'.enter',stem+'.return','audio_controls_read.enter','audio_controls_read.return']
        stages += ['audio_control_selection_possible_write.return','audio_control_selection_verified.return','audio_control_selection.return',
                   'redirect_close.enter','redirect_close.return','helper_unload.enter','helper_unload.return']
        (folder/'probe/worker-1.tsv').write_text(''.join(f'{i+100}\t2002\t{stage}\n' for i,stage in enumerate(stages)),encoding='ascii')
        save(folder,'probe-validation.json',v.selected.probe(folder/'probe',worker))
        record.update(schema='sl3.selection-user.traced-run.v1',completed=True,error=None,probeExitCode=0,traceExitCode=0,
             traceCleanupConfirmed=True,secureBootBefore=True,secureBootAfter=True,recoveryConfirmed=True,withUsbDkLifecycle=True,
             withUsbIdentity=False,driverChanges=False,securityChanges=False,asioRegistration=False,automaticRetry=False,
             workerSha256=worker.lower(),probeSha256=probe.lower(),target=TARGET,**bound,
             completedUtc='2026-10-30T23:01:03+00:00',etlSha256=v.digest(folder/'trace/synthetic.etl'),
             traceStats=v.base.physical.capture_validator.trace_statistics(folder/'events.xml'))
        for name,key in (('intent.json','intentRecordSha256'),('context.json','contextSha256'),('admitted-context.json','admittedContextSha256'),
                         ('before-state.json','beforeStateSha256'),('after-state.json','afterStateSha256'),('trace/capture.json','traceRecordSha256'),
                         ('probe/request.json','requestRecordSha256'),('probe/probe.json','probeRecordSha256'),('probe-validation.json','probeValidationSha256')):
            record[key]=v.digest(folder/name)
        save(folder,'run.json',record)
        return folder,baseline,intent,bound,record,worker,probe

    def test_prerequisite_requires_actual_normal_token_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder,baseline,intent,bound,record,worker,probe=self.fixture(Path(temporary))
            native={'valid':True,'nonElevatedParentProbeAndWorker':True,'probe':{'simulated':False,'rawControls':[0]*22,'rateHz':44100}}
            with patch.object(v,'build_contract',return_value=bound),patch.object(v.user,'validate',return_value=native) as underlying:
                actual=v.prerequisite(baseline,TARGET,worker,probe)
                underlying.assert_called_once_with(baseline.resolve(),worker,probe)
                self.assertEqual(actual['reviewedRawControls'],[0]*22);self.assertEqual(actual['target'],TARGET)
            for key in ('valid','nonElevatedParentProbeAndWorker','simulated'):
                bad=copy.deepcopy(native)
                if key=='simulated':bad['probe']['simulated']=True
                else:bad[key]=False
                with patch.object(v,'build_contract',return_value=bound),patch.object(v.user,'validate',return_value=bad),self.assertRaises(ValueError):
                    v.prerequisite(baseline,TARGET,worker,probe)
            with patch.object(v,'build_contract',return_value=bound),patch.object(v.user,'validate',side_effect=ValueError('old native build')),self.assertRaises(ValueError):
                v.prerequisite(baseline,TARGET,worker,probe)

    def test_admission_changed_baseline_or_recovery_refuses_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder,baseline,intent,bound,record,worker,probe=self.fixture(Path(temporary))
            with patch.object(v,'build_contract',return_value=bound):self.assertTrue(v.admission(folder)['valid'])
            for name in intent['baselineFiles']:
                path=baseline/name;original=path.read_bytes();path.write_bytes(original+b' ')
                with patch.object(v,'build_contract',return_value=bound),self.subTest(file=name),self.assertRaises(ValueError):v.admission(folder)
                path.write_bytes(original)
            for change in ('table','rate','target','overlap','late-baseline','changed-windows'):
                bad=copy.deepcopy(intent);before=v.read(folder/'before-state.json')
                if change=='table':bad['reviewedRawControls'][21]=1
                if change=='rate':bad['reviewedRateHz']=48000
                if change=='target':bad['target']={'setting':'through','group':0,'value':True}
                if change=='overlap':bad['baselineDirectory']=str(folder)
                if change=='late-baseline':bad['baselineCompletedUtc']='2026-10-30T23:00:10+00:00'
                if change=='changed-windows':before['secureBoot']=False
                save(folder,'intent.json',bad);save(folder,'before-state.json',before)
                with patch.object(v,'build_contract',return_value=bound),self.subTest(change=change),self.assertRaises(ValueError):v.admission(folder)
                save(folder,'before-state.json',dict(v.read(baseline/'after-state.json'),collectedUtc='2026-10-30T22:59:55+00:00'))
            save(folder,'intent.json',intent)

    def test_complete_synthetic_setting_envelope_scope_and_independent_outcome(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder,baseline,intent,bound,record,worker,probe=self.fixture(Path(temporary))
            with patch.object(v,'build_contract',return_value=bound),patch.object(v,'prerequisite',return_value=intent) as required:
                result=v.validate(folder,worker,probe)
                required.assert_called_once_with(baseline,TARGET,worker,probe)
            self.assertTrue(result['valid']);self.assertFalse(result['audioStreamingVerified']);self.assertFalse(result['continuousUsbIdentityVerified'])
            self.assertFalse(result['lifecycleTrace']['emissionVerified']);self.assertEqual(result['probe']['outcome']['setters'],1)

    def test_partial_or_mutated_envelope_never_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder,baseline,intent,bound,record,worker,probe=self.fixture(Path(temporary))
            for key,value in (('completed',False),('probeExitCode',True),('traceExitCode',1),('probeTimedOut',True),
                              ('evidencePreservationError','locked'),('recoveryError','snapshot failed'),
                              ('probeContainmentRequested',True),('tokenQueryError','denied'),('target',{'setting':'through','group':1,'value':1}),
                              ('probeStartedUtc','2026-10-30T23:00:08+00:00'),('probeCompletedUtc','2026-10-30T23:01:01+00:00'),
                              ('requestRecordSha256','a'*64),('etlSha256','a'*64),('recoveryConfirmed',False),('withUsbIdentity',True)):
                bad=copy.deepcopy(record);bad[key]=value;save(folder,'run.json',bad)
                with patch.object(v,'build_contract',return_value=bound),patch.object(v,'prerequisite',return_value=intent),self.subTest(key=key),self.assertRaises(ValueError):
                    v.validate(folder,worker,probe)
            save(folder,'run.json',record)
            original=v.read(folder/'probe/probe.json')
            for key,value in (('operation_verified',False),('outcome_unknown',True),('reviewed_baseline_raw_controls',[1]*22),('final',None)):
                bad=copy.deepcopy(original);bad[key]=value;save(folder,'probe/probe.json',bad)
                bound_record=copy.deepcopy(record);bound_record['probeRecordSha256']=v.digest(folder/'probe/probe.json');save(folder,'run.json',bound_record)
                with patch.object(v,'build_contract',return_value=bound),patch.object(v,'prerequisite',return_value=intent),self.subTest(key=key),self.assertRaises(ValueError):
                    v.validate(folder,worker,probe)
            save(folder,'probe/probe.json',original)
            bad=copy.deepcopy(record);bad['userProcesses']['worker']['process']['elevated']=True;save(folder,'run.json',bad)
            with patch.object(v,'build_contract',return_value=bound),patch.object(v,'prerequisite',return_value=intent),self.assertRaises(ValueError):
                v.validate(folder,worker,probe)
            xml=(folder/'events.xml').read_text(encoding='utf-8')
            (folder/'events.xml').write_text(xml.replace('Name="EventsLost">0','Name="EventsLost">1'),encoding='utf-8')
            bad=copy.deepcopy(record);bad['traceStats']=v.base.physical.capture_validator.trace_statistics(folder/'events.xml');save(folder,'run.json',bad)
            with patch.object(v,'build_contract',return_value=bound),patch.object(v,'prerequisite',return_value=intent),self.assertRaisesRegex(ValueError,'loss differs'):
                v.validate(folder,worker,probe)
            (folder/'events.xml').write_text(xml,encoding='utf-8')
            bad_intent=copy.deepcopy(intent);bad_intent['target']={'setting':'through','group':2,'value':1};save(folder,'intent.json',bad_intent)
            bad=copy.deepcopy(record);bad['target']=bad_intent['target'];bad['intentRecordSha256']=v.digest(folder/'intent.json');save(folder,'run.json',bad)
            with patch.object(v,'build_contract',return_value=bound),patch.object(v,'prerequisite',return_value=bad_intent),self.assertRaisesRegex(ValueError,'reviewed table/target/rate'):
                v.validate(folder,worker,probe)


if __name__=='__main__':unittest.main()
