"""Exercise the native activation parser/session through an unregistered simulated ASIO DLL."""
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def require(value, text):
    if not value:
        raise AssertionError(text)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_application(images, output, state, process_handle):
    application = subprocess.Popen([str(path) for path in images] + [str(output), '--application-bound', str(state)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 12
        while not (output / 'host-ready-to-exit').is_file():
            require(application.poll() is None and time.monotonic() < deadline,
                    'Application-bound ASIO fixture did not reach its exit barrier')
            time.sleep(.02)
        key = (output / 'application-key.txt').read_text().strip()
        with process_handle(application.pid) as host:
            require(host and not host[1](0) and key == f'application-{application.pid}-{host[0]}',
                    'Session directory must identify the exact live host')
        owner = state / key
        ready = json.loads((owner / 'ready.json').read_bytes())
        record = dict(line.split('=', 1) for line in (owner / 'broker-session.txt').read_text().splitlines()[1:])
        with process_handle(ready['controllerPid']) as controller:
            require(controller and not controller[1](0) and ready['controllerPid'] == int(record['server_pid']) and
                    controller[0] == int(record['server_created']), 'Exact controller still alive after all DLL unloads')
            controller_identity = ready['controllerPid'], controller[0]
            (output / 'release-host').touch(exist_ok=False)
            application.wait(timeout=8)
            require(controller[1](8000), 'Exact controller must exit after the host')
    finally:
        if application.poll() is None:
            application.kill()
        app_stdout, app_stderr = application.communicate(timeout=5)
        (output.with_suffix('.stdout.json')).write_bytes(app_stdout)
        (output.with_suffix('.stderr.txt')).write_bytes(app_stderr)
    require(application.returncode == 0, 'Application-bound ASIO fixture failed: ' +
            app_stderr.decode('utf-8', errors='replace'))
    bound = json.loads(app_stdout)
    require(bound['applicationBound'] is True and bound['streams'] == 2 and bound['moduleUnloads'] == 3 and
            bound['conflictingSpecRefused'] is True and bound['callbacks'] >= 24, 'Actual retained activation evidence required')
    bound_result = owner / 'result.json'
    retired = json.loads(bound_result.read_bytes())
    require(retired['kind'] == 'simulated' and retired['reason'] == 'application_exit' and
            all(retired[name] is True for name in ('successful', 'applicationExitObserved', 'ioRetiredVerified',
                                                   'deviceReleasedVerified', 'processExited', 'jobEmpty')) and
            all(retired[name] is False for name in ('terminationRequested', 'nativeDeviceAcquired', 'lifetimeExpired')),
            'Independent application-exit retirement required')
    bound['controllerResultSha256'] = sha(bound_result)
    bound['controllerExitObserved'] = True
    return bound, key, controller_identity


def main():
    require(len(sys.argv) == 6, 'Test executable, fixture DLL, simulated controller/worker and reviewed helper required')
    images = [Path(value).absolute() for value in sys.argv[1:]]
    identities = {str(path): sha(path) for path in images}
    names = ('CMakeLists.txt', 'src/asio/activated_driver_session.cpp', 'src/asio/driver_configuration.cpp',
             'src/asio/driver_configuration.hpp', 'src/asio/driver_facade.hpp', 'src/asio/driver_session.hpp',
             'src/asio/broker_session.cpp', 'src/asio/broker_activation.cpp', 'src/asio/broker_activation.hpp',
             'src/windows/worker_process.cpp', 'src/windows/worker_process.hpp', 'src/windows/broker_controller_main.cpp',
             'tests/native/activation_session_provider.cpp', 'tests/native/activation_session_fixture.def',
             'tests/native/activation_asio_tests.cpp', 'scripts/test-activation-asio.py', 'scripts/asio-diagnostic-session.py')
    sources = {name: sha(ROOT / name) for name in names}
    output = ROOT / 'tests/results/local' / ('activation-asio-' + uuid.uuid4().hex)
    require(output.parent.resolve() == (ROOT / 'tests/results/local').resolve() and not output.exists(), 'Fresh fixture output required')
    output.parent.mkdir(parents=True, exist_ok=True)
    child = subprocess.Popen([str(path) for path in images] + [str(output)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    timeout = False
    try:
        stdout, stderr = child.communicate(timeout=45)
    except subprocess.TimeoutExpired:
        timeout = True
        child.kill()
        stdout, stderr = child.communicate(timeout=5)
    require(output.is_dir(), 'Activation fixture output required')
    for name, raw in (('fixture-stdout.json', stdout), ('fixture-stderr.txt', stderr)):
        with (output / name).open('xb') as stream:
            stream.write(raw)
    require(not timeout and child.returncode == 0, 'ASIO activation fixture failed: ' + stderr.decode('utf-8', errors='replace'))
    result = json.loads(stdout)
    require(result['schema'] == 'sl3.activation-asio-tests.v1' and result['passed'] is True and result['simulatedSessions'] == 5 and
            result['normalSessions'] == 3 and result['callbacks'] >= 37 and
            all(result[name] is True for name in ('lazyCreationVerified', 'normalReopenVerified', 'privateUserRootVerified',
                                                'blockedCallbackLeaseVerified', 'rejectedInitRetiresWhileObjectHeld')) and
            result['registrationChanged'] is False and result['nativeDeviceAccess'] is False, 'Expected actual ASIO activation evidence')
    retirements = []
    for ordinal in range(1, 6):
        path = output / ('session-' + str(ordinal)) / 'result.json'
        record = json.loads(path.read_bytes())
        require(record['schema'] == 'sl3.broker-controller-result.v1' and record['kind'] == 'simulated' and
                all(record[name] is True for name in ('ioRetiredVerified', 'deviceReleasedVerified', 'processExited', 'jobEmpty')) and
                all(record[name] is False for name in ('terminationRequested', 'nativeDeviceAcquired', 'helperLoadedInController')),
                'Actual simulated worker retirement required')
        if ordinal < 5:
            require(record['successful'] is True and record['ownerFailureCode'] == 'none', 'Normal ASIO close must preserve success')
        else:
            require(record['successful'] is False and record['ownerFailureCode'] == 'client_control_abandoned',
                    'Destructive callback release must preserve its failure')
        scenario = ('ordinary', 'reopen', 'scope', 'rejected_rate', 'destructive_callback')[ordinal - 1]
        retirements.append({'session': ordinal, 'scenario': scenario, 'resultSha256': sha(path), 'controllerSucceeded': ordinal < 5,
                            'ioRetired': True, 'jobEmpty': True, 'forcedTermination': False})
    process_handle = runpy.run_path(str(ROOT / 'scripts/asio-diagnostic-session.py'))['process_handle']
    state = output / 'application-state'
    state.mkdir()
    bound, first_key, first_controller = run_application(images, output / 'application-bound', state, process_handle)
    paths = ('activation.conf', 'input.conf', 'timing.txt', first_key + '.claim',
             f'{first_key}/ready.json', f'{first_key}/result.json')
    preserved = {path: sha(state / path) for path in paths}
    reopened, second_key, second_controller = run_application(images, output / 'application-reopen', state, process_handle)
    require(first_key != second_key and first_controller != second_controller and
            {path.name for path in state.iterdir() if path.is_dir()} == {first_key, second_key} and
            all(sha(state / path) == identity for path, identity in preserved.items()),
            'A second host must start its own session and preserve the first host records and shared configuration')
    require(all(sha(Path(path)) == identity for path, identity in identities.items()), 'ASIO fixture image changed')
    require(all(sha(ROOT / path) == identity for path, identity in sources.items()), 'ASIO activation source changed')
    report = {'schema': 'sl3.activation-asio-run.v1', 'fixture': result, 'retirements': retirements, 'applicationBound': bound,
              'applicationReopen': reopened, 'distinctApplicationSessions': True, 'priorSessionAndConfigPreserved': True,
              'sourceSha256': sources, 'imageSha256': identities, 'fixtureExited': True, 'timedOut': False,
              'seratoExecuted': False, 'nativeDeviceAccess': False, 'registrationChanged': False,
              'privateUserRootCreatedOrVerified': True}
    with (output / 'run.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'output': str(output), 'simulatedSessions': 5, 'normalSessions': 3,
                      'callbacks': result['callbacks'], 'nativeDeviceAccess': False}, indent=2))


if __name__ == '__main__':
    main()
