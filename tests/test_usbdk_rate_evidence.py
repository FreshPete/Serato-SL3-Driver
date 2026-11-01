import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("rate_evidence", Path(__file__).parents[1] / "scripts/validate-usbdk-rate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sl3-rate-evidence-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder / "rate").mkdir()
        (self.folder / "trace").mkdir()
        self.sha = "1" * 64
        self.native = {"schema": "sl3.rate-diagnostic.v1", "phase": "finished", "utc": "2026-10-27T01:00:03Z",
                       "target_rate_hz": 48000, "initial_rate_hz": 44100, "verified_rate_hz": 48000,
                       "device_may_have_changed": True, "last_io_retired": True, "control_transfer_attempts": 6,
                       "redirect_closed": True, "audio_submissions": 0, "alternate_changes": 0,
                       "automatic_rollback": False, "diagnostic_error": 0, "transaction_error": 0,
                       "exchange_error": 0, "write_attempts": 3, "read_attempts": 3, "error": ""}
        self.run = {"schema": "sl3.usbdk.traced-run.v1", "mode": "Rate", "completed": True, "error": None,
                    "nativeExitCode": 0, "secureBootBefore": True, "secureBootAfter": True, "recoveryConfirmed": True,
                    "driverChanges": False, "rateRestorationAttempted": False, "deviceRateEffectUnknown": False,
                    "nativeSha256": self.sha, "traceExitCode": 0, "traceCleanupConfirmed": True,
                    "traceStartedUtc": "2026-10-27T01:00:00Z", "traceStoppedUtc": "2026-10-27T01:01:00Z",
                    "nativeStartedUtc": "2026-10-27T01:00:01Z", "nativeCompletedUtc": "2026-10-27T01:00:04Z",
                    "targetRate": 48000, "lastKnownDeviceMayHaveChanged": True, "lastIoRetired": True}
        self.state = {"secureBoot": True, "deviceGuard": {"synthetic": True}, "hvciRegistry": None,
                      "devices": [{"device": {"InstanceId": "USB\\VID_1CC5&PID_0001\\SYNTHETIC", "Problem": 39},
                                   "properties": [{"KeyName": "Synthetic", "Data": "original"}]}],
                      "asio": [], "application": {"synthetic": True}}
        self.trace = {"status": "window completed", "session": "synthetic-session",
                      "startedUtc": self.run["traceStartedUtc"], "stoppedUtc": self.run["traceStoppedUtc"]}
        self.xml = ('<Events><Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">'
                    '<System><Provider Guid="{9e814aad-3204-11d2-9a82-006008a86939}"/></System><EventData>'
                    '<Data Name="EventsLost">0</Data><Data Name="BuffersLost">0</Data>'
                    '<Data Name="SessionNameString">synthetic-session</Data></EventData></Event></Events>')
        (self.folder / "events.xml").write_text(self.xml, encoding="utf-8")
        self.run["traceStats"] = module.capture.trace_statistics(self.folder / "events.xml")
        # Deliberately synthetic bytes: validation is record consistency, not
        # an ETL decoder, USB payload correlate or hardware attestation.
        (self.folder / "trace/synthetic.etl").write_bytes(b"synthetic ETL fixture")
        self.run["etlSha256"] = module.digest(self.folder / "trace/synthetic.etl")
        self.prior = {"valid": True, "nativeSha256": self.sha, "reportedRateHz": 44100}
        self.save()

    def save(self):
        records = [("rate/rate.json", self.native, "nativeRecordSha256"),
                   ("before-state.json", self.state, "beforeStateSha256"),
                   ("after-state.json", self.state, "afterStateSha256"),
                   ("prior-capture-validation.json", self.prior, "priorCaptureValidationSha256")]
        for name, record, field in records:
            path = self.folder / name
            path.write_text(json.dumps(record), encoding="utf-8")
            self.run[field] = module.digest(path)
        (self.folder / "trace/capture.json").write_text(json.dumps(self.trace), encoding="utf-8")
        (self.folder / "run.json").write_text(json.dumps(self.run), encoding="utf-8")

    def validate(self):
        return module.validate(self.folder, self.sha, 48000)

    def test_changed_rate_and_noop(self):
        self.assertTrue(self.validate()["deviceMayHaveChanged"])
        self.native.update(initial_rate_hz=48000, device_may_have_changed=False, write_attempts=1,
                           read_attempts=1, control_transfer_attempts=2)
        self.run["lastKnownDeviceMayHaveChanged"] = False
        self.save()
        self.assertTrue(self.validate()["valid"])
        self.assertFalse(self.validate()["deviceMayHaveChanged"])

    def test_native_failure_uncertainty_and_cleanup(self):
        original = copy.deepcopy(self.native)
        for key, value in (("phase", "before control write"), ("diagnostic_error", 1),
                           ("transaction_error", 4), ("exchange_error", 2), ("last_io_retired", False),
                           ("redirect_closed", False), ("verified_rate_hz", 0), ("verified_rate_hz", 44100),
                           ("device_may_have_changed", False), ("automatic_rollback", True),
                           ("audio_submissions", 1), ("alternate_changes", 1), ("error", "timeout")):
            with self.subTest(key=key, value=value):
                self.native = copy.deepcopy(original)
                self.native[key] = value
                self.save()
                with self.assertRaises(ValueError):
                    self.validate()

    def test_counts_and_boolean_confusion(self):
        original = self.native.copy()
        for key, value in (("write_attempts", 4), ("read_attempts", 13), ("read_attempts", 2),
                           ("control_transfer_attempts", 7), ("diagnostic_error", False), ("target_rate_hz", True)):
            self.native = original.copy()
            self.native[key] = value
            self.save()
            with self.assertRaises(ValueError):
                self.validate()

    def test_runner_failure_and_wrong_identity(self):
        original = self.run.copy()
        for key, value in (("completed", False), ("nativeExitCode", 70), ("deviceRateEffectUnknown", True),
                           ("lastKnownDeviceMayHaveChanged", False), ("lastIoRetired", False),
                           ("targetRate", 44100), ("secureBootAfter", False), ("recoveryConfirmed", False),
                           ("driverChanges", True), ("rateRestorationAttempted", True)):
            self.run = original.copy()
            self.run[key] = value
            self.save()
            with self.assertRaises(ValueError):
                self.validate()
        self.run = original
        self.save()
        with self.assertRaisesRegex(ValueError, "Different native"):
            module.validate(self.folder, "2" * 64)
        self.prior["nativeSha256"] = "2" * 64
        self.save()
        with self.assertRaisesRegex(ValueError, "prerequisite"):
            self.validate()

    def test_mutated_files_and_recovery_contract(self):
        for name in ("rate/rate.json", "before-state.json", "after-state.json", "prior-capture-validation.json"):
            path = self.folder / name
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash changed"):
                self.validate()
            self.save()
        changed = copy.deepcopy(self.state)
        changed["devices"][0]["device"]["Problem"] = 0
        path = self.folder / "after-state.json"
        path.write_text(json.dumps(changed), encoding="utf-8")
        self.run["afterStateSha256"] = module.digest(path)
        (self.folder / "run.json").write_text(json.dumps(self.run), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "contracts differ"):
            self.validate()

    def test_trace_loss_identity_and_etl(self):
        xml = self.folder / "events.xml"
        xml.write_text(self.xml.replace('>0</Data>', '>1</Data>', 1), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "statistics/hash"):
            self.validate()
        self.run["traceStats"] = module.capture.trace_statistics(xml)
        self.save()
        with self.assertRaisesRegex(ValueError, "lossy"):
            self.validate()
        xml.write_text(self.xml, encoding="utf-8")
        self.run["traceStats"] = module.capture.trace_statistics(xml)
        self.trace["session"] = "different-session"
        self.save()
        with self.assertRaisesRegex(ValueError, "identity/window"):
            self.validate()
        self.trace["session"] = "synthetic-session"
        self.save()
        (self.folder / "trace/synthetic.etl").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "ETL identity"):
            self.validate()

    def test_time_bounds(self):
        old_start = self.run["nativeStartedUtc"]
        self.run["nativeStartedUtc"] = "2026-10-27T01:00:03.000500Z"
        self.save()
        self.assertTrue(self.validate()["valid"])  # Native timestamp has only ms precision.
        self.run["nativeStartedUtc"] = old_start
        for field, value in (("nativeStartedUtc", "2026-10-26T01:00:00Z"),
                             ("nativeCompletedUtc", "2026-10-27T01:00:02Z")):
            old = self.run[field]
            self.run[field] = value
            self.save()
            with self.assertRaisesRegex(ValueError, "outside trace"):
                self.validate()
            self.run[field] = old
        self.native["utc"] = "2026-10-27T01:00:03"
        self.save()
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.validate()


