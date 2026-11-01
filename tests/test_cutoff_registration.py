"""Bounded XML projections; never loads or executes vendor/USB code."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cutoff',ROOT/'scripts/export-serato-cutoff-registration.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class ProjectionTests(unittest.TestCase):
    def padded(self,raw):return raw+b'\0'*((-len(raw))%8)

    def test_exact_block_and_zero_padded_xml(self):
        self.assertEqual(v.project(b'<root/>\n')['bounds'],'whole-block XML')
        self.assertEqual(v.project(b'<root/>\0')['bounds'],'zero-padded XML')
        self.assertEqual(v.project(b'<root/>\0')['identities'],[])

    def test_typed_nested_identity_and_no_secret_export(self):
        xml=b'<root><group><device name="SL3"><vendor_id value="0x1CC5"/><product_id value="1"/><secret_key value="PRIVATE_MARKER"/></device></group><supported_apps><app value="Serato DJ"/></supported_apps></root>'
        result=v.project(self.padded(xml));self.assertEqual(result['identities'],[{'type':'device','name':'SL3','vendor':7365,'product':1}])
        self.assertEqual(result['supportedApps'],['Serato DJ']);self.assertNotIn('PRIVATE_MARKER',repr(result))

    def test_nonzero_suffix_dtd_and_invalid_identity_refused(self):
        for raw in (b'<root/>\0'+b'X'*8,b'<!DOCTYPE root><root/>',
                    b'<root><vendor_id value="65536"/><product_id value="1"/></root>'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):v.project(self.padded(raw))


if __name__=='__main__':unittest.main()
