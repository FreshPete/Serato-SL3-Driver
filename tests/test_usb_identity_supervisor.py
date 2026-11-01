"""Real harmless child-process containment and synthetic observer evidence checks."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('identity_supervisor', ROOT/'scripts/supervise-usb-identity.py')
supervisor = importlib.util.module_from_spec(spec); spec.loader.exec_module(supervisor)


class IdentitySupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def run_child(self, program, deadline=3):
        return supervisor.run_child([sys.executable, '-u', '-c', program],
                                    self.folder/'out.txt', self.folder/'err.txt', deadline, retirement_seconds=2)

    def test_real_clean_child(self):
        record = self.run_child("print('harmless process fixture')")
        self.assertTrue(record['started']); self.assertTrue(record['child_exited'])
        self.assertEqual(record['exit_code'], 0); self.assertFalse(record['timed_out'])
        self.assertFalse(record['forced_termination'])
        self.assertIn('harmless process fixture', (self.folder/'out.txt').read_text())

    def test_real_stalled_child_is_retired(self):
        record = self.run_child("import time; print('fixture waiting',flush=True); time.sleep(30)", deadline=.7)
        self.assertTrue(record['timed_out']); self.assertTrue(record['forced_termination'])
        self.assertTrue(record['child_exited']); self.assertIsNotNone(record['exit_code'])
        self.assertNotEqual(record['exit_code'], 0)
        self.assertIn('fixture waiting', (self.folder/'out.txt').read_text())

    def test_nonzero_exit_is_preserved(self):
        record = self.run_child('raise SystemExit(7)')
        self.assertEqual(record['exit_code'], 7); self.assertTrue(record['child_exited'])
        self.assertFalse(record['forced_termination'])

    def test_existing_log_refuses_launch(self):
        (self.folder/'out.txt').write_text('preserve')
        with patch.object(supervisor.subprocess, 'Popen') as launch:
            record = self.run_child('raise SystemExit(0)')
            launch.assert_not_called()
        self.assertFalse(record['started']); self.assertIn('FileExistsError', record['error'])
        self.assertEqual((self.folder/'out.txt').read_text(), 'preserve')

    def test_failed_kill_cannot_claim_retirement(self):
        class StalledChild:
            pid = 12345
            def wait(self, timeout):
                raise subprocess.TimeoutExpired('synthetic blocked child', timeout)
            def poll(self):
                return None
            def kill(self):
                raise OSError('injected denial')
        with patch.object(supervisor.subprocess, 'Popen', return_value=StalledChild()):
            record = self.run_child('unused')
        self.assertTrue(record['timed_out']); self.assertTrue(record['forced_termination'])
        self.assertFalse(record['child_exited']); self.assertIsNone(record['exit_code'])
        self.assertIn('Retirement unconfirmed', record['error'])

    def test_failed_pid_journal_callback_still_retires_child(self):
        started = []
        def fail_after_recording(record):
            started.append(record['pid'])
            raise OSError('injected journal write failure')
        record = supervisor.run_child([sys.executable, '-c', 'import time; time.sleep(30)'],
                                      self.folder/'out.txt', self.folder/'err.txt', 3, on_started=fail_after_recording)
        self.assertEqual(started, [record['pid']]); self.assertTrue(record['child_exited'])
        self.assertTrue(record['forced_termination']); self.assertIn('journal write failure', record['error'])

    def observation(self):
        rows = [
            {'event': 'library_load_enter', 'dll_sha256': supervisor.observer.DLL_SHA, 'observer_sha256': 'a'*64},
            {'event': 'context_init_enter'},
            {'event': 'started', 'schema': 'sl3.usb-identity-observer.v1',
             'dll_sha256': supervisor.observer.DLL_SHA, 'duration_seconds': .01, 'interval_seconds': .05},
            {'event': 'snapshot_enter', 'elapsed_seconds': 0},
            {'event': 'sample', 'elapsed_seconds': .01, 'call_seconds': .01,
             'snapshot': {'complete': True, 'identities': [], 'descriptor_failures': 0, 'enumerated_devices': 0},
             'delta': {'comparable': False, 'added': [], 'removed': []}},
            {'event': 'finished', 'samples': 1, 'incomplete_samples': 0, 'changed_comparisons': 0,
             'device_release_verified': False, 'application_coexistence_verified': False},
            {'event': 'context_close_enter'}, {'event': 'context_closed'}]
        for row in rows:
            row['utc'] = '2026-10-30T23:00:00+00:00'
        return rows

    def validate(self, rows):
        path = self.folder/'fixture.jsonl'
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
        return supervisor.validate_observation(path, 'a'*64, .01, .05)

    def test_complete_empty_observation_is_not_hardware_readiness(self):
        result = self.validate(self.observation())
        self.assertTrue(result['valid']); self.assertTrue(result['all_snapshots_complete'])
        self.assertFalse(result['device_recovery_verified']); self.assertFalse(result['application_coexistence_verified'])

    def test_missing_terminal_or_forged_claims_rejected(self):
        rows = self.observation()
        with self.assertRaises(ValueError):
            self.validate(rows[:-1])
        mutations = [
            (0, 'observer_sha256', 'b'*64), (5, 'samples', 2),
            (5, 'samples', True),
            (5, 'application_coexistence_verified', True), (5, 'device_release_verified', True),
            (4, 'elapsed_seconds', float('nan'))]
        for index, key, value in mutations:
            with self.subTest(key=key):
                changed = copy.deepcopy(rows); changed[index][key] = value
                with self.assertRaises(ValueError):
                    self.validate(changed)

    def test_false_delta_and_complete_snapshot_with_errors_rejected(self):
        rows = self.observation(); rows[4]['delta']['comparable'] = True
        with self.assertRaises(ValueError):
            self.validate(rows)
        rows = self.observation(); rows[4]['snapshot']['descriptor_failures'] = 1
        with self.assertRaises(ValueError):
            self.validate(rows)

    def test_default_plan_does_not_create_directory_or_load_libusb(self):
        folder = self.folder/'not-created'
        result = subprocess.run([sys.executable, str(ROOT/'scripts/supervise-usb-identity.py'),
                                 '--result-directory', str(folder)], capture_output=True, text=True, check=True)
        plan = json.loads(result.stdout)
        self.assertEqual(plan['mode'], 'plan'); self.assertFalse(plan['loads_library'])
        self.assertFalse(plan['accesses_usb']); self.assertFalse(folder.exists())

    def supervised_fixture(self):
        source_sha = hashlib.sha256(supervisor.SCRIPT.read_bytes()).hexdigest()
        rows = self.observation(); rows[0]['observer_sha256'] = source_sha
        path = self.folder/'observations.jsonl'
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
        checked = supervisor.validate_observation(path, source_sha, .01, .05)
        stamp = '2026-10-30T23:00:00+00:00'
        record = {'schema': 'sl3.usb-identity-supervisor.v1', 'completed': True, 'successful': True,
                  'observer_sha256': source_sha, 'dll_sha256': supervisor.observer.DLL_SHA,
                  'supervisor_sha256': hashlib.sha256(Path(supervisor.__file__).read_bytes()).hexdigest(),
                  'automatic_retry': False, 'device_recovery_verified': False, 'application_coexistence_verified': False,
                  'duration_seconds': .01, 'interval_ms': 50, 'child_deadline_seconds': 10.01,
                  'retirement_allowance_seconds': 5, 'started_utc': stamp, 'child_started_utc': stamp,
                  'completed_utc': stamp, 'observation': checked,
                  'observations_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'command': [sys.executable, '-u', str(supervisor.SCRIPT), '--run', '--output', str(path.resolve()),
                              '--seconds', '0.01', '--interval-ms', '50'],
                  'child': {'started': True, 'pid': 12345, 'child_exited': True, 'exit_code': 0,
                            'timed_out': False, 'forced_termination': False, 'error': None}}
        (self.folder/'supervisor.json').write_text(json.dumps(record), encoding='utf-8')
        return record

    def test_saved_run_validation_binds_sources_command_record_and_retirement(self):
        record = self.supervised_fixture()
        self.assertTrue(supervisor.validate_supervised_run(self.folder)['valid'])
        for field, value in [('observer_sha256', 'f'*64), ('observations_sha256', 'e'*64),
                             ('command', []), ('successful', False),
                             ('completed_utc', '2026-10-30T22:00:00+00:00')]:
            with self.subTest(field=field):
                bad = copy.deepcopy(record); bad[field] = value
                (self.folder/'supervisor.json').write_text(json.dumps(bad), encoding='utf-8')
                with self.assertRaises(ValueError):
                    supervisor.validate_supervised_run(self.folder)
        for field, value in [('child_exited', False), ('exit_code', 7), ('timed_out', True), ('forced_termination', True)]:
            with self.subTest(child_field=field):
                bad = copy.deepcopy(record); bad['child'][field] = value
                (self.folder/'supervisor.json').write_text(json.dumps(bad), encoding='utf-8')
                with self.assertRaises(ValueError):
                    supervisor.validate_supervised_run(self.folder)


if __name__ == '__main__':
    unittest.main()
