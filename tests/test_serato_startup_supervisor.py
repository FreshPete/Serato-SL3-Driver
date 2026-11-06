import os
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/run-serato-startup-session.py'))
BUILDER = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/prepare-serato-startup-shim.py'))


class PreflightTest(unittest.TestCase):
    def test_launcher_environment_requires_bound_application_and_package(self):
        verify = MODULE['launcher_environment']
        self.assertEqual(verify(None,None,'app','bundle','a'*64),{})
        with self.assertRaisesRegex(ValueError,'Complete'):verify(Path('capsule'),None,'app','bundle','a'*64)
        record={'application':{'path':str(Path('app').absolute())},
                'bundle':{'path':str(Path('bundle').absolute()),'sha256':'a'*64}}
        with patch.object(MODULE['runpy'],'run_path',return_value={'verify':lambda *args:(record,{},Path.cwd())}):
            context=verify(Path('capsule'),'b'*64,'app','bundle','a'*64)
            self.assertEqual(context,{'SL3_SESSION_CAPSULE':str(Path('capsule').absolute()),'SL3_SESSION_CAPSULE_SHA256':'b'*64})
            with self.assertRaisesRegex(ValueError,'differs'):verify(Path('capsule'),'b'*64,'other-app','bundle','a'*64)
            with self.assertRaisesRegex(ValueError,'differs'):verify(Path('capsule'),'b'*64,'app','bundle','c'*64)

    def test_valid_plan_and_tamper_refusals_are_read_only(self):
        preflight = MODULE['preflight']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); prepared = root/'prepared'; prepared.mkdir(); bundle = root/'bundle'; bundle.mkdir()
            app = root/'Serato DJ Pro.exe'; app.write_bytes(b'synthetic, not executed')
            resources = root/'userio_resources.bin'; resources.write_bytes(b'synthetic resources')
            template = MODULE['ROOT'].joinpath('scripts/serato-sl3-startup-shim.js').read_bytes()
            # Native path matching is meaningful on the target Windows host.
            installation = Path('C:/test') if os.name == 'nt' else Path('C:\\test')
            planned = str(installation/'sl3_asio.dll').replace('/','\\')
            script = ('globalThis.SL3_SESSION_CONFIG = Object.freeze('+json.dumps({'asioPath':planned})+');\n').encode()+template
            (prepared/'startup-shim.js').write_bytes(script)
            record = {'schema':'sl3.startup-shim-preparation.v1','applicationSha256':MODULE['digest'](app),
                      'plannedAsioPath':planned,'templateSha256':hashlib.sha256(template).hexdigest(),
                      'preparedScriptSha256':hashlib.sha256(script).hexdigest()}
            manifest = prepared/'preparation.json'; manifest.write_text(json.dumps(record),encoding='utf-8')
            (bundle/'deployment-plan.json').write_text(json.dumps({'installationDirectory':str(installation)}),encoding='utf-8')
            (bundle/'bundle-manifest.json').write_text(json.dumps({'files':{'sl3_asio.dll':{'sha256':'1'*64}}}),encoding='utf-8')
            verified = []
            def modules(path):
                if Path(path).name == 'prepare-serato-startup-shim.py': return BUILDER
                return {'verify':lambda path,expected:verified.append((path,expected))}
            args = (prepared,MODULE['digest'](manifest),app,bundle,'2'*64,'3'*64)
            with patch.dict(preflight.__globals__,APP_SHA=MODULE['digest'](app),ORIGINAL_RESOURCES=MODULE['digest'](resources)), patch.object(MODULE['runpy'],'run_path',side_effect=modules):
                before = sorted(str(p.relative_to(root)) for p in root.rglob('*'))
                result = preflight(*args)
                self.assertEqual(result['resourceState'],'original')
                self.assertEqual(verified,[(bundle.absolute(),'2'*64)])
                self.assertEqual(before,sorted(str(p.relative_to(root)) for p in root.rglob('*')))
                (prepared/'startup-shim.js').write_bytes(script+b'\n// injected change')
                with self.assertRaisesRegex(ValueError,'script differs'): preflight(*args)
                (prepared/'startup-shim.js').write_bytes(script)
                with self.assertRaisesRegex(ValueError,'manifest differs'):
                    preflight(prepared,'0'*64,*args[2:])


