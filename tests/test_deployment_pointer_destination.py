import os
from pathlib import Path
import runpy
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

API = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/prepare-asio-deployment.py'))


class PointerDestinationTest(unittest.TestCase):
    def test_existing_and_absent_regular_leaf_preserve_native_spelling(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary);path=parent/'pointer.txt'
            self.assertEqual(API['pointer_destination'](path,parent),path)
            path.write_text('owned fixture')
            self.assertEqual(API['pointer_destination'](path,parent),path)

    def test_redirected_regular_leaf_does_not_change_containment_or_locator(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);parent=root/'native';parent.mkdir();path=parent/'pointer.txt'
            path.write_text('fixture');original=Path.resolve
            def redirected(self,*args,**kwargs):
                return root/'package-cache/pointer.txt' if self==path else original(self,*args,**kwargs)
            with patch.object(Path,'resolve',redirected):
                with self.assertRaisesRegex(ValueError,'escapes'):API['inside'](path,parent)
                self.assertEqual(API['pointer_destination'](path,parent),path)
                self.assertIn(str(path),API['locator_text'](root/'install',path,'1'*64,'2'*64).decode())

    def test_parent_escape_and_traversal_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);parent=root/'native';parent.mkdir();outside=root/'outside';outside.mkdir()
            for path in (outside/'pointer.txt',parent/'..'/'pointer.txt',Path('relative.txt')):
                with self.subTest(path=path),self.assertRaises(ValueError):API['pointer_destination'](path,parent)
            original=Path.resolve
            def escaped(self,*args,**kwargs):
                return outside if self==parent/'junction' else original(self,*args,**kwargs)
            with patch.object(Path,'resolve',escaped),self.assertRaisesRegex(ValueError,'escapes'):
                API['pointer_destination'](parent/'junction/pointer.txt',parent)

    def test_directory_symlink_and_reparse_leaf_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary);path=parent/'pointer';path.mkdir()
            with self.assertRaisesRegex(ValueError,'regular non-reparse'):API['pointer_destination'](path,parent)
            for info in (SimpleNamespace(st_mode=stat.S_IFREG,st_file_attributes=0x400),
                         SimpleNamespace(st_mode=stat.S_IFLNK,st_file_attributes=0)):
                with self.subTest(info=info),patch.object(Path,'lstat',return_value=info):
                    # Isolate leaf attributes; parent containment remains an
                    # independently tested condition above.
                    with patch.object(Path,'resolve',lambda self:self),self.assertRaisesRegex(ValueError,'regular non-reparse'):
                        API['pointer_destination'](path,parent)

    @unittest.skipUnless(os.name=='nt','Windows native spelling')
    def test_actual_windows_packaged_file_visibility_if_present(self):
        # Exact create-new fixture, never a session pointer or protected file.
        import uuid
        parent=Path(os.environ['LOCALAPPDATA'])/'SL3Rebuild'
        if not parent.is_dir():
            self.skipTest('Host-only check requires existing project user-data directory')
        path=parent/('path-check-'+uuid.uuid4().hex+'.txt')
        try:
            with path.open('x',encoding='utf-8') as stream:stream.write('non-session regression fixture')
            self.assertEqual(API['pointer_destination'](path,parent),path)
            self.assertEqual(path.read_text(),'non-session regression fixture')
            if not path.resolve().is_relative_to(parent.resolve()):
                with self.assertRaisesRegex(ValueError,'escapes'):API['inside'](path,parent)
        finally:
            if path.exists():path.unlink()


if __name__=='__main__':unittest.main()
