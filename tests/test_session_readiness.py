from pathlib import Path
import runpy
import unittest

API = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/inspect-sl3-session-readiness.py'))


class SessionReadinessTest(unittest.TestCase):
    def check(self, name, evidence, expected):
        ready, message = API['classify'](name, evidence)
        self.assertEqual(ready, expected)
        self.assertTrue(message)

    def test_native_ordinary_token_required(self):
        self.check('platform', {'nativeX64': True, 'elevated': False}, True)
        self.check('platform', {'nativeX64': False, 'elevated': False}, False)
        self.check('platform', {'nativeX64': True, 'elevated': True}, False)

    def test_original_application_must_be_closed(self):
        self.check('application', {'running': False}, True)
        self.check('application', {'running': True}, False)

    def test_filter_needs_presence_running_and_reviewed_disk_image(self):
        evidence = {'installed': True, 'running': True, 'reviewedImageOnDisk': True}
        self.check('filter', evidence, True)
        for name in evidence:
            with self.subTest(name=name):
                self.check('filter', {**evidence, name: False}, False)

    def test_exactly_one_present_identity(self):
        for count in (0, 1, 2):
            self.check('device', {'matchingPresentIdentities': count}, count == 1)

    def test_existing_state_is_preserved_and_blocks_launch(self):
        evidence = {'occupiedPaths': [], 'registrationPresent': False, 'originalResources': True}
        self.check('state', evidence, True)
        for changed in ({'occupiedPaths': ['sessionPointer']}, {'registrationPresent': True}, {'originalResources': False}):
            self.check('state', {**evidence, **changed}, False)

    def test_dependency_resolution_required(self):
        self.check('dependencies', {'directImportsResolved': True}, True)
        self.check('dependencies', {'directImportsResolved': False}, False)

    def test_unknown_check_does_not_pass(self):
        with self.assertRaisesRegex(ValueError, 'Unknown readiness check'):
            self.check('unknown', {}, True)


if __name__ == '__main__':
    unittest.main()
