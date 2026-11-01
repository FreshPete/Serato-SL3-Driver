"""Plan by default; opt-in read-only SL3 identity observation using pinned libusb.

No open, claim, control or transfer API is bound. A process watchdog is still
required by a supervising device-test runner: synchronous library calls can hang.
"""
import argparse
import ctypes as C
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

DLL = Path('C:/Program Files/Serato/Serato DJ Pro/libusb-1.0.dll')
DLL_SHA = '68883bc3254dbb4129cf68b49f9efe149cd50fd15e990c58a94a53d3ed4f7151'
VID, PID = 0x1cc5, 0x0001
MAX_DEVICES = 4096
API_NAMES = ('libusb_init', 'libusb_exit', 'libusb_get_device_list', 'libusb_free_device_list',
             'libusb_get_device_descriptor', 'libusb_get_bus_number', 'libusb_get_device_address')


class Descriptor(C.Structure):
    _fields_ = [('length', C.c_uint8), ('type', C.c_uint8), ('usb', C.c_uint16),
                ('device_class', C.c_uint8), ('subclass', C.c_uint8), ('protocol', C.c_uint8),
                ('max_packet', C.c_uint8), ('vendor', C.c_uint16), ('product', C.c_uint16),
                ('revision', C.c_uint16), ('manufacturer', C.c_uint8), ('product_string', C.c_uint8),
                ('serial_string', C.c_uint8), ('configurations', C.c_uint8)]


assert C.sizeof(Descriptor) == 18
assert (Descriptor.vendor.offset, Descriptor.product.offset, Descriptor.revision.offset) == (8, 10, 12)


class LibusbBackend:
    def __init__(self, library):
        self.library = library
        signatures = {
            'libusb_init': ([C.POINTER(C.c_void_p)], C.c_int),
            'libusb_exit': ([C.c_void_p], None),
            'libusb_get_device_list': ([C.c_void_p, C.POINTER(C.POINTER(C.c_void_p))], C.c_ssize_t),
            'libusb_free_device_list': ([C.POINTER(C.c_void_p), C.c_int], None),
            'libusb_get_device_descriptor': ([C.c_void_p, C.POINTER(Descriptor)], C.c_int),
            'libusb_get_bus_number': ([C.c_void_p], C.c_uint8),
            'libusb_get_device_address': ([C.c_void_p], C.c_uint8)}
        for name, (args, result) in signatures.items():
            function = getattr(library, name)
            function.argtypes, function.restype = args, result
        self.context = C.c_void_p()
        result = library.libusb_init(C.byref(self.context))
        if result != 0:
            raise RuntimeError(f'libusb_init failed: {result}')
        self.initialized = True

    def close(self):
        if self.initialized:
            self.initialized = False
            self.library.libusb_exit(self.context)

    def snapshot(self):
        devices = C.POINTER(C.c_void_p)()
        count = self.library.libusb_get_device_list(self.context, C.byref(devices))
        if count < 0:
            return {'complete': False, 'identities': [], 'error': 'device_list', 'native_code': count}
        try:
            if count > MAX_DEVICES or (count and not devices):
                return {'complete': False, 'identities': [], 'error': 'device_list_bounds'}
            identities, failures = [], 0
            for n in range(count):
                device = devices[n]
                if not device:
                    failures += 1
                    continue
                descriptor = Descriptor()
                result = self.library.libusb_get_device_descriptor(device, C.byref(descriptor))
                if result != 0 or descriptor.length != 18 or descriptor.type != 1:
                    failures += 1
                    continue
                if (descriptor.vendor, descriptor.product) != (VID, PID):
                    continue
                identities.append({'vendor': descriptor.vendor, 'product': descriptor.product,
                                   'revision': descriptor.revision,
                                   'bus': int(self.library.libusb_get_bus_number(device)),
                                   'address': int(self.library.libusb_get_device_address(device))})
            identities.sort(key=identity_key)
            return {'complete': failures == 0, 'identities': identities,
                    'descriptor_failures': failures, 'enumerated_devices': count}
        finally:
            self.library.libusb_free_device_list(devices, 1)


