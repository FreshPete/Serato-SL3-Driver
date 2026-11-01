"""Boundary checks for the read-only resource container inspector."""
import importlib.util
import io
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('resource_archive', ROOT/'scripts/inspect-serato-resource-archive.py')
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


def index(*rows):
    result = struct.pack('<Q', len(rows))
    for name, size, offset in rows:
        encoded = name.encode()
        result += struct.pack('<3Q', size, offset, len(encoded)) + encoded
    return result


def zipped(rows):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as output:
        for name, contents in rows:
            output.writestr(name, contents)
    return stream.getvalue()


class ResourceArchiveTests(unittest.TestCase):
    def test_index_preserves_name_and_extent(self):
        rows = archive.parse_index(index(('audio/a.xml', 8, 80), ('hid/b.xml', 12, 88)), 100, 80)
        self.assertEqual(rows, [{'name': 'audio/a.xml', 'offset': 80, 'size': 8},
                                {'name': 'hid/b.xml', 'offset': 88, 'size': 12}])

    def test_index_rejects_truncation_counts_and_suffix(self):
        valid = index(('a.xml', 8, 80))
        for bad in (b'', struct.pack('<Q', 10001), valid[:-1], valid+b'\0', struct.pack('<Q', 0)):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                archive.parse_index(bad, 100, 80)

    def test_index_rejects_paths_and_duplicates(self):
        for name in ('.', '/a.xml', '../a.xml', 'a/../b.xml', 'C:/a.xml', 'a\\b.xml', 'a//b.xml', 'a\0.xml'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                archive.parse_index(index((name, 8, 80)), 100, 80)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            archive.parse_index(index(('a.xml', 8, 80), ('a.xml', 8, 88)), 100, 80)

    def test_index_rejects_overlap_header_and_out_of_range_extents(self):
        for size, offset in ((8, 72), (8, 96), (7, 80), (10, 80), (2**64-1, 80)):
            with self.subTest(size=size, offset=offset), self.assertRaises(ValueError):
                archive.parse_index(index(('a.xml', size, offset)), 100, 80)
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            archive.parse_index(index(('a.xml', 8, 80), ('b.xml', 8, 84)), 100, 80)

    def test_decoder_rejects_invalid_storage_before_processing(self):
        for data in (b'', b'1234', b'123456789'):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                archive.decode_block(data, (0, 0, 0, 0))
        with self.assertRaisesRegex(ValueError, 'key shape'):
            archive.decode_block(b'12345678', (0, 0, 0, -1))

    def test_inner_zip_rejects_wrong_identity_multiple_members_and_bad_crc(self):
        valid = zipped([('a.xml', b'<root>example</root>')])
        with patch.object(archive, 'decode_block', return_value=valid):
            content, _ = archive.unpack_member(b'', (), 'a.xml')
            self.assertEqual(content, b'<root>example</root>')
            with self.assertRaisesRegex(ValueError, 'contract mismatch'):
                archive.unpack_member(b'', (), 'b.xml')
        with patch.object(archive, 'decode_block', return_value=zipped([('a.xml', b'a'), ('b.xml', b'b')])):
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                archive.unpack_member(b'', (), 'a.xml')
        corrupted = valid.replace(b'<root>example</root>', b'<root>corrupt</root>')
        with patch.object(archive, 'decode_block', return_value=corrupted):
            with self.assertRaises(zipfile.BadZipFile):
                archive.unpack_member(b'', (), 'a.xml')


if __name__ == '__main__':
    unittest.main()
