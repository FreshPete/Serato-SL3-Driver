"""Check real Frida child-environment handoff using owned Python children only."""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def exercise(frida_directory):
    if os.name!='nt':raise ValueError('Windows child-process check required')
    sys.path.insert(0,str(frida_directory.absolute()))
    import frida
    api=runpy.run_path(str(ROOT/'scripts/run-serato-startup-session.py'))
    application=Path(sys._base_executable).absolute()
    real=frida.get_local_device()
    rows=[]
    test_root=ROOT/'artifacts/build/portable-environment-tests';test_root.mkdir(exist_ok=True)
    for selected in (False,True):
        with tempfile.TemporaryDirectory(dir=test_root) as temporary:
            directory=Path(temporary)
            assert directory.resolve().is_relative_to(test_root.resolve())
            marker=directory/'exit.txt';output=directory/'observed.json'
            code=('import json,os,pathlib,sys,time; '
                  'pathlib.Path(sys.argv[1]).write_text(json.dumps({k:os.environ.get(k) for k in '
                  '("SL3_SESSION_CAPSULE","SL3_SESSION_CAPSULE_SHA256","SL3_ASIO_PRIVATE_TRACE")})); '
                  'p=pathlib.Path(sys.argv[2]); deadline=time.monotonic()+15;\n'
                  'while not p.exists() and time.monotonic()<deadline: time.sleep(.01)')
            class Device:
                def spawn(self,argv,**kwargs):
                    assert argv==[str(application)]
                    return real.spawn([str(application),'-I','-B','-c',code,str(output),str(marker)],**kwargs)
                def attach(self,pid):return real.attach(pid)
                def resume(self,pid):return real.resume(pid)
            wrapped=type('OwnedPythonFrida',(),{'get_local_device':staticmethod(Device)})()
            context={'SL3_SESSION_CAPSULE':str(directory/'session-capsule.json'),
                     'SL3_SESSION_CAPSULE_SHA256':'a'*64} if selected else {}
            backend=api['WindowsProcess'](application,wrapped,expected_application_sha=api['digest'](application),launcher_context=context)
            observed=None
            with patch.dict(os.environ,SL3_SESSION_CAPSULE='untrusted inherited path',SL3_SESSION_CAPSULE_SHA256='f'*64):
                try:
                    backend.start("send({event:'trace_ready'});",lambda *args:None)
                    backend.resume()
                    deadline=time.monotonic()+8
                    while not output.exists():
                        if backend.wait(.02) or time.monotonic()>=deadline:raise RuntimeError('Owned environment fixture did not publish')
                    # Child writes a small JSON fixture; wait for completed JSON,
                    # without confusing file existence with full publication.
                    while True:
                        try:observed=json.loads(output.read_bytes());break
                        except (ValueError,OSError):
                            if time.monotonic()>=deadline:raise
                            time.sleep(.01)
                    backend.detach();marker.write_text('exit')
                    assert backend.wait(5)
                finally:
                    marker.write_text('exit')
                    retirement=backend.cleanup()
            expected={'SL3_ASIO_PRIVATE_TRACE':'0','SL3_SESSION_CAPSULE':'','SL3_SESSION_CAPSULE_SHA256':''}
            expected.update(context)
            assert observed==expected and retirement['processExited'] and retirement['jobEmpty']
            assert retirement['exitCode']==0 and not retirement['observerForcedTermination']
            rows.append({'selectedContext':selected,'expectedEnvironmentObserved':True,'childExitCode':0,
                         'processAndJobRetired':True,'forcedTermination':False})
    return {'schema':'sl3.portable-environment-tests.v1','cases':rows,'fridaVersion':frida.__version__,
            'actualFridaUsed':True,'vendorApplicationExecuted':False,'deviceAccess':False,'registryWritten':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frida-directory',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=exercise(args.frida_directory)
    if args.output:
        with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))
