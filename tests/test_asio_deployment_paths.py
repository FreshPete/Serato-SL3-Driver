import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


inside = runpy.run_path(str(
    Path(__file__).resolve().parents[1] / "scripts/prepare-asio-deployment.py"
))["inside"]


class DeploymentPathTest(unittest.TestCase):
    def test_redirection_checks_containment_and_preserves_native_spelling(self):
        parent = Path("C:/profile/Local/SL3Rebuild")
        pointer = parent / "session.txt"
        redirected = Path("C:/package/LocalCache/SL3Rebuild")
        resolutions = {parent: redirected, pointer: redirected / pointer.name}
        with patch.object(Path, "resolve", lambda path: resolutions[path]):
            self.assertEqual(inside(pointer, parent), pointer)
        resolutions[pointer] = Path("C:/elsewhere/session.txt")
        with patch.object(Path, "resolve", lambda path: resolutions[path]):
            with self.assertRaisesRegex(ValueError, "escapes"):
                inside(pointer, parent)

    def test_parent_traversal_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Parent traversal"):
            inside(Path("C:/profile/Local/SL3Rebuild/../session.txt"),
                   Path("C:/profile/Local/SL3Rebuild"))


if __name__ == "__main__":
    unittest.main()
