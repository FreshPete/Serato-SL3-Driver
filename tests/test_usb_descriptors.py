"""Replay the real unit's descriptors and reject malformed record boundaries."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('usb_descriptors', ROOT/'scripts/usb-descriptors.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class DescriptorTests(unittest.TestCase):
    def test_connected_unit_fixture(self):
        data = bytes.fromhex((ROOT/'tests/fixtures/sl3-configuration.hex').read_text())
        rows = MODULE.parse_configuration(data)
        self.assertEqual(rows[0]['total_length'], len(data))
        interfaces = [r for r in rows if r['type']==4]
        self.assertEqual({r['interface'] for r in interfaces}, {0,1,2,3})
        self.assertTrue(all(r['interface_class']==255 for r in interfaces))
        endpoints = {r['endpoint']:r for r in rows if r['type']==5}
        self.assertEqual(set(endpoints), {'0x6','0x82','0x81','0x1'})
        self.assertEqual(endpoints['0x6']['transfer'], 'isochronous')
        self.assertEqual(endpoints['0x82']['max_packet'], 126)
        self.assertEqual(endpoints['0x81']['transfer'], 'interrupt')
        self.assertEqual(endpoints['0x1']['max_packet'], 64)

    def test_invalid_lengths(self):
        for data in [b'\x00\x04',b'\x01\x05',b'\x09\x04\x00',b'\x09']:
            with self.subTest(data=data), self.assertRaises(ValueError):
                MODULE.parse_configuration(data)

    def test_unknown_descriptor_preserved(self):
        rows = MODULE.parse_configuration(bytes.fromhex('04fe1234'))
        self.assertEqual(rows, [dict(offset=0,type=254,hex='04fe1234')])

if __name__ == '__main__':
    unittest.main()
