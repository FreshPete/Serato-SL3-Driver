"""Actual separate-process broker diagnostics, simulated transport/pre-device guards."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    native, simulated, worker, helper = [Path(x).resolve() for x in sys.argv[1:]]
    root = native.parent.parent/'broker-scope-artifacts'/uuid.uuid4().hex; root.mkdir(parents=True)
    cases = []; worker_sha = sha(worker)
    def call(exe, args=(), expected=0):
        run = subprocess.run([str(exe), *map(str, args)], capture_output=True, text=True, timeout=30)
        require(run.returncode == expected, f'CLI exit {run.returncode}: {run.stderr}')
        return run
    def case(name, data):
        cases.append({'name': name, 'passed': True}); return data
    def command(output, mode=None):
        args = ['--run', '--worker', worker, '--worker-sha256', worker_sha, '--output', output]
        return args+(['--fixture-mode', mode] if mode else [])
    for exe, kind in [(native, False), (simulated, True)]:
        for suffix in [[], ['--plan']]:
            value = json.loads(call(exe, suffix).stdout)
            require(value['planOnly'] and value['simulated'] is kind and not value['deviceAccess'] and
                    not value['audioAllowed'] and not value['requiresTimingProfile'] and value['clients'] == 3,
                    'Inert control-only plan')
            case(exe.name+('-explicit-plan' if suffix else '-default'), value)
    output = root/'positive'; result = call(simulated, command(output)); record = json.loads((output/'result.json').read_text())
    require(record['successful'] and record['simulated'] and not record['nativeDeviceAcquired'] and
            record['completedClients'] == record['clientAttempts'] == 3 and record['recordPublished'], 'Three simulated clients')
    identities = set()
    for index, row in enumerate(record['clients']):
        child = json.loads((output/f'client-{index}.json').read_text())
        require(child['pid'] == row['pid'] and child['created100ns'] == row['created100ns'] and
                child['workerPid'] == record['workerPid'] and child['rateHz'] == row['rateHz'] == 48000 and
                row['retired'] and not row['terminationRequested'] and child['detached'] and not child['deviceReleased'],
                'Exact separate client process results and retained worker')
        identities.add((row['pid'], row['created100ns']))
    require(len(identities) == 3 and (output/'worker-audit.txt').read_text().splitlines() ==
            ['acquire']+['rate']*7+['release'], 'One worker acquisition, seven getters, one final release; no audio')
    for key in ['deviceReleasedVerified', 'ioRetiredVerified', 'workerProcessExited', 'workerJobEmpty']:
        require(record[key] is True, 'Independent final retirement: '+key)
    for key in ['workerTerminationRequested', 'helperLoadedInProbe', 'asioConfigurationPublished', 'timingProfileReadOrWritten',
                'kernelQuiescenceVerified', 'usbReadyForNextAcquire', 'physicalAudioVerified', 'seratoAdmissionVerified']:
        require(record[key] is False, 'Scope boundary: '+key)
    require(not list(output.glob('*.conf')) and not list(output.glob('*pointer*')), 'No production ASIO metadata generated')
    case('three-client-clock-only-roundtrip', record)
    saved = {p.name: sha(p) for p in output.iterdir()}
    call(simulated, command(output), 2)
    require(saved == {p.name: sha(p) for p in output.iterdir()}, 'Existing diagnostic output preserved')
    case('output-reuse-refused', {})
    broker_record = output/'broker-session.txt'
    stale = call(simulated, ['--client', '--record', broker_record, '--record-sha256', sha(broker_record),
                             '--worker-sha256', worker_sha, '--index', '0'], 2)
    require(saved == {p.name: sha(p) for p in output.iterdir()}, 'Stale parent record does not launch/rewrite anything')
    case('stale-record-after-owner-exit-refused', {'stderr': stale.stderr})
    for mode, expected_attempts in [('fail-acquire', 0), ('fail-rate-refresh', 1)]:
        out = root/mode; call(simulated, command(out, mode), 1); failed = json.loads((out/'result.json').read_text())
        require(not failed['successful'] and failed['completedClients'] == 0 and failed['clientAttempts'] == expected_attempts and
                failed['workerProcessExited'] and failed['workerJobEmpty'] and not failed['asioConfigurationPublished'],
                'Failed owner stops without replacement acquisition')
        case(mode, failed)
    out = root/'native-kind-refusal'; call(native, command(out)+['--helper', helper], 1)
    failed = json.loads((out/'result.json').read_text())
    require(not failed['successful'] and not failed['acquireAttempted'] and not failed['nativeDeviceAcquired'] and
            not failed['acquired'] and not failed['deviceReleasedVerified'] and not failed['ioRetiredVerified'] and
            not failed['recordPublished'] and not (out/'broker-session.txt').exists(), 'Truthful simulated hello rejected before native acquisition')
    case('native-kind-refusal-before-acquire', failed)
    absent = root/'never-created'
    guards = [(simulated, command(absent)+['--output', absent]), (native, command(absent, 'normal')+['--helper', helper]),
              (simulated, ['--plan', '--worker', worker]),
              (simulated, ['--run', '--worker', worker, '--worker-sha256', '0'*64, '--output', absent]),
              (native, command(absent)+['--helper', root/'missing.dll'])]
    for index, (exe, args) in enumerate(guards):
        call(exe, args, 2); require(not absent.exists(), 'Pre-device/pre-output refusal'); case('preflight-guard-'+str(index), {})
    inputs = [native, simulated, worker, helper, Path(__file__)]
    evidence = {'schema': 'sl3.broker-scope-software-tests.v1', 'cases': cases,
                'inputs': {p.name: sha(p) for p in inputs},
                'files': {p.relative_to(root).as_posix(): sha(p) for p in root.rglob('*') if p.is_file()},
                'positiveNativeRun': False, 'deviceAccess': False, 'timingProfileGenerated': False,
                'simulatedClientProcesses': 3, 'simulatedAcquisitions': 1, 'simulatedClockReads': 7,
                'simulatedAudioStarts': 0}
    path = root/'index.json'; path.write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
    (root.parent/'latest.json').write_text(json.dumps({'directory': str(root), 'indexSha256': sha(path)}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'simulatedClients': 3, 'clockReads': 7, 'audioStarts': 0, 'positiveNativeRun': False}))


if __name__ == '__main__':
    main()