class Clock:
    def __init__(self): self.value = 0
    def __call__(self): return self.value


class FakeBackend:
    def __init__(self, clock, messages=None, failure=None, forced=False, early_exit=False):
        self.clock, self.failure, self.forced, self.early_exit = clock, failure, forced, early_exit
        self.messages = messages if messages is not None else ['trace_ready', 'installer_action', 'asio_live_start_end']
        self.calls = []
    def start(self, script, callback):
        self.calls.append('start')
        if self.failure == 'start': raise ValueError('partial startup')
        for name in self.messages:
            callback({'type':'send','payload':{'event':name,'result':0}})
    def resume(self): self.calls.append('resume')
    def wait(self, seconds):
        self.clock.value += seconds
        return self.early_exit
    def detach(self):
        self.calls.append('detach')
        if self.failure == 'detach': raise ValueError('detach failed')
    def cleanup(self):
        self.calls.append('cleanup')
        if self.failure == 'cleanup': raise ValueError('cleanup unproved')
        return {'processExited':True,'jobEmpty':True,'observerForcedTermination':self.forced,
                'exitCode':1 if self.forced else 0}


class SupervisorTest(unittest.TestCase):
    def run_case(self, **options):
        clock = Clock(); backend = FakeBackend(clock, **options)
        checks = []
        result = MODULE['supervise'](backend, 'reviewed script', lambda:checks.append('verified'),lambda:True,clock,
                                     click_seconds=.1,start_seconds=.1,viewing_seconds=.1)
        return result,backend,checks

    def test_success_requires_driver_verification_and_full_detach_before_viewing(self):
        result,backend,checks = self.run_case()
        self.assertTrue(result['supervisionCompleted'])
        self.assertEqual(checks,['verified'])
        self.assertEqual(backend.calls,['start','resume','detach','cleanup'])
        self.assertEqual(result['endReason'],'manual_stop')

    def test_each_failure_still_runs_cleanup_and_preserves_failure(self):
        for failure in ('start','detach','cleanup'):
            with self.subTest(failure=failure):
                result,backend,_ = self.run_case(failure=failure)
                self.assertEqual(backend.calls[-1],'cleanup')
                self.assertFalse(result['supervisionCompleted'])
                self.assertTrue(result['error'] or result.get('cleanupError'))

    def test_missing_click_start_or_ready_never_bypasses_deadline(self):
        for messages in ([],['trace_ready'],['trace_ready','installer_action']):
            with self.subTest(messages=messages):
                result,backend,_ = self.run_case(messages=messages)
                self.assertFalse(result['supervisionCompleted'])
                self.assertNotIn('detach',backend.calls)
                self.assertEqual(backend.calls[-1],'cleanup')

    def test_foreign_start_event_does_not_skip_explicit_installer_action(self):
        result,backend,_ = self.run_case(messages=['trace_ready','asio_live_start_end'])
        self.assertFalse(result['supervisionCompleted'])
        self.assertNotIn('detach',backend.calls)

    def test_forced_termination_is_not_reported_as_success(self):
        result,_,_ = self.run_case(forced=True)
        self.assertTrue(result['asioStartObserved'])
        self.assertFalse(result['supervisionCompleted'])

    def test_mismatched_driver_closes_before_manual_interaction(self):
        clock = Clock(); backend = FakeBackend(clock)
        def reject(): raise ValueError('installed driver mismatch')
        result = MODULE['supervise'](backend,'script',reject,lambda:True,clock)
        self.assertFalse(result['supervisionCompleted'])
        self.assertNotIn('detach',backend.calls)
        self.assertEqual(backend.calls[-1],'cleanup')

    def test_shim_error_aborts_instead_of_reporting_ready(self):
        class ErrorBackend(FakeBackend):
            def start(self, script, callback): callback({'type':'error','description':'bad entry'})
        clock = Clock(); backend = ErrorBackend(clock)
        result = MODULE['supervise'](backend,'script',lambda:None,lambda:True,clock)
        self.assertIn('bad entry',result['error'])
        self.assertFalse(result['supervisionCompleted'])

    def test_event_publication_failure_still_retires_owned_process(self):
        clock = Clock(); backend = FakeBackend(clock)
        def refuse(event): raise OSError('event destination unavailable')
        result = MODULE['supervise'](backend,'script',lambda:None,lambda:True,clock,event_sink=refuse)
        self.assertFalse(result['supervisionCompleted'])
        self.assertEqual(backend.calls[-1],'cleanup')

    def test_hard_deadline_contains_a_blocked_supervisor_without_success_result(self):
        code = ('import runpy,sys,time; m=runpy.run_path(sys.argv[1]); '
                'guard=m["HardDeadline"](.05); time.sleep(5)')
        child = subprocess.run([sys.executable,'-c',code,str(Path(__file__).resolve().parents[1]/'scripts/run-serato-startup-session.py')],
                               capture_output=True,timeout=5)
        self.assertEqual(child.returncode,70)
        self.assertEqual(child.stdout,b'')


