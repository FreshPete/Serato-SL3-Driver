"""Verify the first real read-only libusb observation and report measured cadence."""
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('baseline_supervisor', ROOT/'scripts/supervise-usb-identity.py')
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
require = s.require


def cadence(rows, requested_interval):
    require(type(requested_interval) in (int, float) and math.isfinite(requested_interval) and requested_interval > 0,
            'Invalid requested sleep interval')
    pending, ends, durations, complete = None, [], [], 0
    for row in rows:
        if row['event'] not in ('snapshot_enter', 'sample'):
            continue
        elapsed = row['elapsed_seconds']
        require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0, 'Invalid sample time')
        if row['event'] == 'snapshot_enter':
            require(pending is None and (not ends or elapsed >= ends[-1]), 'Overlapping/regressing observation')
            pending = elapsed
        else:
            require(pending is not None and elapsed >= pending, 'Missing/regressing observation entry')
            require(type(row['snapshot']['complete']) is bool, 'Invalid completeness flag')
            durations.append(elapsed-pending); ends.append(elapsed); pending = None
            complete += row['snapshot']['complete']
    require(pending is None and durations, 'Incomplete or empty observation')
    gaps = [b-a for a, b in zip(ends, ends[1:])]
    def stats(values):
        return {'count': len(values), 'minimum': min(values) if values else None,
                'maximum': max(values) if values else None,
                'mean': math.fsum(values)/len(values) if values else None}
    return {'samples': len(ends), 'completeSamples': complete, 'requestedPostCallSleepSeconds': requested_interval,
            'hostEnumerationDurationSeconds': stats(durations), 'sampleReturnGapSeconds': stats(gaps),
            'lastLoopElapsedSeconds': ends[-1], 'guaranteedTransientDetectionSeconds': None,
            'physicalAudioClockMeasured': False}


def main():
    import hashlib
    folder = ROOT/'tests/results/local/usb-identity-baseline-20261030-01'
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    checked = s.validate_supervised_run(folder)
    record = json.loads((folder/'supervisor.json').read_text(encoding='utf-8'))
    rows = [json.loads(line) for line in (folder/'observations.jsonl').read_text(encoding='utf-8').splitlines()]
    header = rows[2]
    require(record['duration_seconds'] == 5 and record['interval_ms'] == 250 and checked['samples'] == 4 and
            checked['incomplete_samples'] == checked['changed_comparisons'] == 0, 'First baseline shape/result differs')
    identities = [row['snapshot']['identities'] for row in rows if row['event'] == 'sample']
    require(all(identity == [{'vendor': 0x1cc5, 'product': 1, 'revision': 0, 'bus': 3, 'address': 1}]
                for identity in identities), 'Baseline SL3 identities differ')
    post = json.loads((folder/'post-state.json').read_text(encoding='utf-8-sig'))
    props = {p['KeyName']: p['Data'] for p in post['properties']}
    require(post['device']['Status'] == 'Error' and post['device']['InstanceId'].upper() == r'USB\VID_1CC5&PID_0001\SL3.01.00' and
            props == {'DEVPKEY_Device_ProblemCode': 39, 'DEVPKEY_Device_Service': 'strmdrv',
                      'DEVPKEY_Device_DriverInfPath': 'oem136.inf'} and post['testProcesses'] == [] and
            post['secureBootAttested'] is False, 'Post-run resting state differs')
    result = {'scope': 'One actual read-only libusb identity observation; no redirect/control/audio/application open',
              'localRecord': folder.relative_to(ROOT).as_posix(), 'validation': checked,
              'cadence': cadence(rows, header['interval_seconds']), 'sampledIdentity': identities[0][0],
              'sampleTiming': [{'enteredLoopSeconds': rows[n-1]['elapsed_seconds'],
                                'returnedLoopSeconds': row['elapsed_seconds'],
                                'reportedCallSeconds': row['call_seconds']}
                               for n, row in enumerate(rows) if row['event'] == 'sample'],
              'child': record['child'], 'requestedObservationSeconds': 5,
              'producerSha256': {'observer': record['observer_sha256'], 'supervisor': record['supervisor_sha256'],
                                'installedLibusb': record['dll_sha256']},
              'files': {name: digest(folder/name) for name in ('supervisor.json', 'observations.jsonl', 'post-state.json')},
              'postState': {'problemCode': 39, 'service': 'strmdrv', 'inf': 'oem136.inf', 'testProcesses': 0},
              'secureBootAttestedDuringRun': False, 'fullRecoveryAttested': False,
              'redirectCoexistenceVerified': False, 'seratoCoexistenceVerified': False,
              'limits': ['Unchanged returned identity does not exclude unsampled changes or libusb caching',
                         'Snapshot duration includes all host enumeration work; no individual API bottleneck attribution',
                         'Requested interval is sleep after a synchronous call, not achieved polling cadence',
                         'Revision word 0 is USB descriptor data, not an identified firmware version',
                         'Post state is the failed original driver baseline, not a repaired Windows audio driver',
                         'No USB-stack/WPP trace, ownership handoff, rate/control change or audio/DVS validation']}
    test_log = ROOT/'analysis/identity-baseline-python-tests.log'
    text = test_log.read_text(encoding='utf-8-sig')
    require('Ran 109 tests' in text and text.rstrip().endswith('OK'), 'Baseline analysis software checks failed')
    result['softwareChecks'] = {'fullPythonTests': 109, 'logSha256': digest(test_log),
                                'cadenceTestSourceSha256': digest(ROOT/'tests/test_identity_cadence.py')}
    (ROOT/'docs/evidence/usb-identity-baseline-20261030.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified actual four-snapshot SL3 baseline, clean child exit, measured slow cadence and original code-39 post state')


if __name__ == '__main__':
    main()
