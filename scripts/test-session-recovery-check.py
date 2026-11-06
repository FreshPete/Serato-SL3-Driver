"""Native recovery checks with an owned ordinary PowerShell fixture; no repair/UAC/device access."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exercise(reference, expected, powershell, launcher, output):
    assert sha(reference)==expected
    prior=json.loads(reference.read_bytes())
    builder=runpy.run_path(str(ROOT/'scripts/prepare-serato-session-capsule.py'))
    api=runpy.run_path(str(ROOT/'scripts/prepare-serato-session-plan.py'))
    directory=ROOT/'analysis'/('sl3-session-capsule-recovery-check-'+uuid.uuid4().hex)
    capsule=builder['prepare'](prior['application']['path'],prior['nativeBundle']['path'],prior['nativeBundle']['sha256'],directory)
    plan=api['construct'](capsule['capsule'],capsule['capsuleSha256'],prior['preparedShim']['path'],prior['preparedShim']['sha256'],
        prior['archiveSource']['path'],prior['installerResource']['path'],prior['launcher']['path'],prior['fridaDirectory'])
    selected=directory/'session-plan.json';selected.write_text(json.dumps(plan,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    cases=[]
    def check(name, code, phase):
        before={p.name:sha(p) for p in directory.iterdir() if p.is_file()}
        result=subprocess.run([str(launcher),'--check-recovery','--session-plan',str(selected),
            '--expected-session-plan-sha256',sha(selected),'--powershell-directory',str(powershell)],
            capture_output=True,text=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode==code,(name,result.stdout,result.stderr)
        report=json.loads(result.stdout);assert report['phase']==phase
        assert report['recoveryAuthorized'] is False and report['repairAttempted'] is False
        assert report['ordinaryToken'] is True
        assert report['filesWritten'] is False and report['registryWritten'] is False and report['elevationRequested'] is False
        assert before=={p.name:sha(p) for p in directory.iterdir() if p.is_file()}
        recovery=subprocess.run([str(launcher),'--recover-session','--session-plan',str(selected),
            '--expected-session-plan-sha256',sha(selected),'--powershell-directory',str(powershell)],
            capture_output=True,text=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
        assert recovery.returncode==code,(name,recovery.stdout,recovery.stderr)
        gate=json.loads(recovery.stdout)
        assert gate['check']['phase']==phase and gate['recoveryCompleted'] is False
        assert gate['elevatedTransactionRequired'] is False
        assert gate['noChangesNeeded']==(code==0)
        assert before=={p.name:sha(p) for p in directory.iterdir() if p.is_file()}
        (directory/(name+'.json')).write_text(result.stdout,encoding='utf-8')
        cases.append({'name':name,'passed':True,'exitCode':code,'phase':phase,'recoveryEntryAlsoChecked':True})
        return report
    check('prepared-session-currently-clean',0,'clean')
    code="""$ErrorActionPreference='Stop'
$taskDirectory=[Environment]::GetEnvironmentVariable('SL3_RECOVERY_CHECK_FIXTURE')
$taskOwner=@{runner=@{pid=$PID;created=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToFileTimeUtc().ToString()}}
[IO.File]::WriteAllText((Join-Path $taskDirectory 'session-run.lock'),($taskOwner|ConvertTo-Json -Depth 4))
$taskLimit=[Environment]::TickCount64+60000
while(-not(Test-Path -LiteralPath (Join-Path $taskDirectory 'exit.txt')) -and [Environment]::TickCount64 -lt $taskLimit){Start-Sleep -Milliseconds 20}
"""
    environment=os.environ.copy();environment['SL3_RECOVERY_CHECK_FIXTURE']=str(directory)
    owner=subprocess.Popen([str(powershell/'pwsh.exe'),'-NoLogo','-NoProfile','-NonInteractive','-EncodedCommand',
        base64.b64encode(code.encode('utf-16-le')).decode('ascii')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        env=environment,creationflags=subprocess.CREATE_NO_WINDOW)
    record=directory/'session-run.lock'
    try:
        deadline=time.monotonic()+8
        while not record.exists():
            assert owner.poll() is None and time.monotonic()<deadline
            time.sleep(.01)
        original=json.loads(record.read_bytes())
        report=check('live-owner-blocks-without-resource-child',3,'active_session')
        assert report['owners']['runner']['state']=='alive' and report['resourcePlan']['observed'] is False
        assert owner.poll() is None
        altered=json.loads(json.dumps(original));altered['runner']['created']=str(int(altered['runner']['created'])-1)
        record.write_text(json.dumps(altered),encoding='utf-8')
        report=check('stale-owner-does-not-target-current-process',0,'clean')
        assert report['owners']['runner']['state']=='replaced' and owner.poll() is None
        altered['runner']['created']=int(original['runner']['created'])
        record.write_text(json.dumps(altered),encoding='utf-8')
        report=check('malformed-owner-refused',3,'review_required')
        assert report['owners']['runner']['state']=='unknown' and owner.poll() is None
        altered['runner']['created']='0'+original['runner']['created']
        record.write_text(json.dumps(altered),encoding='utf-8')
        report=check('noncanonical-owner-time-refused',3,'review_required')
        assert report['owners']['runner']['state']=='unknown' and owner.poll() is None
        record.write_text(json.dumps(original),encoding='utf-8')
    finally:
        (directory/'exit.txt').write_text('exit',encoding='utf-8')
        try:
            stdout,stderr=owner.communicate(timeout=8)
            assert owner.returncode==0,(stdout,stderr)
        except subprocess.TimeoutExpired:
            owner.kill();owner.communicate(timeout=5);raise
    report=check('retired-owner-currently-clean',0,'clean')
    assert report['owners']['runner']['state']=='exited'
    result={'schema':'sl3.session-recovery-check-tests.v1','cases':cases,'nativeEntryUsed':True,
        'sessionPlanSha256':sha(selected),'ownedPowerShellExitCode':owner.returncode,
        'ordinaryProcessOnly':True,'protectedResourcePreflightExercised':True,'repairAttempted':False,
        'applicationStarted':False,'deviceOpened':False,'elevationRequested':False,'protectedRecoveryValidated':False}
    with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-plan',type=Path,required=True)
    parser.add_argument('--expected-reference-sha256',required=True)
    parser.add_argument('--powershell',type=Path,required=True)
    parser.add_argument('--launcher',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(exercise(args.reference_plan.absolute(),args.expected_reference_sha256,args.powershell.absolute(),
                             args.launcher.absolute(),args.output.absolute()),indent=2))
