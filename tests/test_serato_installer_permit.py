import json
import runpy
import sys
import tempfile
import time
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@unittest.skipUnless(sys.platform == "win32", "Requires Windows file sharing")
class InstallerPermitTest(unittest.TestCase):
    bundle = "a" * 64

    @classmethod
    def setUpClass(cls):
        cls.stage = runpy.run_path(str(SCRIPTS / "asio-install-journal.py"))["stage_module"]()
        cls.permit = runpy.run_path(str(SCRIPTS / "serato-installer-permit.py"))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name).resolve() / "test.sl3-permit"

    def write_permit(self, bundle, seconds):
        self.path.write_text(json.dumps({
            "bundleSha256": bundle,
            "expiresUnix": int(time.time()) + seconds,
        }), encoding="utf-8")

    def test_active_claim_blocks_revoke_until_receipt_scope_exits(self):
        self.write_permit(self.bundle, 120)
        with self.permit["claim"](self.stage, self.path, self.bundle):
            with self.assertRaises(OSError) as blocked:
                self.permit["revoke"](self.stage, self.path, self.bundle)
            self.assertEqual(blocked.exception.winerror, 32)
        self.permit["revoke"](self.stage, self.path, self.bundle)
        self.assertFalse(self.path.exists())
        with self.assertRaises(OSError) as missing:
            with self.permit["claim"](self.stage, self.path, self.bundle):
                self.fail("A late launcher claimed a revoked permit")
        self.assertEqual(missing.exception.winerror, 2)

    def test_expired_and_excessively_long_permits_cannot_be_claimed(self):
        for seconds in (-30, 360):
            with self.subTest(seconds=seconds):
                self.write_permit(self.bundle, seconds)
                with self.assertRaisesRegex(ValueError, "expired or outside"):
                    with self.permit["claim"](self.stage, self.path, self.bundle):
                        self.fail("Claimed a permit outside the allowed window")

    def test_revoke_preserves_a_different_bundles_permit(self):
        self.write_permit("b" * 64, 120)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "identity differs"):
            self.permit["revoke"](self.stage, self.path, self.bundle)
        self.assertEqual(self.path.read_bytes(), before)
