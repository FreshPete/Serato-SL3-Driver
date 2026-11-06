"""Actual workspace archive/native staging with private HKCU registrations; no Serato or USB."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as W
import json
from pathlib import Path
import runpy
import subprocess
import sys
import uuid
import winreg

ROOT=Path(__file__).resolve().parents[1]
API=runpy.run_path(str(ROOT/'scripts/serato-on-demand-test.py'))
require,sha=API['require'],API['sha']
ACCESS=winreg.KEY_ALL_ACCESS|winreg.KEY_WOW64_64KEY
BASE='Software\\SL3RebuildOnDemandPairTests'


def main():
    bundle=Path(sys.argv[1]).absolute();expected=sys.argv[2];pwsh=Path(sys.argv[3]).absolute()
    install=API['module']('asio-install.py');j=install['sibling']('asio-install-journal');s=j.stage_module();r=install['sibling']('asio-registry')
    require(not s.elevated(),'Ordinary user required for isolated tests')
    deployment=API['module']('prepare-asio-deployment.py');manifest,payload=deployment['capture_bundle'](bundle,expected);deployment['verify_payloads'](manifest,payload)
    require(manifest['schema']=='sl3.deployment-bundle.v2','On-demand diagnostic package required')
    plan=deployment['record'](payload['deployment-plan.json'])
    identity=uuid.uuid4().hex;namespace=BASE+'\\'+identity;folder=ROOT/'artifacts/build/on-demand-pair-tests'/identity;folder.mkdir(parents=True)
    sid=s.user_sid();policy=s.Policy(sid,(s.SYSTEM,s.ADMINS,sid));cases=[];details={}
    sources={name:sha(ROOT/name) for name in API['source_names']()};sources[Path(__file__).relative_to(ROOT).as_posix()]=sha(Path(__file__))
    def live():
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,'',0,r.READ) as root,winreg.OpenKey(winreg.HKEY_CURRENT_USER,'',0,r.READ) as overlay:
            return r.inspect(root,plan),r.inspect_overlay(overlay,plan)
    before_live=live();before_bundle={p.name:sha(p) for p in bundle.iterdir()}
    def case(name,operation):
        value=operation();cases.append({'name':name,'passed':True});details[name]=value;return value
    def passed(result):
        require(result['successful'],result.get('error') or 'Expected successful coordinator result');return result
    def failed(result):
        require(not result['successful'] and result['error'],'Expected explicit coordinator failure');return result
    bridge=folder/'fixture-archive.ps1'
    core=str(ROOT/'scripts/serato-archive-file-transaction.ps1').replace("'","''")
    bridge.write_text("""param([string]$Action,[string]$Target,[string]$Source,[string]$Original,[string]$Candidate)
