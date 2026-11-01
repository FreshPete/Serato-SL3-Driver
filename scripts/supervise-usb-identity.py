"""Plan-default supervisor for the pinned read-only USB identity observer."""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

SCRIPT = Path(__file__).with_name('observe-sl3-usb-identity.py')
spec = importlib.util.spec_from_file_location('supervised_identity', SCRIPT)
observer = importlib.util.module_from_spec(spec); spec.loader.exec_module(observer)


def run_child(command, stdout_path, stderr_path, deadline_seconds, retirement_seconds=5, on_started=None):
    """Only owns the returned direct child; never infers kernel/device recovery."""
    record = {'started': False, 'pid': None, 'exit_code': None, 'timed_out': False,
              'forced_termination': False, 'child_exited': False, 'error': None}
    start = time.monotonic()
    child = None
    try:
        with stdout_path.open('xb') as out, stderr_path.open('xb') as err:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                     shell=False, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            record.update(started=True, pid=child.pid)
            if on_started is not None:
                on_started(record)
            try:
                record['exit_code'] = child.wait(timeout=deadline_seconds)
                record['child_exited'] = True
            except subprocess.TimeoutExpired:
                record['timed_out'] = True
    except Exception as error:
        record['error'] = type(error).__name__+': '+str(error)
    finally:
        if child is not None and not record['child_exited']:
            if child.poll() is None:
                record['forced_termination'] = True
                try:
                    child.kill()
                except OSError as error:
                    record['error'] = 'Termination error: '+str(error)
            try:
                record['exit_code'] = child.wait(timeout=retirement_seconds)
                record['child_exited'] = True
            except (subprocess.TimeoutExpired, OSError) as error:
                record['error'] = 'Retirement unconfirmed: '+str(error)
        record['elapsed_seconds'] = time.monotonic()-start
    return record


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_observation(path, source_sha, duration, interval):
    require(0 < path.stat().st_size <= 4*1024*1024, 'Observation missing or exceeds size bound')
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    require(7 <= len(rows) <= 3000 and all(isinstance(r, dict) for r in rows), 'Observation row count/type')
    stamps = [datetime.fromisoformat(r['utc']) for r in rows]
    require(all(t.tzinfo is not None for t in stamps) and stamps == sorted(stamps), 'Observation timestamps')
    require([r['event'] for r in rows[:3]] == ['library_load_enter', 'context_init_enter', 'started'] and
            [r['event'] for r in rows[-3:]] == ['finished', 'context_close_enter', 'context_closed'], 'Incomplete lifecycle')
    require(rows[0]['dll_sha256'] == observer.DLL_SHA and rows[0]['observer_sha256'] == source_sha, 'Observation identity')
    header = rows[2]
    require(header['schema'] == 'sl3.usb-identity-observer.v1' and header['dll_sha256'] == observer.DLL_SHA and
            header['duration_seconds'] == duration and header['interval_seconds'] == interval, 'Observation request differs')
    body = rows[3:-3]
    require(len(body) >= 2 and len(body) % 2 == 0, 'Missing sample pairs')
    previous, elapsed, incomplete, changes = None, -1, 0, 0
    for n in range(0, len(body), 2):
        entry, sample = body[n:n+2]
        require(entry['event'] == 'snapshot_enter' and sample['event'] == 'sample', 'Missing snapshot return')
        for value in (entry['elapsed_seconds'], sample['elapsed_seconds'], sample['call_seconds']):
            require(type(value) in (int, float) and math.isfinite(value) and value >= 0, 'Invalid elapsed time')
        require(elapsed <= entry['elapsed_seconds'] <= sample['elapsed_seconds'], 'Sample order')
        elapsed = sample['elapsed_seconds']
        snapshot = sample['snapshot']
        require(type(snapshot['complete']) is bool and isinstance(snapshot['identities'], list), 'Invalid snapshot')
        require(len(snapshot['identities']) <= observer.MAX_DEVICES, 'Identity bound')
        keys = []
        for identity in snapshot['identities']:
            key = observer.identity_key(identity)
            require(all(type(v) is int for v in key) and key[:2] == (observer.VID, observer.PID) and
                    0 <= key[2] <= 65535 and all(0 <= v <= 255 for v in key[3:]), 'Invalid SL3 identity')
            keys.append(key)
        require(len(set(keys)) == len(keys), 'Duplicate identity')
        if snapshot['complete']:
            require(type(snapshot.get('descriptor_failures')) is int and snapshot['descriptor_failures'] == 0 and
                    type(snapshot.get('enumerated_devices')) is int and
                    len(keys) <= snapshot['enumerated_devices'] <= observer.MAX_DEVICES and 'error' not in snapshot,
                    'Complete snapshot contains failure or invalid counts')
        require(sample['delta'] == observer.compare(previous, snapshot), 'Delta does not match observations')
        incomplete += not snapshot['complete']
        changes += bool(sample['delta']['added'] or sample['delta']['removed'])
        previous = snapshot
    final = rows[-3]
    require(all(type(final[k]) is int and 0 <= final[k] <= 1500
                for k in ('samples', 'incomplete_samples', 'changed_comparisons')), 'Invalid summary counts')
    require(elapsed >= duration and final['samples'] == len(body)//2 and
            final['incomplete_samples'] == incomplete and final['changed_comparisons'] == changes and
            final['device_release_verified'] is False and final['application_coexistence_verified'] is False,
            'Invalid terminal observation summary')
    return {'valid': True, 'samples': final['samples'], 'incomplete_samples': incomplete,
            'changed_comparisons': changes, 'all_snapshots_complete': incomplete == 0,
            'started_utc': rows[0]['utc'], 'closed_utc': rows[-1]['utc'],
            'application_coexistence_verified': False, 'device_recovery_verified': False}


