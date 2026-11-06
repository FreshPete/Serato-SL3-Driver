"""Run native on-demand activation with simulated workers only; preserve evidence."""
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
    require(len(sys.argv) == 5, 'Fixture executable, simulated controller, worker and reviewed helper required')
    images = [Path(value).absolute() for value in sys.argv[1:]]
    pins = {str(path): sha(path) for path in images}
    sources = {name: sha(ROOT / name) for name in ('CMakeLists.txt', 'src/asio/broker_activation.hpp',
               'src/asio/broker_activation.cpp', 'tests/native/broker_activation_tests.cpp', 'scripts/test-broker-activation.py')}
    output = ROOT / 'tests/results/local' / ('broker-activation-' + uuid.uuid4().hex)
    require(output.parent.resolve() == (ROOT / 'tests/results/local').resolve() and not output.exists(), 'Fresh fixture output required')
    output.parent.mkdir(parents=True, exist_ok=True)
    child = subprocess.Popen([str(path) for path in images] + [str(output)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    timeout = False
    try:
        stdout, stderr = child.communicate(timeout=45)
    except subprocess.TimeoutExpired:
        timeout = True
        child.kill()  # Exact owned fixture handle; its private child jobs close.
        stdout, stderr = child.communicate(timeout=5)
    require(output.is_dir(), 'Fixture must preserve an output directory')
    for name, raw in (('fixture-stdout.json', stdout), ('fixture-stderr.txt', stderr)):
        with (output / name).open('xb') as stream:
            stream.write(raw)
    require(not timeout and child.returncode == 0, 'Native activation fixture failed: ' + stderr.decode('utf-8', errors='replace'))
    result = json.loads(stdout)
    require(result['schema'] == 'sl3.broker-activation-tests.v1' and result['passed'] is True and
            result['simulatedSessions'] == 2 and result['asioStartStopCycles'] == 2 and result['callbacks'] >= 24 and
            result['failedStartupNormalExitObserved'] is True and result['failedStartupForcedContainmentObserved'] is True and
            result['nativeDeviceAccess'] is False and result['serviceInstalled'] is False and
            result['productionAsioEntryChanged'] is False, 'Expected simulated activation result')
    retirements = []
    for session in ('session', 'retained'):
        path = output / session / 'result.json'
        observation = json.loads(path.read_bytes())
        require(observation['schema'] == 'sl3.broker-controller-result.v1' and observation['kind'] == 'simulated' and
                all(observation[name] is True for name in ('successful', 'ioRetiredVerified', 'deviceReleasedVerified',
                                                          'processExited', 'jobEmpty')) and
                all(observation[name] is False for name in ('terminationRequested', 'nativeDeviceAcquired', 'helperLoadedInController')),
                'Actual simulated controller/worker retirement required')
        retirements.append({'session': session, 'resultSha256': sha(path), 'simulatedWorkerRetired': True})
    require(all(sha(Path(path)) == identity for path, identity in pins.items()), 'Fixture image changed during test')
    require(all(sha(ROOT / path) == identity for path, identity in sources.items()), 'Activation sources changed during test')
    report = {'schema': 'sl3.broker-activation-run.v1', 'fixture': result, 'retirements': retirements,
              'sourceSha256': sources, 'imageSha256': pins, 'fixtureExited': True, 'timedOut': timeout,
              'ordinaryActivationOnly': True, 'seratoExecuted': False, 'nativeDeviceAccess': False}
    with (output / 'run.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'output': str(output), 'simulatedSessions': 2, 'asioStartStopCycles': 2,
                      'callbacks': result['callbacks'], 'nativeDeviceAccess': False}, indent=2))


if __name__ == '__main__':
    main()
