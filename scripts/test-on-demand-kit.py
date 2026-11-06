"""Prepare the actual moved one-time setup kit; no elevated/install/Serato/USB action."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
API=runpy.run_path(str(ROOT/'scripts/serato-on-demand-test.py'));sha,require=API['sha'],API['require']


def main():
    source=Path(sys.argv[1]).absolute();expected=sys.argv[2];require(sha(source/'kit-manifest.json')==expected,'Exact kit identity required')
    identity=uuid.uuid4().hex;folder=ROOT/'artifacts/build'/('on-demand-kit-tests-'+identity);folder.mkdir();kit=folder/'Moved setup é';shutil.copytree(source,kit)
    python=kit/'runtime/python/python.exe';script=kit/'scripts/prepare-on-demand-kit.py';manifest=kit/'kit-manifest.json'
    env=dict(os.environ);env['PATH']='';env.pop('SL3_ASIO_PRIVATE_TRACE',None);env['PYTHONDONTWRITEBYTECODE']='1'
    application=r'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe';cases=[];details={}
    command=[str(python),'-I','-B',str(script),'--manifest',str(manifest),'--expected-manifest-sha256',expected,'--application',application]
    def call(name,args=None,success=True,reason=None):
        child=subprocess.run(args or command,env=env,capture_output=True,timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
        (folder/(name+'-stdout.txt')).write_bytes(child.stdout);(folder/(name+'-stderr.txt')).write_bytes(child.stderr)
        require((child.returncode==0)==success,name+': '+child.stderr.decode('utf-8',errors='replace'))
        if success:value=json.loads(child.stdout);details[name]=value
        else:
            require(reason in child.stderr.decode('utf-8',errors='replace'),'Exact refusal required: '+name);value=None
        cases.append({'name':name,'passed':True});return value
    call('moved-kit-readonly-plan');require(not (kit/'analysis').exists(),'Read-only Plan must not create state')
    prepared=call('moved-kit-real-preparation',command+['--prepare'])
    require(prepared['preparedExperiment']['prepared'] is True and prepared['bundleBinding']['nativeBinariesUnchanged'] is True and prepared['normalStartupValidated'] is False,'Actual local preparation without startup required')
    require(all(Path(p).is_relative_to(kit) for p in [prepared['planArguments'][0],prepared['planArguments'][3],prepared['preparedExperiment']['experiment']]),'Prepared entry must remain inside moved kit')
    plan=call('prepared-default-plan',prepared['planArguments']);require(plan['after']=={'archive':'original','seratoRunning':False,'native':{'state':'absent'}},'Restored actual host state required')
    call('ordinary-setup-refusal',prepared['setupArguments'],False,'Run this exact reviewed action as administrator')
    call('ordinary-restore-refusal',prepared['restoreArguments'],False,'Run this exact reviewed action as administrator')
    call('kit-valid-after-preparation')
    for name,relative in [('changed-preparer','scripts/prepare-serato-on-demand-test.py'),('changed-python-library','runtime/python/python315.zip'),('changed-powershell-runtime','runtime/powershell/pwsh.dll'),('changed-native-package','native-package/sl3_asio.dll')]:
        path=kit/relative
        if relative.endswith('python315.zip'):
            matches=list((kit/'runtime/python').glob('python3*.zip'));require(len(matches)==1,'One embedded standard library required');path=matches[0]
        saved=path.read_bytes();path.write_bytes(saved+b'changed')
        try:call(name,success=False,reason='Kit file differs:')
        finally:path.write_bytes(saved)
    extra=kit/'unexpected.txt';extra.write_bytes(b'unknown payload\n')
    try:call('unexpected-payload-refusal',success=False,reason='Unexpected kit files')
    finally:extra.unlink()
    wrong=list(command);wrong[wrong.index('--expected-manifest-sha256')+1]='0'*64;call('wrong-kit-identity',wrong,False,'Kit manifest differs')
    foreign=list(command);foreign[-1]=str(folder/'unreviewed.exe');call('unsupported-application-refusal',foreign,False,'Reviewed original installed Serato build required')
    call('final-kit-plan');call('final-prepared-plan',prepared['planArguments'])
    inventory=json.loads((kit/'kit-inventory.json').read_bytes())['files'];require(all(sha(kit/n)==x['sha256'] for n,x in inventory.items()),'Moved payload preserved')
    state=runpy.run_path(str(ROOT/'scripts/inspect-serato-session-status.py'))['current_state'](json.loads((ROOT/'analysis/sl3-session-capsule-manager-retirement-default-20261106/session-plan.json').read_bytes()));require(state['currentSetupClean'],'Actual installed host must remain clean')
    report={'schema':'sl3.on-demand-kit-tests.v1','passed':True,'cases':cases,'details':details,'kitManifestSha256':expected,
        'testSourceSha256':sha(Path(__file__)),'sourcePins':json.loads(manifest.read_bytes())['sourcePins'],'movedPathContainsSpacesAndUnicode':True,
        'emptyPath':True,'hostPostcheck':state,'productionInstallationPerformed':False,'elevationRequested':False,'seratoLaunched':False,'nativeDeviceAccess':False,
        'anotherAccountOrPcTested':False,'nativePreexecutionVerifierProvided':False}
    output=folder/'result.json';output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'passed':True,'cases':len(cases),'report':str(output)},indent=2))


if __name__=='__main__':main()
