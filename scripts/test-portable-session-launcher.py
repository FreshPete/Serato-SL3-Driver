"""Exercise a compiled reusable launcher's Plan and refusal paths, never installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def exercise(launcher, prepared_a, prepared_b):
    identity=hashlib.sha256(launcher.read_bytes()).hexdigest()
    cases=[]
    environment=os.environ.copy()
    for name in ('SL3_SESSION_CAPSULE','SL3_SESSION_CAPSULE_SHA256'):
        environment.pop(name,None)
    def call(name, arguments, expected, executable=launcher):
        result=subprocess.run([str(executable),*arguments],capture_output=True,text=True,encoding='utf-8',
                              env=environment,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode!=expected:
            raise AssertionError(f'{name}: {result.returncode}: {result.stdout} {result.stderr}')
        cases.append({'name':name,'passed':True,'exitCode':result.returncode})
        return result
    def plan(path, expected=None):
        return ['--plan','--capsule',str(path),'--expected-capsule-sha256',expected or hashlib.sha256(path.read_bytes()).hexdigest()]
    for name,path in (('first-session',prepared_a),('second-session-same-executable',prepared_b)):
        result=json.loads(call(name,plan(path),0).stdout)
        assert result['planOnly'] is True and result['deviceAccess'] is False and result['registrationWritten'] is False
    call('no-environment-no-installation',[],1)
    call('unsupported-action',['--install'],2)
    call('wrong-capsule-hash',plan(prepared_a,'0'*64),1)
    test_root=ROOT/'artifacts/build/portable-launcher-tests';test_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=test_root) as temporary:
        directory=Path(temporary)
        assert directory.resolve().is_relative_to(test_root.resolve())
        copy=directory/launcher.name;shutil.copyfile(launcher,copy)
        call('executable-relocated-without-rebuild',plan(prepared_a),0,copy)
        fixture=directory/'session-capsule.json'
        original=json.loads(prepared_a.read_bytes())
        for name,mutation in (
            ('untrusted-interpreter',lambda item:item['python'].update(sha256='0'*64)),
            ('foreign-helper-root',lambda item:item.update(projectRoot=str(directory/'untrusted-root'))),
            ('changed-package-binding',lambda item:item['bundle'].update(sha256='0'*64)),
        ):
            record=json.loads(json.dumps(original));record['sessionDirectory']=str(directory);mutation(record)
            fixture.write_text(json.dumps(record),encoding='utf-8')
            call(name,plan(fixture),1)
        # A valid code root is not enough to admit a moved/mismatched session.
        fixture.write_text(json.dumps(original),encoding='utf-8')
        call('moved-capsule-binding',plan(fixture),1)
    assert hashlib.sha256(launcher.read_bytes()).hexdigest()==identity
    return {'schema':'sl3.portable-launcher-tests.v1','launcherSha256':identity,'cases':cases,
            'sameExecutableAcceptedTwoSessionBindings':True,'binaryRecompiledBetweenSessions':False,
            'onlyPlanOrRefusalInvocations':True,'registryWritten':False,'deviceAccess':False,'liveValidated':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher',type=Path,required=True)
    parser.add_argument('--capsule-a',type=Path,required=True)
    parser.add_argument('--capsule-b',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=exercise(args.launcher.absolute(),args.capsule_a.absolute(),args.capsule_b.absolute())
    if args.output:
        with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))
