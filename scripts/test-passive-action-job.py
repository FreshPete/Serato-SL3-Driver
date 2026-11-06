"""Exercise the passive runner's single-process job with owned Python fixtures only."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def exercise():
    api=runpy.run_path(str(ROOT/'scripts/observe-serato-download-action.py'))
    host=api['module']('run-serato-startup-session.py')
    with tempfile.TemporaryDirectory(prefix='sl3-job-limit-') as temporary:
        root=Path(temporary);go=root/'go';result=root/'result.json';unexpected=root/'unexpected'
        code="""import pathlib,sys,time,subprocess,json
g=pathlib.Path(sys.argv[1]);deadline=time.monotonic()+10
while not g.exists() and time.monotonic()<deadline:time.sleep(.01)
r={'spawnAccepted':False}
try:
 p=subprocess.Popen([sys.executable,'-I','-B','-c','import pathlib,sys;pathlib.Path(sys.argv[1]).write_text("unexpected")',sys.argv[3]])
 r['spawnAccepted']=True;p.wait(timeout=2)
except OSError as e:r['winerror']=e.winerror
pathlib.Path(sys.argv[2]).write_text(json.dumps(r))
"""
        class Script:
            def on(self,*args):pass
            def load(self):pass
            def unload(self):pass
        class Session:
            def create_script(self,*args):return Script()
            def detach(self):pass
        class Device:
            def spawn(self,*args,**kwargs):
                self.child=subprocess.Popen([sys.executable,'-I','-B','-c',code,str(go),str(result),str(unexpected)],
                                            creationflags=subprocess.CREATE_NO_WINDOW)
                return self.child.pid
            def attach(self,*args):return Session()
            def resume(self,*args):pass
        device=Device()
        manager=type('Manager',(),{'get_local_device':staticmethod(lambda:device),'close':staticmethod(lambda:None)})()
        frida=type('MockFrida',(),{'DeviceManager':staticmethod(lambda:manager)})()
        backend=host['WindowsProcess'](Path(sys.executable),frida,expected_application_sha=host['digest'](sys.executable))
        try:
            backend.start('fixture',lambda *args:None)
            policy=api['restrict_children'](backend);go.write_text('go')
            assert backend.wait(8)
            outcome=json.loads(result.read_text())
            assert outcome['spawnAccepted'] is False and not unexpected.exists(),outcome
        finally:cleanup=backend.cleanup()
        assert cleanup['processExited'] and cleanup['exitCode']==0 and cleanup['jobEmpty']
        assert cleanup['instrumentationManagerClosed'] and 'detachError' not in cleanup
        return {'schema':'sl3.passive-action-job-test.v1','policy':policy,'childOutcome':outcome,
            'cleanup':cleanup,'mockedFridaBoundary':True,'seratoExecuted':False,'deviceOpened':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=exercise()
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))
