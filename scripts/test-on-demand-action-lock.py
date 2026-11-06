"""Real exclusive/delete-on-close lock and inherited PowerShell-cohort tests, workspace only."""
import ctypes
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
API=runpy.run_path(str(ROOT/'scripts/on-demand-action-lock.py'))
s=runpy.run_path(str(ROOT/'scripts/asio-install-journal.py'))['stage_module']()
def require(value,text):
    if not value:raise ValueError(text)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def policy():
    sid=s.user_sid();return s.Policy(sid,(s.SYSTEM,s.ADMINS,sid))
def wait_file(path,child):
    began=time.monotonic()
    while not path.is_file():
        require(child.poll() is None,'Owned fixture exited before readiness')
        require(time.monotonic()-began<15,'Bounded fixture readiness');time.sleep(.01)


def child_mode(mode,root,pwsh):
    path=root/API['LOCK_NAME']
    if mode=='--child-try':
        try:
            with API['hold'](s,path,policy()):pass
        except API['ActionLockBusy']:
            print(json.dumps({'acquired':False}));return
        print(json.dumps({'acquired':True}));return
    with API['hold'](s,path,policy()) as lease:
        if mode=='--child-hold':
            (root/'ready.json').write_text(json.dumps({'pid':__import__('os').getpid()}),encoding='utf-8')
            began=time.monotonic()
            while not (root/'stop').exists():
                require(time.monotonic()-began<20,'Bounded child hold');time.sleep(.01)
        else:
            require(mode=='--child-cohort','Known fixture child mode')
            with lease.child() as (handle,options):
                helper=subprocess.Popen([str(pwsh),'-NoProfile','-NonInteractive','-File',str(root/'action-child.ps1'),
                    '-Action','Plan','-ActionLockHandle',str(handle)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW,**options)
                (root/'owner-ready.json').write_text(json.dumps({'pid':__import__('os').getpid(),'helperPid':helper.pid}),encoding='utf-8')
                stdout,stderr=helper.communicate(timeout=25)
                require(helper.returncode==0,'Owned helper failed: '+stderr.decode('utf-8',errors='replace'))
    print(json.dumps({'handleClosed':lease.report['handleClosed']}))


def main():
    require(not s.elevated(),'Ordinary token required for isolated lock suite')
    pwsh_dir=Path(sys.argv[1]).absolute();pwsh_sha=sys.argv[2]
    runpy.run_path(str(ROOT/'scripts/prepare-portable-powershell.py'))['verify'](pwsh_dir,pwsh_sha);pwsh=pwsh_dir/'pwsh.exe'
    paths=[Path(__file__),ROOT/'scripts/on-demand-action-lock.py',ROOT/'scripts/on-demand-action-child.ps1',
        ROOT/'scripts/asio-install-journal.py',ROOT/'scripts/asio-file-stage.py']
    pins={p.relative_to(ROOT).as_posix():sha(p) for p in paths};identity=uuid.uuid4().hex
    folder=ROOT/'artifacts/build/action-lock-tests'/identity;folder.mkdir(parents=True);cases=[];cohort={}
    def fixture(name):
        root=folder/name
        with s.descriptor(policy().sddl(True)) as attributes:
            s.check(s.api('kernel32.dll','CreateDirectoryW',W.BOOL,[W.LPCWSTR,ctypes.POINTER(s.Attributes)])(str(root),ctypes.byref(attributes)))
        return root,root/API['LOCK_NAME']
    def passed(name):cases.append({'name':name,'passed':True})
    def busy(path):
        try:
            with API['hold'](s,path,policy()):raise AssertionError('Second action entered')
        except API['ActionLockBusy']:return
        raise AssertionError('Expected lock conflict')
    def spawn(mode,root):return subprocess.Popen([sys.executable,'-I','-B',str(Path(__file__)),mode,str(root),str(pwsh)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    root,path=fixture('ordinary')
    with API['hold'](s,path,policy()) as lease:
        require(path.exists() and lease.report['fileIdentity'] is not None,'Real owned lock exists');passed('real-exclusive-lock-created')
        busy(path);passed('same-process-overlap-refused')
        try:
            with s.open_file(path):raise AssertionError('Concurrent reader unexpectedly opened lock')
        except OSError:passed('share-none-denies-concurrent-open')
        child=spawn('--child-try',root);stdout,stderr=child.communicate(timeout=15)
        require(child.returncode==0 and json.loads(stdout)=={'acquired':False},stderr.decode('utf-8',errors='replace'));passed('other-process-overlap-refused')
    require(lease.report['handleClosed'] and not path.exists(),'Normal close removes own lock');passed('normal-close-observed-absent')
    try:
        with API['hold'](s,path,policy()):raise RuntimeError('Injected action failure')
    except RuntimeError:pass
    require(not path.exists(),'Exception close removes own lock');passed('exception-releases-own-object')
    foreign=b'INJECTED FOREIGN WITNESS - PRESERVE\n';path.write_bytes(foreign);busy(path)
    require(path.read_bytes()==foreign,'Unknown witness changed');passed('foreign-existing-marker-preserved')
    path.unlink()  # Only the exact injected fixture marker, after byte verification.
    try:
        with API['hold'](s,root/'other-name',policy()):raise AssertionError('Wrong name admitted')
    except ValueError:passed('wrong-lock-name-refused')
    try:
        with API['hold'](s,path,s.PRODUCTION):raise AssertionError('Production admitted ordinary token')
    except ValueError:passed('production-refuses-ordinary-token-without-prompt')
    weak=folder/'unprotected';weak.mkdir()
    try:
        with API['hold'](s,weak/API['LOCK_NAME'],policy()):raise AssertionError('Unprotected fixture directory admitted')
    except ValueError:passed('unprotected-fixture-parent-refused')
    require(not (weak/API['LOCK_NAME']).exists(),'No file after ACL refusal')
    for forced in (False,True):
        root,path=fixture('holder-killed' if forced else 'holder-normal');child=spawn('--child-hold',root)
        try:
            wait_file(root/'ready.json',child);require(json.loads((root/'ready.json').read_bytes())['pid']==child.pid,'Exact owned holder readiness')
            busy(path)
            if forced:child.kill()
            else:(root/'stop').write_bytes(b'normal owned stop\n')
            stdout,stderr=child.communicate(timeout=10);require(child.returncode==(1 if forced else 0),'Expected holder exit')
            require(not path.exists(),'Kernel did not remove retired holder lock')
            with API['hold'](s,path,policy()):pass
            passed('killed-holder-releases-lock' if forced else 'other-process-normal-release-reacquires')
        finally:
            if child.poll() is None:child.kill();child.communicate(timeout=5)
    root,path=fixture('inherited-cohort')
    shutil.copyfile(ROOT/'scripts/on-demand-action-child.ps1',root/'action-child.ps1')
    (root/'archive-test.ps1').write_text("""param([string]$Action)
$ErrorActionPreference='Stop'
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'helper-ready.json'),('{"pid":'+$PID+'}'))
$began=[Environment]::TickCount64
while(-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'helper-stop'))){
 if([Environment]::TickCount64-$began -gt 15000){throw 'Bounded owned helper hold'}
 Start-Sleep -Milliseconds 10
}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'helper-finished'),'owned helper body returned')
""",encoding='utf-8')
    child=spawn('--child-cohort',root);helper_handle=None
    try:
        wait_file(root/'owner-ready.json',child);wait_file(root/'helper-ready.json',child)
        owner=json.loads((root/'owner-ready.json').read_bytes());helper=json.loads((root/'helper-ready.json').read_bytes())
        require(owner['pid']==child.pid and owner['helperPid']==helper['pid'],'Exact owned helper publication')
        helper_handle=s.Handle(s.api('kernel32.dll','OpenProcess',W.HANDLE,[W.DWORD,W.BOOL,W.DWORD])(0x101000,False,helper['pid']))
        wait=s.api('kernel32.dll','WaitForSingleObject',W.DWORD,[W.HANDLE,W.DWORD]);require(wait(helper_handle.value,0)==258,'Helper must be alive')
        buffer=ctypes.create_unicode_buffer(32768);length=W.DWORD(len(buffer))
        s.check(s.api('kernel32.dll','QueryFullProcessImageNameW',W.BOOL,[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)])(helper_handle.value,0,buffer,ctypes.byref(length)))
        require(sha(Path(buffer.value))==sha(pwsh),'Owned helper image identity differs')
        child.kill();child.communicate(timeout=5);require(child.returncode==1,'Exact owned coordinator terminated')
        require(wait(helper_handle.value,0)==258 and path.exists(),'Inherited helper must retain the lock after parent death')
        busy(path);passed('live-helper-retains-lock-after-coordinator-death')
        (root/'helper-stop').write_bytes(b'owned helper stop\n');require(wait(helper_handle.value,10000)==0,'Owned helper did not exit')
        require((root/'helper-finished').is_file() and not path.exists(),'Helper body finished before lock retirement')
        with API['hold'](s,path,policy()):pass
        passed('last-helper-release-permits-next-action')
        cohort={'ownedCoordinatorTerminated':True,'helperRetainedLock':True,'helperExited':True,'lockAbsenceObserved':True}
    finally:
        (root/'helper-stop').write_bytes(b'fixture cleanup\n')
        if child.poll() is None:child.kill();child.communicate(timeout=5)
        if helper_handle is not None:
            s.api('kernel32.dll','WaitForSingleObject',W.DWORD,[W.HANDLE,W.DWORD])(helper_handle.value,20000);helper_handle.close()
    require(all(sha(ROOT/name)==value for name,value in pins.items()),'Lock suite source changed')
    result={'schema':'sl3.on-demand-action-lock-tests.v1','passed':True,'cases':cases,'sourceSha256':pins,'cohort':cohort,
        'actualOwnedProcessTerminationTested':True,'ownedProcessesTerminated':2,'productionLockCreated':False,
        'productionSetupExecuted':False,'registryModified':False,'seratoLaunched':False,'nativeDeviceAccess':False}
    output=folder/'result.json';output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'cases':len(cases),'report':str(output)},indent=2))


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1].startswith('--child-'):child_mode(sys.argv[1],Path(sys.argv[2]).absolute(),Path(sys.argv[3]).absolute())
    else:main()
