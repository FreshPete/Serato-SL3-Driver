"""Read-only reporting regression with a live writer; no driver or USB calls."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/read-startup-journal.ps1'
PWSH = shutil.which('pwsh')


@unittest.skipUnless(PWSH, 'PowerShell 7 is required for the Windows journal reader')
class StartupJournalSnapshotTests(unittest.TestCase):
    def execute(self, path):
        return subprocess.run([PWSH, '-NoProfile', '-File', str(SCRIPT), '-Path', str(path)],
                              capture_output=True, text=True, timeout=20)

    def test_live_writer_snapshot_and_later_append(self):
        with tempfile.TemporaryDirectory(prefix='sl3-journal-reader-') as directory:
            path = Path(directory)/'worker.tsv'
            with path.open('wb') as writer:
                first = b'100\t123\tworker.enter\n101\t123\tredirect_start.enter\n'
                writer.write(first)
                writer.flush()
                result = self.execute(path)
                self.assertEqual(result.returncode, 0, result.stderr)
                snapshot = json.loads(result.stdout)
                self.assertEqual(snapshot['snapshotSha256'].lower(), hashlib.sha256(first).hexdigest())
                self.assertEqual(snapshot['completeRecords'], 2)
                self.assertEqual(snapshot['lastCompleteMarker'], '101\t123\tredirect_start.enter')
                self.assertTrue(snapshot['endsWithCompleteRecord'])
                writer.write(b'102\t123\tredirect_start.return\n')
                writer.flush()
                later = json.loads(self.execute(path).stdout)
                self.assertEqual(later['completeRecords'], 3)
                self.assertNotEqual(later['snapshotSha256'], snapshot['snapshotSha256'])

    def test_partial_suffix_and_empty_file(self):
        with tempfile.TemporaryDirectory(prefix='sl3-journal-reader-') as directory:
            path = Path(directory)/'worker.tsv'
            path.write_bytes(b'100\t123\tworker.enter\n101\t123\tredirect_st')
            result = self.execute(path)
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = json.loads(result.stdout)
            self.assertFalse(snapshot['endsWithCompleteRecord'])
            self.assertEqual(snapshot['completeRecords'], 1)
            self.assertEqual(snapshot['lastCompleteMarker'], '100\t123\tworker.enter')
            path.write_bytes(b'')
            snapshot = json.loads(self.execute(path).stdout)
            self.assertEqual(snapshot['completeRecords'], 0)
            self.assertIsNone(snapshot['lastCompleteMarker'])

    def test_guard_marker_spellings_and_unknown_dotted_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'worker.tsv'
            for name in ('redirect_owner_acquire', 'redirect_owner.acquire'):
                path.write_bytes(f'100\t123\t{name}.enter\n101\t123\t{name}.return\n'.encode('ascii'))
                result = self.execute(path)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['completeRecords'], 2)
            path.write_bytes(b'100\t123\tother.acquire.enter\n')
            self.assertNotEqual(self.execute(path).returncode, 0)

    def test_malformed_and_oversized_records(self):
        with tempfile.TemporaryDirectory(prefix='sl3-journal-reader-') as directory:
            path = Path(directory)/'worker.tsv'
            for payload in (b'not-a-marker\n', b'x'*65537):
                path.write_bytes(payload)
                self.assertNotEqual(self.execute(path).returncode, 0)


if __name__ == '__main__':
    unittest.main()
