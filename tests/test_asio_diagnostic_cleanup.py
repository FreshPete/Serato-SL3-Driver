import contextlib
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


class DiagnosticCleanupTest(unittest.TestCase):
    def test_start_rejects_invalid_lifetimes_before_reading_inputs(self):
        start = runpy.run_path(str(
            Path(__file__).resolve().parents[1] / "scripts/asio-diagnostic-session.py"
        ))["start"]
        for lifetime in (999, 600001, 120000.0, True):
            with self.assertRaisesRegex(RuntimeError, "Diagnostic lifetime"):
                start(None, None, None, None, None, lifetime)

    def test_failed_session_can_retire_only_with_complete_release_evidence(self):
        stop = runpy.run_path(str(
            Path(__file__).resolve().parents[1] / "scripts/asio-diagnostic-session.py"
        ))["stop"]
        session = Path("C:/diagnostic/session")
        pointer = Path("C:/diagnostic/current.txt")
        ownership = {
            "controllerSha256": "controller-hash",
            "pointer": str(pointer),
            "configSha256": "config-hash",
            "controllerPid": 123,
            "controllerCreatedFileTime": "456",
        }
        result = {
            "successful": False,
            "processExited": True,
            "jobEmpty": True,
            "ioRetiredVerified": True,
            "deviceReleasedVerified": True,
        }
        values = {
            "digest": lambda path: "controller-hash" if path.name == "controller.exe" else "config-hash",
            "read": lambda path: ownership if path.suffix == ".json" and path.name != "result.json" else result,
            "process_handle": lambda pid: contextlib.nullcontext(None),
        }
        with patch.dict(stop.__globals__, values), patch.object(Path, "exists", return_value=False), patch.object(Path, "is_file", return_value=True):
            report = stop(Path("C:/diagnostic/controller.exe"), session, pointer, "controller-hash")
            self.assertTrue(report["controllerExited"])
            self.assertFalse(report["successful"])
            for field in ("processExited", "jobEmpty", "ioRetiredVerified", "deviceReleasedVerified"):
                result[field] = False
                with self.assertRaisesRegex(RuntimeError, "retirement is incomplete"):
                    stop(Path("C:/diagnostic/controller.exe"), session, pointer, "controller-hash")
                result[field] = True


if __name__ == "__main__":
    unittest.main()
