"""Software-only tests; these never start ETW, open a device or elevate."""
import copy
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('kernel_rundown', HERE / 'inspect-kernel-image-rundown.py')
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)
E, T = inspector.NS['e'], inspector.NS['t']
EXPECTED = {'kernelPath': r'\SystemRoot\System32\drivers\USBHUB3.SYS', 'sizeOfImage': 733184,
            'timeDateStamp': 180548141, 'imageChecksum': 12345, 'diskSha256': 'fixture-only'}


def fixture(operations=(3, 4), pid=0, image_version=2):
    root = ET.Element('Events')
    def event(guid, opcode, fields, version=2):
        row = ET.SubElement(root, f'{{{E}}}Event')
        system = ET.SubElement(row, f'{{{E}}}System')
        ET.SubElement(system, f'{{{E}}}Provider', Guid=inspector.SYSTEM_PROVIDER)
        ET.SubElement(system, f'{{{E}}}Version').text = str(version)
        ET.SubElement(system, f'{{{E}}}Opcode').text = str(opcode)
        ET.SubElement(system, f'{{{E}}}TimeCreated', SystemTime='2026-10-31T12:00:00.0000000+00:00')
        payload = ET.SubElement(row, f'{{{E}}}EventData')
        for name, value in fields.items():
            ET.SubElement(payload, f'{{{E}}}Data', Name=name).text = str(value)
        extension = ET.SubElement(row, f'{{{T}}}ExtendedTracingInfo')
        ET.SubElement(extension, f'{{{T}}}EventGuid').text = guid
        return row
    event(inspector.HEADER_GUID, 0, {'EventsLost': 0, 'BuffersLost': 0, 'StartTime': 10, 'EndTime': 20})
    for opcode in operations:
        fields={'ImageBase': '0xFFFFF80000000000',
              'ImageSize': EXPECTED['sizeOfImage'], 'ProcessId': pid, 'ImageChecksum': EXPECTED['imageChecksum'],
              'TimeDateStamp': EXPECTED['timeDateStamp'], 'FileName': EXPECTED['kernelPath']}
        if image_version==3:
            fields.update(SignatureLevel=12,SignatureType=1,Reserved0=0,DefaultBase=0,Reserved1=0,Reserved2=0,Reserved3=0,Reserved4=0)
        event(inspector.IMAGE_GUID, opcode, fields, version=image_version)
    return root


