"""Plan by default: bounded, source-only PLA experiment. No USB operations or elevation."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def query_process(arguments, timeout, log, record):
    """Own the actual interpreter, avoiding the Windows venv proxy process.

    This helper's query script spawns no children. A timeout stays a failure;
    retain the direct PID and confirmed wait result without retrying the query.
    """
    base = Path(sys._base_executable).resolve()
    require(base.is_file(), 'Base interpreter is missing')
    state = {'baseInterpreter':str(base), 'startedUtc':datetime.now(timezone.utc).isoformat(),
             'pid':None, 'timedOut':False, 'retired':False, 'exitCode':None}
    child = None
    try:
        with log.open('xb') as stream:
            child = subprocess.Popen([str(base), *arguments], stdout=stream, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0), cwd=ROOT)
            state['pid'] = child.pid
            try:
                state['exitCode'] = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                state['timedOut'] = True
                child.kill()
                state['exitCode'] = child.wait(timeout=3)
            state['retired'] = True
    finally:
        state['completedUtc'] = datetime.now(timezone.utc).isoformat()
        with record.open('x',encoding='utf-8') as stream:
            json.dump(state,stream,indent=2);stream.write('\n')
    require(not state['timedOut'], 'Session query timed out; direct-child retirement: '+str(state['retired']))
    return state['exitCode']


def read(path):
    require(path.stat().st_size <= 131072, 'Oversized JSON input')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def plan(preparation, context, native_identity_policy='configured'):
    require(native_identity_policy in ('configured', 'observed-rechecked'), 'Unknown native identity policy')
    record = read(preparation)
    spec = importlib.util.spec_from_file_location('source_query', ROOT/'scripts/inspect-image-source-session.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.validate_identity(record['sessionName'], record['sessionGuid'])
    require(record['configurationValidated'] is True and record['sourceStarted'] is False
            and record['sourceCommitted'] is False and type(record['durationSeconds']) is int
            and 1 <= record['durationSeconds'] <= 60, 'Invalid preparation role or duration')
    require(record['sourceSha256'] == sha(ROOT/'scripts/prepare-hub-image-source.ps1'), 'Preparation source changed')
    expected = ROOT/'tests/results/local'/record['sessionName']
    require(Path(record['prospectiveRootPath']).resolve() == expected.resolve() and not expected.exists(),
            'Expected an unused private capture root')
    require(context.resolve().is_relative_to(ROOT/'tests/results/local') and not context.exists()
            and context.resolve() != expected.resolve() and context.parent.is_dir(), 'Expected a new local context directory')
    inputs = ['prepare-hub-image-source.ps1', 'validate-hub-image-source.ps1', 'inspect-process.psm1',
              'inspect-image-source-session.py', 'hub-image-source-action.ps1', 'test-hub-image-source.py',
              'inspect-loaded-hub.py']
    return {'scope': 'Source-only timed logger experiment; no USB/audio/driver operations',
            'planOnly': True, 'preparation': str(preparation.resolve()), 'preparationSha256': sha(preparation),
            'contextDirectory': str(context.resolve()), 'captureRoot': str(expected.resolve()),
            'sessionName': record['sessionName'], 'sessionGuid': record['sessionGuid'],
            'nativeIdentityPolicy': native_identity_policy,
            'durationSeconds': record['durationSeconds'], 'watchSeconds': record['durationSeconds']+8,
            'requiresAlreadyElevatedTerminal': True, 'requestsElevation': False,
            'childActionTimeoutSeconds': 12, 'queryTimeoutSeconds': 3,
            'queryBaseInterpreter': str(Path(sys._base_executable).resolve()),
            'queryBaseInterpreterSha256': sha(Path(sys._base_executable).resolve()),
            'sourceStarted': False, 'readinessAdmission': False,
            'inputs': {name: sha(ROOT/'scripts'/name) for name in inputs}}


def evaluate_observations(observations):
    active = [row for row in observations if row['sourceActive'] is True]
    stopped = bool(active and observations[-1]['sourceActive'] is False)
    flags = bool(active and all(row['properties']['systemLoggerModePresent'] is True
                               and row['properties']['clockType'] == 1
                               and not row['properties']['logFileMode'] & 0x906 for row in active))
    no_loss = bool(active and all(all(row['properties'][key] == 0 for key in
                                   ('eventsLost', 'logBuffersLost', 'realTimeBuffersLost')) for row in active))
    return {'liveSourceObserved': bool(active), 'runtimeFlagForwardingVerified': flags,
            'sourceDisappearanceObserved': stopped, 'sampledLossCountersZero': no_loss}


def own_token():
    spec = importlib.util.spec_from_file_location('token_query', ROOT/'scripts/inspect-loaded-hub.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper.own_token()  # Only own-token information, not its loaded-module query.


def run(experiment):
    require(os.name == 'nt', 'Requires Windows')
    identity_policy = experiment.get('nativeIdentityPolicy', 'configured')
    require(identity_policy in ('configured', 'observed-rechecked'), 'Unknown native identity policy')
    token = own_token()
    require(token['queried'] and token['elevated'], 'Run requires an already elevated terminal; no prompt is launched')
    pwsh = shutil.which('pwsh')
    require(pwsh is not None, 'PowerShell 7 is required')
    for name, digest in experiment['inputs'].items():
        require(sha(ROOT/'scripts'/name) == digest, 'Runner input changed: '+name)
    require(experiment['queryBaseInterpreter'] == str(Path(sys._base_executable).resolve())
            and experiment['queryBaseInterpreterSha256'] == sha(Path(sys._base_executable).resolve()),
            'Query interpreter changed')
    context = Path(experiment['contextDirectory'])
    context.mkdir()  # Never reuse a prior context, even after failure.
    frozen = context/'preparation.json'
    frozen.write_bytes(Path(experiment['preparation']).read_bytes())
    require(sha(frozen) == experiment['preparationSha256'], 'Preparation changed before freezing')
    result = {**experiment, 'planOnly': False, 'producerToken': token, 'startedUtc': datetime.now(timezone.utc).isoformat(),
              'successful': False, 'observations': [], 'error': None, 'cleanup': None,
              'independentStopValidated': False, 'imageRundownObserved': False, 'etlFiles': []}
    hidden = subprocess.CREATE_NO_WINDOW

    def process(arguments, timeout, log):
        with (context/log).open('xb') as stream:
            return subprocess.run(arguments, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout,
                                  creationflags=hidden, cwd=ROOT).returncode

    observed_guid = None

    def private_live_properties(properties):
        require(isinstance(properties, dict) and properties.get('sessionName') == experiment['sessionName']
                and properties.get('sessionNameMatchesExpected') is True, 'Native candidate name differs')
        require(isinstance(properties.get('logFileName'), str)
                and Path(properties['logFileName']).resolve() == (Path(experiment['captureRoot'])/'images.etl').resolve(),
                'Native candidate output differs')
        require(type(properties.get('logFileMode')) is int and properties['logFileMode'] in
                (0x02000000, 0x02000001, 0x02800000, 0x02800001)
                and properties.get('systemLoggerModePresent') is True
                and type(properties.get('clockType')) is int and properties['clockType'] == 1
                and type(properties.get('enableFlags')) is int and properties['enableFlags'] == 4,
                'Native candidate mode/clock differs')
        require(all(type(properties.get(k)) is int and properties[k] == 0 for k in
                    ('eventsLost','logBuffersLost','realTimeBuffersLost')), 'Native candidate has observed loss')

    def observation(label, expected_guid=None, discover=False):
        nonlocal observed_guid
        expected = str(uuid.UUID(expected_guid or observed_guid or experiment['sessionGuid']))
        output = context/(label+'.json')
        code = query_process([str(ROOT/'scripts/inspect-image-source-session.py'),
                        '--session-name', experiment['sessionName'], '--session-guid', expected,
                        '--output', str(output)], experiment['queryTimeoutSeconds'],
                        context/(label+'.log'), context/(label+'-process.json'))
        value = read(output) if output.exists() else None
        require(value is not None, 'Session query failed without metadata; see '+label+'.log')
        require(value['sourceSha256'] == experiment['inputs']['inspect-image-source-session.py']
                and type(value['controlCode']) is int and value['controlCode'] == 0 and value['sessionName'] == experiment['sessionName']
                and value['expectedSessionGuid'] == expected, 'Query helper binding differs')
        status=value['win32Status'];properties=value['properties']
        coherent=type(status) is int and value['validationError'] is None and (
            status==4201 and value['sourceActive'] is False and properties is None or
            status==0 and value['sourceActive'] is True and isinstance(properties,dict) and
            properties.get('sessionGuidMatchesExpected') is True and properties.get('sessionNameMatchesExpected') is True and
            properties.get('sessionGuid')==expected and
            isinstance(properties.get('sessionName'),str) and properties['sessionName'].casefold()==experiment['sessionName'].casefold())
        if code != 0 or value['diagnosticAccepted'] is not True or not coherent:
            result.setdefault('queryRejections', []).append({'file':output.name, 'sha256':sha(output),
                'exitCode':code, 'win32Status':value['win32Status'], 'sourceActive':value['sourceActive'],
                'validationError':value['validationError'] or 'Contradictory query identity/status'})
            if identity_policy == 'observed-rechecked' and discover and observed_guid is None:
                require(not result['observations'] and result.get('startAction', {}).get('sourceCommitted') is True
                        and result['startAction']['startRequested'] is True,
                        'Native discovery lacks admitted committed start')
                require(code == 1 and type(status) is int and status == 0 and value['sourceActive'] is True
                        and value['diagnosticAccepted'] is False, 'Native discovery requires an exact rejected live query')
                private_live_properties(properties)
                candidate = uuid.UUID(properties['sessionGuid'])
                require(candidate.version == 4 and candidate.variant == uuid.RFC_4122 and str(candidate) != expected,
                        'Native candidate is not a distinct version-4 UUID')
                require(properties.get('sessionGuidMatchesExpected') is False and value['validationError'] ==
                        f'Session GUID differs from expected source (expected {expected}, returned {candidate})',
                        'Native discovery rejection has another cause')
                result['nativeGuidDiscovery'] = {'file': output.name, 'sha256': sha(output),
                    'configuredGuid': expected, 'candidateNativeGuid': str(candidate),
                    'recheckFile': label+'-native-recheck.json', 'recheckAccepted': False}
                # The failed query remains rejected. Only a new strict query
                # against this candidate can become the accepted observation.
                checked = observation(label+'-native-recheck', expected_guid=str(candidate))
                require(checked['sourceActive'] is True, 'Native identity recheck did not observe an active source')
                private_live_properties(checked['properties'])
                observed_guid = str(candidate)
                result['nativeSessionGuid'] = observed_guid
                result['nativeGuidDiscovery']['recheckAccepted'] = True
                result['nativeGuidDiscovery']['recheckSha256'] = sha(context/(label+'-native-recheck.json'))
                return checked
            raise ValueError('Session query rejected; diagnostic metadata retained in '+output.name)
        if identity_policy == 'observed-rechecked' and value['sourceActive'] is True:
            private_live_properties(properties)
        return value

    def action(kind):
        output = context/(kind.lower()+'.json')
        code = process([pwsh, '-NoProfile', '-File', str(ROOT/'scripts/hub-image-source-action.ps1'), '-Run',
                        '-Action', kind, '-PreparationRecord', str(frozen),
                        '-PreparationSha256', experiment['preparationSha256'], '-Output', str(output)],
                       12, kind.lower()+'.log')
        value = read(output) if output.exists() else None
        require(code == 0 and value and value['successful'], kind+' action failed; see action log/report')
        require(value['sourceSha256'] == experiment['inputs']['hub-image-source-action.ps1']
                and value['preparationSha256'] == experiment['preparationSha256'], 'Action input binding differs')
        if kind == 'Start':
            reference = value.get('committedConfiguration')
            require(isinstance(reference, dict)
                    and reference.get('file') == 'start.json.committed.json'
                    and reference.get('configurationMatchesExpected') is True, 'Missing accepted committed configuration')
            snapshot_path = context/reference['file']
            require(sha(snapshot_path) == reference['sha256'], 'Committed configuration hash differs')
            snapshot = read(snapshot_path)
            require(snapshot['querySucceeded'] is True and type(snapshot['status']) is int and snapshot['status'] == 0
                    and snapshot['configurationMatchesExpected'] is True and snapshot['mismatches'] == []
                    and snapshot['error'] is None and snapshot['sourceStarted'] is False
                    and snapshot['readinessAdmission'] is False
                    and snapshot['preparationSha256'] == experiment['preparationSha256']
                    and snapshot['collectorName'] == '[Service]'+experiment['sessionName'],
                    'Committed configuration observation differs')
        return value

    ownership_possible = False
    try:
        before = observation('before')
        require(before['sourceActive'] is False, 'Source already active; no start or cleanup admitted')
        ownership_possible = True  # From here a failed/timed-out start may have persisted a set.
        result['sourceStarted'] = None  # Uncertain until independently observed; a request is not a start.
        result['startAction'] = action('Start')
        result['startRequested'] = bool(result['startAction']['startRequested'])
        deadline = time.monotonic()+experiment['watchSeconds']
        while time.monotonic() < deadline:
            row = observation('sample-'+str(len(result['observations'])), discover=not result['observations'])
            row['receivedWithinWatchDeadline'] = time.monotonic() <= deadline
            result['observations'].append(row)
            if row['sourceActive']:
                result['sourceStarted'] = True
                require(Path(row['properties']['logFileName']).resolve().is_relative_to(Path(experiment['captureRoot'])),
                        'Live logger output is outside the private capture root')
            require(row['receivedWithinWatchDeadline'], 'Query exceeded observation deadline')
            outcome = evaluate_observations(result['observations'])
            if outcome['sourceDisappearanceObserved']:
                break
            time.sleep(0.25)
        result.update(evaluate_observations(result['observations']))
        require(result['liveSourceObserved'], 'No live source was observed')
        require(result['runtimeFlagForwardingVerified'], 'Effective source mode/clock differs')
        require(result['sourceDisappearanceObserved'], 'Source did not disappear before bounded watch expired')
        require(result['sampledLossCountersZero'], 'Observed trace loss counters are nonzero')
        # Absence before our cleanup is useful, but could reflect a service
        # failure rather than Duration expiry. Do not promote it to timer proof.
        result['timedExpiryCauseVerified'] = False
    except Exception as failure:
        result['error'] = str(failure)
    finally:
        if ownership_possible:
            try:
                result['cleanup'] = action('Cleanup')
                result['after'] = observation('after')
                require(result['after']['sourceActive'] is False, 'Source still present after cleanup')
                # An intervening cleanup stop invalidates any independent-expiry inference.
                if result['cleanup']['stopRequested']:
                    result['independentStopValidated'] = False
            except Exception as failure:
                result['cleanupError'] = str(failure)
        result['finishedUtc'] = datetime.now(timezone.utc).isoformat()
        try:
            for path in Path(experiment['captureRoot']).rglob('*.etl'):
                require(len(result['etlFiles']) < 4, 'Unexpected ETL file count')
                require(path.resolve().is_relative_to(Path(experiment['captureRoot'])), 'ETL escapes source root')
                size = path.stat().st_size
                require(0 < size <= 64*1024*1024, 'ETL exceeds offline inspection bound or is empty')
                result['etlFiles'].append({'path': str(path), 'bytes': size, 'sha256': sha(path)})
            require(result['etlFiles'], 'No bounded ETL artifact was produced')
        except Exception as failure:
            result['artifactError'] = str(failure)
        result['successful'] = bool(result['error'] is None and result['cleanup'] and result['cleanup']['successful']
                                    and not result.get('cleanupError') and not result.get('artifactError')
                                    and not result['cleanup']['stopRequested'] and result.get('sourceDisappearanceObserved')
                                    and result.get('sampledLossCountersZero') and result['etlFiles'])
        result['limits'] = ['ETL presence/hash and sampled loss counters do not establish complete rundown or final loss counts.',
                            'Child-process deadlines bound waits, not the Windows service; failed cleanup remains explicit.',
                            'No loaded-image match, USB window or readiness admission is inferred.']
        with (context/'run.json').open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', required=True, type=Path)
    parser.add_argument('--context', type=Path)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--native-identity-policy', choices=('configured','observed-rechecked'), default='configured')
    args = parser.parse_args()
    context = args.context or ROOT/'tests/results/local'/('image-source-'+uuid.uuid4().hex)
    experiment = plan(args.preparation, context, args.native_identity_policy)
    result = run(experiment) if args.run else experiment
    print(json.dumps(result, indent=2))
    return 0 if not args.run or result['successful'] else 1


if __name__ == '__main__':
    sys.exit(main())
