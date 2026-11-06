"""Exercise the native activation parser/session through an unregistered simulated ASIO DLL."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def require(value, text):
    if not value:
        raise AssertionError(text)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    require(len(sys.argv) == 6, 'Test executable, fixture DLL, simulated controller/worker and reviewed helper required')
    images = [Path(value).absolute() for value in sys.argv[1:]]
    identities = {str(path): sha(path) for path in images}
    names = ('CMakeLists.txt', 'src/asio/activated_driver_session.cpp', 'src/asio/driver_configuration.cpp',
             'src/asio/driver_configuration.hpp', 'src/asio/driver_facade.hpp', 'src/asio/driver_session.hpp',
             'src/asio/broker_session.cpp', 'src/asio/broker_activation.cpp', 'src/asio/broker_activation.hpp',
             'tests/native/activation_session_provider.cpp', 'tests/native/activation_session_fixture.def',
             'tests/native/activation_asio_tests.cpp', 'scripts/test-activation-asio.py')
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
    require(all(sha(Path(path)) == identity for path, identity in identities.items()), 'ASIO fixture image changed')
    require(all(sha(ROOT / path) == identity for path, identity in sources.items()), 'ASIO activation source changed')
    report = {'schema': 'sl3.activation-asio-run.v1', 'fixture': result, 'retirements': retirements,
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
