"""Test stop dispatch with owned headless children and synthetic startup events."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def exercise(reference, expected, powershell, launcher=None):
    assert sha(reference) == expected
    prior = json.loads(reference.read_bytes())
    capsule_builder = runpy.run_path(str(ROOT / 'scripts/prepare-serato-session-capsule.py'))
    plan_api = runpy.run_path(str(ROOT / 'scripts/prepare-serato-session-plan.py'))
    stop = runpy.run_path(str(ROOT / 'scripts/serato-session-stop.py'))
    host = runpy.run_path(str(ROOT / 'scripts/run-serato-startup-session.py'))
    tag = uuid.uuid4().hex
    directory = ROOT / 'analysis' / ('sl3-session-capsule-stop-fixture-' + tag)
    made = capsule_builder['prepare'](prior['application']['path'], prior['nativeBundle']['path'],
                                       prior['nativeBundle']['sha256'], directory)
    plan = plan_api['construct'](made['capsule'], made['capsuleSha256'], prior['preparedShim']['path'],
        prior['preparedShim']['sha256'], prior['archiveSource']['path'], prior['installerResource']['path'],
        prior['launcher']['path'], prior['fridaDirectory'])
    configuration = directory / 'session-plan.json'
    configuration.write_text(json.dumps(plan, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    identity = sha(configuration)
    output = Path(plan['hostOutput']); output.mkdir()
    script_manifest = json.loads((Path(plan['preparedShim']['path']) / 'preparation.json').read_bytes())
    intent = {'schema': 'sl3.startup-supervisor-intent.v1', 'applicationSha256': plan['application']['sha256'],
              'scriptSha256': script_manifest['preparedScriptSha256'], 'preparationSha256': plan['preparedShim']['sha256'],
              'deploymentManifestSha256': plan['nativeBundle']['sha256'], 'requiresExternalRollback': True,
              'hardDeadlineSeconds': 840, 'launcherCapsuleBound': True,
              'launcherCapsuleSha256': plan['capsule']['sha256'], 'supervisorOwner': stop['current_owner'](Path(sys.executable))}
    intent_path = output / 'intent.json'; intent_path.write_text(json.dumps(intent), encoding='utf-8')
    # This is an owned ordinary-token runner fixture, never the session wrapper.
    owner_code = '''$ErrorActionPreference='Stop'
$taskDirectory=[Environment]::GetEnvironmentVariable('SL3_STOP_FIXTURE_DIRECTORY')
$taskOwner=@{runner=@{pid=$PID;created=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToFileTimeUtc().ToString()}}
[IO.File]::WriteAllText((Join-Path $taskDirectory 'session-run.lock'),($taskOwner|ConvertTo-Json -Depth 4))
$taskLimit=[Environment]::TickCount64+60000
while(-not(Test-Path -LiteralPath (Join-Path $taskDirectory 'owner-exit.txt')) -and [Environment]::TickCount64 -lt $taskLimit){Start-Sleep -Milliseconds 20}
'''
    environment = os.environ.copy(); environment['SL3_STOP_FIXTURE_DIRECTORY'] = str(directory)
    owner = subprocess.Popen([str(powershell / 'pwsh.exe'), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', owner_code],
                              env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    cases = []

    def passed(name):
        cases.append({'name': name, 'passed': True})

    def refused(name, function, message):
        try:
            function()
        except (ValueError, OSError) as error:
            assert message in str(error), (name, str(error))
        else:
            raise AssertionError('Unexpected stop acceptance: ' + name)
        assert not (output / 'stop.txt').exists()
        passed(name)

    try:
        deadline = time.monotonic() + 8
        while True:
            try:
                owner_record = json.loads((directory / 'session-run.lock').read_bytes()); break
            except (OSError, ValueError):
                assert owner.poll() is None and time.monotonic() < deadline
                time.sleep(.02)
        planned = stop['request'](configuration, identity, powershell)
        assert planned['liveOwnersVerified'] and planned['planOnly'] and not (output / 'stop.txt').exists()
        passed('live-owned-processes-read-only-stop-plan')
        lock = directory / 'session-run.lock'; original_lock = lock.read_bytes()
        changed = json.loads(original_lock); changed['runner']['created'] = '0'
        try:
            lock.write_text(json.dumps(changed), encoding='utf-8')
            refused('stale-runner-creation-refused', lambda: stop['request'](configuration, identity, powershell, True),
                    'creation differs')
        finally:
            lock.write_bytes(original_lock)
        other = directory / 'other-runner-image'; other.mkdir(); shutil.copyfile(powershell / 'pwsh.exe', other / 'pwsh.exe')
        refused('different-runner-file-identity-refused', lambda: stop['request'](configuration, identity, other, True),
                'image differs')
        original_intent = intent_path.read_bytes()
        changed = json.loads(original_intent); changed['deploymentManifestSha256'] = '0' * 64
        try:
            intent_path.write_text(json.dumps(changed), encoding='utf-8')
            refused('foreign-supervisor-intent-refused', lambda: stop['request'](configuration, identity, powershell, True),
                    'intent differs')
        finally:
            intent_path.write_bytes(original_intent)
        result_path = output / 'result.json'
        try:
            result_path.write_bytes(b'{}')
            refused('finished-session-result-preserved', lambda: stop['request'](configuration, identity, powershell, True),
                    'already finished')
            assert result_path.read_bytes() == b'{}'
        finally:
            result_path.unlink()
        sys.path.insert(0, str(Path(plan['python']['path']).parent / 'packages'))
        import frida
        manager = frida.DeviceManager(); real = manager.get_local_device(); application = Path(sys.executable)
        exit_marker = output / 'child-exit.txt'
        child_code = 'import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); limit=time.monotonic()+30\nwhile not p.exists() and time.monotonic()<limit: time.sleep(.01)'
        class Device:
            def spawn(self, argv, **kwargs):
                assert argv == [str(application)]
                return real.spawn([str(application), '-I', '-B', '-c', child_code, str(exit_marker)], **kwargs)
            def attach(self, pid): return real.attach(pid)
            def resume(self, pid): return real.resume(pid)
        managed = type('Manager', (), {'get_local_device': staticmethod(Device), 'close': staticmethod(manager.close)})()
        wrapped = type('OwnedHeadlessFrida', (), {'DeviceManager': staticmethod(lambda: managed)})()
        class Backend(host['WindowsProcess']):
            def cleanup(self):
                # Headless fixture cooperates on a marker; this does not test
                # Serato's WM_CLOSE handler or claim its graceful shutdown.
                exit_marker.write_text('exit', encoding='utf-8')
                if self.handle:
                    self.wait(5)
                return super().cleanup()
        backend = Backend(application, wrapped, expected_application_sha=sha(application))
        requested = []
        def stop_requested():
            if backend.session is None and backend.handle is not None and not requested:
                if launcher is None:
                    requested.append(stop['request'](configuration, identity, powershell, True))
                else:
                    response=subprocess.run([str(launcher),'--stop-session','--session-plan',str(configuration),
                        '--expected-session-plan-sha256',identity,'--powershell-directory',str(powershell)],
                        capture_output=True,text=True,encoding='utf-8',timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
                    assert response.returncode==0,(response.stdout,response.stderr)
                    requested.append(json.loads(response.stdout))
            return stop['read_request'](output / 'stop.txt', plan['capsule']['sha256'], sha(intent_path), intent['supervisorOwner'])
        synthetic = "send({event:'trace_ready'});send({event:'installer_action'});send({event:'asio_live_start_end',result:0});"
        observed = host['supervise'](backend, synthetic, lambda: None, stop_requested, viewing_seconds=5)
        assert requested and requested[0]['stopRequested'] is True and requested[0]['shutdownConfirmed'] is False
        assert observed['endReason'] == 'manual_stop' and observed['supervisionCompleted'] is True
        assert observed['tracerDetached'] is True and observed['process']['exitCode'] == 0
        assert observed['instrumentationManagerClosedBeforeViewing'] is True
        assert observed['process']['instrumentationManagerClosed'] is True
        assert observed['process']['jobEmpty'] and not observed['process']['observerForcedTermination']
        passed('atomic-stop-observed-by-real-owned-headless-child-supervisor')
        before = (output / 'stop.txt').read_bytes()
        again = stop['request'](configuration, identity, powershell, True)
        assert again['stopAlreadyRequested'] is True and (output / 'stop.txt').read_bytes() == before
        passed('repeat-stop-is-idempotent')
        try:
            stop['read_request'](output / 'stop.txt', '0' * 64, sha(intent_path), intent['supervisorOwner'])
        except ValueError as error:
            assert 'another session' in str(error)
        else:
            raise AssertionError('Foreign stop request accepted')
        passed('foreign-capsule-stop-record-refused')
    finally:
        (directory / 'owner-exit.txt').write_text('exit', encoding='utf-8')
        try:
            stdout, stderr = owner.communicate(timeout=8)
            assert owner.returncode == 0, (stdout, stderr)
        except subprocess.TimeoutExpired:
            owner.kill(); owner.communicate(timeout=5)
            raise
    report = {'schema': 'sl3.session-stop-channel-tests.v1', 'cases': cases, 'actualFridaUsed': True,
              'syntheticStartupEvents': True, 'ownedHeadlessChildOnly': True, 'normalFixtureExit': True,
              'forcedFixtureTermination': False, 'sessionPlanSha256': identity, 'fridaVersion': frida.__version__,
              'nativeStopEntryUsed':launcher is not None,
              'vendorApplicationExecuted': False, 'packageBinaryLoaded': False, 'deviceAccess': False,
              'registryWritten': False, 'elevationRequested': False, 'seratoShutdownValidated': False}
    (directory / 'fixture-complete.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-plan', type=Path, required=True)
    parser.add_argument('--expected-reference-sha256', required=True)
    parser.add_argument('--powershell', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--launcher',type=Path)
    args = parser.parse_args()
    result = exercise(args.reference_plan.absolute(), args.expected_reference_sha256, args.powershell.absolute(),
                      args.launcher.absolute() if args.launcher else None)
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(result, indent=2))
