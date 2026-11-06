"""Check candidate payload selection without starting an interpreter or Frida."""
from pathlib import Path
import base64
import hashlib
import runpy
import tempfile
import unittest

API = runpy.run_path(str(Path(__file__).with_name('prepare-local-frida-probe-runtime.py')))


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name); self.base = self.root / 'base'; self.generated = self.root / 'generated'
        self.manifest = {'files': {}}
        for name, data in {'python.exe': b'python', 'python3.dll': b'abi', 'LICENSE.txt': b'license',
                           'packages/frida/_frida.pyd': b'stock binary', 'packages/unrelated.bin': b'other'}.items():
            path = self.base / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            self.manifest['files'][name] = {}
        self.generated.mkdir()
        for name in ('__init__.py', 'aio.py', '_frida.pyi'):
            (self.generated / name).write_bytes(b'binding')
            (self.base / 'packages/frida' / name).write_bytes(b'binding')
        (self.generated / '_frida.pyd').write_bytes(b'reviewed candidate')

    def tearDown(self): self.temporary.cleanup()

    def test_only_candidate_native_extension_selected(self):
        result = API['payload'](self.base, self.manifest, self.generated)
        self.assertEqual(result['packages/frida/_frida.pyd'], b'reviewed candidate')
        self.assertNotIn(b'stock binary', result.values())
        self.assertNotIn('packages/unrelated.bin', result)

    def test_binding_drift_refused(self):
        (self.generated / 'aio.py').write_bytes(b'changed')
        with self.assertRaises(ValueError): API['payload'](self.base, self.manifest, self.generated)

    def test_incomplete_interpreter_refused(self):
        del self.manifest['files']['python3.dll']
        with self.assertRaises(ValueError): API['payload'](self.base, self.manifest, self.generated)

    def dependency(self, name, extra=None):
        info = name + '-1.dist-info'
        contents = {name + '/__init__.py': b'dependency', info + '/licenses/LICENSE': b'license', **(extra or {})}
        rows = []
        for relative, data in contents.items():
            target = self.base / 'packages' / relative; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            rows.append(relative + ',sha256=' + digest + ',' + str(len(data)))
        record = info + '/RECORD'; rows.append(record + ',,')
        target = self.base / 'packages' / record; target.write_text('\n'.join(rows) + '\n')
        self.manifest['files']['packages/' + record] = {}

    def test_reviewed_inspection_dependencies_selected(self):
        self.dependency('capstone'); self.dependency('pefile')
        files, records = API['inspection_dependencies'](self.base, self.manifest)
        self.assertEqual(set(records), {'capstone', 'pefile'})
        self.assertTrue(all(not name.startswith('packages/frida') for name in files))

    def test_frida_native_payload_in_inspection_record_refused(self):
        self.dependency('capstone', {'frida/_frida.pyd': b'wrong native dependency'}); self.dependency('pefile')
        with self.assertRaises(ValueError): API['inspection_dependencies'](self.base, self.manifest)

    def test_missing_inspection_record_refused(self):
        self.dependency('capstone')
        with self.assertRaises(ValueError): API['inspection_dependencies'](self.base, self.manifest)


if __name__ == '__main__': unittest.main()
