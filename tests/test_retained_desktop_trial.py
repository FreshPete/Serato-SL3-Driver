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


class IdentityTests(unittest.TestCase):
    @staticmethod
    def sample(address, complete=True):
        identities = [] if address is None else [dict(vendor=0x1cc5, product=1, revision=0, bus=3, address=address)]
        return {'event':'sample','snapshot':{'complete':complete,'identities':identities}}

    def test_full_identity_distinguishes_address_and_visibility(self):
        original = DESKTOP['identity_samples']([self.sample(2),self.sample(2)])
        redirected = DESKTOP['identity_samples']([self.sample(3)])
        absent = DESKTOP['identity_samples']([self.sample(None)])
        self.assertEqual(absent['identitySets'],[[]])
        self.assertEqual(DESKTOP['compare_identity'](original,original),'same_sampled_identity_set')
        for changed in (redirected,absent):
            self.assertEqual(DESKTOP['compare_identity'](original,changed),'different_sampled_identity_set')

    def test_incomplete_or_changing_phase_is_indeterminate(self):
        original = DESKTOP['identity_samples']([self.sample(2)])
        for samples in ([self.sample(2,False)],[self.sample(2),self.sample(2,False)],
                        [self.sample(None),self.sample(2)]):
            with self.subTest(samples=samples):
                changed = DESKTOP['identity_samples'](samples)
                self.assertEqual(DESKTOP['compare_identity'](original,changed),'indeterminate')

    def test_release_observation_preserves_retirement_and_readiness_limits(self):
        original = DESKTOP['identity_samples']([self.sample(2)])
        held = DESKTOP['identity_samples']([self.sample(None)])
        previous = {'before':original,'during':held}
        result = {'outcome':'retired'}

        def observe(phase, seconds):
            self.assertEqual((phase,seconds),('after',15))
            return original

        DESKTOP['observe_release'](result,observe,previous)
        self.assertEqual(result['beforeToAfter'],'same_sampled_identity_set')
        self.assertEqual(result['duringToAfter'],'different_sampled_identity_set')
        self.assertIs(result['usbReadyForNextAcquire'],False)

        def fail(*_):
            raise OSError('USB observer failed')

        result = {'outcome':'retired'}
        DESKTOP['observe_release'](result,fail,previous)
        self.assertEqual(result['outcome'],'retired')
        self.assertEqual(result['postReleaseObservationError'],'USB observer failed')
        self.assertIs(result['usbReadyForNextAcquire'],False)


class FinishTests(unittest.TestCase):
    def finish(self, startup_bytes=None, owned=True, idle=True):
        calls = []
        result = {'schema':'sl3.retained-desktop-trial.v1'}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            startup, owner = path/'startup.json', path/'broker.pointer.json'
            if startup_bytes is not None:
                startup.write_bytes(startup_bytes)
            if owned:
                owner.touch()

            def check_idle():
                calls.append('idle')
                if not idle:
                    raise ValueError('Serato is open')

            def retire():
                calls.append('retire')
                return {'controllerExited':True}

            def observe(*_):
                calls.append('observe')
                return {'completeSamples':1,'incompleteSamples':0,'identitySets':[[]]}

            try:
                DESKTOP['finish_trial'](result,startup,owner,check_idle,retire,
                                        lambda:calls.append('restore'),observe)
            except ValueError as error:
                result['refusal'] = str(error)
        return result,calls

    def test_interrupted_record_recovers_owned_broker(self):
        for raw in (None,b'{"schema":'):
            with self.subTest(raw=raw):
                result,calls = self.finish(raw)
                self.assertEqual(result['outcome'],'retired_after_interruption')
                self.assertNotIn('duringToAfter',result)
                self.assertIs(result['usbReadyForNextAcquire'],False)
                self.assertEqual(calls,['idle','retire','restore','observe'])

    def test_absent_owner_refuses_interrupted_finish(self):
        result,calls = self.finish(owned=False)
        self.assertIn('No completed startup',result['refusal'])
        self.assertEqual(calls,[])

    def test_serato_must_close_before_interrupted_finish(self):
        result,calls = self.finish(idle=False)
        self.assertEqual(result['refusal'],'Serato is open')
        self.assertEqual(calls,['idle'])

    def test_normal_startup_still_produces_phase_comparisons(self):
        empty = {'completeSamples':1,'incompleteSamples':0,'identitySets':[[]]}
        record = {'schema':'sl3.retained-desktop-trial.v1','action':'start','outcome':'broker_ready',
                  'usbIdentity':{'before':empty,'during':empty}}
        result,calls = self.finish(json.dumps(record).encode('ascii'))
        self.assertEqual(result['outcome'],'retired')
        self.assertEqual(result['beforeToAfter'],'same_sampled_identity_set')
        self.assertEqual(calls,['idle','retire','restore','observe'])

    def test_older_startup_record_can_retire_without_phase_comparisons(self):
        raw = b'{"schema":"sl3.retained-desktop-trial.v1","action":"start","outcome":"broker_ready"}'
        result,calls = self.finish(raw)
        self.assertEqual(result['outcome'],'retired')
        self.assertNotIn('beforeToAfter',result)
        self.assertEqual(calls,['idle','retire','restore','observe'])


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