@unittest.skipUnless(shutil.which("pwsh"), "PowerShell is unavailable")
class RateWrapperPlanTests(unittest.TestCase):
    def command(self, args, destination):
        script = Path(__file__).parents[1] / "scripts/test-usbdk-traced.ps1"
        return subprocess.run([shutil.which("pwsh"), "-NoProfile", "-File", str(script),
                               "-ResultDirectory", str(destination), *args],
                              capture_output=True, text=True, timeout=10)

    def test_all_plan_modes_touch_no_output(self):
        with tempfile.TemporaryDirectory(prefix="sl3-rate-plans-") as temporary:
            destination = Path(temporary) / "not-created"
            for mode, target in (("List", 0), ("Capture", 0), ("DuplexSilence", 0), ("Rate", 44100), ("Rate", 48000)):
                args = ["-Mode", mode] + (["-TargetRate", str(target)] if target else [])
                result = self.command(args, destination)
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads(result.stdout)
                self.assertTrue(plan["planOnly"])
                self.assertFalse(plan["helperLoaded"])
                self.assertFalse(plan["driverChanges"])
                self.assertEqual(plan["audioSubmissions"], 0)
                self.assertFalse(destination.exists())
                if target:
                    self.assertEqual(plan["arguments"][:2], ["--select-rate", str(target)])
                    self.assertFalse(plan["rateRestorationAttempted"])

    def test_invalid_plan_arguments_rejected_before_output(self):
        with tempfile.TemporaryDirectory(prefix="sl3-rate-invalid-") as temporary:
            destination = Path(temporary) / "not-created"
            for args in (["-Mode", "Rate"], ["-Mode", "Rate", "-TargetRate", "0"],
                         ["-Mode", "Rate", "-TargetRate", "96000"],
                         ["-Mode", "Capture", "-TargetRate", "48000"],
                         ["-Mode", "List", "-ValidatedCaptureRun", "unused"]):
                self.assertNotEqual(self.command(args, destination).returncode, 0)
                self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
