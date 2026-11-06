"""Exercise the read-only getter decoder with independent machine-code fixtures."""
from pathlib import Path
import runpy
import struct
import unittest

API = runpy.run_path(str(Path(__file__).with_name('inspect-frida-embedded-assets.py')))


def getter(descriptor=0x2000, aligned=False, segment=False):
    first = (b'\x64' if segment else b'') + b'\x48\x8b\x05'
    first += struct.pack('<i', descriptor + 16 - (0x1000 + len(first) + 4))
    store = b'\x48\x89\x41\x10'
    load = (b'\x0f\x28\x05' if aligned else b'\x0f\x10\x05')
    load += struct.pack('<i', descriptor - (0x1000 + len(first) + len(store) + len(load) + 4))
    return first + store + load + b'\x0f\x11\x01\xc3'


class GetterTests(unittest.TestCase):
    def test_expected_descriptor(self):
        self.assertEqual(API['descriptor_rva'](getter(), 0x1000)[0], 0x2000)

    def test_aligned_read_variant(self):
        self.assertEqual(API['descriptor_rva'](getter(aligned=True), 0x1000)[0], 0x2000)

    def test_noncontiguous_descriptor_rejected(self):
        data = bytearray(getter())
        struct.pack_into('<i', data, 3, struct.unpack_from('<i', data, 3)[0] + 8)
        with self.assertRaises(ValueError): API['descriptor_rva'](bytes(data), 0x1000)

    def test_wrong_output_field_rejected(self):
        data = getter().replace(b'\x48\x89\x41\x10', b'\x48\x89\x41\x18')
        with self.assertRaises(ValueError): API['descriptor_rva'](data, 0x1000)

    def test_wrong_output_register_rejected(self):
        data = getter().replace(b'\x48\x89\x41\x10', b'\x48\x89\x43\x10')
        with self.assertRaises(ValueError): API['descriptor_rva'](data, 0x1000)

    def test_segment_override_rejected(self):
        with self.assertRaises(ValueError): API['descriptor_rva'](getter(segment=True), 0x1000)

    def test_extra_call_rejected(self):
        with self.assertRaises(ValueError): API['descriptor_rva'](b'\xe8\0\0\0\0' + getter(), 0x1000)

    def test_missing_return_rejected(self):
        with self.assertRaises(ValueError): API['descriptor_rva'](getter()[:-1], 0x1000)

    def test_early_return_rejected(self):
        with self.assertRaises(ValueError): API['descriptor_rva'](b'\xc3' + getter(), 0x1000)


if __name__ == '__main__':
    unittest.main()
