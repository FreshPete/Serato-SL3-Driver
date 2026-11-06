"""Reject backend/configuration drift without loading Frida or a PE image."""
import copy
from pathlib import Path
import runpy
import unittest

API = runpy.run_path(str(Path(__file__).with_name('inspect-frida-local-build.py')))
CHECK = API['check_configuration']


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        values = {'frida_python': 'enabled', 'frida-core:local_backend': 'enabled',
                  'frida-core:compat': ['disabled'], 'frida-core:tests': 'disabled',
                  'frida-gum:tests': 'disabled'}
        values.update({x: 'disabled' for x in ('frida_tools', 'frida_node', 'frida_net',
                      'frida_swift', 'frida_qml', 'server', 'portal', 'gadget', 'inject', 'graft_tool')})
        values.update({'frida-core:' + x + '_backend': 'disabled' for x in
                       ('fruity', 'droidy', 'socket', 'simmy', 'barebone', 'compiler')})
        self.options = [{'name': name, 'value': value} for name, value in values.items()]
        self.targets = [{'name': '_frida', 'filename': ['subprojects/frida-python/frida/_frida.pyd']}]
        self.ninja = 'vala --define=HAVE_LOCAL_BACKEND'

    def test_expected_configuration(self):
        self.assertEqual(CHECK(self.options, self.targets, self.ninja)['frida-core:local_backend'], 'enabled')

    def test_every_required_option_rejects_drift(self):
        for index, item in enumerate(self.options):
            with self.subTest(option=item['name']):
                changed = copy.deepcopy(self.options)
                changed[index]['value'] = 'auto'
                with self.assertRaises(ValueError): CHECK(changed, self.targets, self.ninja)

    def test_missing_option(self):
        with self.assertRaises(ValueError): CHECK(self.options[1:], self.targets, self.ninja)

    def test_idun_target_rejected(self):
        with self.assertRaises(ValueError): CHECK(self.options, self.targets + [{'name': 'idund-blob'}], self.ninja)

    def test_idun_dependency_rejected(self):
        with self.assertRaises(ValueError): CHECK(self.options, self.targets, self.ninja + '\nbuild helper: idun')

    def test_each_nonlocal_flag_rejected(self):
        for backend in ('FRUITY', 'DROIDY', 'SOCKET', 'SIMMY', 'BAREBONE', 'COMPILER'):
            with self.subTest(backend=backend), self.assertRaises(ValueError):
                CHECK(self.options, self.targets, self.ninja + ' HAVE_' + backend + '_BACKEND')

    def test_local_flag_required(self):
        with self.assertRaises(ValueError): CHECK(self.options, self.targets, '')

    def test_binding_target_required(self):
        with self.assertRaises(ValueError): CHECK(self.options, [], self.ninja)


if __name__ == '__main__':
    unittest.main()
