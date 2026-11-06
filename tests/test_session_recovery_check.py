from pathlib import Path
import runpy
import unittest

API=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/inspect-serato-session-recovery.py'))


class RecoveryCheckTest(unittest.TestCase):
    def fixture(self):
        return {'current':{'observed':True,'currentSetupClean':True},
                'resources':{'observed':True,'archiveState':'original','bundlePresent':False,'pendingPresent':False},
                'owners':{role:{'state':'exited'} for role in ('runner','stage','supervisor')},
                'running':False,'issues':[],'has_run':True,'broker_retired':True}

    def test_clean_is_current_state_not_recovery_authorization(self):
        result=API['classify'](**self.fixture())
        self.assertEqual(result['phase'],'clean');self.assertFalse(result['recoveryAuthorized'])

    def test_live_owner_or_serato_blocks_recovery_even_when_files_clean(self):
        for role in ('runner','stage','supervisor','application'):
            values=self.fixture()
            if role=='application':values['running']=True
            else:values['owners'][role]['state']='alive'
            result=API['classify'](**values)
            self.assertEqual(result['phase'],'active_session');self.assertFalse(result['originalSetupClean'])

    def test_unknown_owner_or_partial_observation_cannot_pass(self):
        values=self.fixture();values['owners']['stage']['state']='unknown'
        self.assertEqual(API['classify'](**values)['phase'],'review_required')
        for change in ({'current':{'observed':False}}, {'issues':[{'record':'runner'}]},
                       {'resources':{'observed':True,'archiveState':'conflict'}}):
            self.assertEqual(API['classify'](**{**self.fixture(),**change})['phase'],'review_required')

    def test_archive_witnesses_prevent_clean_even_when_status_file_checks_pass(self):
        for state in ('install-staged','installed','rollback-staged','restored'):
            values=self.fixture();values['resources']['archiveState']=state
            result=API['classify'](**values)
            self.assertEqual(result['phase'],'recovery_required');self.assertFalse(result['recoveryAuthorized'])
        values=self.fixture();values['resources']['pendingPresent']=True
        self.assertEqual(API['classify'](**values)['phase'],'recovery_required')

    def test_missing_retired_stage_owner_prevents_known_dirty_recovery(self):
        values=self.fixture();values['current']['currentSetupClean']=False
        for state in ('not_recorded','unknown'):
            values['owners']['stage']['state']=state
            self.assertEqual(API['classify'](**values)['phase'],'review_required')

    def test_broker_retirement_is_separate_from_retired_wrapper_owners(self):
        values=self.fixture();values['current']['currentSetupClean']=False;values['broker_retired']=False
        result=API['classify'](**values)
        self.assertEqual(result['phase'],'broker_retirement_required');self.assertFalse(result['recoveryAuthorized'])


if __name__=='__main__':unittest.main()
