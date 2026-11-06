"""Read-only real-host Plan and pre-mutation refusals; never elevates or installs."""
from contextlib import ExitStack
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
API=runpy.run_path(str(ROOT/'scripts/serato-on-demand-test.py'))
require,sha=API['require'],API['sha']


def main():
    path=Path(sys.argv[1]).absolute();expected=sys.argv[2];meta=json.loads(path.read_bytes())
    stage=API['module']('asio-install-journal.py')['stage_module']();require(not stage.elevated(),'Ordinary token required')
    identity=uuid.uuid4().hex;folder=ROOT/'analysis'/('sl3-on-demand-test-verification-'+identity);shutil.copytree(path.parent,folder)
    copied=folder/'experiment.json';original=path.read_bytes();cases=[];details={}
    sources={name:sha(ROOT/name) for name in API['source_names']()};sources[Path(__file__).relative_to(ROOT).as_posix()]=sha(Path(__file__))
    before={p.relative_to(path.parent).as_posix():sha(p) for p in path.parent.rglob('*') if p.is_file()}
    def call(name,action=None,success=True,reason=None):
        command=[sys.executable,'-I','-B',str(ROOT/'scripts/serato-on-demand-test.py')]
        if action is not None:command.append(action)
        command+=['--experiment',str(path),'--expected-experiment-sha256',expected]
        child=subprocess.run(command,capture_output=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
        (folder/(name+'-stdout.txt')).write_bytes(child.stdout);(folder/(name+'-stderr.txt')).write_bytes(child.stderr)
        require(child.returncode==(0 if success else 1),name+': unexpected exit')
        if success:
            value=json.loads(child.stdout);require(value['successful'] and value['steps']==[] and value['before']==value['after'], 'Default Plan must be idle')
            require(value['after']=={'archive':'original','seratoRunning':False,'native':{'state':'absent'}}, 'Expected real restored host state')
            details[name]=value
        else:require(reason in child.stderr.decode('utf-8',errors='replace'),'Expected exact pre-mutation refusal')
        cases.append({'name':name,'passed':True})
    def refused(name,reason,review_sha=None):
        try:
            with ExitStack() as held:API['verify'](copied,review_sha or sha(copied),held)
        except ValueError as error:
            require(str(error)==reason,name+': '+str(error));cases.append({'name':name,'passed':True})
        else:raise AssertionError('Unexpected admission: '+name)
    call('default-readonly-host-plan')
    call('ordinary-setup-refuses-without-prompt','setup',False,'Run this exact reviewed action as administrator')
    call('ordinary-restoration-refuses-without-prompt','restore',False,'Run this exact reviewed action as administrator')
    refused('wrong-manifest-hash','Experiment manifest identity changed','0'*64)
    candidate=folder/'archive/candidate-userio_resources.bin';saved=candidate.read_bytes();candidate.write_bytes(saved+b'changed')
    refused('altered-candidate-asset','Pinned source/asset differs');candidate.write_bytes(saved)
    for name,key,value,reason in [
        ('excessive-diagnostic-limit','maximumOwnerLifetimeMs',600001,'Bounded unexecuted no-shim experiment required'),
        ('claimed-shim-mode','startupShimUsed',True,'Bounded unexecuted no-shim experiment required'),
        ('claimed-installed-result','installed',True,'Bounded unexecuted no-shim experiment required'),
        ('foreign-application-path','application',str(folder/'Serato DJ Pro.exe'),'Original application path and identity required')]:
        changed={**meta,key:value};copied.write_text(json.dumps(changed),encoding='utf-8');refused(name,reason)
    copied.write_bytes(original)
    changed=json.loads(original);changed['sources']['../foreign.py']='0'*64;copied.write_text(json.dumps(changed),encoding='utf-8')
    refused('foreign-source-name','Exact source/asset inventory required');copied.write_bytes(original)
    prepare=API['module']('prepare-serato-on-demand-test.py')['prepare']
    try:prepare(Path(meta['application']),Path(meta['bundle']['directory']),meta['bundle']['sha256'],
        Path(meta['powershell']['directory']),meta['powershell']['manifestSha256'],meta['python']['manifestSha256'],path.parent)
    except ValueError as error:
        require(str(error)=='Fresh direct analysis/sl3-on-demand-test-* output required','Existing-output refusal must precede generation')
        cases.append({'name':'existing-prepared-experiment-preserved','passed':True})
    else:raise AssertionError('Existing output was overwritten')
    require(before=={p.relative_to(path.parent).as_posix():sha(p) for p in path.parent.rglob('*') if p.is_file()},'Original preparation preserved')
    call('final-readonly-host-plan')
    require(all(sha(ROOT/name)==value for name,value in sources.items()),'Preparation test source changed')
    result={'schema':'sl3.on-demand-preparation-tests.v1','passed':True,'cases':cases,'details':details,'sourceSha256':sources,
        'experimentSha256':expected,'productionSetupExecuted':False,'elevationRequested':False,'applicationLaunched':False,
        'nativeDeviceAccess':False,'originalPreparedExperimentUnchanged':True}
    output=ROOT/'tests/results/local'/('on-demand-preparation-'+identity+'.json');output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'cases':len(cases),'report':str(output)},indent=2))


if __name__=='__main__':main()
