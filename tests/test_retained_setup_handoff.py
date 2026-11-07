"""Retained administrator handoff decisions with no privileged fixture operations."""
from pathlib import Path
import runpy
import unittest

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


if __name__=='__main__':
    unittest.main()
