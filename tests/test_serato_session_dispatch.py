from contextlib import contextmanager, redirect_stdout
import io
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
API = runpy.run_path(str(ROOT/'scripts/serato-session-capsule.py'))
INSTALLER = runpy.run_path(str(ROOT/'scripts/serato-session-installer.py'))
BROKER = runpy.run_path(str(ROOT/'scripts/serato-session-broker.py'))


class InstallerDispatchTest(unittest.TestCase):
    def execute(self, root, action='plan', elevated=True, success=True):
        state = {'claimed':False,'installCalled':False,'retirementChecked':False}
        record = {'bundle':{'path':str(root/'bundle'),'sha256':'1'*64},'permitPath':str(root/'permit')}
        plan = {'pointerPath':str(root/'pointer'),'installationDirectory':str(root/'installation')}
        @contextmanager
        def parents(path): yield [1]
        class Stage:
            SYSTEM='system'; ADMINS='admins'
            def local(self,path): return path
            def pinned_parents(self,path): return parents(path)
            def elevated(self): return elevated
            def safe_parent(self,handle,trusted): state['parentChecked']=True
            def account_sid(self,name): return 'trusted-installer'
        stage = Stage()
        @contextmanager
        def claim(*args):
            state['claimed']=True
            yield
            state['receiptAtPermitRelease']=json.loads((root/'install-receipt.json').read_bytes())
            state['claimed']=False
        def install(bundle,expected):
            self.assertTrue(state['claimed']); self.assertTrue(state['parentChecked'])
            self.assertTrue((root/'install-receipt.json').exists())
            state['installCalled']=True
            if success: return {'successful':True}
            raise RuntimeError('synthetic installation failure')
        def retired(directory,plan): state['retirementChecked']=True
        def uninstall(base,destination,digest):
            self.assertTrue(state['retirementChecked']);self.assertEqual(digest,'2'*64)
            state['uninstallCalled']=True;return {'successful':True}
        def module(name,function):
            if name=='asio-install-journal.py': return lambda:stage
            if name=='asio-install.py': return install
            if name=='asio-uninstall.py': return uninstall
            raise AssertionError(name)
        api = {**API,'verify':lambda *args:(record,plan,root),'module':module,'require_retired':retired}
        def load(path):
            if Path(path).name=='serato-session-capsule.py': return api
            return {'claim':claim}
        args=[action,'--capsule',str(root/'session-capsule.json'),'--expected-capsule-sha256','3'*64]
        with patch.object(INSTALLER['runpy'],'run_path',side_effect=load), redirect_stdout(io.StringIO()):
            result=INSTALLER['main'](args)
        return result,state

    def test_plan_does_not_install_or_create_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); result,state=self.execute(root)
            self.assertEqual(result,0);self.assertFalse(state['installCalled'])
            self.assertEqual(list(root.iterdir()),[])

    def test_install_requires_elevation_before_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaisesRegex(ValueError,'administrator'):
                self.execute(root,'install',elevated=False)
            self.assertEqual(list(root.iterdir()),[])

    def test_receipt_is_flushed_inside_claim_and_failure_is_preserved(self):
        for success in (True,False):
            with self.subTest(success=success), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary); result,state=self.execute(root,'install',success=success)
                self.assertEqual(result,0 if success else 1)
                self.assertTrue(state['installCalled']);self.assertFalse(state['claimed'])
                self.assertEqual(state['receiptAtPermitRelease']['successful'],success)
                before=(root/'install-receipt.json').read_bytes()
                with self.assertRaises(FileExistsError):self.execute(root,'install',success=success)
                self.assertEqual((root/'install-receipt.json').read_bytes(),before)

    def test_rollback_checks_retirement_before_uninstall(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'install-receipt.json').write_text(json.dumps({'stageResult':{'stageRecordSha256':'2'*64}}))
            result,state=self.execute(root,'rollback')
            self.assertEqual(result,0);self.assertTrue(state['uninstallCalled'])


class BrokerDispatchTest(unittest.TestCase):
    def test_plan_and_verified_stop_retry_never_launch_processes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); called=[]
            record={'bundle':{'path':str(root/'bundle')},'brokerLimitMs':600000,'captureOutput':False}
            plan={'installationDirectory':str(root/'installation')}
            api={**API,'verify':lambda *args:(record,plan,root),'require_retired':lambda *args:called.append('retired')}
            with patch.object(BROKER['runpy'],'run_path',return_value=api), patch.object(BROKER['subprocess'],'run') as process:
                for action in ('plan','stop'):
                    if action=='stop':(root/'broker-clean.json').write_text(json.dumps({'successful':False,'controllerExited':True}))
                    with redirect_stdout(io.StringIO()) as output:
                        result=BROKER['main']([action,'--capsule',str(root/'session-capsule.json'),'--expected-capsule-sha256','1'*64])
                    self.assertEqual(result,0)
                    if action=='stop':self.assertFalse(json.loads(output.getvalue())['successful'])
                process.assert_not_called()
                self.assertEqual(called,['retired'])

    def test_start_builds_bounded_configuration_and_scopes_capture_environment(self):
        for capture in (True,False):
            with self.subTest(capture=capture), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary); bundle=root/'bundle';bundle.mkdir(); installation=root/'installation';installation.mkdir()
                files={}
                for name in ('sl3_broker_controller.exe','sl3_usbdk.exe','UsbDkHelper.dll'):
                    (installation/name).write_bytes(b'synthetic, never executed')
                    files[name]={'sha256':API['sha'](installation/name)}
                (bundle/'bundle-manifest.json').write_text(json.dumps({'files':files}))
                (root/'install-receipt.json').write_text(json.dumps({'successful':True}))
                record={'bundle':{'path':str(bundle)},'brokerLimitMs':600000,'captureOutput':capture}
                plan={'installationDirectory':str(installation),'pointerPath':str(root/'pointer')}
                api={**API,'verify':lambda *args:(record,plan,root)}
                def launch(command,**kwargs):
                    self.assertEqual(command[-2:],['--limit-ms','600000'])
                    self.assertEqual((root/'broker-timing.txt').read_text().splitlines()[-2:],['rate_hz=44100','buffer_frames=128'])
                    self.assertEqual(kwargs['env'].get('SL3_OUTPUT_CAPTURE_DIRECTORY'),str(root/'output-capture') if capture else None)
                    return subprocess.CompletedProcess(command,0,stdout=json.dumps({'pointerPublished':True}),stderr='')
                with patch.object(BROKER['runpy'],'run_path',return_value=api), patch.object(BROKER['subprocess'],'run',side_effect=launch), patch.dict(BROKER['os'].environ,SL3_OUTPUT_CAPTURE_DIRECTORY='inherited-not-authorized'), redirect_stdout(io.StringIO()):
                    self.assertEqual(BROKER['main'](['start','--capsule',str(root/'session-capsule.json'),'--expected-capsule-sha256','1'*64]),0)


if __name__=='__main__':unittest.main()
