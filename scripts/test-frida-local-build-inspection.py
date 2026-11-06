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
                  'frida-gum:tests': 'disabled', 'frida-gum:quickjs': 'enabled', 'frida-gum:v8': 'disabled'}
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


class HeaderPatchTests(unittest.TestCase):
    def setUp(self):
        self.original = b'#include "old.h"\n\nvoid f(void) {}\n'
        self.patched = b'#include "old.h"\n\n#include "new.h"\n\nvoid f(void) {}\n'

    def verify(self, actual):
        API['verify_header_change'](self.original, actual, '#include "old.h"', 'new.h')

    def test_exact_include_allowed(self):
        self.verify(self.patched)

    def test_crlf_checkout_allowed(self):
        self.verify(self.patched.replace(b'\n', b'\r\n'))

    def test_unrelated_code_edit_rejected(self):
        with self.assertRaises(ValueError): self.verify(self.patched.replace(b'f(void)', b'g(void)'))

    def test_wrong_header_rejected(self):
        with self.assertRaises(ValueError): self.verify(self.patched.replace(b'new.h', b'guess.h'))

    def test_unpatched_content_rejected(self):
        with self.assertRaises(ValueError): self.verify(self.original)

    def test_ambiguous_anchor_rejected(self):
        for original in (b'void f(void) {}\n', self.original + self.original):
            with self.subTest(original=original), self.assertRaises(ValueError):
                API['expected_header_change'](original, '#include "old.h"', 'new.h')


class AgentDeclarationTests(unittest.TestCase):
    def setUp(self):
        self.original = API['AGENT_ANCHOR'] + b'\nvoid body(void) {}\n'
        self.patched = self.original.replace(API['AGENT_ANCHOR'], API['AGENT_ANCHOR'] + API['AGENT_DECLARATIONS'])

    def test_exact_declarations_allowed(self):
        API['verify_agent_change'](self.original, self.patched)

    def test_guessed_return_type_rejected(self):
        with self.assertRaises(ValueError):
            API['verify_agent_change'](self.original, self.patched.replace(b'void frida_libc', b'int frida_libc'))

    def test_function_body_change_rejected(self):
        with self.assertRaises(ValueError):
            API['verify_agent_change'](self.original, self.patched.replace(b'body(void)', b'body(int x)'))

    def test_missing_anchor_rejected(self):
        with self.assertRaises(ValueError): API['verify_agent_change'](b'void body(void) {}\n', self.patched)


class TlsPatchTests(unittest.TestCase):
    def setUp(self):
        self.original = b'void f(void) {\n' + API['TLS_ANCHOR'] + b'}\n'
        self.patched = self.original.replace(API['TLS_ANCHOR'], API['TLS_REPLACEMENT'])

    def test_exact_clang_store_allowed(self):
        API['verify_tls_change'](self.original, self.patched)

    def test_wrong_segment_rejected(self):
        with self.assertRaises(ValueError):
            API['verify_tls_change'](self.original, self.patched.replace(b'256', b'257'))

    def test_changed_offset_rejected(self):
        with self.assertRaises(ValueError):
            API['verify_tls_change'](self.original, self.patched.replace(b'0x1480', b'0x1490'))

    def test_removed_msvc_path_rejected(self):
        with self.assertRaises(ValueError):
            API['verify_tls_change'](self.original, self.patched.replace(API['TLS_ANCHOR'], b''))


if __name__ == '__main__':
    unittest.main()
