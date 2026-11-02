"""Actual controller/publication/ASIO processes. Positive cases are simulated only."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
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


def main():
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

    def config(rate):
        timing = root/f'timing-{rate}.txt'
        timing.write_text(f'SL3-ASIO-TIMING-1\nreview=approved\nworker_sha256={sha(worker)}\nhelper_sha256={sha(helper)}\n'
                          f'rate_hz={rate}\nbuffer_frames=128\nintervals=8\nrequests_per_direction=4\ninput_extra_frames=7\noutput_extra_frames=11\n'
                          f'measurement_file={measurement}\nmeasurement_sha256={sha(measurement)}\n', encoding='utf-8')
        file = root/f'input-{rate}.conf'
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
        return result

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
            try:
                with published.open('r+b'):
                    pass
            except PermissionError:
                pass
            else:
                raise AssertionError('Published configuration must stay write locked')
            require('SL3-ASIO-BROKER-CONFIG-1' in published.read_text(), 'Separate reviewed broker format')
            entry = published
            if mode in ('ordinary-sta', 'ordinary-mta'):
                deployment = root/f'{name}-deployment'; deployment.mkdir()
                pointer = root/f'{name}-current-session.txt'
                publication = json.loads(call([native, '--publish-pointer', '--config', published, '--pointer', pointer]).stdout)
                require(publication['pointerPublished'] and not publication['replaced'] and not publication['deviceAccess'] and not publication['deviceReadinessVerified'], 'Explicit pointer publication changes metadata only')
                original_pointer = pointer.read_bytes()
                call([native, '--publish-pointer', '--config', published, '--pointer', pointer], expected=1)
                require(pointer.read_bytes() == original_pointer and not Path(str(pointer)+'.pending').exists(), 'Publisher refuses existing pointer without changing bytes')
                entry = deployment/'sl3-asio.conf'
                entry.write_text(f'SL3-ASIO-LOCATOR-1\nsession_pointer={pointer}\nbroker={simulated}\nbroker_sha256={sha(simulated)}\nworker_sha256={sha(worker)}\n', encoding='utf-8')
            response = call([client, '--published', entry, library, mode])
            (output/'asio-client-stdout.txt').write_text(response.stdout, encoding='utf-8')
            (output/'asio-client-stderr.txt').write_text(response.stderr, encoding='utf-8')
            if mode.startswith('ordinary'):
                stop = json.loads(call([native, '--stop', '--config', published]).stdout)
                require(stop['stopRequested'] is True and stop['deviceReleasedVerified'] is False, 'Stop is only a request')
                final = finish_case(output, proc, 0)
                require(final['successful'] is True and final['reason'] == 'stop_requested' and final['published'] is True and
                        final['snapshotValid'] is True and final['ioRetiredVerified'] is True and final['deviceReleasedVerified'] is True and not final['failed'], 'Idle stop verified independently')
            else:
                final = finish_case(output, proc, 1)
                require(not final['successful'] and final['failed'] and final['reason'] == 'owner_failure', 'Destructive client release preserves owner failure')
            audit = (output/'worker-audit.txt').read_text().splitlines()
            require(audit.count('acquire') == 1 and audit.count('release') == 1, 'No controller reacquisition loop')
            if mode.startswith('ordinary'):
                require(audit.count('rate') == 8 and audit.count('begin') == 4 and audit.count('end') == 4, 'Three ordinary COM objects/four SDK streams retain one worker')
            require(call([native, '--stop', '--config', published], expected=1).returncode == 1, 'Stale process record refused after exit')
            if entry != published:
                call([client, '--published', entry, library, mode], expected=1)  # Stale locator cannot reconnect.
                refused_pointer = root/f'{name}-stale-pointer.txt'
                call([native, '--publish-pointer', '--config', published, '--pointer', refused_pointer], expected=1)
                require(not refused_pointer.exists() and not Path(str(refused_pointer)+'.pending').exists(), 'Stale broker refusal publishes no pointer')
            cases.append({'name': name, 'passed': True, 'kind': 'simulated', 'activation': mode})
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate(timeout=5)

    active('ordinary-session')
    active('com-sta-session', 'ordinary-sta')
    active('com-mta-session', 'ordinary-mta')
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

    existing = root/'existing-output'; existing.mkdir(); (existing/'preserve.txt').write_text('preserve', encoding='utf-8')
    call(command(simulated, normal, existing), expected=1)
    require(list(p.name for p in existing.iterdir()) == ['preserve.txt'] and (existing/'preserve.txt').read_text() == 'preserve', 'Existing output refusal preserves all bytes')
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
