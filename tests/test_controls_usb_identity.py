"""Synthetic shared-window/identity admission checks; no USB or vendor library."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('controls_identity_test', ROOT/'scripts/controls-usb-identity.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


class ControlsIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve(); self.obs = self.folder/'usb-identity'; self.obs.mkdir()
        self.base = datetime(2026, 10, 30, tzinfo=timezone.utc)

    def stamp(self, seconds):
        return (self.base+timedelta(seconds=seconds)).isoformat()

    def fixture(self):
        source = c.digest(c.s.SCRIPT)
        rows = [{'event': 'library_load_enter', 'observer_sha256': source, 'dll_sha256': c.s.observer.DLL_SHA, 'utc': self.stamp(1)},
                {'event': 'context_init_enter', 'utc': self.stamp(1)},
                {'event': 'started', 'schema': 'sl3.usb-identity-observer.v1', 'dll_sha256': c.s.observer.DLL_SHA,
                 'duration_seconds': 45, 'interval_seconds': .05, 'utc': self.stamp(1)}]
        previous = None
        for seconds, address in ((2, 9), (4, 10), (6, 10), (46, 10)):
            snapshot = {'complete': True, 'descriptor_failures': 0, 'enumerated_devices': 1,
                        'identities': [{'vendor': c.s.observer.VID, 'product': c.s.observer.PID,
                                        'revision': 256, 'bus': 3, 'address': address}]}
            rows.extend([{'event': 'snapshot_enter', 'elapsed_seconds': seconds-1, 'utc': self.stamp(seconds)},
                         {'event': 'sample', 'elapsed_seconds': seconds-.99, 'call_seconds': .01,
                          'snapshot': snapshot, 'delta': c.s.observer.compare(previous, snapshot), 'utc': self.stamp(seconds+.01)}])
            previous = snapshot
        rows.extend([{'event': 'finished', 'utc': self.stamp(46.02), 'samples': 4, 'incomplete_samples': 0,
                      'changed_comparisons': 1, 'device_release_verified': False, 'application_coexistence_verified': False},
                     {'event': 'context_close_enter', 'utc': self.stamp(46.03)},
                     {'event': 'context_closed', 'utc': self.stamp(46.04)}])
        raw = ''.join(json.dumps(r)+'\n' for r in rows).encode()
        (self.obs/'observations.jsonl').write_bytes(raw)
        prefix = ''.join(json.dumps(r)+'\n' for r in rows[:5]).encode()
        admission = c.ready(self.obs, self.base+timedelta(seconds=2.1), prefix)
        (self.folder/'identity-ready.json').write_text(json.dumps(admission), encoding='utf-8')
        checked = c.s.validate_observation(self.obs/'observations.jsonl', source, 45.0, .05)
        supervisor = {'schema': 'sl3.usb-identity-supervisor.v1', 'completed': True, 'successful': True,
                      'observer_sha256': source, 'supervisor_sha256': c.digest(Path(c.s.__file__)),
                      'dll_sha256': c.s.observer.DLL_SHA, 'automatic_retry': False, 'device_recovery_verified': False,
                      'application_coexistence_verified': False, 'duration_seconds': 45.0, 'interval_ms': 50,
                      'child_deadline_seconds': 55, 'retirement_allowance_seconds': 5, 'observation': checked,
                      'observations_sha256': hashlib.sha256(raw).hexdigest(), 'started_utc': self.stamp(.5),
                      'child_started_utc': self.stamp(.6), 'completed_utc': self.stamp(47),
                      'command': [sys.executable, '-u', str(c.s.SCRIPT), '--run', '--output', str(self.obs/'observations.jsonl'),
                                  '--seconds', '45.0', '--interval-ms', '50'],
                      'child': {'started': True, 'pid': 12345, 'child_exited': True, 'exit_code': 0,
                                'timed_out': False, 'forced_termination': False, 'error': None}}
        (self.obs/'supervisor.json').write_text(json.dumps(supervisor), encoding='utf-8')
        (self.folder/'identity-validation.json').write_text(json.dumps(checked), encoding='utf-8')
        record = {'withUsbIdentity': True, 'usbIdentityExitCode': 0,
                  'usbIdentitySupervisorRecordSha256': c.digest(self.obs/'supervisor.json'),
                  'usbIdentityValidationSha256': c.digest(self.folder/'identity-validation.json'),
                  'usbIdentityReadySha256': c.digest(self.folder/'identity-ready.json'),
                  'probeStartedUtc': self.stamp(3), 'probeCompletedUtc': self.stamp(5)}
        trace = {'startedUtc': self.stamp(0), 'stoppedUtc': self.stamp(60)}
        return record, trace, prefix

    def test_real_validation_chain_reports_changed_identity_without_held_claim(self):
        record, trace, _ = self.fixture()
        result = c.coverage(self.folder, record, trace)
        self.assertTrue(result['valid']); self.assertEqual(result['sampledIdentityChanges'], 1)
        self.assertEqual(result['samplesInsideProbeProcessWindow'], 1)
        self.assertGreater(result['completeBeforeProbe'], 0); self.assertGreater(result['completeAfterProbe'], 0)
        self.assertFalse(result['heldDeviceCoverageVerified']); self.assertFalse(result['seratoCoexistenceVerified'])

    def test_live_partial_suffix_and_stale_sample(self):
        _, _, prefix = self.fixture()
        checked = c.ready(self.obs, self.base+timedelta(seconds=2.1), prefix)
        self.assertEqual(c.ready(self.obs, self.base+timedelta(seconds=2.1), prefix+b'{"event":'), checked)
        with self.assertRaises(ValueError):
            c.ready(self.obs, self.base+timedelta(seconds=3), prefix)
        changed = prefix.replace(b'"complete": true', b'"complete": false')
        with self.assertRaises(ValueError):
            c.ready(self.obs, self.base+timedelta(seconds=2.1), changed)

    def test_window_binding_and_unrequested_observer_rejected(self):
        record, trace, _ = self.fixture()
        for key, value in [('usbIdentityExitCode', 7), ('probeStartedUtc', self.stamp(.5)),
                           ('probeCompletedUtc', self.stamp(47)), ('usbIdentityReadySha256', 'f'*64)]:
            with self.subTest(key=key):
                bad = copy.deepcopy(record); bad[key] = value
                with self.assertRaises(ValueError):
                    c.coverage(self.folder, bad, trace)
        with self.assertRaises(ValueError):
            c.coverage(self.folder, {'withUsbIdentity': False}, trace)

    def test_missing_post_probe_sample_is_not_covered(self):
        record, trace, _ = self.fixture()
        record['probeCompletedUtc'] = self.stamp(46.02)  # Before close, after the last sample entry.
        with self.assertRaisesRegex(ValueError, 'before/after'):
            c.coverage(self.folder, record, trace)

    def test_combined_plan_creates_no_directory(self):
        target = self.folder/'not-created'
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(ROOT/'scripts/test-controls-host-traced.ps1'),
                                 '-WithUsbDkLifecycle', '-WithUsbIdentity', '-ResultDirectory', str(target)],
                                capture_output=True, text=True, timeout=20, check=True)
        plan = json.loads(result.stdout)
        self.assertTrue(plan['withUsbIdentity']); self.assertTrue(plan['withUsbDkLifecycle'])
        self.assertEqual(plan['identitySeconds'], 45); self.assertEqual(plan['identityIntervalMilliseconds'], 50)
        self.assertFalse(plan['heldDeviceIdentityCoverageVerified']); self.assertFalse(plan['deviceAccess'])
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
