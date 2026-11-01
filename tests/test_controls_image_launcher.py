"""Actual plan-only/denied child launches under a normal token; never requests UAC."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('collector_launcher_tests',ROOT/'scripts/collect-controls-with-images.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        token=v.batch.source_runner().own_token()
        if not token['queried'] or token['elevated']:raise unittest.SkipTest('Denied-child checks require the normal user token')
        cls.folder=ROOT/'analysis'/('logging-batch-wrapper-test-'+uuid.uuid4().hex)
        cls.plan=v.prepare(cls.folder)
        cls.path=cls.folder/'controls-image.json'
        cls.script=ROOT/'scripts/start-controls-image-capture.ps1'

    def invoke(self,*arguments):
        return subprocess.run(['pwsh','-NoProfile','-File',str(self.script),'-Plan',str(self.path),*arguments],
                              capture_output=True,text=True,timeout=25)

    def test_real_default_plan_launches_nothing(self):
        child=self.invoke();self.assertEqual(child.returncode,0,child.stderr)
        self.assertFalse(json.loads(child.stdout)['launchesProbe'])
        self.assertFalse(Path(self.plan['contextDirectory']).exists())
        self.assertFalse((self.folder/'controls-image-started.json').exists())
        self.assertFalse((self.folder/'controls-image-launch.json').exists())

    def test_real_normal_child_is_denied_and_records_exit(self):
        ident=uuid.uuid4().hex
        child=self.invoke('-Execute','-ExpectedSha256',v.sha(self.path),'-LaunchId',ident)
        self.assertNotEqual(child.returncode,0)
        saved=json.loads((self.folder/f'controls-child-{ident}-exit.json').read_text(encoding='utf-8-sig'))
        self.assertNotEqual(saved['exitCode'],0)
        self.assertIn('already elevated token',(self.folder/f'controls-child-{ident}.log').read_text())
        self.assertFalse((self.folder/'controls-image-started.json').exists())
        self.assertFalse((self.folder/'execution-started.json').exists())
        self.assertFalse(Path(self.plan['contextDirectory']).exists())

    def test_hash_failure_saved_and_same_child_cannot_overwrite(self):
        ident=uuid.uuid4().hex
        args=('-Execute','-ExpectedSha256','0'*64,'-LaunchId',ident)
        child=self.invoke(*args);self.assertNotEqual(child.returncode,0)
        output=self.folder/f'controls-child-{ident}-exit.json'
        before=v.sha(output)
        self.assertIn('Plan changed',json.loads(output.read_text(encoding='utf-8-sig'))['error'])
        retry=self.invoke(*args);self.assertNotEqual(retry.returncode,0)
        self.assertEqual(v.sha(output),before)
        self.assertFalse((self.folder/'controls-image-started.json').exists())


if __name__=='__main__':unittest.main()
