"""Offline resource preservation, inverse-codec and additive-only archive checks."""
import importlib.util
import struct
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sl3_archive_candidate', ROOT/'scripts/prepare-serato-sl3-archive.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
r = v.c.module('test_archive_reader', 'inspect-serato-resource-archive.py')
KEY = (0x12345678, 0xabcdef01, 0x76543210, 0xfedcba98)


def fixture():
    # Two independent original entries with non-member gap and trailing bytes.
    from io import BytesIO
    import zipfile
    blocks = []
    for name, raw in [('audio/first.xml', b'<root>original-a</root>'), ('hid/second.xml', b'<root>original-b</root>')]:
        stream = BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as out:
            out.writestr(name, raw)
        blocks.append((name, v.encode_block(stream.getvalue(), KEY, r)))
    entries = [{'name': n, 'size': len(b), 'offset': 0} for n, b in blocks]
    size = len(v.encode_block(v.index_bytes(entries), KEY, r))
    entries[0]['offset'] = 8+size+3
    entries[1]['offset'] = entries[0]['offset']+entries[0]['size']+5
    index = v.encode_block(v.index_bytes(entries), KEY, r)
    return struct.pack('<Q', size)+index+b'gap'+blocks[0][1]+b'other'+blocks[1][1]+b'keep-suffix'


class ArchiveCandidateTests(unittest.TestCase):
    def test_encoder_inverse_across_word_counts_and_padding(self):
        for size in [4, 5, 6, 7, 8, 15, 16, 31, 64, 1001, 4096]:
            for key in [KEY, (0, 0, 0, 0), (r.MASK,)*4]:
                plain = bytes((n*71+3) % 256 for n in range(size))
                with self.subTest(size=size, key=key):
                    encoded = v.encode_block(plain, key, r)
                    self.assertEqual(r.decode_block(encoded, key), plain)
                    self.assertEqual(v.encode_block(r.decode_block(encoded, key), key, r), encoded)

    def test_encoder_refuses_unbounded_inputs_and_bad_key(self):
        for raw in [b'', b'a', b'abc', b'a'*r.LIMIT]:
            with self.assertRaises(ValueError):
                v.encode_block(raw, KEY, r)
        for key in [(), (-1, 0, 0, 0), (0, 0, 0, 2**32), (True, 0, 0, 0)]:
            with self.assertRaises(ValueError):
                v.encode_block(b'1234', key, r)

    def test_append_preserves_all_original_ciphertext_gaps_suffix_and_order(self):
        original = fixture()
        xml = b'<root>our own candidate</root>'
        result, proof = v.append_candidate(original, xml, KEY, r)
        self.assertEqual(proof['originalMembers'], 2)
        self.assertEqual(proof['candidateMembers'], 3)
        for key in ['allOriginalEncryptedMembersUnchanged', 'allOriginalMemberCrcsPassed', 'allOriginalCodecInverseChecksPassed']:
            self.assertIs(proof[key], True)
        oldsize, old = v.inspect_index(original, KEY, r)
        newsize, new = v.inspect_index(result, KEY, r)
        self.assertEqual([e['name'] for e in new], [e['name'] for e in old]+[v.MEMBER])
        self.assertEqual(result[8+newsize:new[-1]['offset']], original[8+oldsize:])
        self.assertEqual(r.unpack_member(result[new[-1]['offset']:], KEY, v.MEMBER)[0], xml)
        self.assertEqual(v.append_candidate(original, xml, KEY, r), (result, proof))

    def test_second_append_and_corrupt_original_refused(self):
        original = fixture()
        result, _ = v.append_candidate(original, b'<root/>', KEY, r)
        with self.assertRaisesRegex(ValueError, 'already present'):
            v.append_candidate(result, b'<root/>', KEY, r)
        _, entries = v.inspect_index(original, KEY, r)
        broken = bytearray(original)
        broken[entries[0]['offset']+10] ^= 0x80
        with self.assertRaises(ValueError):
            v.append_candidate(bytes(broken), b'<root/>', KEY, r)

    def test_zip_metadata_and_size_are_fixed(self):
        import io
        import zipfile
        xml = b'<root/>'
        self.assertEqual(v.zip_candidate(xml), v.zip_candidate(xml))
        with zipfile.ZipFile(io.BytesIO(v.zip_candidate(xml))) as z:
            self.assertEqual(z.namelist(), [v.MEMBER])
            self.assertEqual(z.getinfo(v.MEMBER).date_time, (2026, 11, 2, 0, 0, 0))
            self.assertEqual(z.read(v.MEMBER), xml)
        for raw in [b'', b'x'*65537]:
            with self.assertRaises(ValueError):
                v.zip_candidate(raw)

    def test_invalid_index_extents_and_path_refused(self):
        for raw in [b'', b'12345678', struct.pack('<Q', 1000)+b'x'*16]:
            with self.assertRaises(ValueError):
                v.inspect_index(raw, KEY, r)
        for p in [ROOT/'outside', ROOT/'analysis/sl3-archive-candidate-a/nested', ROOT/'analysis/sl3-archive-candidate-..']:
            with self.assertRaises(ValueError):
                v.location(p)
        self.assertEqual(v.location(ROOT/'analysis/sl3-archive-candidate-test'), ROOT/'analysis/sl3-archive-candidate-test')

    def test_no_overwrite_before_reading_source(self):
        import sys
        with patch.object(sys, 'argv', ['tool', '--candidate', 'unused', '--prepare', str(ROOT/'analysis/sl3-archive-candidate-test')]), \
             patch.object(Path, 'exists', return_value=True), patch.object(v, 'prepare') as prepare:
            with self.assertRaisesRegex(ValueError, 'Fresh output'):
                v.main()
            prepare.assert_not_called()


if __name__ == '__main__':
    unittest.main()
