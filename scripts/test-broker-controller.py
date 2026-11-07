"""Actual controller/publication/ASIO processes. Positive cases are simulated only."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid


def require(value, reason):
    if not value:
        raise AssertionError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def call(args, expected=0, timeout=15):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True,
                            encoding='utf-8', timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == expected, f'{args[0]}: code {result.returncode}\n{result.stdout}\n{result.stderr}')
    return result


def process_identity(process):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    times = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(int(process._handle), *(ctypes.byref(value) for value in times)):
        raise ctypes.WinError(ctypes.get_last_error())
    created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    return f'{process.pid}:{created}'


def unmeasured(production, simulated, worker, helper, client, library):
    with tempfile.TemporaryDirectory(prefix='sl3-unmeasured-') as temporary:
        root = Path(temporary).resolve()
        timing = root / 'timing.txt'
        timing.write_bytes(
            f'SL3-ASIO-DIAGNOSTIC-TIMING-1\nworker_sha256={sha(worker)}\n'
            f'helper_sha256={sha(helper)}\nrate_hz=44100\nbuffer_frames=128\n'.encode())
        config = root / 'input.conf'
        config.write_bytes(
            f'SL3-ASIO-CONFIG-1\nworker={worker}\nworker_sha256={sha(worker)}\nhelper={helper}\n'
            f'timing_record={timing}\ntiming_record_sha256={sha(timing)}\n'.encode())
        before = sorted(p.name for p in root.iterdir())
        inspection = json.loads(call([simulated, '--inspect-input', '--input', config]).stdout)
        require(inspection['rateHz'] == 44100 and inspection['bufferFrames'] == 128
                and inspection['latencyAvailable'] is False and inspection['deviceAccess'] is False
                and inspection['workerSha256'] == sha(worker), 'Unmeasured input preflight')
        require(sorted(p.name for p in root.iterdir()) == before, 'Input inspection creates no files')
        output = root / 'session'
        args = ['--run', '--input', config, '--output', output, '--limit-ms', 10000]
        call([production, *args], expected=1)
        require(not output.exists(), 'Production must refuse diagnostic input before creating a session')
        proc = subprocess.Popen([str(x) for x in (simulated, *args)], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            ready_path = output / 'ready.json'
            deadline = time.monotonic() + 8
            while not ready_path.exists():
                require(proc.poll() is None and time.monotonic() < deadline, 'Simulated broker readiness')
                time.sleep(.02)
            ready = load(ready_path)
            require(ready['controllerPid'] == proc.pid and ready['rateHz'] == 44100
                    and ready['kind'] == 'simulated' and proc.poll() is None, 'Bound 44.1 kHz session')
            published = output / 'sl3-asio.conf'
            require(ready['configSha256'] == sha(published), 'Verified published config hash')
            pointer = root / 'session-pointer.txt'
            args = ['--publish-pointer', '--config', published, '--pointer', pointer]
            call([production, *args], expected=1)
            require(not pointer.exists(), 'Production must refuse diagnostic pointer publication')
            call([simulated, *args])
            locator = root / 'sl3-asio.conf'
            locator.write_bytes(
                f'SL3-ASIO-LOCATOR-1\nsession_pointer={pointer}\nbroker={simulated}\n'
                f'broker_sha256={sha(simulated)}\nworker_sha256={sha(worker)}\n'.encode())
            call([client, '--published', locator, library, 'unmeasured'])
            call([simulated, '--withdraw-pointer', '--pointer', pointer, '--sha256', sha(pointer)])
            require(not pointer.exists(), 'Explicit diagnostic pointer withdrawal')
            call([simulated, '--stop', '--config', published])
            stdout, stderr = proc.communicate(timeout=12)
            require(proc.returncode == 0, f'Unmeasured controller retirement: {stdout}\n{stderr}')
            final = load(output / 'result.json')
            require(final['processExited'] and final['jobEmpty'] and not final['nativeDeviceAcquired']
                    and not final['helperLoadedInController'], 'Simulated worker exits with no native access')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate(timeout=5)
        coordinator = Path(__file__).with_name('asio-diagnostic-session.py')
        args = ['--controller', simulated, '--controller-sha256', sha(simulated),
                '--session', root / 'coordinated', '--pointer', pointer]
        started = json.loads(call([sys.executable, coordinator, 'start', *args, '--input', config]).stdout)
        require(started['pointerPublished'] and pointer.is_file(), 'Separate coordinator publishes exact pointer')
        for _ in range(2):
            final = json.loads(call([sys.executable, coordinator, 'stop', *args]).stdout)
            require(final['successful'] and final['jobEmpty'] and final['controllerExited'] and not pointer.exists(),
                    'Separate coordinator retires worker and accepts cleanup retry')
        call([sys.executable, coordinator, 'start', *args, '--input', config], expected=1)
        never_started = root / 'never-started'
        args[5] = never_started
        closed = json.loads(call([sys.executable, coordinator, 'stop', *args]).stdout)
        require(closed == {'controllerExited': True, 'brokerStarted': False}, 'Cleanup can close an unused handoff')
        call([sys.executable, coordinator, 'start', *args, '--input', config], expected=1)
        require(not never_started.exists() and not pointer.exists(), 'Closed handoff refuses a delayed launcher')
    print('Simulated 44.1 kHz diagnostic ASIO callbacks, pointer withdrawal and worker retirement passed')


def main():
    if len(sys.argv) == 8 and sys.argv[1] == '--unmeasured':
        unmeasured(*(Path(x).resolve() for x in sys.argv[2:]))
        return
    require(len(sys.argv) == 7, 'native/simulated controller, worker, helper, ASIO client and fixture DLL required')
    native, simulated, worker, helper, client, library = [Path(x).resolve() for x in sys.argv[1:]]
    for path in (native, simulated, worker, helper, client, library):
        require(path.is_file(), f'Missing reviewed test input: {path.name}')
    require(sha(helper) == '66bbfe6f99b417f97c7a9e97816e24af7dde0e01b8e535c41e91e1c6c19cfeda', 'Reviewed helper bytes required; never loaded here')
    root = native.parent.parent/'controller-lifecycle-artifacts'/uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    before = sorted(p.name for p in root.iterdir())
    for executable, mode in ((native, 'native'), (simulated, 'simulated')):
        for suffix in ([], ['--plan']):
            plan = json.loads(call([executable, *suffix]).stdout)
            require(plan['kind'] == mode and plan['planOnly'] is True and plan['deviceAccess'] is False and
                    plan['filesWritten'] is False and plan['helperLoaded'] is False, 'Inert default controller plan')
    require(sorted(p.name for p in root.iterdir()) == before, 'Default plan creates no session files')
    measurement = root/'measurement.txt'
    measurement.write_text('SYNTHETIC CONTROLLER TEST ONLY. No physical measurement or approval.\n', encoding='utf-8')

    def config(rate, version=1):
        timing = root/f'timing-{rate}-v{version}.txt'
        timing.write_text(f'SL3-ASIO-TIMING-{version}\nreview=approved\nworker_sha256={sha(worker)}\nhelper_sha256={sha(helper)}\n'
                          f'rate_hz={rate}\nbuffer_frames=128\nintervals=8\nrequests_per_direction=4\ninput_extra_frames=7\noutput_extra_frames=11\n'
                          f'measurement_file={measurement}\nmeasurement_sha256={sha(measurement)}\n', encoding='utf-8')
        file = root/f'input-{rate}-v{version}.conf'
        file.write_text(f'SL3-ASIO-CONFIG-1\nworker={worker}\nworker_sha256={sha(worker)}\nhelper={helper}\n'
                        f'timing_record={timing}\ntiming_record_sha256={sha(timing)}\n', encoding='utf-8')
        return file

    normal, wrong_rate = config(48000), config(44100)
    cases = []

    def command(executable, input_file, output, limit=10000):
        return [str(x) for x in (executable, '--run', '--input', input_file, '--output', output, '--limit-ms', limit)]

    def finish_case(output, proc, expected):
        stdout, stderr = proc.communicate(timeout=15)
        (output/'captured-stdout.txt').write_text(stdout, encoding='utf-8')
        (output/'captured-stderr.txt').write_text(stderr, encoding='utf-8')
        require(proc.returncode == expected, f'Controller final code {proc.returncode}\n{stdout}\n{stderr}')
        result = load(output/'result.json')
        require(result['kind'] == 'simulated' and result['nativeDeviceAcquired'] is False and result['helperLoadedInController'] is False,
                'Simulation never becomes native evidence')
        require(result['usbReadyForNextAcquire'] is False and result['rateRestorationVerified'] is False, 'No inferred readiness/restoration')
        require(result['processExited'] is True and result['jobEmpty'] is True, 'Actual worker/job retirement')
        require(isinstance(result['connectionDiagnostic'], str) and len(result['connectionDiagnostic']) <= 512,
                'Bounded connection diagnostic must survive final publication')
        return result

    def application_bound(interrupted):
        name = 'application-exits-streaming' if interrupted else 'application-exits-after-reopens'
        output = root/name
        published = output/'sl3-asio.conf'
        gate = root/f'{name}.go'
        mode = 'ordinary-sta-withdrawal' if interrupted else 'ordinary-sta'
        app = subprocess.Popen([str(x) for x in (client, '--await-published', published, library, mode, gate)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
                               creationflags=subprocess.CREATE_NO_WINDOW)
        controller = None
        try:
            identity = process_identity(app)
            args = command(simulated, normal, output, 20000)
            if not interrupted:
                for bad in (str(app.pid), f'{app.pid}:1', '4294967296:1'):
                    call([*args, '--application-process', bad], expected=1)
                    require(not output.exists(), 'Wrong application identity refused before session creation')
            controller = subprocess.Popen([*args, '--application-process', identity], stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True, encoding='utf-8',
                                          creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic()+8
            while not (output/'ready.json').exists():
                require(controller.poll() is None and app.poll() is None and time.monotonic()<deadline,
                        'Application-bound controller readiness')
                time.sleep(.01)
            require(load(output/'intent.json')['applicationBound'] is True, 'Bound lifetime recorded')
            if not interrupted:
                call([client, '--published', published, library, 'ordinary-sta'], expected=1)
                require(controller.poll() is None, 'Out-of-process refusal preserves the bound broker')
            gate.touch(exist_ok=False)
            if interrupted:
                deadline = time.monotonic()+8
                while not (output/'client-running.txt').exists():
                    require(controller.poll() is None and app.poll() is None and time.monotonic()<deadline,
                            'Bound application callback barrier')
                    time.sleep(.01)
                app.kill()
            stdout, stderr = app.communicate(timeout=12)
            (output/'application-stdout.txt').write_text(stdout, encoding='utf-8')
            (output/'application-stderr.txt').write_text(stderr, encoding='utf-8')
            require((app.returncode != 0) if interrupted else (app.returncode == 0),
                    f'Application exit matches scenario: {stdout} {stderr}')
            final = finish_case(output, controller, 1 if interrupted else 0)
            require(final['applicationExitObserved'] and not final['lifetimeExpired'], 'Exact app exit observed before lifetime cap')
            observations = final['clientObservations']
            expected_starts = [0, 1] if interrupted else [0, 2, 2]
            require(final['clientObservationsTruncated'] is False and
                    [row['streamStartReplies'] for row in observations] == expected_starts and
                    all(row['pid'] == app.pid and row['creationFileTimeUtc'] == identity.split(':', 1)[1] and
                        row['admissionReplySent'] is True for row in observations),
                    'Exactly the authenticated host supplies the admitted enumeration and streaming objects')
            require([row['detachAcknowledged'] for row in observations] ==
                    ([True, False] if interrupted else [True, True, True]), 'Detach requires the actual terminal acknowledgement')
            audit = (output/'worker-audit.txt').read_text().splitlines()
            require(audit.count('acquire') == 1 and audit.count('release') == 1, 'One acquisition and release')
            if interrupted:
                require(final['failed'] and not final['successful'] and final['ownerFailureCode'] != 'none' and
                        final['deviceReleasedVerified'] and final['ioRetiredVerified'],
                        'Interrupted stream retains the ownership failure separately from worker retirement')
            else:
                require(final['reason'] == 'application_exit' and final['successful'] and
                        final['deviceReleasedVerified'] and final['ioRetiredVerified'] and
                        audit.count('begin') == audit.count('end') == 4,
                        'Four streams through three ASIO objects share one application-bound controller')
                call([*command(simulated, normal, root/'exited-application'), '--application-process', identity], expected=1)
                require(not (root/'exited-application').exists(), 'Exited application cannot start a controller')
        finally:
            for process in (app, controller):
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)
        cases.append({'name':name, 'passed':True, 'result':final})

    application_bound(False)
    application_bound(True)

    def active(name, mode='ordinary', lifetime=10000):
        output = root/name
        proc = subprocess.Popen(command(simulated, normal, output, lifetime), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic()+10
            while not (output/'ready.json').exists():
                require(proc.poll() is None, 'Controller must remain alive until ready publication')
                require(time.monotonic() < deadline, 'Controller ready deadline')
                time.sleep(.01)
            ready = load(output/'ready.json')
            require(proc.poll() is None and ready['kind'] == 'simulated' and ready['controllerPid'] == proc.pid,
                    'Ready snapshot belongs to confirmed live controller process')
            require(ready['brokerSha256'] == sha(simulated) and ready['workerSha256'] == sha(worker) and ready['rateHz'] == 48000,
                    'Published executable/worker/clock consistency')
            published = output/'sl3-asio.conf'
            require(ready['configSha256'] == sha(published) and ready['recordSha256'] == sha(output/'broker-session.txt'), 'Published record/config digest binding')
            require(ready['recordSha256'] == sha(output/'startup-stop.txt'), 'Startup stop record binds the same controller')
            try:
                with published.open('r+b'):
                    pass
            except PermissionError:
                pass
            else:
                raise AssertionError('Published configuration must stay write locked')
            require('SL3-ASIO-BROKER-CONFIG-1' in published.read_text(), 'Separate reviewed broker format')
            entry = published
            if mode in ('ordinary-sta', 'ordinary-mta', 'ordinary-sta-withdrawal'):
                deployment = root/f'{name}-deployment'; deployment.mkdir()
                pointer = root/f'{name}-current-session.txt'
                publication = json.loads(call([native, '--publish-pointer', '--config', published, '--pointer', pointer]).stdout)
                require(publication['pointerPublished'] and not publication['replaced'] and not publication['deviceAccess'] and not publication['deviceReadinessVerified'], 'Explicit pointer publication changes metadata only')
                original_pointer = pointer.read_bytes()
                call([native, '--publish-pointer', '--config', published, '--pointer', pointer], expected=1)
                require(pointer.read_bytes() == original_pointer and not Path(str(pointer)+'.pending').exists(), 'Publisher refuses existing pointer without changing bytes')
                entry = deployment/'sl3-asio.conf'
                entry.write_text(f'SL3-ASIO-LOCATOR-1\nsession_pointer={pointer}\nbroker={simulated}\nbroker_sha256={sha(simulated)}\nworker_sha256={sha(worker)}\n', encoding='utf-8')
            if mode == 'ordinary-sta-withdrawal':
                running = subprocess.Popen([str(x) for x in [client, '--published', entry, library, mode]], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    deadline = time.monotonic()+5
                    while not (deployment/'client-running.txt').exists():
                        require(running.poll() is None and proc.poll() is None, 'Both exact processes live before active withdrawal')
                        require(time.monotonic() < deadline, 'Actual callback barrier deadline')
                        time.sleep(.005)
                    (deployment/'pointer-before-withdrawal.txt').write_bytes(original_pointer)
                    receipt = json.loads(call([native, '--withdraw-pointer', '--pointer', pointer, '--sha256', sha(pointer)]).stdout)
                    (deployment/'withdrawal-live.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
                    require(receipt['pointerDeletionMarked'] and receipt['pointerAbsentObserved'] and not receipt['deviceAccess'] and not receipt['brokerStopped'] and not pointer.exists(), 'Exact pointer withdrawal does not stop live broker')
                    require(proc.poll() is None and running.poll() is None, 'Broker and callback host remain live after pointer withdrawal')
                    call([client, '--published', entry, library, 'ordinary-sta'], expected=1)
                    call([native, '--publish-pointer', '--config', published, '--pointer', pointer])
                    require(pointer.read_bytes() == original_pointer, 'Explicit create-new publication after verified withdrawal')
                    (deployment/'client-resume.txt').write_text('continue existing attachment\n', encoding='utf-8')
                    stdout, stderr = running.communicate(timeout=10)
                    require(running.returncode == 0, f'Existing COM/audio client must survive withdrawal/publication: {stdout} {stderr}')
                    response = subprocess.CompletedProcess([], running.returncode, stdout, stderr)
                finally:
                    if running.poll() is None:
                        running.kill(); running.communicate(timeout=5)
            else:
                response = call([client, '--published', entry, library, mode])
            (output/'asio-client-stdout.txt').write_text(response.stdout, encoding='utf-8')
            (output/'asio-client-stderr.txt').write_text(response.stderr, encoding='utf-8')
            if mode.startswith('ordinary'):
                stop = json.loads(call([native, '--stop', '--config', published]).stdout)
                require(stop['stopRequested'] is True and stop['deviceReleasedVerified'] is False, 'Stop is only a request')
                final = finish_case(output, proc, 0)
                require(final['successful'] is True and final['reason'] == 'stop_requested' and final['published'] is True and
                        final['snapshotValid'] is True and final['ioRetiredVerified'] is True and final['deviceReleasedVerified'] is True and not final['failed'], 'Idle stop verified independently')
                require(final['ownerFailureCode'] == 'none' and not final['connectionDiagnostic'],
                        'Ordinary stop must not fabricate an ownership failure')
            else:
                final = finish_case(output, proc, 1)
                require(not final['successful'] and final['failed'] and final['reason'] == 'owner_failure', 'Destructive client release preserves owner failure')
                require(final['ownerFailureCode'] != 'none', 'Destructive release must preserve a typed first failure')
            audit = (output/'worker-audit.txt').read_text().splitlines()
            require(audit.count('acquire') == 1 and audit.count('release') == 1, 'No controller reacquisition loop')
            if mode.startswith('ordinary'):
                require(audit.count('rate') == 8 and audit.count('begin') == 4 and audit.count('end') == 4, 'Three ordinary COM objects/four SDK streams retain one worker')
                observations = final['clientObservations']
                require(final['clientObservationsTruncated'] is False and
                        [row['streamStartReplies'] for row in observations] == [0, 2, 2] and
                        len({(row['pid'], row['creationFileTimeUtc']) for row in observations}) == 1 and
                        all(row['admissionReplySent'] is True and row['detachAcknowledged'] is True and
                            int(row['creationFileTimeUtc']) > 0 for row in observations),
                        'Unbound controller distinguishes enumeration from streaming by one proved process')
            require(call([native, '--stop', '--config', published], expected=1).returncode == 1, 'Stale process record refused after exit')
            if entry != published:
                call([client, '--published', entry, library, mode], expected=1)  # Stale locator cannot reconnect.
                refused_pointer = root/f'{name}-stale-pointer.txt'
                call([native, '--publish-pointer', '--config', published, '--pointer', refused_pointer], expected=1)
                require(not refused_pointer.exists() and not Path(str(refused_pointer)+'.pending').exists(), 'Stale broker refusal publishes no pointer')
                if mode == 'ordinary-sta-withdrawal':
                    receipt = json.loads(call([native, '--withdraw-pointer', '--pointer', pointer, '--sha256', sha(pointer)]).stdout)
                    (deployment/'withdrawal-stale.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
                    require(receipt['pointerAbsentObserved'] and not pointer.exists(), 'Stale pointer withdrawal does not need target process')
            cases.append({'name': name, 'passed': True, 'kind': 'simulated', 'activation': mode})
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate(timeout=5)

    active('ordinary-session')
    active('com-sta-session', 'ordinary-sta')
    active('com-mta-session', 'ordinary-mta')
    active('com-live-withdrawal', 'ordinary-sta-withdrawal')
    active('blocked-client', 'blocked')

    output = root/'lifetime-limit'
    proc = subprocess.Popen(command(simulated, normal, output, 1000), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        final = finish_case(output, proc, 0)
        require(final['successful'] and final['lifetimeExpired'] and final['reason'] == 'lifetime_limit', 'Explicit lifetime ceiling retires idle owner')
        require((output/'worker-audit.txt').read_text().splitlines() == ['acquire', 'rate', 'release'], 'Idle lifetime expiry starts no audio')
    finally:
        if proc.poll() is None:
            proc.kill(); proc.communicate(timeout=5)
    cases.append({'name': 'lifetime-limit', 'passed': True, 'kind': 'simulated'})

    for name, executable, input_file in (('wrong-rate', simulated, wrong_rate), ('native-kind-refusal', native, normal)):
        output = root/name
        outcome = call(command(executable, input_file, output), expected=1)
        (output/'captured-stdout.txt').write_text(outcome.stdout, encoding='utf-8')
        (output/'captured-stderr.txt').write_text(outcome.stderr, encoding='utf-8')
        final = load(output/'result.json')
        require(not final['successful'] and not final['published'] and not (output/'ready.json').exists() and
                not (output/'broker-session.txt').exists() and not (output/'sl3-asio.conf').exists(), 'Failed startup publishes no session/config/ready record')
        if name == 'wrong-rate':
            require(final['acquired'] and final['deviceReleasedVerified'] and 'clock differs' in final['error'], 'Clock/profile disagreement causes no setter or publication')
            require((output/'worker-audit.txt').read_text().splitlines() == ['acquire', 'rate', 'release'], 'Mismatch preserves one acquisition/final release only')
        else:
            require(final['kind'] == 'native' and not final['acquireAttempted'] and not final['acquired'] and not final['nativeDeviceAcquired'] and
                    not final['deviceReleasedVerified'], 'Native CLI refuses truthful simulated worker before acquisition; no native release inference')
        cases.append({'name': name, 'passed': True, 'positiveNativeRun': False})

    guards = root/'pointer-withdrawal-guards'; guards.mkdir()
    pointer = guards/'pointer.txt'
    good = f'SL3-ASIO-SESSION-POINTER-1\nconfiguration={guards/"missing.conf"}\nconfiguration_sha256={"0"*64}\n'.encode('utf-8')
    pointer.write_bytes(good)
    def withdraw(path, digest=None, expected=1, extra=()):
        return call([native, '--withdraw-pointer', '--pointer', path, '--sha256', digest or sha(path), *extra], expected=expected)
    withdraw(pointer, 'f'*64)
    withdraw(pointer, 'A'*64)
    withdraw(pointer, extra=['--force', 'true'])
    require(pointer.read_bytes() == good, 'Hash/option refusal preserves exact pointer')
    with pointer.open('rb'):
        withdraw(pointer)
    require(pointer.read_bytes() == good, 'Exclusive-open refusal preserves a resolving reader')
    alias = guards/'hardlink.txt'; os.link(pointer, alias)
    withdraw(pointer)
    require(pointer.read_bytes() == alias.read_bytes() == good, 'Hard-linked pointer refused without unlinking either name')
    alias.unlink()
    for bad in (b'not a pointer\n', b'', good+b'extra=1\n', b'\xef\xbb\xbf'+good, b'x'*65537):
        pointer.write_bytes(bad); withdraw(pointer)
        require(pointer.read_bytes() == bad, 'Malformed/type/size refusal preserves input bytes')
    withdraw(guards, '0'*64)
    require(guards.is_dir(), 'Directory withdrawal refused without removing it')
    pointer.write_bytes(good)
    receipt = json.loads(withdraw(pointer, expected=0).stdout)
    (guards/'withdrawal.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    require(receipt['pointerAbsentObserved'] and not pointer.exists(), 'Typed owned stale pointer removed by held handle')
    withdraw(pointer, '0'*64)
    cases.append({'name': 'pointer-withdrawal-guards', 'passed': True, 'deviceAccess': False})

    existing = root/'existing-output'; existing.mkdir(); (existing/'preserve.txt').write_text('preserve', encoding='utf-8')
    call(command(simulated, normal, existing), expected=1)
    require(list(p.name for p in existing.iterdir()) == ['preserve.txt'] and (existing/'preserve.txt').read_text() == 'preserve', 'Existing output refusal preserves all bytes')
    mode_output = root/'timing-mode-mismatch'
    for profile, option in ((normal, ['--playback-keepalive', 'on']), (config(48000, 2), [])):
        refused = call([*command(native, profile, mode_output), *option], expected=1)
        require('playback mode differs' in refused.stderr and not mode_output.exists(),
                'Mismatched timing and playback modes fail before session creation')
    for extra in (['--simulate'], ['--input', str(normal)], ['--limit-ms', '0']):
        call([native, '--run', '--input', normal, '--output', root/'invalid-output', '--limit-ms', '1000', *extra], expected=1)
        require(not (root/'invalid-output').exists(), 'Malformed/duplicate flags create no context')
    no_pointer = root/'refused-private-pointer.txt'
    call([native, '--publish-pointer', '--config', normal, '--pointer', no_pointer], expected=1)
    require(not no_pointer.exists() and not Path(str(no_pointer)+'.pending').exists(), 'Private-worker configuration cannot be published as a broker pointer')
    call([native, '--publish-pointer', '--config', normal, '--pointer', no_pointer, '--replace', 'true'], expected=1)
    cases.append({'name': 'refusal-guards', 'passed': True, 'deviceAccess': False})
    call(command(native, normal, root/'zero-limit-output', 0), expected=1)
    require(not (root/'zero-limit-output').exists(), 'Invalid lifetime refuses before context/device access')
    files = {str(p.relative_to(root)).replace('\\', '/'): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
    report = {'schema': 'sl3.broker-controller-software-tests.v1', 'cases': cases, 'files': files,
              'nativePositiveRun': False, 'physicalAudioTested': False, 'securityChanged': False, 'evidenceDirectory': str(root)}
    (root/'index.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    pointer = native.parent.parent/f'controller-last-{native.parent.name}.json'
    pointer.write_text(json.dumps({'directory': str(root), 'indexSha256': sha(root/'index.json')}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'evidenceDirectory': str(root), 'nativePositiveRun': False}))


if __name__ == '__main__':
    main()
