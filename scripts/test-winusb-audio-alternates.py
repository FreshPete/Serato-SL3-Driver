"""One bounded SL3 audio-alternate activation and restoration experiment.

Selects alternate 1 on interfaces 1 then 2, queries active settings/pipes, holds
for two seconds, then restores attempted interfaces in reverse order. No audio,
interrupt transfers, vendor controls, resets or firmware operations. The parent
runner enforces a process deadline and restores the original driver/trust.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import datetime as dt
import importlib.util
import json
from pathlib import Path
import time


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run(output, probe=None):
    if probe is None:
        spec = importlib.util.spec_from_file_location('sl3_probe', Path(__file__).with_name('probe-winusb.py'))
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
    record = {'scope': __doc__, 'started_utc': utc(), 'activation_succeeded': False,
              'restoration_succeeded': False, 'operations': [], 'error': None}

    def save():
        output.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')

    def exercise(winusb, handles, Descriptor, Pipe, initial):
        winusb.WinUsb_SetCurrentAlternateSetting.argtypes = [W.HANDLE, C.c_ubyte]
        winusb.WinUsb_SetCurrentAlternateSetting.restype = W.BOOL
        record['before'] = {k: v for k, v in initial.items() if k != 'scope'}
        save()
        if initial['active_settings'] != [{'number': i, 'alternate': 0} for i in range(4)]:
            raise RuntimeError('Expected four interfaces at alternate zero; no setting changed')
        mapping = {}
        for handle in handles:
            descriptor = Descriptor()
            if not winusb.WinUsb_QueryInterfaceSettings(handle, 0, C.byref(descriptor)):
                raise C.WinError(C.get_last_error())
            if descriptor.number in mapping:
                raise RuntimeError('Duplicate interface identity; no setting changed')
            mapping[descriptor.number] = handle
        if set(mapping) != {0, 1, 2, 3}:
            raise RuntimeError('Unexpected interface identities; no setting changed')
        for number, endpoint in [(1, '0x6'), (2, '0x82')]:
            descriptors = [d for d in initial['interfaces'] if d['number'] == number and d['alternate'] == 1]
            expected = [{'id': endpoint, 'type': 1, 'max_packet': 126, 'interval': 1, 'max_bytes_per_interval': 126}]
            if len(descriptors) != 1 or descriptors[0]['pipes'] != expected:
                raise RuntimeError(f'Unexpected audio pipe fixture on interface {number}; no setting changed')

        def snapshot():
            rows = []
            for number in sorted(mapping):
                active = C.c_ubyte()
                if not winusb.WinUsb_GetCurrentAlternateSetting(mapping[number], C.byref(active)):
                    raise C.WinError(C.get_last_error())
                descriptor = Descriptor()
                if not winusb.WinUsb_QueryInterfaceSettings(mapping[number], active.value, C.byref(descriptor)):
                    raise C.WinError(C.get_last_error())
                pipes = []
                for index in range(descriptor.endpoints):
                    pipe = Pipe()
                    if not winusb.WinUsb_QueryPipeEx(mapping[number], active.value, index, C.byref(pipe)):
                        raise C.WinError(C.get_last_error())
                    pipes.append({'id': hex(pipe.id), 'type': pipe.type, 'max_packet': pipe.max_packet,
                                  'interval': pipe.interval, 'max_bytes_per_interval': pipe.max_bytes_per_interval})
                expected = [d for d in initial['interfaces'] if d['number'] == number and d['alternate'] == active.value]
                if len(expected) != 1 or pipes != expected[0]['pipes']:
                    raise RuntimeError(f'Active pipe map differs from fixture on interface {number}')
                rows.append({'number': number, 'alternate': active.value, 'pipes': pipes})
            return rows

        def select(number, alternate, phase):
            row = {'phase': phase, 'interface': number, 'alternate': alternate, 'started_utc': utc()}
            record['operations'].append(row)
            save()  # Persist intent before the state-changing call.
            ok = winusb.WinUsb_SetCurrentAlternateSetting(mapping[number], alternate)
            error = C.get_last_error() if not ok else 0
            row.update(completed_utc=utc(), succeeded=bool(ok), win32_error=error)
            save()
            if not ok:
                raise C.WinError(error)

        attempted = []
        try:
            for number in [1, 2]:
                attempted.append(number)  # Restore even if a failing call changed state.
                select(number, 1, 'activate')
                state = snapshot()
                record[f'after_interface_{number}'] = state
                expected = [0, 1, 0, 0] if number == 1 else [0, 1, 1, 0]
                if [r['alternate'] for r in state] != expected:
                    raise RuntimeError(f'Unexpected active settings after selecting interface {number}')
                save()
            record['activation_succeeded'] = True
            record['active_hold_started_utc'] = utc()
            save()
            time.sleep(2)
        finally:
            record['restoration_errors'] = []
            for number in reversed(attempted):
                try:
                    select(number, 0, 'restore')
                except (OSError, RuntimeError) as error:
                    record['restoration_errors'].append({'interface': number, 'error': str(error)})
                    save()
            try:
                record['after_restore'] = snapshot()
                record['restoration_succeeded'] = (
                    not record['restoration_errors'] and
                    [r['alternate'] for r in record['after_restore']] == [0, 0, 0, 0])
            except (OSError, RuntimeError) as error:
                record['restoration_errors'].append({'query_error': str(error)})
            save()

    save()
    try:
        probe.collect(interface_action=exercise)
    except (OSError, RuntimeError) as error:
        record['error'] = str(error)
    finally:
        record['completed_utc'] = utc()
        save()
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate', action='store_true', help='Perform the explicitly authorized setting changes')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if not args.activate:
        print(json.dumps({'action': __doc__, 'state_changes': False, 'plan_only': True}))
    else:
        if args.output.exists():
            raise SystemExit('Refusing to overwrite an existing experiment record')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result = run(args.output)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['activation_succeeded'] and result['restoration_succeeded'] and not result['error'] else 1)
