import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/prepare-serato-startup-shim.py'))
prepare = MODULE['prepare']


class FakePE:
    FILE_HEADER = type('Header', (), {'Machine': 0x8664})()
    OPTIONAL_HEADER = type('Optional', (), {'Magic': 0x20b})()
    def __init__(self, **kwargs):
        self.entries = {rva: bytes.fromhex(value) for _, rva, value in MODULE['points'](MODULE['TEMPLATE'].read_text())}
    def get_data(self, rva, length):
        return self.entries[rva]
    def close(self):
        pass


class PreparationTest(unittest.TestCase):
    def test_guard_inventory_and_local_path_contract(self):
        source = MODULE['TEMPLATE'].read_text()
        self.assertEqual(len(MODULE['points'](source)), 3)
        self.assertEqual(MODULE['asio_path']('C:/Program Files/SL3 Rebuild/test/sl3_asio.dll'),
                         'C:\\Program Files\\SL3 Rebuild\\test\\sl3_asio.dll')
        for path in ('relative/sl3_asio.dll', '//server/share/sl3_asio.dll',
                     'C:/test/../sl3_asio.dll', 'C:/test/sl3_asio.dll:stream', 'C:/test/other.dll'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                MODULE['asio_path'](path)

    def test_offline_preparation_matches_exact_source_and_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'analysis').mkdir()
            app = root/'app.exe'
            app.write_bytes(b'synthetic image; never executed')
            with patch.dict(prepare.__globals__, ROOT=root, APP_SHA=hashlib.sha256(app.read_bytes()).hexdigest()), patch.object(MODULE['pefile'], 'PE', FakePE):
                result = prepare(app, 'C:/test/sl3_asio.dll')
                self.assertFalse(result['prepared'])
                self.assertEqual(list((root/'analysis').iterdir()), [])
                output = root/'analysis/sl3-startup-shim-test'
                result = prepare(app, 'C:/test/sl3_asio.dll', output)
                self.assertEqual(result, json.loads((output/'preparation.json').read_bytes()))
                self.assertEqual(result['preparedScriptSha256'], hashlib.sha256((output/'startup-shim.js').read_bytes()).hexdigest())
                self.assertFalse(result['applicationLaunched'])
                self.assertFalse(result['processAttached'])
                with self.assertRaises(ValueError):
                    prepare(app, 'C:/test/sl3_asio.dll', output)

    def test_wrong_application_refused_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'analysis').mkdir()
            app = root/'app.exe'
            app.write_bytes(b'not Serato')
            with patch.dict(prepare.__globals__, ROOT=root):
                with self.assertRaisesRegex(ValueError, 'Application differs'):
                    prepare(app, 'C:/test/sl3_asio.dll', root/'analysis/sl3-startup-shim-refused')
                self.assertEqual(list((root/'analysis').iterdir()), [])

    def test_wrong_entry_refused_before_output_creation(self):
        class WrongEntry(FakePE):
            def get_data(self, rva, length):
                return b'\x00' * length
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'analysis').mkdir()
            app = root/'app.exe'
            app.write_bytes(b'synthetic image')
            with patch.dict(prepare.__globals__, ROOT=root, APP_SHA=hashlib.sha256(app.read_bytes()).hexdigest()), patch.object(MODULE['pefile'], 'PE', WrongEntry):
                with self.assertRaisesRegex(ValueError, 'entry differs'):
                    prepare(app, 'C:/test/sl3_asio.dll', root/'analysis/sl3-startup-shim-refused')
                self.assertEqual(list((root/'analysis').iterdir()), [])


if __name__ == '__main__':
    unittest.main()
