"""Offline broker-scope consistency; never attests physical provenance or readiness."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    raw = path.read_bytes(); require(0 < len(raw) <= 65536, 'Bounded evidence file required')
    return raw, json.loads(raw)


def positive(value):
    return type(value) is int and 0 < value < 2**64


def validate(folder, worker_sha, simulated=False):
    require(re.fullmatch('[0-9a-f]{64}', worker_sha), 'Lowercase worker hash required')
    raw, result = read(folder/'result.json')
    require(result.get('schema') == 'sl3.broker-scope-probe.v1' and result.get('simulated') is simulated and
            result.get('successful') is True and result.get('error') == '' and result.get('workerSha256') == worker_sha,
            'Wrong worker/kind or failed broker result')
    for key in ['acquireAttempted', 'acquired', 'recordPublished', 'deviceReleasedVerified', 'ioRetiredVerified',
                'workerProcessExited', 'workerJobEmpty']:
        require(result.get(key) is True, 'Incomplete lifecycle: '+key)
    require(result.get('nativeDeviceAcquired') is (not simulated), 'Native acquisition claim differs')
    for key in ['audioAllowed', 'timingProfileReadOrWritten', 'asioConfigurationPublished', 'workerTerminationRequested',
                'helperLoadedInProbe', 'kernelQuiescenceVerified', 'usbReadyForNextAcquire', 'physicalAudioVerified', 'seratoAdmissionVerified']:
        require(result.get(key) is False, 'Unsupported activity/claim: '+key)
    for key, expected in [('clientAttempts', 3), ('completedClients', 3), ('audioStarts', 0), ('rateSetters', 0)]:
        require(type(result.get(key)) is int and result[key] == expected, 'Wrong operation count: '+key)
    require(positive(result.get('workerPid')) and result['workerPid'] < 2**32, 'Invalid worker identity')
    session_raw = (folder/'broker-session.txt').read_bytes()
    require(0 < len(session_raw) <= 4096, 'Bounded session record required')
    session_text = session_raw.decode('ascii')
    session = re.fullmatch(r'SL3-BROKER-SESSION-1\nendpoint=\\\\\.\\pipe\\SL3Broker-[0-9a-f]{32}\nserver_pid=([1-9][0-9]*)\nserver_created=([1-9][0-9]*)\nworker_sha256=([0-9a-f]{64})\n', session_text)
    require(session is not None and int(session[1]) < 2**32 and int(session[2]) < 2**64 and session[3] == worker_sha,
            'Typed session identity/worker mismatch')
    rows = result.get('clients'); require(type(rows) is list and len(rows) == 3, 'Three client observations required')
    identities = []; rates = []; bindings = {'result.json': hashlib.sha256(raw).hexdigest(), 'broker-session.txt': hashlib.sha256(session_raw).hexdigest()}
    for n, row in enumerate(rows):
        require(type(row) is dict and type(row.get('index')) is int and row['index'] == n and
                positive(row.get('pid')) and row['pid'] < 2**32 and positive(row.get('created100ns')) and
                row.get('retired') is True and row.get('terminationRequested') is False and
                type(row.get('rateHz')) is int and row['rateHz'] in (44100, 48000), 'Invalid retired client')
        client_raw, client = read(folder/f'client-{n}.json')
        expected = {'schema': 'sl3.broker-scope-client.v1', 'index': n, 'pid': row['pid'], 'workerPid': result['workerPid'],
                    'rateHz': row['rateHz'], 'created100ns': row['created100ns'], 'simulated': simulated,
                    'detached': True, 'audioStarted': False, 'deviceReleased': False}
        require(client == expected and all(client[k] is expected[k] for k in ['simulated', 'detached', 'audioStarted', 'deviceReleased']) and
                all(type(client[k]) is int for k in ['index', 'pid', 'workerPid', 'rateHz', 'created100ns']), 'Client result differs')
        identities.append((row['pid'], row['created100ns'])); rates.append(row['rateHz'])
        bindings[f'client-{n}.json'] = hashlib.sha256(client_raw).hexdigest()
    require(len(set(identities)) == 3 and len(set(rates)) == 1, 'Reused client process identity or changed clock')
    native = None; journals = list(folder.glob('worker-*.tsv'))
    if simulated:
        require(not journals, 'Simulation must not contain native journal')
        audit = (folder/'worker-audit.txt').read_bytes()
        require(audit.decode().splitlines() == ['acquire']+['rate']*7+['release'], 'Exact simulated no-audio audit required')
        bindings['worker-audit.txt'] = hashlib.sha256(audit).hexdigest()
    else:
        require(len(journals) == 1 and journals[0].name == 'worker-startup.tsv', 'Exactly one native worker journal required')
        data = journals[0].read_bytes(); require(0 < len(data) <= 65536 and data.endswith(b'\n'), 'Incomplete native journal')
        lines = [line.split('\t') for line in data.decode('ascii').splitlines()]
        require(all(len(row) == 3 and row[0].isdigit() and row[1].isdigit() for row in lines), 'Malformed native journal')
        require(all(int(row[1]) == result['workerPid'] and 0 < int(row[0]) < 2**64 for row in lines) and
                [int(row[0]) for row in lines] == sorted(int(row[0]) for row in lines), 'Worker/timestamp mismatch')
        stages = [row[2] for row in lines]; at = 3
        require(stages[:3] == ['worker.enter', 'helper_load.enter', 'helper_load.return'], 'Wrong native journal prefix')
        while stages[at:at+2] == ['enumerate.enter', 'enumerate.return']:
            at += 2
        require(at > 3, 'Native enumeration evidence required')
        expected = ['configuration.enter', 'configuration.return', 'redirect_owner_acquire.enter', 'redirect_owner_acquire.return',
                    'redirect_start.enter', 'redirect_start.return', 'system_handle.enter', 'system_handle.return']+[
                    'clock_getter.enter', 'clock_getter.return']*7+[
                    'redirect_close.enter', 'redirect_close.return', 'helper_unload.enter', 'helper_unload.return']
        require(stages[at:] == expected, 'Expected exactly one acquisition, seven getters and one release; no audio')
        native = {'workerPid': result['workerPid'], 'records': len(lines), 'sha256': hashlib.sha256(data).hexdigest()}
        bindings['worker-startup.tsv'] = native['sha256']
    require(not list(folder.glob('*.conf')) and not list(folder.glob('*pointer*')), 'Diagnostic must not publish ASIO configuration/pointer')
    return {'valid': True, 'simulated': simulated, 'clients': 3, 'rateHz': rates[0], 'expectedClockQueries': 7,
            'nativeJournal': native, 'bindings': bindings, 'physicalProvenanceVerified': False,
            'scope': 'Recorded metadata/retirement consistency only; not physical audio, timing, COM/Serato or readiness'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('folder', type=Path)
    parser.add_argument('--worker-sha256', required=True); parser.add_argument('--simulated', action='store_true'); args = parser.parse_args()
    try:
        print(json.dumps(validate(args.folder, args.worker_sha256, args.simulated), indent=2))
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as error:
        print(json.dumps({'valid': False, 'error': str(error)})); raise SystemExit(1)
