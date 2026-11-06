import io
import json
from pathlib import Path
import runpy
import tempfile
import unittest
import warnings
import zipfile

API = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/prepare-portable-powershell.py'))


class PortablePowerShellTest(unittest.TestCase):
    def archive(self, extras=()):
        data = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(data, 'w') as archive:
                for name in sorted(API['REQUIRED']):
                    archive.writestr(name, b'fixture; never executed')
                for name, content in extras:
                    archive.writestr(name, content)
        return zipfile.ZipFile(io.BytesIO(data.getvalue()))

    def test_preserves_runtime_and_notices(self):
        with self.archive([('Modules/Test/notice.txt', b'notice')]) as archive:
            files = API['inventory'](archive)
            self.assertEqual(set(files), API['REQUIRED'] | {'Modules/Test/notice.txt'})

    def test_rejects_windows_aliases_traversal_and_file_directory_collision(self):
        for name in ('../escape', '/escape', 'a:stream', './escape', 'a//b', 'a.',
                     'a ', 'CON.txt', 'NUL', 'COM1.txt', 'pwsh.exe', 'PWSH.exe', 'pwsh.exe/child',
                     'a\x01b', 'a?b'):
            with self.subTest(name=name), self.archive([(name, b'x')]) as archive:
                with self.assertRaises(ValueError):
                    API['inventory'](archive)
        # ZipInfo construction normalizes backslashes on Windows; exercise the
        # post-read name directly, as it can appear in an untrusted ZIP.
        with self.archive([('fixture', b'x')]) as archive:
            archive.getinfo('fixture').filename = 'a\\b'
            with self.assertRaises(ValueError):
                API['inventory'](archive)

    def test_rejects_links_encryption_and_oversized_metadata_before_extraction(self):
        with self.archive([('link', b'target')]) as archive:
            row = archive.getinfo('link')
            row.external_attr = 0o120777 << 16
            with self.assertRaises(ValueError):
                API['inventory'](archive)
            row.external_attr = 0
            row.flag_bits |= 1
            with self.assertRaises(ValueError):
                API['inventory'](archive)
            row.flag_bits = 0
            row.file_size = API['MAX_FILE'] + 1
            with self.assertRaises(ValueError):
                API['inventory'](archive)

    def test_manifest_refuses_changed_missing_extra_and_wrong_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = {}
            for name in sorted(API['REQUIRED']):
                path = root / name
                path.write_bytes(b'not executed')
                records[name] = {'bytes': path.stat().st_size, 'sha256': API['sha'](path)}
            manifest = {'schema': 'sl3.portable-powershell.v1', 'files': records}
            path = root / 'runtime-manifest.json'
            path.write_text(json.dumps(manifest))
            expected = API['sha'](path)
            self.assertEqual(API['verify'](root, expected), manifest)
            with self.assertRaisesRegex(ValueError, 'manifest differs'):
                API['verify'](root, '0' * 64)
            exe = root / 'pwsh.exe'
            exe.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'member differs'):
                API['verify'](root, expected)
            exe.write_bytes(b'not executed')
            extra = root / 'extra.ps1'
            extra.write_bytes(b'not executed')
            with self.assertRaisesRegex(ValueError, 'Unexpected'):
                API['verify'](root, expected)
            extra.unlink()
            exe.unlink()
            with self.assertRaises(FileNotFoundError):
                API['verify'](root, expected)

    def test_bad_archive_hash_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'fixture.zip'
            path.write_bytes(b'not a zip')
            with self.assertRaisesRegex(ValueError, 'archive hash/size differs'):
                API['prepare'](path, '0' * 64, Path(temporary) / 'output')
            self.assertFalse((Path(temporary) / 'output').exists())


if __name__ == '__main__':
    unittest.main()
