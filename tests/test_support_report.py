import copy
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

API = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/export-sl3-support-report.py'))


class SupportReportTest(unittest.TestCase):
    def readiness(self):
        return {'schema': API['SCHEMAS']['readiness'], 'readyForAttempt': True,
                'checks': [{'id': name, 'status': 'pass', 'message': 'PRIVATE',
                            'evidence': {'path': 'PRIVATE'}} for name in API['CHECKS']]}

    def test_messages_paths_events_and_unknown_fields_are_not_exported(self):
        source = {'schema': API['SCHEMAS']['supervisor'], 'events': [{'event': 'PRIVATE'}],
                  'error': 'PRIVATE', 'cleanupError': None, 'endReason': 'failure',
                  'process': {'pid': 12345, 'path': 'PRIVATE', 'detachError': 'PRIVATE',
                              'processExited': True, 'exitCode': 1}}
        result = API['summarize']('supervisor', source)
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('pid', json.dumps(result))
        self.assertTrue(result['errorPresent'])
        self.assertTrue(result['process']['detachErrorPresent'])

    def test_readiness_statuses_survive_without_raw_evidence(self):
        source = self.readiness()
        source['readyForAttempt'] = False
        source['checks'][0]['status'] = 'unknown'
        result = API['summarize']('readiness', source)
        self.assertEqual(result['checks']['platform'], 'unknown')
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_contradictory_or_incomplete_readiness_refused(self):
        source = self.readiness()
        for change in ('contradiction', 'missing', 'duplicate', 'unknown'):
            value = copy.deepcopy(source)
            if change == 'contradiction': value['checks'][0]['status'] = 'blocked'
            if change == 'missing': value['checks'].pop()
            if change == 'duplicate': value['checks'][0]['id'] = value['checks'][1]['id']
            if change == 'unknown': value['checks'][0]['id'] = 'PRIVATE'
            with self.subTest(change=change), self.assertRaises(ValueError):
                API['summarize']('readiness', value)

    def test_clean_recovery_does_not_promote_shutdown(self):
        result = API['summarize']('recovery', {'schema': API['SCHEMAS']['recovery'],
                 'originalSetupClean': True, 'previousSessionShutdownVerified': False,
                 'issues': ['PRIVATE'], 'message': 'PRIVATE'})
        self.assertTrue(result['originalSetupClean'])
        self.assertFalse(result['previousSessionShutdownVerified'])
        self.assertEqual(result['issueCount'], 1)
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_bool_strings_and_integer_bools_refused(self):
        for value in ('true', 1, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                API['summarize']('recovery', {'schema': API['SCHEMAS']['recovery'], 'deviceOpened': value})

    def test_unsupported_schema_and_enum_refused(self):
        with self.assertRaises(ValueError): API['summarize']('recovery', {'schema': 'unknown'})
        with self.assertRaises(ValueError):
            API['summarize']('supervisor', {'schema': API['SCHEMAS']['supervisor'], 'endReason': 'PRIVATE'})

    def test_digest_binds_input_without_disclosing_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'PRIVATE.json'
            raw = json.dumps(self.readiness()).encode()
            path.write_bytes(raw)
            result = API['export']({'readiness': path})
            self.assertEqual(result['observations']['readiness']['sourceSha256'], hashlib.sha256(raw).hexdigest())
            self.assertNotIn('PRIVATE', json.dumps(result))
            self.assertIn('different sessions', result['interpretation'])

    def test_duplicate_json_nonfinite_and_oversized_input_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.json'
            for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b' ' * (API['MAX_BYTES'] + 1)):
                path.write_bytes(raw)
                with self.subTest(size=len(raw)), self.assertRaises(ValueError): API['load'](path)

    def test_cli_never_overwrites_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'input.json'
            output = Path(folder) / 'output.json'
            source.write_text(json.dumps(self.readiness()))
            command = [sys.executable, API['__file__'], '--readiness', str(source), '--output', str(output)]
            first = subprocess.run(command, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            saved = output.read_bytes()
            second = subprocess.run(command, capture_output=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(output.read_bytes(), saved)


if __name__ == '__main__':
    unittest.main()
