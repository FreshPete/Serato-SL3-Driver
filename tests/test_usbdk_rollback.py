"""Offline supplement selection and actual prepare CLI; never trace or open USB."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/export-usbdk-rollback-contract.py'
spec = importlib.util.spec_from_file_location('rollback_contract', SCRIPT)
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)


def formats():
    return (f'{v.GUID} UsbDk // SRC=ControlDevice.cpp MJ= MN=\n'+''.join(
        f'#typev example {number} "message" // LEVEL=TRACE_LEVEL_ERROR FLAGS=TRACE_CONTROLDEVICE FUNC=CUsbDkControlDevice::AddRedirectRollBack\n{{\n}}\n'
        for number in (34, 35))).encode()


class RollbackTests(unittest.TestCase):
    def test_exact_two_formats_and_identical_architecture_repetitions(self):
        raw = formats(); first, rows = v.rollback_formats(raw)
        repeated, _ = v.rollback_formats(raw+raw)
        self.assertEqual(first, repeated); self.assertEqual(first.count(b'#typev'), 2)
        self.assertEqual([r['messageId'] for r in rows], [34, 35])

    def test_architecture_dependent_format_rejected(self):
        raw = formats()
        with self.assertRaisesRegex(ValueError, 'architecture-dependent'):
            v.rollback_formats(raw+raw.replace(b'"message"', b'"different"'))

    def test_missing_wrong_guid_source_and_metadata_rejected(self):
        raw = formats()
        for changed in [raw.replace(b'example 35', b'example 36'), raw.replace(v.GUID.encode(), b'00000000-0000-0000-0000-000000000000'),
                        raw.replace(b'ControlDevice.cpp', b'Other.cpp'), raw.replace(b'TRACE_LEVEL_ERROR', b'TRACE_LEVEL_INFORMATION'),
                        raw.replace(b'::AddRedirectRollBack', b'::OtherFunction')]:
            with self.subTest(changed=changed[:90]), self.assertRaises(ValueError):
                v.rollback_formats(changed)

    def test_truncated_invalid_and_unbounded_formats_rejected(self):
        for raw in [b'', formats().rsplit(b'}', 1)[0], b'\xff', bytes(8*1024*1024+1)]:
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                v.rollback_formats(raw)

    def test_actual_binary_contract_has_failure_specific_reset_arguments(self):
        record, supplement = v.verify()
        self.assertEqual([r['withReset'] for r in record['failureBranches']], [False, True, True])
        self.assertEqual(record['attachmentWait']['relative100ns'], -1_200_000_000)
        self.assertFalse(record['attachmentWait']['boundsEntireStartOrRollback'])
        self.assertFalse(record['rollback']['forceD0']); self.assertEqual(supplement.count(b'#typev'), 2)
        self.assertFalse(record['historicalStallCauseProven']); self.assertFalse(record['reacquisitionRepairVerified'])
        self.assertFalse(record['deviceAccess']); self.assertFalse(record['tracingEnabled'])

    def test_actual_prepare_new_only_and_historical_decoder_unchanged(self):
        baseline = ROOT/'tests/results/local/logging-batch-port-attended-20261101-1640-controls/trace/lifecycle-decoder/lifecycle.tmf'
        before = baseline.read_bytes(); out = ROOT/'analysis'/('rollback-cli-test-'+uuid.uuid4().hex)
        args = [sys.executable, str(SCRIPT), '--prepare', str(out)]
        try:
            run = subprocess.run(args, capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr)
            saved = {p.name: p.read_bytes() for p in out.iterdir()}
            self.assertEqual(set(saved), {'rollback-supplement.tmf', 'plan.json'})
            self.assertEqual(saved['rollback-supplement.tmf'].count(b'#typev'), 2)
            self.assertFalse(json.loads(saved['plan.json'])['baselineDecoderChanged'])
            self.assertEqual(subprocess.run(args, capture_output=True, timeout=20).returncode, 1)
            self.assertEqual({p.name: p.read_bytes() for p in out.iterdir()}, saved)
            self.assertEqual(baseline.read_bytes(), before)
        finally:
            if out.exists():
                self.assertEqual(out.resolve().parent, (ROOT/'analysis').resolve())
                self.assertTrue(out.name.startswith('rollback-cli-test-'))
                self.assertLessEqual({p.name for p in out.iterdir()}, {'rollback-supplement.tmf', 'plan.json'})
                for p in out.iterdir():
                    self.assertTrue(p.is_file() and not p.is_symlink()); p.unlink()
                out.rmdir()

    def test_actual_cli_rejects_output_outside_direct_analysis_scope(self):
        out = ROOT/'artifacts'/('rollback-refused-'+uuid.uuid4().hex)
        run = subprocess.run([sys.executable, str(SCRIPT), '--prepare', str(out)], capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 1); self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
