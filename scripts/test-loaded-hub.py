"""Offline module-buffer/parser tests; no Windows query or device operation."""
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location('loaded_hub', Path(__file__).with_name('inspect-loaded-hub.py'))
hub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hub)
EXPECTED = {'sizeOfImage': 733184, 'imageChecksum': 781464, 'timeDateStamp': 180548141}


def fixture(timestamp=0, name=hub.KERNEL_PATH.encode('ascii')):
    data = bytearray(322)
    struct.pack_into('<H', data, 0, 320)
    struct.pack_into('<I', data, 32, EXPECTED['sizeOfImage'])
    struct.pack_into('<H', data, 46, name.rfind(b'\\') + 1)
    data[48:48 + len(name)] = name
    struct.pack_into('<II', data, 304, EXPECTED['imageChecksum'], timestamp)
    return data


class LoadedHubTests(unittest.TestCase):
    def test_redacted_address_and_missing_timestamp_remain_incomplete(self):
        result = hub.compare(hub.parse_modules(fixture()), EXPECTED)
        self.assertTrue(result['targetPresent'])
        self.assertTrue(result['availableMetadataMatches'])
        self.assertTrue(result['loaded']['imageBaseRedacted'])
        for key in ('identityMetadataComplete', 'completeMetadataMatches', 'loadedMemoryIdentityVerified',
                    'usbWindowQualified', 'readinessAdmission'):
            self.assertIs(result[key], False)

    def test_full_metadata_match_still_does_not_attest_memory_or_usb(self):
        data = fixture(timestamp=EXPECTED['timeDateStamp'])
        struct.pack_into('<Q', data, 24, 0xfffff80000000000)
        result = hub.compare(hub.parse_modules(data), EXPECTED)
        self.assertTrue(result['completeMetadataMatches'])
        self.assertFalse(result['loaded']['imageBaseRedacted'])
        for key in ('loadedMemoryIdentityVerified', 'usbWindowQualified', 'readinessAdmission'):
            self.assertIs(result[key], False)

    def test_mismatch_and_zero_checksum_do_not_match(self):
        for field in ('sizeOfImage', 'imageChecksum', 'timeDateStamp'):
            rows = hub.parse_modules(fixture(timestamp=EXPECTED['timeDateStamp']))
            rows[0][field] += 1
            self.assertFalse(hub.compare(rows, EXPECTED)['availableMetadataMatches'])
        rows = hub.parse_modules(fixture())
        rows[0]['imageChecksum'] = 0
        result = hub.compare(rows, EXPECTED)
        self.assertFalse(result['availableMetadataMatches'])
        self.assertFalse(result['identityMetadataComplete'])

    def test_missing_lookalike_and_duplicate_targets(self):
        for rows in ([], hub.parse_modules(fixture(name=rb'\SystemRoot\Temp\UsbHub3.sys'))):
            result = hub.compare(rows, EXPECTED)
            self.assertFalse(result['targetPresent'])
            self.assertFalse(result['completeMetadataMatches'])
        rows = hub.parse_modules(fixture(name=hub.KERNEL_PATH.lower().encode('ascii')))
        self.assertTrue(hub.compare(rows, EXPECTED)['targetPresent'])
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            hub.compare(rows * 2, EXPECTED)

    def test_unknown_truncated_and_terminal_layouts_rejected(self):
        cases = [b'', b'\0\0', fixture()[:-1], fixture() + b'\0', b'x' * (hub.MAX_BYTES + 1)]
        unknown = fixture()
        struct.pack_into('<H', unknown, 0, 328)
        cases.append(unknown)
        for raw in cases:
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                hub.parse_modules(raw)

    def test_invalid_path_offset_and_size_rejected(self):
        cases = []
        for offset in (0, 1, 255):
            data = fixture()
            struct.pack_into('<H', data, 46, offset)
            cases.append(data)
        data = fixture()
        data[48:304] = b'x' * 256
        cases.append(data)
        data = fixture()
        struct.pack_into('<I', data, 32, 0)
        cases.append(data)
        for raw in cases:
            with self.assertRaises(ValueError):
                hub.parse_modules(raw)


if __name__ == '__main__':
    unittest.main(verbosity=2)
