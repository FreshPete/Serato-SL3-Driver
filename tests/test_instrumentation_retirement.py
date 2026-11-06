import runpy
from pathlib import Path
import unittest
from types import SimpleNamespace

API = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/run-serato-startup-session.py'))


class RetirementTests(unittest.TestCase):
    def backend(self, failure=None):
        calls = []
        def operation(name):
            def invoke():
                calls.append(name)
                if failure == name: raise ValueError(name + ' failed')
            return invoke
        backend = API['WindowsProcess'].__new__(API['WindowsProcess'])
        backend.script = type('Script', (), {'unload': staticmethod(operation('script'))})()
        backend.session = type('Session', (), {'detach': staticmethod(operation('session'))})()
        backend.manager = type('Manager', (), {'close': staticmethod(operation('manager'))})()
        backend.manager_closed = False; backend.device = object()
        return backend, calls

    def test_unload_detach_close_order_and_idempotence(self):
        backend, calls = self.backend(); backend.detach(); backend.detach()
        self.assertEqual(calls, ['script', 'session', 'manager'])
        self.assertTrue(backend.manager_closed); self.assertIsNone(backend.device)

    def test_script_failure_still_attempts_session_and_manager(self):
        backend, calls = self.backend('script')
        with self.assertRaisesRegex(RuntimeError, 'script failed'): backend.detach()
        self.assertEqual(calls, ['script', 'session', 'manager']); self.assertTrue(backend.manager_closed)
        self.assertIsNotNone(backend.script)

    def test_session_failure_still_attempts_manager(self):
        backend, calls = self.backend('session')
        with self.assertRaisesRegex(RuntimeError, 'session failed'): backend.detach()
        self.assertEqual(calls, ['script', 'session', 'manager']); self.assertTrue(backend.manager_closed)

    def test_manager_failure_does_not_claim_retirement(self):
        backend, calls = self.backend('manager')
        with self.assertRaisesRegex(RuntimeError, 'manager failed'): backend.detach()
        self.assertFalse(backend.manager_closed); self.assertIsNotNone(backend.device)

    def test_all_failures_are_retained(self):
        backend, calls = self.backend()
        def fail(): raise ValueError('stage failed')
        backend.script.unload = backend.session.detach = backend.manager.close = fail
        with self.assertRaises(RuntimeError) as caught: backend.detach()
        self.assertEqual(str(caught.exception).count('stage failed'), 3)
        self.assertFalse(backend.manager_closed)

    def test_device_acquisition_failure_closes_the_owned_manager(self):
        calls = []
        def get_device(): calls.append('device'); raise ValueError('device unavailable')
        manager = SimpleNamespace(get_local_device=get_device, close=lambda: calls.append('close'))
        frida = SimpleNamespace(DeviceManager=lambda: manager)
        with self.assertRaisesRegex(ValueError, 'device unavailable'):
            API['WindowsProcess'](Path('fixture.exe'), frida)
        self.assertEqual(calls, ['device', 'close'])

    def test_constructor_preserves_primary_error_and_cleanup_note(self):
        def get_device(): raise ValueError('primary device error')
        def close(): raise RuntimeError('close error')
        frida = SimpleNamespace(DeviceManager=lambda: SimpleNamespace(get_local_device=get_device, close=close))
        with self.assertRaisesRegex(ValueError, 'primary device error') as caught:
            API['WindowsProcess'](Path('fixture.exe'), frida)
        self.assertTrue(any('close error' in note for note in caught.exception.__notes__))


if __name__ == '__main__': unittest.main()