$ErrorActionPreference='Stop'
. '"""+core+"""'
$t=New-Sl3ArchiveTransaction $Target $Original $Candidate
$before=Get-Sl3ArchiveTransactionState $t
$guard={}
switch($Action){
 'Plan' {$after=$before}
 'Install' {$after=Install-Sl3ArchiveFile $t $Source $guard}
 'Rollback' {$after=Restore-Sl3ArchiveFile $t $guard}
 'Clean' {$after=Clear-Sl3ArchiveWitnesses $t $guard}
 default {throw 'Unknown fixture action'}
}
[ordered]@{schema='sl3.archive-deployment-action.v1';action=$Action;before=$before;after=$after;seratoRunning=$false}|ConvertTo-Json -Depth 8
""",encoding='utf-8')

    @contextmanager
    def fixture(name):
        here=folder/name;here.mkdir();base=here/'native-base'
        with s.descriptor(policy.sddl(True)) as attributes:
            s.check(s.api('kernel32.dll','CreateDirectoryW',W.BOOL,[W.LPCWSTR,ctypes.POINTER(s.Attributes)])(str(base),ctypes.byref(attributes)))
        archive_dir=here/'archive';archive_dir.mkdir();target=archive_dir/'userio_resources.bin';source=here/'candidate.bin'
        original=b'ORIGINAL OWNED SYNTHETIC ARCHIVE\n';candidate=b'CANDIDATE OWNED SYNTHETIC ARCHIVE\n';target.write_bytes(original);source.write_bytes(candidate)
        control={'running':False,'archiveInstallFailure':False,'nativeInstallFailure':False,'installs':0,'removals':0}
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,namespace+'\\'+name,0,ACCESS) as parent, \
             winreg.CreateKeyEx(parent,'machine-model',0,ACCESS) as root,winreg.CreateKeyEx(parent,'overlay-model',0,ACCESS) as overlay:
            for key in ('SOFTWARE\\Classes\\CLSID','SOFTWARE\\ASIO'):
                with winreg.CreateKeyEx(root,key,0,ACCESS):pass
            with winreg.CreateKeyEx(root,'UnrelatedVendor',0,ACCESS) as foreign:
                winreg.SetValueEx(foreign,'Preserve',0,winreg.REG_SZ,identity)
            unrelated=r.snapshot(root,'UnrelatedVendor')
            class Native:
                def observe(self):return API['observe_owned_native'](s,r,plan,base/'stage',expected,policy,root,overlay)
                def install(self):
                    if control['nativeInstallFailure']:
                        raise install['InstallFailure']({'successful':False,'error':'Injected native admission failure','stageAttempted':False})
                    control['installs']+=1
                    return install['install_owned'](bundle,expected,base,base/'stage',policy,root,overlay)
                def remove(self,receipt):
                    control['removals']+=1
                    return install['sibling']('asio-uninstall').uninstall_owned(base,base/'stage',receipt,policy,root,overlay)
            def archive(action):
                if action=='Install' and control['archiveInstallFailure']:raise OSError('Injected failure between native and archive install')
                child=subprocess.run([str(pwsh),'-NoProfile','-NonInteractive','-File',str(bridge),'-Action',action,
                    '-Target',str(target),'-Source',str(source),'-Original',API['hashlib'].sha256(original).hexdigest(),
                    '-Candidate',sha(source)],capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
                require(child.returncode==0,child.stderr.decode('utf-8',errors='replace'))
                result=json.loads(child.stdout);result['seratoRunning']=control['running'];return result
            yield archive,Native(),control,target,root,overlay,base
            require(r.snapshot(root,'UnrelatedVendor')==unrelated,'Foreign registration sibling preserved')
    def run(f,action):return API['coordinate'](action,f[0],f[1])
    def remove_tree(path):
        require(path==namespace or path.startswith(namespace+'\\'),'Private registry cleanup boundary')
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path,0,ACCESS) as node:
            children=[winreg.EnumKey(node,n) for n in range(winreg.QueryInfoKey(node)[0])]
        for child in children:remove_tree(path+'\\'+child)
        winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER,path,winreg.KEY_WOW64_64KEY,0)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,namespace,0,ACCESS) as marker:winreg.SetValueEx(marker,'SL3TestOwner',0,winreg.REG_SZ,identity)
    try:
        with fixture('roundtrip') as f:
            case('read-only-plan',lambda:passed(run(f,'plan')));require(f[2]['installs']==0 and f[1].observe()['state']=='absent','Plan is idle')
            case('native-then-archive-setup',lambda:passed(run(f,'setup')))
            require(f[1].observe()['state']=='installed' and f[2]['installs']==1,'Actual staged/registered native owner')
            before={p.name:sha(p) for p in f[3].parent.iterdir()}
            case('repeat-setup-does-not-reinstall',lambda:passed(run(f,'setup')))
            require(before=={p.name:sha(p) for p in f[3].parent.iterdir()} and f[2]['installs']==1,'No second installation/witness write')
            case('archive-then-native-restoration',lambda:passed(run(f,'restore')))
            require(f[1].observe()['state']=='absent' and len(list(f[3].parent.iterdir()))==1,'Original archive, no native stage or witnesses')
            case('repeat-restoration-is-idle',lambda:passed(run(f,'restore')))
        with fixture('partial-setup') as f:
            f[2]['archiveInstallFailure']=True
            value=case('failure-after-native-install-preserves-observed-state',lambda:failed(run(f,'setup')))
            require(value['after']['archive']=='original' and value['after']['native']['state']=='installed' and f[2]['removals']==0,'No guessed undo after partial setup')
            f[2]['archiveInstallFailure']=False
            case('retry-recovers-from-protected-receipts',lambda:passed(run(f,'setup')))
            require(f[2]['installs']==1,'Reuse existing exact native owner')
            case('restore-retried-setup',lambda:passed(run(f,'restore')))
        with fixture('native-failure') as f:
            f[2]['nativeInstallFailure']=True
            value=case('typed-native-failure-preserved',lambda:failed(run(f,'setup')))
            require(value['componentFailure']['stageAttempted'] is False and value['after']['archive']=='original','No archive replacement after failed native admission')
        with fixture('running') as f:
            f[2]['running']=True
            case('reported-running-app-refuses-setup',lambda:failed(run(f,'setup')))
            case('reported-running-app-refuses-restoration',lambda:failed(run(f,'restore')))
            require(f[2]['installs']==f[2]['removals']==0,'Running-state injection precedes mutations')
        with fixture('foreign-registration') as f:
            passed(run(f,'setup'));key='SOFTWARE\\ASIO\\'+deployment['NAME']
            with winreg.OpenKey(f[4],key,0,ACCESS) as item:winreg.SetValueEx(item,'ForeignValue',0,winreg.REG_SZ,'preserve')
            value=case('foreign-registration-restores-profile-but-preserves-native-conflict',lambda:failed(run(f,'restore')))
            require(value['after']['archive']=='original' and f[2]['removals']==0,'Restore original before preserving conflicting registration')
            with winreg.OpenKey(f[4],key,0,ACCESS) as item:
                require(winreg.QueryValueEx(item,'ForeignValue')[0]=='preserve','Foreign value survived');winreg.DeleteValue(item,'ForeignValue')
            case('native-removal-after-explicit-conflict-resolution',lambda:passed(run(f,'restore')))
        with fixture('archive-conflict') as f:
            passed(run(f,'setup'));known=f[3].read_bytes();f[3].write_bytes(b'UNKNOWN ARCHIVE MUST SURVIVE\n')
            case('unknown-archive-preserved-before-native-removal',lambda:failed(run(f,'restore')))
            require(f[2]['removals']==0 and f[3].read_bytes()==b'UNKNOWN ARCHIVE MUST SURVIVE\n','No blind cleanup')
            f[3].write_bytes(known);case('restore-after-explicit-fixture-archive-resolution',lambda:passed(run(f,'restore')))
        require(live()==before_live,'Real registrations unchanged')
        require(before_bundle=={p.name:sha(p) for p in bundle.iterdir()},'Source package preserved')
    finally:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,namespace,0,ACCESS) as marker:require(winreg.QueryValueEx(marker,'SL3TestOwner')[0]==identity,'Owned cleanup marker')
        remove_tree(namespace)
    try:winreg.OpenKey(winreg.HKEY_CURRENT_USER,namespace)
    except FileNotFoundError:removed=True
    else:raise AssertionError('Private namespace remains')
    require(all(sha(ROOT/name)==value for name,value in sources.items()),'Source changed during isolated pair tests')
    result={'schema':'sl3.on-demand-pair-tests.v1','passed':True,'cases':cases,'details':details,'sourceSha256':sources,
        'bundleManifestSha256':expected,'privateRegistryNamespaceRemoved':removed,'liveRegistrationsUnchanged':True,
        'productionInstallationPerformed':False,'actualProcessCrashTested':False,'archiveBytesSynthetic':True,
        'nativePackageCodeExecuted':False,'seratoLaunched':False,'nativeDeviceAccess':False}
    path=folder/'result.json';path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'cases':len(cases),'report':str(path)},indent=2))


if __name__=='__main__':main()
