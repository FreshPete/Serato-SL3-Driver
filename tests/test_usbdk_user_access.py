"""Mutate saved access evidence without loading the helper or touching USB."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('user_access', Path(__file__).resolve().parents[1]/'scripts/export-usbdk-user-access.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class UserAccessTests(unittest.TestCase):
    def setUp(self):
        self.record = {'parentToken': {'elevated': False, 'elevationType': 3},
                       'childToken': {'elevated': False, 'elevationType': 3},
                       'tokenQueryError': None, 'childExited': True, 'forcedTermination': False,
                       'exitCode': 0, 'elapsedSeconds': .04}
        self.output = {'matched_sl3': 1, 'descriptor_fixture_matches': True, 'high_speed': True, 'device_redirected': False}

    def test_valid_descriptor_access_does_not_verify_redirect_or_streaming(self):
        result = m.validate_result(self.record, self.output)
        self.assertTrue(result['nonElevatedDescriptorAccessVerified'])
        self.assertFalse(result['redirectAccessVerified']); self.assertFalse(result['nonElevatedStreamingVerified'])
        self.assertFalse(result['separateStandardAccountTested'])

    def test_actual_non_elevated_typed_tokens_required_for_parent_and_child(self):
        for token in ('parentToken', 'childToken'):
            for key, value in [('elevated', True), ('elevated', 0), ('elevationType', 2), ('elevationType', '3')]:
                record = copy.deepcopy(self.record); record[token][key] = value
                with self.subTest(token=token, key=key, value=value):
                    with self.assertRaises(ValueError):
                        m.validate_result(record, self.output)

    def test_failure_unconfirmed_exit_or_forced_termination_rejected(self):
        for key, value in [('tokenQueryError', 'access denied'), ('childExited', False), ('forcedTermination', True),
                           ('exitCode', 1), ('exitCode', False)]:
            record = copy.deepcopy(self.record); record[key] = value
            with self.assertRaises(ValueError):
                m.validate_result(record, self.output)

    def test_descriptor_success_flags_and_types_are_exact(self):
        for key, value in [('matched_sl3', True), ('matched_sl3', 0), ('descriptor_fixture_matches', False),
                           ('high_speed', 1), ('device_redirected', True)]:
            output = copy.deepcopy(self.output); output[key] = value
            with self.assertRaises(ValueError):
                m.validate_result(self.record, output)

    def test_invalid_process_timing_rejected(self):
        for value in (-1, 0, True, float('nan'), float('inf')):
            record = copy.deepcopy(self.record); record['elapsedSeconds'] = value
            with self.assertRaises(ValueError):
                m.validate_result(record, self.output)


if __name__ == '__main__':
    unittest.main()