def identity_key(record):
    # Values match the fields in Serato's key; no assumption about its exact hex formatting.
    return tuple(record[k] for k in ('vendor', 'product', 'revision', 'bus', 'address'))


def compare(previous, current):
    if previous is None or not previous['complete'] or not current['complete']:
        return {'comparable': False, 'added': [], 'removed': []}
    old = {identity_key(r): r for r in previous['identities']}
    new = {identity_key(r): r for r in current['identities']}
    return {'comparable': True, 'added': [new[k] for k in sorted(new.keys()-old.keys())],
            'removed': [old[k] for k in sorted(old.keys()-new.keys())]}


def utc():
    return datetime.now(timezone.utc).isoformat()


def emit(output, row):
    output.write(json.dumps(row, separators=(',', ':'))+'\n')
    output.flush()


def observe(backend, output, duration, interval, monotonic=time.monotonic, sleep=time.sleep):
    start = monotonic()
    previous = None
    samples, incomplete, changes = 0, 0, 0

    emit(output, {'schema': 'sl3.usb-identity-observer.v1', 'event': 'started', 'utc': utc(),
          'dll_sha256': DLL_SHA, 'duration_seconds': duration, 'interval_seconds': interval,
          'scope': 'Descriptor identity only; no device open or transfers'})
    while True:
        entered = monotonic()
        emit(output, {'event': 'snapshot_enter', 'utc': utc(), 'elapsed_seconds': entered-start})
        sample = backend.snapshot()
        elapsed = monotonic()-start
        delta = compare(previous, sample)
        samples += 1
        incomplete += not sample['complete']
        changes += bool(delta['added'] or delta['removed'])
        emit(output, {'event': 'sample', 'utc': utc(), 'elapsed_seconds': elapsed,
              'call_seconds': monotonic()-entered, 'snapshot': sample, 'delta': delta})
        previous = sample  # Any incomplete sample also invalidates the next comparison.
        if elapsed >= duration:
            break
        sleep(min(interval, duration-elapsed))
    emit(output, {'event': 'finished', 'utc': utc(), 'samples': samples, 'incomplete_samples': incomplete,
          'changed_comparisons': changes, 'device_release_verified': False,
          'application_coexistence_verified': False})


def observe_and_close(backend, output, duration, interval):
    try:
        observe(backend, output, duration, interval)
    finally:
        try:
            emit(output, {'event': 'context_close_enter', 'utc': utc()})
        finally:
            backend.close()
        emit(output, {'event': 'context_closed', 'utc': utc()})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', action='store_true')
    ap.add_argument('--output', type=Path)
    ap.add_argument('--seconds', type=float, default=5)
    ap.add_argument('--interval-ms', type=int, default=250)
    args = ap.parse_args()
    if not 0 < args.seconds <= 60 or not 50 <= args.interval_ms <= 1000:
        ap.error('Use 0 < seconds <= 60 and 50 <= interval-ms <= 1000')
    if not args.run:
        print(json.dumps({'mode': 'plan', 'loads_library': False, 'accesses_usb': False,
                          'dll': str(DLL), 'dll_sha256': DLL_SHA, 'bound_functions': API_NAMES,
                          'duration_seconds': args.seconds, 'interval_ms': args.interval_ms,
                          'requires_supervisor_watchdog': True}))
        return
    if not args.output:
        ap.error('--run requires --output; parent directory must already exist')
    if os.name != 'nt' or C.sizeof(C.c_void_p) != 8:
        raise RuntimeError('Requires Windows x64')
    if hashlib.sha256(DLL.read_bytes()).hexdigest() != DLL_SHA:
        raise RuntimeError('Installed libusb identity differs')
    # Reserve before loading vendor code; preserve partial records and refuse overwrite.
    with args.output.open('x', encoding='utf-8') as output:
        emit(output, {'event': 'library_load_enter', 'utc': utc(), 'dll_sha256': DLL_SHA,
                      'observer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
        with os.add_dll_directory(str(DLL.parent)):
            library = C.CDLL(str(DLL), winmode=0x1100)
            emit(output, {'event': 'context_init_enter', 'utc': utc()})
            backend = LibusbBackend(library)
            observe_and_close(backend, output, args.seconds, args.interval_ms/1000)


if __name__ == '__main__':
    main()
