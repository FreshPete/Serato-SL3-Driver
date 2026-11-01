"""Fault injection for state-change recovery; never accesses USB hardware."""
import ctypes as C
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
import sys
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('alternate_test', Path(__file__).parents[1] / 'scripts/test-winusb-audio-alternates.py')
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


class Descriptor(C.Structure):
    _fields_ = [('number', C.c_ubyte), ('endpoints', C.c_ubyte)]


class Pipe(C.Structure):
    _fields_ = [('id', C.c_ubyte), ('type', C.c_int), ('max_packet', C.c_ushort),
                ('interval', C.c_ubyte), ('max_bytes_per_interval', C.c_ulong)]


class NativeCall:
    def __init__(self, function):
        self.function = function

    def __call__(self, *args):
        return self.function(*args)


class FakeProbe:
    def __init__(self, fail_second=False, bad_fixture=False):
        self.state = [0, 0, 0, 0]
        self.calls = []
        self.fail_second = fail_second
        self.bad_fixture = bad_fixture

    def pipe(self, number, alternate):
        if alternate == 1 and number in [1, 2]:
            return [dict(id='0x6' if number == 1 else '0x82', type=1, max_packet=126,
                         interval=1, max_bytes_per_interval=126)]
        return []

    def collect(self, interface_action):
        def descriptor(number, alternate, pointer):
            row = C.cast(pointer, C.POINTER(Descriptor)).contents
            row.number = number
            row.endpoints = len(self.pipe(number, alternate))
            return True

        def active(number, pointer):
            C.cast(pointer, C.POINTER(C.c_ubyte)).contents.value = self.state[number]
            return True

        def pipe(number, alternate, index, pointer):
            value = self.pipe(number, alternate)[index]
            row = C.cast(pointer, C.POINTER(Pipe)).contents
            for key, val in value.items():
                setattr(row, key, int(val, 16) if key == 'id' else val)
            return True

        def select(number, alternate):
            self.calls.append((number, alternate))
            # Simulate a partial state change followed by API failure. Cleanup
            # must restore this attempted interface as well as the earlier one.
            self.state[number] = alternate
            if self.fail_second and number == 2 and alternate == 1:
                C.set_last_error(31)
                return False
            return True

        native = types.SimpleNamespace(
            WinUsb_SetCurrentAlternateSetting=NativeCall(select),
            WinUsb_QueryInterfaceSettings=NativeCall(descriptor),
            WinUsb_GetCurrentAlternateSetting=NativeCall(active),
            WinUsb_QueryPipeEx=NativeCall(pipe))
        interfaces = [dict(number=n, alternate=a, pipes=self.pipe(n, a))
                      for n in range(4) for a in ([0, 1] if n in [1, 2] else [0])]
        if self.bad_fixture:
            interfaces[2]['pipes'][0]['max_packet'] = 127
        initial = {'active_settings': [dict(number=n, alternate=0) for n in range(4)], 'interfaces': interfaces}
        interface_action(native, list(range(4)), Descriptor, Pipe, initial)


@unittest.skipUnless(sys.platform == 'win32', 'Windows ctypes error handling')
class RecoveryTests(unittest.TestCase):
    def exercise(self, fake):
        with tempfile.TemporaryDirectory() as directory, patch.object(experiment.time, 'sleep'):
            output = Path(directory) / 'record.json'
            result = experiment.run(output, probe=fake)
            self.assertEqual(json.loads(output.read_text()), result)
            return result

    def test_success_activates_then_restores_in_reverse(self):
        fake = FakeProbe()
        result = self.exercise(fake)
        self.assertTrue(result['activation_succeeded'])
        self.assertTrue(result['restoration_succeeded'])
        self.assertEqual(fake.calls, [(1, 1), (2, 1), (2, 0), (1, 0)])

    def test_failed_second_activation_restores_both_attempted_interfaces(self):
        fake = FakeProbe(fail_second=True)
        result = self.exercise(fake)
        self.assertFalse(result['activation_succeeded'])
        self.assertTrue(result['restoration_succeeded'])
        self.assertIsNotNone(result['error'])
        self.assertEqual(fake.state, [0, 0, 0, 0])
        self.assertEqual(fake.calls, [(1, 1), (2, 1), (2, 0), (1, 0)])

    def test_unexpected_fixture_prevents_every_state_change(self):
        fake = FakeProbe(bad_fixture=True)
        result = self.exercise(fake)
        self.assertIsNotNone(result['error'])
        self.assertEqual(fake.calls, [])


if __name__ == '__main__':
    unittest.main()
