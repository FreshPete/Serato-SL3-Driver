"""Send one original-driver rate getter (0x30) and receive bounded responses.

No rate setter, status-enable, route, audio, firmware or reset request is used.
Both audio interfaces stay at zero. Pipe timeouts are restored before closing.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import datetime as dt
import importlib.util
import json
from pathlib import Path
from sl3_protocol import rate_query_frame, parse_interrupt_frame


def run(output):
    spec = importlib.util.spec_from_file_location('sl3_probe', Path(__file__).with_name('probe-winusb.py'))
    probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
    record = dict(scope=__doc__, started_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  rate_received=False, error=None, responses=[], operations=[])
    def save():
        output.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    def action(api, handles, Descriptor, Pipe, before):
        if before['active_settings'] != [dict(number=i, alternate=0) for i in range(4)]:
            raise RuntimeError('Expected all alternate settings zero; no command sent')
        control = None
        for handle in handles:
            descriptor = Descriptor()
            if not api.WinUsb_QueryInterfaceSettings(handle, 0, C.byref(descriptor)):
                raise C.WinError(C.get_last_error())
            if descriptor.number == 3: control = handle
        fixture = next(d for d in before['interfaces'] if d['number'] == 3)
        if control is None or [(p['id'], p['type'], p['max_packet']) for p in fixture['pipes']] != [('0x81', 3, 64), ('0x1', 3, 64)]:
            raise RuntimeError('Unexpected interrupt interface; no command sent')
        api.WinUsb_GetPipePolicy.argtypes = [W.HANDLE, C.c_ubyte, W.ULONG, C.POINTER(W.ULONG), C.c_void_p]
        api.WinUsb_SetPipePolicy.argtypes = [W.HANDLE, C.c_ubyte, W.ULONG, W.ULONG, C.c_void_p]
        for name in ['WinUsb_ReadPipe', 'WinUsb_WritePipe']:
            getattr(api, name).argtypes = [W.HANDLE, C.c_ubyte, C.c_void_p, W.ULONG, C.POINTER(W.ULONG), C.c_void_p]
        original = {}
        try:
            for pipe, timeout in [(0x81, 300), (0x01, 100)]:
                value = W.ULONG(); size = W.ULONG(4)
                if not api.WinUsb_GetPipePolicy(control, pipe, 3, C.byref(size), C.byref(value)):
                    raise C.WinError(C.get_last_error())
                original[pipe] = value.value
                value.value = timeout
                if not api.WinUsb_SetPipePolicy(control, pipe, 3, 4, C.byref(value)):
                    raise C.WinError(C.get_last_error())
            frame = rate_query_frame()
            sent = W.ULONG(); buffer = (C.c_ubyte * 64).from_buffer_copy(frame)
            record['query_hex'] = frame.hex()
            record['operations'].append(dict(operation='rate_query_write', utc=dt.datetime.now(dt.timezone.utc).isoformat()))
            save()
            if not api.WinUsb_WritePipe(control, 0x01, buffer, 64, C.byref(sent), None):
                raise C.WinError(C.get_last_error())
            record['written_bytes'] = sent.value; save()
            if sent.value != 64: raise RuntimeError('Short command write; stopping')
            for _ in range(4):
                received = W.ULONG(); buffer = (C.c_ubyte * 64)()
                if not api.WinUsb_ReadPipe(control, 0x81, buffer, 64, C.byref(received), None):
                    raise C.WinError(C.get_last_error())
                raw = bytes(buffer[:received.value]); decoded = parse_interrupt_frame(raw)
                record['responses'].append(dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), hex=raw.hex(), decoded=decoded)); save()
                if decoded['kind'] == 'reply':
                    if decoded['command'] != 0x30: raise RuntimeError('Unexpected reply command; stopping')
                    record['rate_hz'] = decoded['rate_hz']
                    if decoded['rate_hz'] not in [44100, 48000]: raise RuntimeError('Unexpected rate value; retain raw response')
                    record['rate_received'] = True
                    break
            if not record['rate_received']: raise RuntimeError('No rate reply within four frames; no retry or additional command')
        finally:
            record['timeout_restore_errors'] = []
            for pipe, timeout in original.items():
                value = W.ULONG(timeout)
                if not api.WinUsb_SetPipePolicy(control, pipe, 3, 4, C.byref(value)):
                    record['timeout_restore_errors'].append(dict(pipe=hex(pipe), error=C.get_last_error()))
            save()
    save()
    try: probe.collect(interface_action=action)
    except (OSError, RuntimeError, ValueError) as error: record['error'] = str(error)
    finally:
        record['completed_utc'] = dt.datetime.now(dt.timezone.utc).isoformat(); save()
    return record


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--query-rate', action='store_true'); p.add_argument('output', type=Path); args = p.parse_args()
    if not args.query_rate: print(json.dumps(dict(plan_only=True, action=__doc__)))
    else:
        if args.output.exists(): raise SystemExit('Refusing to overwrite prior query evidence')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result = run(args.output); print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['rate_received'] and not result['error'] and not result.get('timeout_restore_errors') else 1)
