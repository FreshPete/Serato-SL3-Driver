"""Verify the bounded setting probe's actual build/process-test evidence."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def require(ok,reason):
    if not ok:raise ValueError(reason)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    builds={};feature={'simulatedLifecyclePassed':True,'nativeSettingRunDuringBuild':False,'audioStartAttempts':0,
                      'singleTarget':True,'immutableRequestBeforeLaunch':True,'outcomeSeparateFromCleanup':True}
    for config in ('Release','Debug'):
        folder=ROOT/'artifacts/build/native';manifest=folder/f'native-build-{config}.json';build=read(manifest)
        for name,digest in build['inputs'].items():require(sha(ROOT/name)==digest.lower(),'Stale source: '+name)
        require(sha(ROOT/'scripts/build-native.ps1')==build['buildScriptSha256'].lower(),'Build runner differs')
        actual=build['hostProbe']['selection'];require({k:actual[k] for k in feature}==feature,'Selection probe feature differs')
        require(set(actual['scriptInputs'])=={'test-selection-host-probe.py','validate-selection-host-probe.py','validate-controls-host-probe.py'},'Selection script inventory differs')
        for name,digest in actual['scriptInputs'].items():require(sha(ROOT/'scripts'/name)==digest.lower(),'Selection script changed: '+name)
        require(actual['supervisedLauncherPrepared'] is True and len(actual['traceScriptInputs'])==22,'Supervised launcher not prepared')
        for name,digest in actual['traceScriptInputs'].items():require(sha(ROOT/'scripts'/name)==digest.lower(),'Setting trace dependency changed: '+name)
        log=folder/f'ctest-{config}.log';text=log.read_text(encoding='utf-8-sig')
        require(sha(log)==build['ctestLogSha256'].lower() and 'sl3_selection_probe_lifecycle' in build['ctestTests'] and len(build['ctestTests'])==40
                and '100% tests passed, 0 tests failed out of 40' in text,'Full selection-probe suite did not pass')
        binaries={'sl3_host_probe.exe':build['hostProbe']['executableSha256'],
                  'sl3_host_probe_simulated.exe':build['hostProbe']['simulatedExecutableSha256'],
                  'sl3_device_session_fixture.exe':build['deviceSession']['fixtureSha256'],'sl3_usbdk.exe':build['usbdk']['executableSha256']}
        for name,digest in binaries.items():require(sha(folder/config/name)==digest.lower(),'Tested binary differs: '+name)
        builds[config]={'manifestSha256':sha(manifest),'ctestLogSha256':sha(log),'testsPassed':40,
                        'scriptInputs':actual['scriptInputs'],'traceScriptInputs':actual['traceScriptInputs'],'binaries':binaries}
    source=(ROOT/'src/windows/host_probe_main.cpp').read_text(encoding='utf-8-sig')
    run=source.split('int run_selection(',1)[1].split('int run_controls(',1)[0]
    require(run.index('save_selection(folder/L"request.json",e)')<run.index('HostSession session(spec)')
            and run.index('e.baseline->audio.raw==*reviewed')<run.index('e.pending=true;')
            and run.index('e.pending=true;')<run.index('e.result=session.select_control(target)')
            and 'e.result.outcome_unknown=true;e.result.device_may_have_changed=true;' in run,'Prelaunch/prepublication intent order differs')
    py=ROOT/'analysis/selection-probe-python-tests.log';text=py.read_text(encoding='utf-8-sig')
    require('Ran 140 tests' in text and text.rstrip().endswith('OK') and
            'test_native_journal_target_order_counts_and_single_close' in text and
            'test_complete_synthetic_setting_envelope_scope_and_independent_outcome' in text,'Full Python evidence suite did not pass')
    plan_path=ROOT/'analysis/selection-user-plan.json';plan=read(plan_path)
    require(plan['planOnly'] is True and plan['deviceAccess'] is False and plan['selfElevates'] is False and
            plan['securityChanges'] is False and plan['requiresCurrentReadOnlyBaseline'] is True and
            plan['maximumControlSetters']==1 and plan['reviewedTableBytes']==22 and plan['probeDeadlineSeconds']==50 and
            plan['target']=='','Unexpected default setting plan')
    rejection_path=ROOT/'analysis/selection-user-prerequisite-rejection.json';rejection=read(rejection_path)
    require(rejection['exitCode']==1 and rejection['result']=={'valid':False,'error':'Completed split-role read-only controls run required'} and
            rejection['workerSha256'].lower()==builds['Release']['binaries']['sl3_usbdk.exe'].lower() and
            rejection['probeSha256'].lower()==builds['Release']['binaries']['sl3_host_probe.exe'].lower() and
            rejection['validatorSha256']==sha(ROOT/'scripts/validate-selection-user-probe.py'),'Old descriptor prerequisite was not refused')
    result={'scope':'Actual setting-probe executables with simulated positives and safe native negatives; no physical setting/trace acceptance',
            'feature':feature,'builds':builds,'python':{'testsPassed':140,'logSha256':sha(py)},
            'validatorSourceSha256':sha(ROOT/'scripts/validate-selection-host-probe.py'),
            'testSourceSha256':sha(ROOT/'tests/test_selection_probe_evidence.py'),
            'recordSchema':'sl3.selection-host-probe.v2','wireVersion':1,'wireReplyBytes':132,
            'nativeReviewedTableRequired':True,'reviewedTableComparedBeforePublication':True,
            'supervisedLauncherPrepared':True,'supervisedNativeSettingRun':False,
            'splitRoleValidatorSourceSha256':sha(ROOT/'scripts/validate-selection-user-probe.py'),
            'splitRoleTestSourceSha256':sha(ROOT/'tests/test_selection_user_probe.py'),
            'splitRoleDefaultPlanSha256':sha(plan_path),'descriptorOnlyPrerequisiteRejectedSha256':sha(rejection_path),
            'requestSavedBeforeWorker':True,'pendingPublicationConservative':True,'operationAndCleanupSeparate':True,
            'limits':['Wire/result/owner/journal checks are recorded consistency, not USB trace/security/recovery validation',
                      'No supervised native setting run, analogue gain/through mapping or control-panel deployment',
                      'A verified operation with failed close remains unsuccessful while preserving its outcome',
                      'Missing/malformed outcome preserves possible-write uncertainty; no retry/rollback',
                      'Current-build normal-token read-only baseline and attended traced setting run remain required',
                      'Split-role unit tests use synthetic trace/results and isolated prerequisite/build dependencies; no physical WPP emission proved']}
    (ROOT/'docs/evidence/selection-probe-build.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Verified setting probe 40/40 Release/Debug, 140 Python, reviewed intent, split-role preparation and independent operation/cleanup evidence')


if __name__=='__main__':main()
