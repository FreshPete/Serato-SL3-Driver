import hashlib
import json
import os
from pathlib import Path
import runpy
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
PLAN=runpy.run_path(str(ROOT/'scripts/prepare-serato-session-plan.py'))
CACHE=runpy.run_path(str(ROOT/'scripts/retire-serato-session-cache.py'))
PACKER=runpy.run_path(str(ROOT/'scripts/prepare-serato-sl3-installer-bundle.py'))


class SessionPlanTest(unittest.TestCase):
    def test_changed_plan_fields_and_moved_plan_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);capsule=root/'session-capsule.json';path=root/'session-plan.json'
            record={'schema':'sl3.serato-session-plan.v1','capsule':{'path':str(capsule),'sha256':'1'*64},
                    'preparedShim':{'path':str(root/'prepared'),'sha256':'2'*64},'archiveSource':{'path':'archive'},
                    'installerResource':{'path':'resource'},'launcher':{'path':'launcher'},'fridaDirectory':'frida',
                    'stageLimitSeconds':900,'asioPrivateTrace':False,'liveValidated':False}
            def save(value):path.write_text(json.dumps(value));return PLAN['sha'](path)
            with patch.dict(PLAN['verify'].__globals__,construct=lambda *args:record):
                identity=save(record);self.assertEqual(PLAN['verify'](path,identity),record)
                for changes in ({'stageLimitSeconds':0},{'liveValidated':True},{'asioPrivateTrace':True}):
                    with self.assertRaisesRegex(ValueError,'changed'):PLAN['verify'](path,save({**record,**changes}))
                with self.assertRaisesRegex(ValueError,'identity'):PLAN['verify'](path,'0'*64)
                other=root/'moved';other.mkdir();moved=other/path.name;moved.write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError,'bound capsule'):PLAN['verify'](moved,PLAN['sha'](moved))

    def test_private_trace_requires_exact_boolean_before_reading_inputs(self):
        for value in (None, 0, 1, '1', {}, []):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,'explicit Boolean'):
                PLAN['construct'](*(['unused']*8),asio_private_trace=value)

    def test_installer_resource_must_contain_the_selected_launcher(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);launcher=root/'SL3_Rebuild_Development_x64.exe';resource=root/'8c7758f23375cee18a9cf3be4a3acc15.bin'
            launcher.write_bytes(b'MZ'+b'synthetic payload'*8);resource.write_bytes(b'synthetic encrypted resource')
            plain=PACKER['resource_bundle'](launcher.name,launcher.read_bytes())
            class PE:
                def __init__(self,*args,**kwargs):pass
                def get_data(self,rva,count):return bytes(range(16))
                def close(self):pass
            def modules(name):
                return {'decode_block':lambda *args:plain} if name=='inspect-serato-resource-archive.py' else PACKER
            with patch.object(PLAN['pefile'],'PE',PE),patch.dict(PLAN['bind_installer'].__globals__,module=modules):
                PLAN['bind_installer'](root/'app',launcher,resource)
                launcher.write_bytes(b'MZ'+b'different payload'*8)
                with self.assertRaisesRegex(ValueError,'exact selected launcher'):PLAN['bind_installer'](root/'app',launcher,resource)


@unittest.skipUnless(os.name=='nt','Actual Windows cache-handle tests')
class CacheTest(unittest.TestCase):
    def fixture(self,root):
        path=root/'Serato/Serato DJ Pro/Drivers'/CACHE['LAUNCHER'];path.parent.mkdir(parents=True)
        data=b'MZ synthetic owned cache fixture';path.write_bytes(data)
        return path,hashlib.sha256(data).hexdigest()

    def test_readonly_inspection_and_owned_readonly_file_retirement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path,identity=self.fixture(root)
            result=CACHE['inspect_or_retire'](root,identity)
            self.assertTrue(result['cachedLauncherPresent']);self.assertTrue(path.exists())
            path.chmod(stat.S_IREAD)
            try:
                self.assertTrue(CACHE['inspect_or_retire'](root,identity,True)['retired'])
                self.assertFalse(path.exists())
            finally:
                if path.exists():path.chmod(stat.S_IWRITE)
            self.assertTrue(CACHE['inspect_or_retire'](root,identity)['alreadyAbsent'])

    def test_wrong_hash_hardlink_and_busy_file_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path,identity=self.fixture(root);original=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'differs'):CACHE['inspect_or_retire'](root,'0'*64,True)
            alias=root/'alias.exe';os.link(path,alias)
            with self.assertRaisesRegex(ValueError,'link count'):CACHE['inspect_or_retire'](root,identity,True)
            alias.unlink()
            with path.open('rb'):
                with self.assertRaises(OSError):CACHE['inspect_or_retire'](root,identity,True)
            self.assertEqual(path.read_bytes(),original)


if __name__=='__main__':unittest.main()
