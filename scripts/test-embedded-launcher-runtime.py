"""Run a Plan with a copied private runtime, then refuse changed module/stdlib bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def exercise(launcher,runtime,capsule,session_plan=None):
    root=ROOT/'artifacts/build/embedded-launcher-tests';root.mkdir(exist_ok=True)
    rows=[]
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        directory=Path(temporary)
        assert directory.resolve().is_relative_to(root.resolve())
        copied=directory/'runtime';shutil.copytree(runtime,copied)
        record=json.loads(capsule.read_bytes())
        record['python']['path']=str(copied/'python.exe');record['sessionDirectory']=str(directory)
        configuration=directory/'session-capsule.json';configuration.write_text(json.dumps(record),encoding='utf-8')
        arguments=[str(launcher),'--plan','--capsule',str(configuration),'--expected-capsule-sha256',
                   hashlib.sha256(configuration.read_bytes()).hexdigest()]
        def call(name,expected):
            result=subprocess.run(arguments,capture_output=True,text=True,encoding='utf-8',timeout=30,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode!=expected:raise AssertionError(f'{name}: {result.returncode}: {result.stdout} {result.stderr}')
            rows.append({'name':name,'passed':True,'exitCode':result.returncode})
            return result
        assert json.loads(call('copied-runtime-plan',0).stdout)['planOnly'] is True
        marker=directory/'must-not-execute.txt'
        module=copied/'packages/pefile.py';original=module.read_bytes()
        try:
            module.write_bytes(original+('\nimport pathlib; pathlib.Path('+repr(str(marker))+').write_text("unexpected execution")\n').encode())
            result=call('changed-module-refused-before-python',1)
            assert 'Reviewed launcher input differs: pefile.py' in result.stderr and not marker.exists()
        finally:module.write_bytes(original)
        standard=next(copied.glob('python3*.zip'));original_standard=standard.read_bytes()
        try:
            standard.write_bytes(original_standard+b'changed')
            result=call('changed-standard-library-refused-before-python',1)
            assert 'Reviewed launcher input differs:' in result.stderr and standard.name in result.stderr
        finally:standard.write_bytes(original_standard)
        if session_plan is not None:
            source_plan=json.loads(session_plan.read_bytes())
            generated=directory/'session-plan.json'
            prepare=[str(copied/'python.exe'),'-I','-B',str(ROOT/'scripts/prepare-serato-session-plan.py'),
                     '--capsule',str(configuration),'--expected-capsule-sha256',hashlib.sha256(configuration.read_bytes()).hexdigest(),
                     '--prepared',source_plan['preparedShim']['path'],'--expected-preparation-sha256',source_plan['preparedShim']['sha256'],
                     '--archive',source_plan['archiveSource']['path'],'--installer-resource',source_plan['installerResource']['path'],
                     '--launcher',source_plan['launcher']['path'],'--frida-directory',str(copied/'packages'),'--prepare',str(generated)]
            prepared=subprocess.run(prepare,capture_output=True,text=True,encoding='utf-8',timeout=30)
            if prepared.returncode:raise AssertionError('Copied runtime plan preparation: '+prepared.stderr)
            plan_hash=hashlib.sha256(generated.read_bytes()).hexdigest()
            command=['pwsh','-NoProfile','-File',str(ROOT/'scripts/serato-session.ps1'),'-Mode','Plan',
                     '-SessionPlan',str(generated),'-ExpectedPlanSha256',plan_hash]
            positive=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=30)
            if positive.returncode:raise AssertionError('Copied full wrapper Plan: '+positive.stderr)
            rows.append({'name':'copied-runtime-complete-wrapper-plan','passed':True,'exitCode':0})
            try:
                module.write_bytes(original+('\nimport pathlib; pathlib.Path('+repr(str(marker))+').write_text("unexpected execution")\n').encode())
                refused=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=30)
                assert refused.returncode!=0 and 'Reviewed input differs: pefile.py' in refused.stderr and not marker.exists()
                rows.append({'name':'wrapper-refuses-module-before-python-verifier','passed':True,'exitCode':refused.returncode})
            finally:module.write_bytes(original)
    return {'schema':'sl3.embedded-launcher-runtime-tests.v1','cases':rows,
            'actualCopiedRuntimeUsed':True,'tamperedCodeExecuted':False,'deviceAccess':False,
            'vendorApplicationExecuted':False,'registryWritten':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--capsule',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--session-plan',type=Path)
    args=parser.parse_args()
    report=exercise(args.launcher.absolute(),args.runtime.absolute(),args.capsule.absolute(),args.session_plan)
    if args.output:
        with args.output.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(report,indent=2))
