from pathlib import Path
import runpy
import unittest

API = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/inspect-serato-installed-profile-options.py'))


def schema(body):
    return ('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">' + body + '</xs:schema>').encode()


class InstalledProfileOptionsTest(unittest.TestCase):
    def test_inherited_element_and_attribute_are_both_seen(self):
        raw = schema('<xs:complexType name="base"><xs:sequence><xs:element name="connect_on_start"/></xs:sequence>'
                     '<xs:attribute name="driver_option"/></xs:complexType>'
                     '<xs:complexType name="midi_native_pro_device_type"><xs:complexContent><xs:extension base="base">'
                     '<xs:sequence><xs:element name="connect_on_finish_install"/></xs:sequence>'
                     '</xs:extension></xs:complexContent></xs:complexType>')
        hierarchy, elements, attributes = API['declarations'](raw)
        self.assertEqual(hierarchy, ['midi_native_pro_device_type', 'base'])
        self.assertEqual(elements, ['connect_on_start', 'connect_on_finish_install'])
        self.assertEqual(attributes, ['driver_option'])

    def test_nested_elements_are_not_mislabelled_top_level_options(self):
        raw = schema('<xs:complexType name="midi_native_pro_device_type"><xs:sequence>'
                     '<xs:element name="mapping"><xs:complexType><xs:sequence><xs:element name="auto_connect"/>'
                     '</xs:sequence></xs:complexType></xs:element></xs:sequence></xs:complexType>')
        self.assertEqual(API['declarations'](raw)[1], ['mapping'])

    def test_unknown_or_cyclic_base_is_refused(self):
        for base in ('missing', 'midi_native_pro_device_type'):
            raw = schema('<xs:complexType name="midi_native_pro_device_type"><xs:complexContent>'
                         '<xs:extension base="' + base + '"/></xs:complexContent></xs:complexType>')
            with self.subTest(base=base), self.assertRaises(ValueError): API['declarations'](raw)

    def test_unexpanded_or_duplicate_declarations_are_refused(self):
        for declaration in ('<xs:any/>', '<xs:choice/>', '<xs:group ref="other"/>',
                            '<xs:attributeGroup ref="other"/>', '<xs:anyAttribute/>',
                            '<xs:sequence><xs:element ref="other"/></xs:sequence>',
                            '<xs:sequence><xs:element name="same"/><xs:element name="same"/></xs:sequence>'):
            raw = schema('<xs:complexType name="midi_native_pro_device_type">' + declaration + '</xs:complexType>')
            with self.subTest(declaration=declaration), self.assertRaises(ValueError): API['declarations'](raw)

    def test_external_entities_size_and_wrong_root_are_refused(self):
        for raw in (b'<!DOCTYPE x><x/>', b'<!ENTITY x "y"><x/>', b'<root/>', b' ' * (16 * 1024 * 1024 + 1)):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError): API['declarations'](raw)

    def test_exact_known_external_doctype_is_removed_not_resolved(self):
        raw = API['KNOWN_DOCTYPE'] + schema('<xs:complexType name="midi_native_pro_device_type"/>')
        self.assertEqual(API['declarations'](raw), (['midi_native_pro_device_type'], [], []))
        for changed in (raw.replace(b'xhtml1-strict.dtd', b'other.dtd'), API['KNOWN_DOCTYPE'] + raw):
            with self.assertRaises(ValueError): API['declarations'](changed)

    def test_named_nested_type_is_inspected_separately(self):
        raw = schema('<xs:complexType name="device_driver_type"><xs:sequence>'
                     '<xs:element name="driver_detection"/></xs:sequence></xs:complexType>')
        self.assertEqual(API['declarations'](raw, 'device_driver_type'),
                         (['device_driver_type'], ['driver_detection'], []))

    def test_repeated_inherited_name_is_counted_without_discarding_a_type(self):
        raw = schema('<xs:complexType name="base"><xs:sequence><xs:element name="same"/></xs:sequence></xs:complexType>'
                     '<xs:complexType name="midi_native_pro_device_type"><xs:complexContent><xs:extension base="base">'
                     '<xs:sequence><xs:element name="same"/></xs:sequence></xs:extension></xs:complexContent></xs:complexType>')
        self.assertEqual(API['declarations'](raw)[1], ['same', 'same'])


if __name__ == '__main__':
    unittest.main()
