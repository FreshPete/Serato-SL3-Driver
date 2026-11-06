"""Exercise native pre-helper refusal and actual copied-kit preparation; no installer or hardware."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,t):
    if not v:raise ValueError(t)


def main():
    build_path=Path(sys.argv[1]).absolute();require(sha(build_path)==sys.argv[2],'Reviewed native build required')
    build=json.loads(build_path.read_bytes());require(build['schema']=='sl3.native-setup-entry-build.v1' and build['configuration']=='Release' and build['inertChecksPassed'],'Successful Release entry build required')
    source_path=build_path.parent/'entry-source.json';require(sha(source_path)==build['sourceManifestSha256'],'Exact native source binding required');source=json.loads(source_path.read_bytes())
    require(all(sha(ROOT/n)==v for n,v in source['sourcePins'].items()) and all(sha(source_path.parent/n)==v for n,v in source['generatedPins'].items()),'Native entry source changed')
    host=build_path.parent/'build/Release/SL3_Setup_Engineering.exe';require(sha(host)==build['executableSha256'],'Native entry image changed')
    original=Path(sys.argv[3]).absolute();require(sha(original/'kit-manifest.json')==source['kitManifestSha256'],'Compiled kit binding required')
    identity=uuid.uuid4().hex;folder=ROOT/'artifacts/build'/('native-entry-tests-'+identity);folder.mkdir();kit=folder/'Moved kit é';shutil.copytree(original,kit)
    env=dict(os.environ);env['PATH']='';env['PYTHONDONTWRITEBYTECODE']='1';env.pop('SL3_ASIO_PRIVATE_TRACE',None)
    app=r'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe';cases=[];details={}
    def command(action):return [str(host),action,'--kit',str(kit),'--app',app]
    def call(name,args,success=True,reason=None):
        child=subprocess.run(args,env=env,capture_output=True,timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
        (folder/(name+'-stdout.txt')).write_bytes(child.stdout);(folder/(name+'-stderr.txt')).write_bytes(child.stderr)
        require((child.returncode==0)==success,name+': '+child.stderr.decode('utf-8',errors='replace'))
        if success:
            value=json.loads(child.stdout);details[name]=value
        else:
            error=child.stderr.decode('utf-8',errors='replace');require('SL3 setup entry refused:' in error and 'Traceback' not in error and not child.stdout and reason in error,'Expected native pre-helper refusal: '+name);value=None
        cases.append({'name':name,'passed':True});return value
    first=call('native-verification-only',command('--verify'));require(first['filesPinned']==source['compiledPayloadFiles'] and first['pythonStarted'] is False and not (kit/'analysis').exists(),'Native verify must remain idle')
    call('native-readonly-plan',command('--plan'));require(not (kit/'analysis').exists(),'Plan creates no mutable state')
    prepared=call('native-real-preparation',command('--prepare'));require(prepared['preparedExperiment']['prepared'] is True and prepared['normalStartupValidated'] is False,'Actual copied-kit preparation required')
    experiment=Path(prepared['preparedExperiment']['experiment']);experiment_sha=prepared['preparedExperiment']['experimentSha256']
    def reviewed(action,selected=experiment,identity=experiment_sha):return command(action)+['--experiment',str(selected),'--expected-experiment-sha256',identity]
    plan=call('native-generated-experiment-check',reviewed('--check-experiment'));require(plan['after']=={'archive':'original','seratoRunning':False,'native':{'state':'absent'}},'Actual restored host observation required')
    call('native-apply-refuses-ordinary-token',reviewed('--apply-experiment'),False,'Run this exact reviewed setup/restore entry as administrator')
    call('native-restore-refuses-ordinary-token',reviewed('--restore-experiment'),False,'Run this exact reviewed setup/restore entry as administrator')
    call('native-wrong-experiment-hash',reviewed('--check-experiment',identity='0'*64),False,'Reviewed setup input hash differs')
    call('native-foreign-experiment-scope',reviewed('--check-experiment',selected=folder/('sl3-on-demand-test-'+'0'*32)/'experiment.json'),False,'Prepared state must belong to this kit')
    asset=experiment.parent/'archive/archive-test.ps1';saved=asset.read_bytes();asset.write_bytes(saved+b'changed')
    try:call('native-changed-prepared-asset',reviewed('--check-experiment'),False,'Reviewed setup input hash differs')
    finally:asset.write_bytes(saved)
    experiment_record=json.loads(experiment.read_bytes());bundle=Path(experiment_record['bundle']['directory']);image=bundle/'sl3_usbdk.exe';saved=image.read_bytes();image.write_bytes(saved[:-1]+bytes([saved[-1]^1]))
    try:call('native-changed-rebound-worker',reviewed('--check-experiment'),False,'Reviewed setup input hash differs')
    finally:image.write_bytes(saved)
    saved=experiment.read_bytes();changed=json.loads(saved);changed['projectRoot']=str(folder);experiment.write_text(json.dumps(changed),encoding='utf-8')
    try:call('native-foreign-project-root',reviewed('--check-experiment',identity=sha(experiment)),False,'Prepared experiment root/application differs')
    finally:experiment.write_bytes(saved)
    call('native-final-experiment-check',reviewed('--check-experiment'))
    call('native-verification-after-preparation',command('--verify'))
    before={p.relative_to(kit/'analysis').as_posix():sha(p) for p in (kit/'analysis').rglob('*') if p.is_file()}
    marker=folder/'altered-helper-executed';helper=kit/'scripts/prepare-on-demand-kit.py';saved=helper.read_bytes();helper.write_bytes(('from pathlib import Path\nPath('+repr(str(marker))+').write_text("unexpected helper execution")\n').encode()+saved)
    try:call('changed-helper-refused-before-execution',command('--prepare'),False,'Setup input size or file type differs');require(not marker.exists(),'Altered helper must never execute')
    finally:helper.write_bytes(saved)
    for name,relative in [('changed-python-library','runtime/python/'+next(p.name for p in (kit/'runtime/python').glob('python3*.zip'))),('changed-powershell-runtime','runtime/powershell/pwsh.dll'),('changed-native-driver','native-package/sl3_asio.dll')]:
        path=kit/relative;saved=path.read_bytes();path.write_bytes(saved[:-1]+bytes([saved[-1]^1]))
        try:call(name,command('--plan'),False,'Reviewed setup input hash differs')
        finally:path.write_bytes(saved)
    manifest=kit/'kit-manifest.json';saved=manifest.read_bytes();manifest.write_bytes(saved+b' ')
    try:call('changed-manifest-refused',command('--plan'),False,'Setup input size or file type differs')
    finally:manifest.write_bytes(saved)
    extra=kit/'runtime/python/unexpected.dll';extra.write_bytes(b'unknown payload')
    try:call('extra-dll-refused-before-interpreter',command('--plan'),False,'Unexpected setup payload before helper execution')
    finally:extra.unlink()
    wrong=command('--plan');wrong[-1]=str(folder/'unreviewed.exe');call('unreviewed-application-refused',wrong,False,'Original Serato executable required')
    call('unknown-mutable-action-refused',command('--install'),False,'Known setup entry action required')
    semicolon=command('--plan');semicolon[3]=str(folder/'unsupported;kit');call('unsupported-kit-path',semicolon,False,'Local fixed-drive kit without semicolons')
    require(before=={p.relative_to(kit/'analysis').as_posix():sha(p) for p in (kit/'analysis').rglob('*') if p.is_file()},'Refusals must not create or change prepared state')
    call('final-native-plan',command('--plan'))
    import pefile
    pe=pefile.PE(str(host));imports=sorted(x.dll.decode('ascii') for x in pe.DIRECTORY_ENTRY_IMPORT);pe.close()
    require(not any(n.lower().startswith(('mscoree','vcruntime','msvcp','msvcr','clr')) for n in imports),'Entry must not require CLR or external MSVC runtime')
    state=runpy.run_path(str(ROOT/'scripts/inspect-serato-session-status.py'))['current_state'](json.loads((ROOT/'analysis/sl3-session-capsule-manager-retirement-default-20261106/session-plan.json').read_bytes()));require(state['currentSetupClean'],'Host remains restored')
    require(all(sha(ROOT/n)==v for n,v in source['sourcePins'].items()),'Native entry source changed during test')
    report={'schema':'sl3.native-setup-entry-tests.v1','passed':True,'cases':cases,'details':details,'testSourceSha256':sha(Path(__file__)),
        'buildSha256':sha(build_path),'sourceManifestSha256':sha(source_path),'sourcePins':source['sourcePins'],'generatedPins':source['generatedPins'],
        'executableSha256':sha(host),'kitManifestSha256':source['kitManifestSha256'],'filesPinnedBeforeHelper':source['compiledPayloadFiles'],
        'imports':imports,'emptyPath':True,'movedKitTested':True,'modifiedHelperExecuted':False,'productionInstallationPerformed':False,'elevationRequested':False,
        'seratoLaunched':False,'nativeDeviceAccess':False,'hostPostcheck':state,'graphicalSetupProvided':False,'installedRegistryActivationValidated':False,
        'preparedExperimentNativeCheckPassed':True,'mutableActionsTestedOnlyAsOrdinaryTokenRefusals':True,'elevatedSetupOrRestoreValidated':False}
    output=folder/'result.json';output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'passed':True,'cases':len(cases),'report':str(output)},indent=2))


if __name__=='__main__':main()
