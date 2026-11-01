"""Read-only admission/coverage checks for the controls trace's identity observer."""
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('controls_identity_supervisor', Path(__file__).with_name('supervise-usb-identity.py'))
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
require = s.require


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def ready(folder, now=None, prefix=None):
    now = now or datetime.now(timezone.utc)
    if prefix is None:
        with (folder/'observations.jsonl').open('rb') as source:
            raw = source.read(4*1024*1024+1)
    else:
        raw = prefix
    require(0 < len(raw) <= 4*1024*1024, 'Missing/oversized live observation')
    end = raw.rfind(b'\n')+1
    raw = raw[:end]  # A concurrent final write may be incomplete; retain only complete lines.
    rows = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
    require(len(rows) >= 5 and [r['event'] for r in rows[:3]] ==
            ['library_load_enter', 'context_init_enter', 'started'], 'Observer not initialized')
    require(rows[0]['dll_sha256'] == s.observer.DLL_SHA and rows[0]['observer_sha256'] == digest(s.SCRIPT) and
            rows[2]['duration_seconds'] == 45 and rows[2]['interval_seconds'] == .05, 'Observer request/identity differs')
    samples = [r for r in rows if r['event'] == 'sample']
    require(samples and not any(r['event'] in ('finished', 'context_close_enter', 'context_closed') for r in rows),
            'Observer already finished or has no sample')
    sample = samples[-1]
    snapshot = sample['snapshot']
    identities = snapshot['identities']
    require(snapshot['complete'] is True and snapshot['descriptor_failures'] == 0 and len(identities) == 1,
            'One complete normal SL3 observation required')
    key = s.observer.identity_key(identities[0])
    require(all(type(v) is int for v in key) and key[:2] == (s.observer.VID, s.observer.PID) and
            0 <= key[2] <= 65535 and all(0 <= v <= 255 for v in key[3:]), 'Invalid initial identity')
    stamp = datetime.fromisoformat(sample['utc'])
    require(stamp.tzinfo is not None and 0 <= (now-stamp).total_seconds() <= .5, 'Initial observation is stale')
    return {'ready': True, 'checkedUtc': now.isoformat(), 'sampleUtc': sample['utc'], 'identity': identities[0],
            'prefixBytes': len(raw), 'prefixSha256': hashlib.sha256(raw).hexdigest()}


def coverage(folder, record, trace):
    requested = record['withUsbIdentity']
    require(type(requested) is bool, 'Invalid identity selection')
    observation = folder/'usb-identity'
    if not requested:
        require(not observation.exists() and not any(k.startswith('usbIdentity') for k in record), 'Unrequested identity observation')
        return None
    require(type(record['usbIdentityExitCode']) is int and record['usbIdentityExitCode'] == 0,
            'Identity supervisor failed')
    require(digest(observation/'supervisor.json') == record['usbIdentitySupervisorRecordSha256'].lower() and
            digest(folder/'identity-validation.json') == record['usbIdentityValidationSha256'].lower() and
            digest(folder/'identity-ready.json') == record['usbIdentityReadySha256'].lower(), 'Identity evidence binding differs')
    validated = s.validate_supervised_run(observation)
    require(read(folder/'identity-validation.json') == validated, 'Saved identity validation differs')
    supervisor = read(observation/'supervisor.json')
    require(supervisor['duration_seconds'] == 45 and supervisor['interval_ms'] == 50, 'Wrong integrated observation shape')
    raw = (observation/'observations.jsonl').read_bytes()
    admission = read(folder/'identity-ready.json')
    require(type(admission['prefixBytes']) is int and 0 < admission['prefixBytes'] <= len(raw), 'Invalid admitted prefix')
    admitted = ready(observation, datetime.fromisoformat(admission['checkedUtc']), raw[:admission['prefixBytes']])
    require(admitted == admission, 'Admitted observation prefix differs')
    utc = datetime.fromisoformat
    start, stop = utc(record['probeStartedUtc']), utc(record['probeCompletedUtc'])
    require(utc(trace['startedUtc']) <= utc(validated['started_utc']) <= utc(admission['sampleUtc']) <=
            utc(admission['checkedUtc']) <= start <= stop <= utc(validated['closed_utc']) <= utc(trace['stoppedUtc']),
            'Identity/probe outside shared trace window')
    rows = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
    pairs = [(rows[n-1], row) for n, row in enumerate(rows) if row['event'] == 'sample']
    before = [sample for entry, sample in pairs if utc(sample['utc']) <= start and sample['snapshot']['complete']]
    after = [sample for entry, sample in pairs if utc(entry['utc']) >= stop and sample['snapshot']['complete']]
    during = [sample for entry, sample in pairs if start <= utc(entry['utc']) <= utc(sample['utc']) <= stop]
    require(before and after, 'Missing complete before/after probe observations')
    return {'valid': True, 'observer': validated, 'completeBeforeProbe': len(before), 'completeAfterProbe': len(after),
            'samplesInsideProbeProcessWindow': len(during),
            'sampledIdentityChanges': validated['changed_comparisons'],
            'heldDeviceCoverageVerified': False, 'seratoCoexistenceVerified': False,
            'scope': 'Sampled identity across the probe process; brief changes and the held subwindow may be missed'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--ready', type=Path)
    mode.add_argument('--coverage', type=Path)
    args = ap.parse_args()
    try:
        value = ready(args.ready) if args.ready else coverage(args.coverage, read(args.coverage/'run.json'),
                                                             read(args.coverage/'trace/capture.json'))
        print(json.dumps(value))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'ready': False, 'error': str(error)} if args.ready else {'valid': False, 'error': str(error)}))
        if not args.ready:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
