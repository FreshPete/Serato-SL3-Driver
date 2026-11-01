"""Bounded Qt resource index parser checks, without vendor or device execution."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('qrc_index', ROOT/'scripts/inspect-serato-qrc-resources.py')
qrc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qrc)


def fixture(name='file', languages=(0,)):
    encoded = name.encode('utf-16-be')
    names = struct.pack('>HI', len(encoded)//2, 0)+encoded
    payload = struct.pack('>I', 3)+b'abc'
    tree = struct.pack('>IHIIQ', 0, 2, len(languages), 1, 0)
    tree += b''.join(struct.pack('>IHHHIQ', 0, 0, 0, language, 0, 0) for language in languages)
    return b'qres'+struct.pack('>5I', 3, 24+len(payload)+len(names), 24, 24+len(payload), 0)+payload+names+tree


class QrcIndexTests(unittest.TestCase):
    def test_valid_and_locale_variants(self):
        files, nodes = qrc.bundle_index(fixture(languages=(1, 2)))
        self.assertEqual(nodes, 3)
        self.assertEqual([f['path'] for f in files], ['/file', '/file'])
        self.assertEqual([f['language'] for f in files], [1, 2])

    def test_header_rejections(self):
        good = fixture()
        for at, value in ((0, b'nope'), (4, struct.pack('>I', 2)), (20, struct.pack('>I', 8)), (12, struct.pack('>I', len(good)))):
            bad = bytearray(good);bad[at:at+4] = value
            with self.subTest(at=at), self.assertRaises(ValueError):
                qrc.bundle_index(bytes(bad))
        with self.assertRaises(ValueError):
            qrc.bundle_index(good[:-1])

    def test_tree_cycle_bounds_and_orphan(self):
        good = fixture();tree = struct.unpack_from('>I', good, 8)[0]
        for count, first in ((1, 0), (1, 99), (0, 1)):
            bad = bytearray(good);struct.pack_into('>II', bad, tree+6, count, first)
            with self.subTest(count=count, first=first), self.assertRaises(ValueError):
                qrc.bundle_index(bytes(bad))

    def test_unsafe_and_out_of_bounds_names(self):
        for name in ('..', 'a/b', 'a\\b', 'a\0b', 'a:b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                qrc.bundle_index(fixture(name))
        bad = bytearray(fixture());tree = struct.unpack_from('>I', bad, 8)[0]
        struct.pack_into('>I', bad, tree+22, 100000)
        with self.assertRaises(ValueError):
            qrc.bundle_index(bytes(bad))

    def test_payload_bounds_and_flags(self):
        bad = bytearray(fixture());struct.pack_into('>I', bad, 24, len(bad))
        with self.assertRaises(ValueError):
            qrc.bundle_index(bytes(bad))
        bad = bytearray(fixture());tree = struct.unpack_from('>I', bad, 8)[0]
        struct.pack_into('>H', bad, tree+22+4, 3)
        with self.assertRaises(ValueError):
            qrc.bundle_index(bytes(bad))

    def test_duplicate_locale_and_directory_classification(self):
        with self.assertRaises(ValueError):
            qrc.bundle_index(fixture(languages=(1, 1)))
        report = qrc.summary([{'path': '/modules/UserIO.qml', 'flags': 0}], 2)
        self.assertEqual(report['deviceFolderPaths'], [])
        self.assertEqual(report['userioNamedPaths'], ['/modules/UserIO.qml'])
        report = qrc.summary([{'path': '/userio_partner/audio/x.xml', 'flags': 0}], 4)
        self.assertEqual(report['deviceFolderPaths'], ['/userio_partner/audio/x.xml'])


if __name__ == '__main__':
    unittest.main()
