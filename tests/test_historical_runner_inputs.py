"""Historical evidence must bind original scripts, never a convenient replacement."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('physical_checkpoint', ROOT/'scripts/validate-historical-usbdk-run.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HistoricalRunnerInputsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.archive = Path(temporary.name)
        self.commit = '13fd6c4950053f37f2aeef9d03e4f7699e4ff3b8'
        self.name = 'validate-usbdk-capture.py'
        self.original = subprocess.run(['git', 'show', self.commit+':scripts/'+self.name],
                                       cwd=ROOT, check=True, capture_output=True).stdout
        self.record = {'runnerInputs': {self.name: hashlib.sha256(self.original).hexdigest()}}

    def test_archive_bytes_match_without_git(self):
        (self.archive/self.name).write_bytes(self.original)
        module.validate_runner_inputs(self.record, self.archive)

    def test_missing_file_requires_explicit_pinned_history(self):
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            module.validate_runner_inputs(self.record, self.archive)
        module.validate_runner_inputs(self.record, self.archive, self.commit)

    def test_corrupted_archive_cannot_fall_back_to_good_git(self):
        (self.archive/self.name).write_bytes(self.original+b'\n# changed\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            module.validate_runner_inputs(self.record, self.archive, self.commit)

    def test_git_bytes_must_match_recorded_hash(self):
        self.record['runnerInputs'][self.name] = '0'*64
        with self.assertRaisesRegex(ValueError, 'changed'):
            module.validate_runner_inputs(self.record, self.archive, self.commit)

    def test_crlf_git_reconstruction_matches_exact_recorded_bytes(self):
        raw = self.original.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        self.record['runnerInputs'][self.name] = hashlib.sha256(raw).hexdigest()
        module.validate_runner_inputs(self.record, self.archive, self.commit)

    def test_unsafe_names_empty_inputs_and_unpinned_revision_rejected(self):
        for name in ('../outside.py', '..\\outside.py', 'C:outside.py', '.', '..'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Unsafe'):
                module.validate_runner_inputs({'runnerInputs': {name: '0'*64}}, self.archive, self.commit)
        with self.assertRaisesRegex(ValueError, 'Missing'):
            module.validate_runner_inputs({'runnerInputs': {}}, self.archive)
        with self.assertRaisesRegex(ValueError, 'full object ID'):
            module.validate_runner_inputs(self.record, self.archive, 'HEAD')


if __name__ == '__main__':
    unittest.main()
