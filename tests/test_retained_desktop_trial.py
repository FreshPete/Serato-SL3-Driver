"""Check the retained desktop window and rollback decisions without touching USB."""

from contextlib import contextmanager
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
DESKTOP = runpy.run_path(str(SCRIPTS/'retained-desktop-trial.py'))
EXPERIMENT = 'a'*64


class StartupTests(unittest.TestCase):
    def trial(self, before=True, during=True, fail_start=False, fail_retire=False, fail_record=False):
        calls = []

        def snapshot(phase):
            calls.append(phase)
            value = before if phase=='before' else during
            if isinstance(value, Exception):
                raise value
            return value

        def start():
            calls.append('start')
            if fail_start:
                raise RuntimeError('acquisition failed')
            return {'controllerPid':23}

        def retire():
            calls.append('retire')
            if fail_retire:
                raise RuntimeError('retirement unverified')
            return {'controllerExited':True}

        def record(_):
            calls.append('record')
            if fail_record:
                raise OSError('record failed')

        result = DESKTOP['start_trial'](snapshot,start,retire,lambda:calls.append('restore'),record)
        return result,calls

    def test_identity_can_disappear_under_broker(self):
        result,calls = self.trial(during=False)
        self.assertEqual(result['outcome'],'broker_ready')
        self.assertIs(result['sl3VisibleDuring'],False)
        self.assertEqual(calls,['before','start','during','record'])

    def test_incomplete_snapshot_remains_unknown(self):
        result,calls = self.trial(during=None)
        self.assertIsNone(result['sl3VisibleDuring'])
        self.assertEqual(calls,['before','start','during','record'])

    def test_no_visible_device_never_attempts_start(self):
        result,calls = self.trial(before=False)
        self.assertEqual(result['outcome'],'startup_failed')
        self.assertEqual(calls,['before','restore'])

    def test_failed_start_leaves_unconfirmed_owner_to_existing_guard(self):
        result,calls = self.trial(fail_start=True)
        self.assertIn('acquisition failed',result['error'])
        self.assertEqual(calls,['before','start','restore'])

    def test_observer_failure_retires_started_broker(self):
        result,calls = self.trial(during=OSError('observer failed'))
        self.assertIs(result['retirement']['controllerExited'],True)
        self.assertEqual(calls,['before','start','during','retire','restore'])

    def test_failed_ready_record_requests_restore_even_if_retirement_fails(self):
        result,calls = self.trial(fail_record=True,fail_retire=True)
        self.assertIn('record failed',result['error'])
        self.assertIn('retirement unverified',result['retirementError'])
        self.assertEqual(calls,['before','start','during','record','retire','restore'])


@unittest.skipUnless(sys.platform=='win32','Windows process handles required')
class WindowTests(unittest.TestCase):
    def test_exact_child_window_is_admitted_only_while_live(self):
        broker = runpy.run_path(str(SCRIPTS/'asio-diagnostic-session.py'))
        handle = broker['process_handle']
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            receipt = folder/'setup-stdout.json'
            receipt.write_text(json.dumps({'schema':'sl3.on-demand-test-action.v1','action':'setup',
                'successful':True,'after':{'archive':'installed','native':{'state':'installed'}}}),encoding='utf-8')
            publish = ('import runpy,sys; from pathlib import Path; '
                       'module=runpy.run_path(str(Path(sys.argv[1])/"retained-setup-handoff.py")); '
                       'broker=runpy.run_path(str(Path(sys.argv[1])/"asio-diagnostic-session.py")); '
                       'module["publish_window"](Path(sys.argv[2]),sys.argv[3],broker["process_handle"]); '
                       'sys.stdin.read()')
            with subprocess.Popen([sys.executable,'-I','-B','-c',publish,str(SCRIPTS),temp,EXPERIMENT],
                                  stdin=subprocess.PIPE) as child:
                window = folder/'window.json'
                deadline = time.monotonic()+10
                try:
                    while not window.exists() or window.stat().st_size==0:
                        self.assertIsNone(child.poll())
                        self.assertLess(time.monotonic(),deadline)
                        time.sleep(.025)
                    with DESKTOP['open_window'](folder,EXPERIMENT,handle,170) as check:
                        check(135)
                        with self.assertRaisesRegex(ValueError,'too close'):
                            check(241)
                        (folder/'restore.request').touch()
                        with self.assertRaisesRegex(ValueError,'closing'):
                            check()
                        (folder/'restore.request').unlink()
                    @contextmanager
                    def wrong_creation(pid):
                        with handle(pid) as exact:
                            yield exact[0]+1,exact[1]
                    with self.assertRaisesRegex(ValueError,'exact administrator handoff'):
                        with DESKTOP['open_window'](folder,EXPERIMENT,wrong_creation):
                            self.fail('Wrong creation time accepted')
                    with receipt.open('a',encoding='utf-8') as stream:
                        stream.write(' ')
                    with self.assertRaisesRegex(ValueError,'Setup receipt hash differs'):
                        with DESKTOP['open_window'](folder,EXPERIMENT,handle):
                            self.fail('Changed receipt accepted')
                    receipt.write_text(receipt.read_text(encoding='utf-8').rstrip(),encoding='utf-8')
                finally:
                    child.stdin.close()
                    child.wait(timeout=10)
            with self.assertRaisesRegex(ValueError,'exact administrator handoff'):
                with DESKTOP['open_window'](folder,EXPERIMENT,handle):
                    self.fail('Retired process accepted')


if __name__=='__main__':
    unittest.main()