class RundownTests(unittest.TestCase):
    def inspect(self, root, expected=EXPECTED):
        with tempfile.TemporaryDirectory(prefix='sl3-rundown-unit-') as folder:
            path = Path(folder) / 'events.xml'
            ET.ElementTree(root).write(path, encoding='utf-8')
            return inspector.inspect_xml(path, expected)

    def field(self, root, name, value, row=-1):
        root[row].find(f'e:EventData/e:Data[@Name="{name}"]', inspector.NS).text = str(value)

    def test_pair_is_metadata_only(self):
        root = fixture()
        self.field(root, 'FileName', EXPECTED['kernelPath'].lower())
        result = self.inspect(root)
        self.assertTrue(result['comparison']['matchingRundownMetadata'])
        self.assertEqual(result['kernelImageOperations'], {'DCStart': 1, 'DCEnd': 1})
        for flag in ('loadedMemoryIdentityVerified', 'usbWindowQualified', 'readinessAdmission'):
            self.assertIs(result[flag], False)

    def test_missing_duplicate_reversed_and_reload_are_not_pairs(self):
        for operations in ((), (3,), (4,), (4, 3), (3, 3, 4), (3, 2, 10, 4)):
            with self.subTest(operations=operations):
                self.assertFalse(self.inspect(fixture(operations))['comparison']['matchingRundownMetadata'])

    def test_identity_disagreement_and_zero_are_not_matches(self):
        for field in ('TimeDateStamp', 'ImageChecksum', 'ImageBase', 'ImageSize'):
            root = fixture()
            self.field(root, field, 42)
            self.assertFalse(self.inspect(root)['comparison']['matchingRundownMetadata'])
        for field in ('TimeDateStamp', 'ImageChecksum'):
            root = fixture()
            for row in (1, 2):
                self.field(root, field, 0, row)
            self.assertFalse(self.inspect(root)['comparison']['matchingRundownMetadata'])
        for field in ('ImageBase', 'ImageSize'):
            root = fixture()
            self.field(root, field, 0)
            with self.assertRaisesRegex(ValueError, 'extent'):
                self.inspect(root)

    def test_non_kernel_and_lookalike_path_are_not_matches(self):
        result = self.inspect(fixture(pid=123))
        self.assertEqual(result['nonKernelImageEvents'], 2)
        self.assertFalse(result['comparison']['targetPresent'])
        root = fixture()
        for row in (1, 2):
            self.field(root, 'FileName', r'\SystemRoot\Temp\USBHUB3.SYS', row)
        self.assertFalse(self.inspect(root)['comparison']['targetPresent'])

    def test_loss_missing_header_and_invalid_window_prevent_match(self):
        for field in ('EventsLost', 'BuffersLost', 'StartTime', 'EndTime'):
            root = fixture()
            self.field(root, field, 21 if field == 'StartTime' else 1, 0)
            self.assertFalse(self.inspect(root)['comparison']['matchingRundownMetadata'])
        root = fixture()
        root.remove(root[0])
        self.assertFalse(self.inspect(root)['comparison']['matchingRundownMetadata'])

    def test_unknown_version_and_provider_are_rejected(self):
        root = fixture()
        root[-1].find('e:System/e:Version', inspector.NS).text = '4'
        with self.assertRaisesRegex(ValueError, 'version'):
            self.inspect(root)
        root = fixture()
        root[-1].find('e:System/e:Provider', inspector.NS).set('Guid', inspector.IMAGE_GUID)
        with self.assertRaisesRegex(ValueError, 'provider'):
            self.inspect(root)

    def test_version3_pair_keeps_metadata_scope(self):
        result=self.inspect(fixture(image_version=3))
        self.assertTrue(result['comparison']['matchingRundownMetadata'])
        self.assertEqual(result['imageEventVersions'],{'3':2})
        row=result['kernelImages'][0]['observations'][0]
        self.assertEqual((row['signatureLevel'],row['signatureType']),(12,1))
        self.assertFalse(result['loadedMemoryIdentityVerified'])
        self.assertFalse(result['usbWindowQualified'])
        self.assertFalse(result['readinessAdmission'])

    def test_version3_missing_extra_and_wrong_widths_reject(self):
        root=fixture(image_version=3);data=root[-1].find('e:EventData',inspector.NS)
        data.remove(data.find('e:Data[@Name="SignatureLevel"]',inspector.NS))
        with self.assertRaisesRegex(ValueError,'schema'):self.inspect(root)
        root=fixture(image_version=3);data=root[-1].find('e:EventData',inspector.NS)
        ET.SubElement(data,f'{{{E}}}Data',Name='Unexpected').text='0'
        with self.assertRaisesRegex(ValueError,'schema'):self.inspect(root)
        for name,bits in [('SignatureLevel',8),('SignatureType',8),('Reserved0',16),('DefaultBase',64),('Reserved1',32)]:
            root=fixture(image_version=3);self.field(root,name,1<<bits)
            with self.subTest(field=name),self.assertRaises(ValueError):self.inspect(root)

    def test_mixed_versions_are_not_a_consistent_pair(self):
        root=fixture(image_version=3)
        root[1].find('e:System/e:Version',inspector.NS).text='2'
        self.assertFalse(self.inspect(root)['comparison']['matchingRundownMetadata'])

    def test_version3_process_images_do_not_match_kernel(self):
        result=self.inspect(fixture(pid=123,image_version=3))
        self.assertEqual(result['nonKernelImageEvents'],2)
        self.assertFalse(result['comparison']['targetPresent'])

    def test_bad_numeric_duplicate_and_missing_properties_rejected(self):
        for value in ('-1', '0x', str(1 << 32), 'abc'):
            root = fixture()
            self.field(root, 'TimeDateStamp', value)
            with self.assertRaises(ValueError):
                self.inspect(root)
        root = fixture()
        data = root[-1].find('e:EventData', inspector.NS)
        data.append(copy.deepcopy(data[0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.inspect(root)
        root = fixture()
        data = root[-1].find('e:EventData', inspector.NS)
        data.remove(data.find('e:Data[@Name="ImageChecksum"]', inspector.NS))
        with self.assertRaisesRegex(ValueError, 'Missing'):
            self.inspect(root)

    def test_xperf_added_rsds_is_not_kernel_identity(self):
        root = fixture(())
        row = copy.deepcopy(fixture()[1])
        row.find('t:ExtendedTracingInfo/t:EventGuid', inspector.NS).text = '{b3e675d7-2554-4f18-830b-2762732560de}'
        root.append(row)
        result = self.inspect(root)
        self.assertEqual(result['imageEvents'], 0)
        self.assertFalse(result['comparison']['matchingRundownMetadata'])

    def test_dtd_and_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory(prefix='sl3-rundown-unit-') as folder:
            path = Path(folder) / 'events.xml'
            path.write_text('<!DOCTYPE Events [<!ENTITY x "bad">]><Events/>', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'DTD'):
                inspector.inspect_xml(path)
        root = fixture()
        self.field(root, 'FileName', r'\SystemRoot\System32\..\USBHUB3.SYS')
        with self.assertRaisesRegex(ValueError, 'absolute'):
            self.inspect(root)

    def test_pe_comparison_fields_and_input_bounds(self):
        raw = bytearray(512)
        raw[:2] = b'MZ'
        struct.pack_into('<I', raw, 0x3c, 64)
        raw[64:68] = b'PE\0\0'
        struct.pack_into('<H', raw, 68, 0x8664)
        struct.pack_into('<I', raw, 72, EXPECTED['timeDateStamp'])
        struct.pack_into('<H', raw, 84, 112)
        struct.pack_into('<H', raw, 88, 0x20b)
        struct.pack_into('<I4xI', raw, 144, EXPECTED['sizeOfImage'], EXPECTED['imageChecksum'])
        with tempfile.TemporaryDirectory(prefix='sl3-rundown-unit-') as folder:
            path = Path(folder) / 'USBHUB3.SYS'
            path.write_bytes(raw)
            metadata = inspector.image_metadata(path, EXPECTED['kernelPath'])
            for key in ('sizeOfImage', 'timeDateStamp', 'imageChecksum'):
                self.assertEqual(metadata[key], EXPECTED[key])
            with self.assertRaisesRegex(ValueError, 'basename'):
                inspector.image_metadata(path, r'\SystemRoot\other.sys')
            path.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'size'):
                inspector.image_metadata(path, EXPECTED['kernelPath'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
