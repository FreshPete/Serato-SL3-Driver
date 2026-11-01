"""Constrained static-copy interpretation must not invent bytes or execute calls."""
import importlib.util
from pathlib import Path
import struct
import unittest
import capstone

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('literal_copies', ROOT / 'scripts/static-string-copies.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
START = 0x140001000
ALLOCATOR = 0x140010000
SSO = bytes.fromhex('488d55e0 48c745f004000000 48c745f80f000000 c745e073616665 c645e400')


class CopiesTests(unittest.TestCase):
    def setUp(self):
        self.decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.decoder.detail = True
        self.copy = v.LiteralCopies(lambda address, size: b'', ALLOCATOR)

    def run_bytes(self, data):
        instructions = list(self.decoder.disasm(data, START))
        self.assertEqual(sum(i.size for i in instructions), len(data))
        self.copy.run(instructions)

    def test_complete_small_string(self):
        self.run_bytes(SSO)
        self.assertEqual(self.copy.string_argument('rdx'), 'safe')

    def test_unknown_object_cannot_become_empty_or_zero(self):
        self.run_bytes(bytes.fromhex('488d55e0'))
        with self.assertRaisesRegex(ValueError, 'Unknown value'):
            self.copy.string_argument('rdx')

    def test_missing_or_nonzero_terminator_refused(self):
        for data in (SSO[:-4], SSO[:-1] + b'!'):
            with self.subTest(data=data):
                self.copy = v.LiteralCopies(lambda address, size: b'', ALLOCATOR)
                self.run_bytes(data)
                with self.assertRaisesRegex(ValueError, 'terminator'):
                    self.copy.string_argument('rdx')

    def test_branch_and_unrecognised_call_refused(self):
        for data in (bytes.fromhex('eb00'), bytes.fromhex('e800000000')):
            with self.subTest(data=data), self.assertRaisesRegex(ValueError, 'Outside literal-copy scope'):
                self.run_bytes(data)

    def test_no_image_or_unallocated_heap_writes(self):
        for data in (bytes.fromhex('c7050000000000000000'),
                     bytes.fromhex('48b80000003000000000 c60001')):
            with self.subTest(data=data), self.assertRaisesRegex(ValueError, 'Cannot modify'):
                self.run_bytes(data)

    def test_allocator_clobbers_volatile_arguments(self):
        prefix = SSO + bytes.fromhex('b920000000')
        call = b'\xe8' + struct.pack('<i', ALLOCATOR - (START + len(prefix) + 5))
        self.run_bytes(prefix + call)
        with self.assertRaisesRegex(ValueError, 'Unknown value'):
            self.copy.string_argument('rdx')
        self.assertEqual(self.copy.integer(self.copy.read_register('rax')), 0x30000000)

    def test_32_bit_register_write_zero_extends(self):
        self.run_bytes(bytes.fromhex('48b8ffffffffffffffff b800000000'))
        self.assertEqual(self.copy.integer(self.copy.read_register('rax')), 0)

    def test_incomplete_image_literal_refused(self):
        with self.assertRaisesRegex(ValueError, 'Incomplete image literal'):
            self.run_bytes(bytes.fromhex('488b0500000000'))


if __name__ == '__main__':
    unittest.main()
