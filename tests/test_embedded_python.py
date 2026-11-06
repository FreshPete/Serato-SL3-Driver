import base64
import hashlib
import io
import json
from pathlib import Path
import runpy
import tempfile
import unittest
import warnings
import zipfile

API=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/prepare-embedded-python.py'))


class EmbeddedPythonTest(unittest.TestCase):
    def archive(self,extra=()):
        stream=io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(stream,'w') as package:
                for name,data in [('python.exe',b'not executed'),('python3.dll',b'not loaded'),
                                  ('python315.dll',b'not loaded'),('python315.zip',b'synthetic stdlib'),
                                  ('LICENSE.txt',b'fixture license'),('python315._pth',b'import site\n'),*extra]:
                    package.writestr(name,data)
        return stream.getvalue()

    def test_module_path_is_fixed_and_site_is_not_enabled(self):
        files=API['embedded_files'](self.archive())
        self.assertEqual(files['python315._pth'],b'python315.zip\n.\npackages\n')

    def test_zip_traversal_streams_alias_duplicates_and_links_refused(self):
        for name in ('../escape','/escape','folder\\escape','file:stream','./escape','folder//escape','python.exe'):
            with self.subTest(name=name),self.assertRaises(ValueError):API['embedded_files'](self.archive([(name,b'fixture')]))
        link=zipfile.ZipInfo('link');link.create_system=3;link.external_attr=0o120777<<16
        with self.assertRaises(ValueError):API['embedded_files'](self.archive([(link,b'target')]))

    def wheel(self,parent,extra=''):
        metadata=parent/'pefile-test.dist-info';metadata.mkdir()
        (parent/'module.py').write_bytes(b'not imported');(metadata/'LICENSE').write_bytes(b'fixture notice')
        rows=[]
        for name in ('module.py','pefile-test.dist-info/LICENSE'):
            raw=(parent/name).read_bytes();digest=base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
            rows.append(f'{name},sha256={digest},{len(raw)}\n')
        record=metadata/'RECORD';record.write_text(''.join(rows)+'pefile-test.dist-info/RECORD,,\n'+extra)
        return record

    def test_wheel_hash_is_checked_before_copying_and_notice_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);record=self.wheel(root)
            _,_,files=API['wheel_files'](record)
            self.assertIn('packages/pefile-test.dist-info/LICENSE',files)
            (root/'module.py').write_text('tampered')
            with self.assertRaises(ValueError):API['wheel_files'](record)

    def test_wheel_traversal_and_duplicate_inventory_refused(self):
        for extra in ('../escape,sha256=abc,1\n','module.py,sha256=abc,1\n'):
            with self.subTest(extra=extra),tempfile.TemporaryDirectory() as temporary:
                record=self.wheel(Path(temporary),extra)
                with self.assertRaises(ValueError):API['wheel_files'](record)

    def test_runtime_verifier_rejects_changed_missing_and_unexpected_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);target=root/'module.py';target.write_bytes(b'not imported')
            manifest={'schema':'sl3.embedded-python.v1','files':{'module.py':{'bytes':target.stat().st_size,
                       'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}}}
            path=root/'runtime-manifest.json';path.write_text(json.dumps(manifest))
            expected=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(API['verify'](root,expected),manifest)
            with self.assertRaisesRegex(ValueError,'manifest differs'):API['verify'](root,'0'*64)
            target.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'member differs'):API['verify'](root,expected)
            target.write_bytes(b'not imported');(root/'unexpected').write_text('fixture')
            with self.assertRaisesRegex(ValueError,'Unexpected'):API['verify'](root,expected)
            (root/'unexpected').unlink();target.unlink()
            with self.assertRaises(FileNotFoundError):API['verify'](root,expected)


if __name__=='__main__':unittest.main()
