"""Exercise discovery failures and evidence gaps without loading libusb or accessing USB."""
import ctypes as C
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('identity_observer', ROOT/'scripts/observe-sl3-usb-identity.py')
observer = importlib.util.module_from_spec(spec); spec.loader.exec_module(observer)


class Function:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args):
        return self.fn(*args)


class Library:
    def __init__(self):
        self.free_calls, self.exits, self.descriptor_calls = [], [], []
        self.result, self.descriptor_result, self.raise_descriptor = 2, 0, False
        self.array = (C.c_void_p*2)(101, 102)
        self.libusb_init = Function(self.init)
        self.libusb_exit = Function(lambda ctx: self.exits.append(ctx.value))
        self.libusb_get_device_list = Function(self.devices)
        self.libusb_free_device_list = Function(lambda ptr, unref: self.free_calls.append(unref))
        self.libusb_get_device_descriptor = Function(self.descriptor)
        self.libusb_get_bus_number = Function(lambda dev: 3)
        self.libusb_get_device_address = Function(lambda dev: 9)

    def init(self, context):
        C.cast(context, C.POINTER(C.c_void_p))[0] = C.c_void_p(0x123)
        return 0

    def devices(self, context, output):
        C.cast(output, C.POINTER(C.POINTER(C.c_void_p)))[0] = C.cast(self.array, C.POINTER(C.c_void_p))
        return self.result

    def descriptor(self, device, output):
        self.descriptor_calls.append(device)
        if self.raise_descriptor:
            raise RuntimeError('injected descriptor exception')
        d = C.cast(output, C.POINTER(observer.Descriptor)).contents
        d.length, d.type = 18, 1
        d.vendor = observer.VID if device == 101 else 0x1234
        d.product, d.revision = observer.PID, 0x100
        return self.descriptor_result


def identity(address=9):
    return {'vendor': observer.VID, 'product': observer.PID, 'revision': 256, 'bus': 3, 'address': address}


class UsbIdentityTests(unittest.TestCase):
    def test_filter_and_free_then_context_exit_once(self):
        lib = Library(); backend = observer.LibusbBackend(lib)
        snapshot = backend.snapshot()
        self.assertTrue(snapshot['complete'])
        self.assertEqual(snapshot['identities'], [identity()])
        self.assertEqual(lib.free_calls, [1])
        self.assertEqual(lib.descriptor_calls, [101, 102])
        backend.close(); backend.close()
        self.assertEqual(lib.exits, [0x123])
        self.assertEqual(set(vars(lib)) & set(observer.API_NAMES), set(observer.API_NAMES))

    def test_descriptor_error_makes_absence_unknown_and_frees(self):
        lib = Library(); lib.descriptor_result = -3
        backend = observer.LibusbBackend(lib)
        try:
            sample = backend.snapshot()
            self.assertFalse(sample['complete'])
            self.assertEqual(sample['descriptor_failures'], 2)
            self.assertFalse(observer.compare({'complete': True, 'identities': [identity()]}, sample)['comparable'])
        finally:
            backend.close()
        self.assertEqual(lib.free_calls, [1])

    def test_exception_still_frees_list(self):
        lib = Library(); lib.raise_descriptor = True
        backend = observer.LibusbBackend(lib)
        try:
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                backend.snapshot()
        finally:
            backend.close()
        self.assertEqual(lib.free_calls, [1]); self.assertEqual(lib.exits, [0x123])

    def test_negative_list_result_has_no_list_to_free(self):
        lib = Library(); lib.result = -4
        backend = observer.LibusbBackend(lib)
        try:
            self.assertEqual(backend.snapshot()['native_code'], -4)
        finally:
            backend.close()
        self.assertEqual(lib.free_calls, [])

    def test_failed_evidence_write_cannot_skip_context_close(self):
        lib = Library(); backend = observer.LibusbBackend(lib)
        class FailedOutput:
            def write(self, data):
                raise OSError('injected full disk')
        with self.assertRaisesRegex(OSError, 'full disk'):
            observer.observe_and_close(backend, FailedOutput(), .01, .05)
        self.assertEqual(lib.exits, [0x123])
        self.assertEqual(lib.descriptor_calls, [])

    def test_excessive_count_never_dereferences_array(self):
        lib = Library(); lib.result = observer.MAX_DEVICES+1
        backend = observer.LibusbBackend(lib)
        try:
            self.assertEqual(backend.snapshot()['error'], 'device_list_bounds')
        finally:
            backend.close()
        self.assertEqual(lib.descriptor_calls, []); self.assertEqual(lib.free_calls, [1])

    def test_address_change_is_removal_and_addition_even_with_same_vid_pid(self):
        old = {'complete': True, 'identities': [identity()]}
        new = {'complete': True, 'identities': [identity(10)]}
        self.assertEqual(observer.compare(old, new), {'comparable': True, 'added': [identity(10)], 'removed': [identity()]})
        self.assertEqual(observer.compare(old, old), {'comparable': True, 'added': [], 'removed': []})
        self.assertFalse(observer.compare({'complete': False, 'identities': []}, new)['comparable'])

    def test_observation_gap_invalidates_both_adjacent_comparisons(self):
        clock = [0.0]
        class Backend:
            def snapshot(self):
                clock[0] += 1
                return {'complete': clock[0] != 2, 'identities': [identity(int(clock[0]))]}
        output = io.StringIO()
        observer.observe(Backend(), output, 4, .05, monotonic=lambda: clock[0], sleep=lambda _: None)
        rows = [json.loads(s) for s in output.getvalue().splitlines()]
        self.assertEqual([r['delta']['comparable'] for r in rows if r['event'] == 'sample'], [False, False, False, True])
        self.assertEqual(rows[-1]['incomplete_samples'], 1)
        self.assertEqual(rows[-1]['changed_comparisons'], 1)
        self.assertFalse(rows[-1]['application_coexistence_verified'])

    def test_default_plan_never_loads_library_or_creates_output(self):
        completed = subprocess.run([sys.executable, str(ROOT/'scripts/observe-sl3-usb-identity.py')],
                                   capture_output=True, text=True, check=True)
        plan = json.loads(completed.stdout)
        self.assertEqual(plan['mode'], 'plan')
        self.assertFalse(plan['loads_library']); self.assertFalse(plan['accesses_usb'])
        self.assertTrue(plan['requires_supervisor_watchdog'])


if __name__ == '__main__':
    unittest.main()