def validate_supervised_run(folder):
    folder = folder.resolve()
    record = json.loads((folder/'supervisor.json').read_text(encoding='utf-8'))
    require(record['schema'] == 'sl3.usb-identity-supervisor.v1' and record['completed'] is True and
            record['successful'] is True and record.get('error') is None and record['automatic_retry'] is False and
            record['device_recovery_verified'] is False and record['application_coexistence_verified'] is False,
            'Supervisor is incomplete, failed or overclaims scope')
    source_sha = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    require(record['observer_sha256'] == source_sha and record['dll_sha256'] == observer.DLL_SHA and
            record['supervisor_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'Supervisor source/library identities differ')
    duration, interval_ms = record['duration_seconds'], record['interval_ms']
    require(type(duration) in (int, float) and math.isfinite(duration) and 0 < duration <= 60 and
            type(interval_ms) is int and 50 <= interval_ms <= 1000, 'Invalid supervised request')
    require(record['command'] == [sys.executable, '-u', str(SCRIPT), '--run', '--output',
                                  str(folder/'observations.jsonl'), '--seconds', str(duration),
                                  '--interval-ms', str(interval_ms)] and
            record['child_deadline_seconds'] == duration+10 and record['retirement_allowance_seconds'] == 5,
            'Supervisor command or deadlines differ')
    child = record['child']
    require(child['started'] is True and type(child['pid']) is int and child['pid'] > 0 and
            child['child_exited'] is True and type(child['exit_code']) is int and child['exit_code'] == 0 and
            child['timed_out'] is False and child['forced_termination'] is False and child['error'] is None,
            'Observer process retirement failed')
    checked = validate_observation(folder/'observations.jsonl', source_sha, duration, interval_ms/1000)
    stamps = [datetime.fromisoformat(record[k]) for k in ('started_utc', 'child_started_utc', 'completed_utc')]
    require(all(t.tzinfo is not None for t in stamps) and stamps == sorted(stamps) and
            stamps[0] <= datetime.fromisoformat(checked['started_utc']) <=
            datetime.fromisoformat(checked['closed_utc']) <= stamps[-1], 'Observation outside supervisor window')
    require(checked == record['observation'] and hashlib.sha256((folder/'observations.jsonl').read_bytes()).hexdigest()
            == record['observations_sha256'], 'Saved observation/validation differs')
    return checked


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--validate', type=Path)
    ap.add_argument('--result-directory', type=Path)
    ap.add_argument('--seconds', type=float, default=5)
    ap.add_argument('--interval-ms', type=int, default=250)
    args = ap.parse_args()
    if args.validate is not None:
        print(json.dumps(validate_supervised_run(args.validate)))
        return
    if not 0 < args.seconds <= 60 or not 50 <= args.interval_ms <= 1000:
        ap.error('Use 0 < seconds <= 60 and 50 <= interval-ms <= 1000')
    deadline = args.seconds+10
    if not args.run:
        print(json.dumps({'mode': 'plan', 'loads_library': False, 'accesses_usb': False,
                          'child_deadline_seconds': deadline, 'retirement_allowance_seconds': 5,
                          'automatic_retry': False, 'observes_only': 'SL3 descriptor identity',
                          'device_recovery_verified': False}))
        return
    if args.result_directory is None:
        ap.error('--run requires a fresh --result-directory')
    require(os.name == 'nt' and observer.C.sizeof(observer.C.c_void_p) == 8, 'Requires Windows x64')
    require(hashlib.sha256(observer.DLL.read_bytes()).hexdigest() == observer.DLL_SHA, 'Installed libusb differs')
    folder = args.result_directory.resolve()
    require(not str(folder).startswith('\\\\'), 'A local result directory is required')
    folder.mkdir()  # Exclusive creation; parent must already exist.
    source_sha = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    command = [sys.executable, '-u', str(SCRIPT), '--run', '--output', str(folder/'observations.jsonl'),
               '--seconds', str(args.seconds), '--interval-ms', str(args.interval_ms)]
    record = {'schema': 'sl3.usb-identity-supervisor.v1', 'started_utc': observer.utc(), 'completed': False,
              'successful': False, 'observer_sha256': source_sha,
              'supervisor_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'dll_sha256': observer.DLL_SHA, 'command': command, 'automatic_retry': False,
              'duration_seconds': args.seconds, 'interval_ms': args.interval_ms,
              'child_deadline_seconds': deadline, 'retirement_allowance_seconds': 5,
              'device_recovery_verified': False, 'application_coexistence_verified': False}
    with (folder/'supervisor.json').open('x', encoding='utf-8') as output:
        def save():
            output.seek(0); output.write(json.dumps(record, indent=2)+'\n'); output.truncate(); output.flush()
        def started(child):
            record['child'] = child
            record['child_started_utc'] = observer.utc()
            save()
        save()
        try:
            record['child'] = run_child(command, folder/'stdout.txt', folder/'stderr.txt', deadline, on_started=started)
        except BaseException as error:
            record.update(error=type(error).__name__+': '+str(error), completed_utc=observer.utc())
            save()
            raise
        child = record['child']
        try:
            require(child['started'] and child['child_exited'] and child['exit_code'] == 0 and
                    not child['timed_out'] and not child['forced_termination'] and child['error'] is None,
                    'Observer child did not exit cleanly within deadline')
            require(hashlib.sha256(SCRIPT.read_bytes()).hexdigest() == source_sha, 'Observer source changed during run')
            record['observation'] = validate_observation(folder/'observations.jsonl', source_sha,
                                                        args.seconds, args.interval_ms/1000)
            record['observations_sha256'] = hashlib.sha256((folder/'observations.jsonl').read_bytes()).hexdigest()
            record['successful'] = True
        except Exception as error:
            record['error'] = type(error).__name__+': '+str(error)
        record.update(completed=True, completed_utc=observer.utc())
        save()
    print(json.dumps({'successful': record['successful'], 'result_directory': str(folder),
                      'child_exited': child['child_exited'], 'error': record.get('error')}))
    if not record['successful']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
