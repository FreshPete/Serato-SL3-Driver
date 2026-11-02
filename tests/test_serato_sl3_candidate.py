"""Offline candidate identity/shape/CLI guards and actual isolated .NET XML validation."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sl3_candidate',ROOT/'scripts/prepare-serato-sl3-candidate.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
HISTORY=json.loads((ROOT/'docs/evidence/serato-legacy-sl3-descriptors.json').read_text(encoding='utf-8'))['targets'][0]
ORDER=list(v.KEEP)+['secret_key','has_hid','handshake_type','use_legacy_portaudio','win_audio_api','win_audio_device_name',
                    'buffer_alignments','input_endpoint','output_endpoints','record_sources','driver']
SMALL=b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="root"><xs:complexType><xs:sequence><xs:element name="value" type="xs:int"/></xs:sequence></xs:complexType></xs:element></xs:schema>'

class CandidateTests(unittest.TestCase):
    def test_own_identity_historical_endpoints_and_only_empty_secret(self):
        raw=v.candidate_bytes(copy.deepcopy(HISTORY),ORDER);root=ET.fromstring(raw)
        d=root.find('native_pro_device');fields={n.tag:n.get('value') for n in d if n.get('value') is not None}
        self.assertEqual(d.get('name'),'Rane SL3')
        self.assertEqual((fields['vendor_id'],fields['product_id']),('0x1CC5','0x0001'))
        self.assertEqual(fields['handshake_type'],'HANDSHAKE_TYPE_NONE')
        self.assertEqual(fields['win_audio_device_name'],'SL3 Rebuild Development')
        self.assertEqual(fields['num_decks'],'3');self.assertEqual(fields['midi_direction'],'none')
        self.assertEqual(fields['dvs_device'],HISTORY['fields']['dvs_device'])
        self.assertEqual(fields['secret_key'],'');self.assertNotIn('secret_serato_key',fields)
        self.assertIsNone(root.find('midi'));self.assertIsNone(root.find('hid'))
        self.assertEqual([n.get('value') for n in d.findall('input_endpoint/mixer_in')],['Deck3In','Deck1In','Deck2In'])
        self.assertEqual([n.get('value') for n in d.findall('output_endpoints/mixer_out')],['Deck3Out','Deck1Out','Deck2Out'])
        self.assertEqual(d.find('buffer_alignments/buffer_alignment').get('value'),'48')
        self.assertEqual(d.find('driver/driver_detection/win_x64').get('name'),'SOFTWARE\\ASIO\\SL3 Rebuild Development')
        self.assertTrue(all(d.find('driver/driver_detection/'+p).get('name')=='' for p in ['osx','win_x86']))
        for omitted in ['has_faders','platter_resolution','provides_software_through']:self.assertNotIn(omitted,fields)

    def test_identity_capability_secret_and_mapping_mutations_refused(self):
        for key,value in [('vendor_id','0x1234'),('product_id','0x0002'),('handshake_type','HANDSHAKE_TYPE_SERATO_DJ_HID'),
                          ('midi_direction','duplex'),('requires_usb','false'),('sample_rate','HZ44100'),('num_decks','2'),('dvs_device','DVS_DEVICE_NO')]:
            changed=copy.deepcopy(HISTORY);changed['fields'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.candidate_bytes(changed,ORDER)
        for change in ['secret','input','output','alignment']:
            h=copy.deepcopy(HISTORY)
            if change=='secret':h['resource']['deviceSecretFieldEmpty']=False
            if change=='input':h['inputsInDeclaredOrder'].reverse()
            if change=='output':h['outputsInDeclaredOrder'].reverse()
            if change=='alignment':h['bufferAlignments'][0]['values']=['128']
            with self.subTest(change=change),self.assertRaises(ValueError):v.candidate_bytes(h,ORDER)

    def test_schema_sequence_required_and_deterministic(self):
        first=v.candidate_bytes(HISTORY,ORDER);self.assertEqual(first,v.candidate_bytes(copy.deepcopy(HISTORY),ORDER))
        with self.assertRaises(ValueError):v.candidate_bytes(HISTORY,['vendor_id'])
        schema=b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:complexType name="base"><xs:sequence><xs:element name="first"/></xs:sequence></xs:complexType><xs:complexType name="midi_native_pro_device_type"><xs:complexContent><xs:extension base="base"><xs:sequence><xs:element name="second"/></xs:sequence></xs:extension></xs:complexContent></xs:complexType></xs:schema>'
        self.assertEqual(v.schema_device_order(schema),['first','second'])
        with self.assertRaises(ValueError):v.schema_device_order(schema.replace(b'base="base"',b'base="midi_native_pro_device_type"'))
        with self.assertRaises(ValueError):v.schema_device_order(b'<!ENTITY bad "x">'+schema)

    def test_manifest_keeps_hypothesis_and_physical_deployment_false(self):
        context={'history':HISTORY,'currentApplicationSha256':'a'*64,'pins':{},'contracts':{},'nativeBuildInputPinsVerified':146,'schemaMetadata':{}}
        value=v.manifest(context,v.candidate_bytes(HISTORY,ORDER),{'valid':True})
        self.assertEqual(value['status'],'offline_hypothesis')
        for key in ['applicationExecuted','applicationModified','archiveModified','providerInstalled','descriptorRegistered',
                    'driverInstalled','deviceAccess','audioPlayed','firmwareModified','accountOrEntitlementModified',
                    'currentSeratoAdmissionVerified','twoDeckDvsVerified','deploymentApproved','schemaAcceptanceIsApplicationAcceptance']:
            self.assertFalse(value[key],key)
        self.assertIn('hypothesis',value['intentionalChanges']['handshake_type']['status'].lower())
        self.assertEqual(sorted(c for pair in value['logicalMaps']['input'].values() for c in pair),list(range(6)))

    def test_location_and_existing_output_refused_before_loading_sources(self):
        tmp=tempfile.TemporaryDirectory(prefix='sl3-candidate-test-');folder=Path(tmp.name).resolve()
        self.assertEqual(folder.parent,Path(tempfile.gettempdir()).resolve());self.assertTrue(folder.name.startswith('sl3-candidate-test-'));self.addCleanup(tmp.cleanup)
        (folder/'analysis').mkdir();target=folder/'analysis/sl3-descriptor-candidate-existing';target.mkdir();sentinel=target/'keep';sentinel.write_bytes(b'keep')
        with patch.object(v,'ROOT',folder),patch.object(v,'source_context',side_effect=AssertionError('must not read sources')):
            with patch.object(sys,'argv',['candidate','--prepare',str(target)]),self.assertRaises(ValueError):v.main()
            for bad in [folder/'elsewhere',folder/'analysis/not-a-candidate',target/'nested']:
                with self.assertRaises(ValueError):v.location(bad)
        self.assertEqual(sentinel.read_bytes(),b'keep')

    def test_strict_manifest_json(self):
        for raw in [b'{"a":1,"a":2}',b'{"a":NaN}',b'[]']:
            with self.assertRaises(ValueError):v.parsed(raw)

class ActualSchemaTests(unittest.TestCase):
    def test_framework_accepts_valid_xml_rejects_wrong_value_and_xml_dtd(self):
        result=v.validate_schema(b'<root><value>12</value></root>',SMALL)
        self.assertTrue(result['valid']);self.assertFalse(result['externalResolution']);self.assertFalse(result['knownSchemaDtdIgnored'])
        for raw in [b'<root><value>not-an-integer</value></root>',b'<!DOCTYPE root [<!ENTITY x "12">]><root><value>&x;</value></root>']:
            with self.subTest(xml=raw),self.assertRaises(ValueError):v.validate_schema(raw,SMALL)

    def test_external_schema_include_and_unknown_schema_dtd_refused(self):
        for schema in [SMALL.replace(b'<xs:element name="root">',b'<xs:include schemaLocation="https://example.invalid/never-fetch.xsd"/><xs:element name="root">'),
                       b'<!DOCTYPE xs:schema SYSTEM "https://example.invalid/never-fetch.dtd">'+SMALL]:
            with self.subTest(schema=schema[:80]),self.assertRaises(ValueError):v.validate_schema(b'<root><value>1</value></root>',schema)

if __name__=='__main__':unittest.main()
