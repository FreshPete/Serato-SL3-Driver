"""Plan by default: coordinate bounded image and USB collectors, never launch a device probe.

Start test-controls-user-probe.ps1 separately from a normal token. Execution of
this fixed collector plan needs one already elevated process; no broker persists.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT/'scripts'/name)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


batch = module('logging-batch.py')
require, read, sha, write_new = batch.require, batch.read, batch.sha, batch.write_new


def now():
    return datetime.now(timezone.utc).isoformat()


def utc(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.utcoffset() is not None, 'Timestamp must include its timezone')
    return result


def runtime(scope=False):
    build_path = ROOT/'artifacts/build/native/native-build-Release.json'
    build = read(build_path)
    pins = build['scopeProbe']['scriptInputs'] if scope else build['hostProbe']['controls']['scriptInputs']
    require(len(pins) == (19 if scope else 18), 'Expected reviewed probe runtime')
    for name, expected in pins.items():
        require(sha(ROOT/'scripts'/name) == expected.lower(), 'Controls dependency changed: '+name)
    natives = {}
    probe=('sl3_scope_probe.exe',build['scopeProbe']['executableSha256']) if scope else ('sl3_host_probe.exe',build['hostProbe']['executableSha256'])
    for name, expected in (probe,
                           ('sl3_usbdk.exe', build['usbdk']['executableSha256'])):
        path = ROOT/'artifacts/build/native/Release'/name
        require(sha(path) == expected.lower(), 'Native executable changed: '+name)
        natives[name] = sha(path)
    value = {'collectorSha256': sha(Path(__file__)), 'buildManifestSha256': sha(build_path),
            'launcherSha256': sha(ROOT/'scripts/start-controls-image-capture.ps1'),
            'windowValidatorSha256': sha(ROOT/'scripts/validate-controls-image-window.py'),
            'imageInspectorSha256': sha(ROOT/'scripts/inspect-kernel-image-rundown.py'),
            'controlsInputs': pins, 'nativeImages': natives, 'loggingRuntime': batch.runtime()}
    if scope:
        value['scopeRuntime']=module('prepare-scope-trace.py').runtime()
    return value


def plan_value(batch_path, image_batch, scope=False):
    name = batch_path.parent.name
    context = ROOT/'tests/results/local'/(name+('-scope' if scope else '-controls'))
    image_seconds,trace_seconds=(120,60) if scope else (60,20)
    require(len(image_batch['jobs']) == 1 and image_batch['jobs'][0]['durationSeconds'] == image_seconds and
            image_batch['nativeIdentityPolicy'] == 'observed-rechecked', 'Expected the fixed scenario image window')
    require(not context.exists(), 'Controls context must be fresh')
    value = {'schema': 'sl3.scope-image-collector.v1' if scope else 'sl3.controls-image-collector.v1', 'imageBatch': str(batch_path.resolve()),
            'imageBatchSha256': sha(batch_path), 'contextDirectory': str(context.resolve()),
            'runtime': runtime(scope=True) if scope else runtime(), 'traceSeconds': trace_seconds, 'withStateObserver': True,
            'launchesProbe': False, 'requiresNormalUserProbe': True,
            'deviceAccess': False, 'securityChanges': False, 'readinessAdmission': False,
            'scope': 'Image and USB/WPP collectors only; separate normal-user '+('scope' if scope else 'control')+' probe may open SL3',
            'normalUserCommand': [image_batch['runtime']['powershell'], '-NoProfile', '-File',
                                  str(ROOT/'scripts/test-controls-user-probe.ps1'), '-Run',
                                  '-TraceSeconds', str(trace_seconds), '-ContextDirectory', str(context.resolve())]}
    if scope:
        value['scenario']='Scope'
        value['normalUserCommand']+=['-Scenario','Scope']
    return value


def prepare(directory,scope=False):
    image_batch = batch.prepare(directory, [120 if scope else 60], 'observed-rechecked')
    result = plan_value(directory/'batch.json', image_batch,scope=scope)
    write_new(directory/'controls-image.json', result)
    return result


def validate(path):
    require(path.name == 'controls-image.json', 'Unexpected combined plan filename')
    saved=read(path)
    require(saved['schema'] in ('sl3.controls-image-collector.v1','sl3.scope-image-collector.v1'),'Unknown collector scenario')
    scope=saved['schema']=='sl3.scope-image-collector.v1'
    image_batch = batch.validate(path.parent/'batch.json')
    expected = plan_value(path.parent/'batch.json', image_batch,scope=scope)
    require(saved == expected, 'Collector plan or reviewed inputs changed')
    require(not (path.parent/'controls-image-started.json').exists(), 'Collector plan already attempted')
    return expected, image_batch


def live_query(value, job, checked):
    """Strict image-source observation, never a USB readiness decision."""
    props = value['properties']
    require(value['sourceSha256'] == job['inputs']['inspect-image-source-session.py'] and
            value['sessionName'] == job['sessionName'] and value['controlCode'] == 0 and
            type(value['controlCode']) is int and type(value['win32Status']) is int and
            value['win32Status'] == 0 and value['sourceActive'] is True and
            value['diagnosticAccepted'] is True and value['validationError'] is None and
            value['readinessAdmission'] is False, 'Image source query was not accepted live')
    require(utc(value['queryStartedUtc']) <= utc(value['queryFinishedUtc']) <= utc(checked) and
            (utc(checked)-utc(value['queryStartedUtc'])).total_seconds() <= 3, 'Image source query is stale')
    native = str(uuid.UUID(value['expectedSessionGuid']))
    require(props['sessionGuid'] == native and props['sessionGuidMatchesExpected'] is True and
            props['sessionNameMatchesExpected'] is True and props['sessionName'] == job['sessionName'] and
            Path(props['logFileName']).resolve() == (Path(job['captureRoot'])/'images.etl').resolve(),
            'Image query identity or private path differs')
    require(type(props['logFileMode']) is int and props['logFileMode'] in
            (0x02000000, 0x02000001, 0x02800000, 0x02800001) and
            props['systemLoggerModePresent'] is True and type(props['clockType']) is int and props['clockType'] == 1 and
            type(props['enableFlags']) is int and props['enableFlags'] == 4 and
            all(type(props[k]) is int and props[k] == 0 for k in
                ('eventsLost', 'logBuffersLost', 'realTimeBuffersLost')), 'Image source mode or loss counters differ')
    return native


def wait_candidate(source, job, seconds=25):
    deadline = time.monotonic()+seconds
    paths = [Path(job['contextDirectory'])/name for name in ('sample-0-native-recheck.json', 'sample-0.json')]
    while time.monotonic() < deadline:
        require(source.poll() is None, 'Image controller exited before USB collection')
        for path in paths:
            if path.exists():
                try:
                    value = read(path)
                except (OSError, ValueError):  # A concurrently written JSON file is not yet evidence.
                    continue
                if value.get('diagnosticAccepted') is not True:
                    continue  # Preserve the first GUID rejection; only its strict recheck can qualify.
                return path, live_query(value, job, now())
        time.sleep(.05)
    raise ValueError('No fresh strict image observation; USB collector not started')


def committed_start(job):
    context=Path(job['contextDirectory']);start=read(context/'start.json')
    reference=start['committedConfiguration']
    require(start['successful'] is True and start['sourceCommitted'] is True and start['startRequested'] is True and
            start['stopRequested'] is False and start['sourceSha256']==job['inputs']['hub-image-source-action.ps1'] and
            start['preparationSha256']==job['preparationSha256'] and
            reference['file']=='start.json.committed.json' and reference['configurationMatchesExpected'] is True,
            'Image source lacks its owned committed start')
    snapshot_path=context/reference['file']
    require(sha(snapshot_path)==reference['sha256'],'Committed image configuration hash differs')
    snapshot=read(snapshot_path)
    require(snapshot['querySucceeded'] is True and type(snapshot['status']) is int and snapshot['status']==0 and
            snapshot['configurationMatchesExpected'] is True and snapshot['mismatches']==[] and snapshot['error'] is None and
            snapshot['sourceStarted'] is False and snapshot['readinessAdmission'] is False and
            snapshot['preparationSha256']==job['preparationSha256'] and
            snapshot['collectorName']=='[Service]'+job['sessionName'],'Committed image configuration differs')


def wait_owned(child, seconds, label):
    try:
        return child.wait(timeout=seconds)
    except subprocess.TimeoutExpired as error:
        # Each controller owns its own bounded cleanup. Killing it can strand its
        # source. Leave its PID in the result and refuse another acquisition.
        raise ValueError(label+' is still running; inspect this exact process before any further test') from error


def execute(path, expected_sha):
    require(sha(path) == expected_sha, 'Plan changed after administrator launch')
    plan, image_batch = validate(path)
    scope=plan.get('schema')=='sl3.scope-image-collector.v1'
    token = batch.source_runner().own_token()
    require(token['queried'] is True and token['elevated'] is True, 'Collector requires an already elevated token')
    directory = path.parent
    write_new(directory/'controls-image-started.json', {'planSha256': expected_sha, 'startedUtc': now(), 'token': token})
    result = {'schema': 'sl3.scope-image-collection.v1' if scope else 'sl3.controls-image-collection.v1', 'planSha256': expected_sha,
              'startedUtc': now(), 'collectionCompleted': False, 'launchesProbe': False,
              'readinessAdmission': False, 'sameWindowVerified': False, 'error': None,
              'imageControllerPid': None, 'usbCollectorPid': None}
    source = None
    try:
        with (directory/'combined-image-controller.log').open('xb') as image_log:
            source = subprocess.Popen([sys.executable, str(ROOT/'scripts/logging-batch.py'), '--plan', plan['imageBatch'],
                                       '--execute', '--expected-sha256', plan['imageBatchSha256']],
                                      stdout=image_log, stderr=subprocess.STDOUT, cwd=ROOT,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            result['imageControllerPid'] = source.pid
            job = image_batch['jobs'][0]
            candidate, native = wait_candidate(source, job)
            committed_start(job)
            result['candidate'] = {'path': str(candidate), 'sha256': sha(candidate), 'nativeGuid': native}
            query = directory/'pre-usb-image-query.json'
            subprocess.run([sys.executable, str(ROOT/'scripts/inspect-image-source-session.py'),
                            '--session-name', job['sessionName'], '--session-guid', native, '--output', str(query)],
                           check=True, capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
            require(live_query(read(query), job, now()) == native, 'Image GUID changed before USB collector')
            result['preUsbImageQuerySha256'] = sha(query)
            require(plan['runtime'] == (runtime(scope=True) if scope else runtime()) and sha(Path(plan['imageBatch'])) == plan['imageBatchSha256'],
                    'Runtime changed before USB collector')
            require(source.poll() is None, 'Image controller ended before USB collector')
            command = [image_batch['runtime']['powershell'], '-NoProfile', '-File',
                       str(ROOT/'scripts/capture-controls-user-context.ps1'), '-Run', '-WithStateObserver',
                       '-TraceSeconds', str(plan.get('traceSeconds',20)), '-ContextDirectory', plan['contextDirectory']]
            with (directory/'combined-usb-collector.log').open('xb') as usb_log:
                collector = subprocess.Popen(command, stdout=usb_log, stderr=subprocess.STDOUT,
                                             cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)
                result['usbCollectorPid'] = collector.pid
                result['usbCollectorExitCode'] = wait_owned(collector, 90, 'USB collector')
            require(result['usbCollectorExitCode'] == 0, 'USB collector failed; preserve the context')
            result['collectionCompleted'] = True
    except Exception as error:
        result['error'] = str(error)
    finally:
        if source is not None:
            try:
                result['imageControllerExitCode'] = wait_owned(source, 190 if scope else 130, 'Image controller')
                require(result['imageControllerExitCode'] == 0, 'Image controller failed')
            except Exception as error:
                result['imageCleanupError'] = str(error)
        result['completedUtc'] = now()
        write_new(directory/'controls-image-result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', type=Path)
    group.add_argument('--plan', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--expected-sha256')
    parser.add_argument('--scenario',choices=('Controls','Scope'),default=None,help='Preparation only; execution uses the frozen plan')
    args = parser.parse_args()
    require(not args.execute or (args.plan and args.expected_sha256), 'Execution needs a frozen plan hash')
    require(args.scenario is None or args.prepare is not None,'Scenario selection is preparation-only')
    if args.prepare:
        require(not args.execute, 'Preparation never executes')
        result = prepare(args.prepare.resolve(),scope=args.scenario=='Scope')
    elif args.execute:
        result = execute(args.plan.resolve(), args.expected_sha256)
    else:
        result, _ = validate(args.plan.resolve())
    print(json.dumps(result, indent=2))
    return int(args.execute and (result['error'] is not None or result.get('imageCleanupError') is not None))


if __name__ == '__main__':
    sys.exit(main())
