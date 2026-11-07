"""Retained administrator handoff decisions with no privileged fixture operations."""
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

API = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/retained-setup-handoff.py'))
INSTALLED = {'archive':'installed','seratoRunning':False,'native':{'state':'installed'}}


class HandoffTests(unittest.TestCase):
    def scenario(self, setup, restore=None, idle=True):
        calls = []
        def invoke(action):
            calls.append(action)
            return setup if action=='setup' else restore
        def wait_idle():
            calls.append('idle')
            return idle
        outcome = API['coordinate'](invoke,lambda:calls.append('request'),wait_idle)
        return outcome,calls

    def test_installed_waits_for_request_and_idle(self):
        self.assertEqual(self.scenario({'successful':True,'after':INSTALLED},
                                      {'successful':True,'after':API['CLEAN']}),
                         ('restored',['setup','request','idle','restore']))

    def test_known_partial_setup_skips_viewing_window(self):
        partial = {**INSTALLED,'archive':'original'}
        self.assertEqual(self.scenario({'successful':False,'after':partial},
                                      {'successful':True,'after':API['CLEAN']}),
                         ('restored_after_failed_setup',['setup','idle','restore']))

    def test_unverified_setup_preserves_state(self):
        for report in (None,{'successful':False,'after':None},
                       {'successful':False,'after':{'archive':'original','native':None}},
                       {'successful':False,'after':{**INSTALLED,'archive':'conflict'}}):
            with self.subTest(report=report):
                self.assertEqual(self.scenario(report),('setup_outcome_unverified',['setup']))

    def test_busy_handoff_defers_restoration(self):
        self.assertEqual(self.scenario({'successful':True,'after':INSTALLED},idle=False),
                         ('restore_deferred',['setup','request','idle']))

    def test_serato_already_open_skips_viewing_window(self):
        open_app = {**INSTALLED,'seratoRunning':True}
        self.assertEqual(self.scenario({'successful':True,'after':open_app},idle=False),
                         ('restore_deferred',['setup','idle']))

    def test_failed_restore_is_reported_once(self):
        self.assertEqual(self.scenario({'successful':True,'after':INSTALLED},
                                      {'successful':False,'after':INSTALLED}),
                         ('restore_outcome_unverified',['setup','request','idle','restore']))

    def test_window_is_published_only_after_complete_json_is_written(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            receipt = b'{"fixture":true}'
            (folder/'setup-stdout.json').write_bytes(receipt)
            window = folder/'window.json'
            dump = json.dump

            def check_partial_write(record, stream):
                stream.write('{')
                stream.flush()
                self.assertFalse(window.exists())
                stream.seek(0)
                dump(record, stream)

            def process_handle(pid):
                self.assertEqual(pid, os.getpid())
                return nullcontext((123, None))

            with patch.object(json, 'dump', side_effect=check_partial_write):
                deadline = API['publish_window'](folder, 'fixture-sha', process_handle)

            record = json.loads(window.read_bytes())
            self.assertEqual(record['setupReceiptSha256'], hashlib.sha256(receipt).hexdigest())
            self.assertEqual(record['creationFileTimeUtc'], '123')
            self.assertEqual(record['deadlineMonotonicNs'], deadline)
            self.assertFalse((folder/'window.pending').exists())


if __name__=='__main__':
    unittest.main()