@unittest.skipUnless(os.name == 'nt','Win32 owned-process simulation')
class WindowsOwnershipTest(unittest.TestCase):
    def test_changed_application_never_spawns_a_process(self):
        class Device:
            def spawn(self, *args, **kwargs): raise AssertionError('Must not spawn changed application')
        frida = type('Frida',(),{'get_local_device':staticmethod(Device)})()
        backend = MODULE['WindowsProcess'](Path(sys.executable),frida,expected_application_sha='0'*64)
        with self.assertRaisesRegex(ValueError,'Application changed'):
            backend.start('script',lambda *args:None)
        self.assertIsNone(backend.pid)
        self.assertIsNone(backend.job)

    def test_actual_owned_process_normal_exit_and_forced_close_are_distinct(self):
        # The Frida interface is mocked. The Windows process/job/wait/termination
        # APIs are real; the child is this interpreter, never Serato or a driver.
        for graceful in (True, False):
            with self.subTest(graceful=graceful), tempfile.TemporaryDirectory() as temporary:
                marker = Path(temporary)/'exit.txt'
                class Script:
                    def on(self, name, callback): self.callback = callback
                    def load(self):
                        for event in ('trace_ready','installer_action','asio_live_start_end'):
                            self.callback({'type':'send','payload':{'event':event,'result':0}})
                    def unload(self): pass
                class Session:
                    def create_script(self, source): return Script()
                    def detach(self):
                        if graceful: marker.write_text('exit',encoding='utf-8')
                class Device:
                    child = None
                    def spawn(self, argv, **kwargs):
                        self.spawn_environment=kwargs['env']
                        code = 'import pathlib,sys,time; p=pathlib.Path(sys.argv[1]);\nwhile not p.exists(): time.sleep(.01)'
                        self.child = subprocess.Popen([sys.executable,'-c',code,str(marker)],creationflags=subprocess.CREATE_NO_WINDOW)
                        return self.child.pid
                    def attach(self, pid):
                        self.assert_pid = pid
                        return Session()
                    def resume(self, pid): pass
                device = Device()
                frida = type('Frida',(),{'get_local_device':staticmethod(lambda:device)})()
                try:
                    backend = MODULE['WindowsProcess'](Path(sys.executable),frida,expected_application_sha=MODULE['digest'](sys.executable))
                    result = MODULE['supervise'](backend,'synthetic script',lambda:None,lambda:not graceful,
                                                viewing_seconds=2)
                    device.child.wait(timeout=5)
                    self.assertTrue(result['process']['processExited'])
                    self.assertTrue(result['process']['jobEmpty'])
                    self.assertEqual(result['process']['observerForcedTermination'],not graceful)
                    self.assertEqual(result['process']['exitCode'],0 if graceful else 1)
                    self.assertEqual(result['supervisionCompleted'],graceful)
                    self.assertTrue(result['tracerDetached'])
                    self.assertEqual(device.spawn_environment,{'SL3_ASIO_PRIVATE_TRACE':'0',
                        'SL3_SESSION_CAPSULE':'','SL3_SESSION_CAPSULE_SHA256':''})
                finally:
                    if device.child is not None and device.child.poll() is None:
                        device.child.kill();device.child.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
