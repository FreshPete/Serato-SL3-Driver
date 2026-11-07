"""Prepare and retire one retained connection during a live administrator handoff."""

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
BROKER_LIMIT_MS = 120000
MINIMUM_BROKER_WINDOW_SECONDS = BROKER_LIMIT_MS // 1000 + 15
IDENTITY_SECONDS = 5
POST_RELEASE_SECONDS = 15
USB_OBSERVER_TIMEOUT_SECONDS = IDENTITY_SECONDS + 30


def require(condition, message):
    if not condition:
        raise ValueError(message)


def matches(raw, expected, description):
    require(hashlib.sha256(raw).hexdigest() == expected, description + ' hash differs')
    return raw


def write_report(path, report):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')


def identity_samples(rows):
    samples = [row['snapshot'] for row in rows if row['event']=='sample']
    complete = [sample for sample in samples if sample['complete']]
    keys = ('vendor','product','revision','bus','address')
    sets = {tuple(sorted(tuple(item[key] for key in keys) for item in sample['identities']))
            for sample in complete}
    return {'completeSamples':len(complete),'incompleteSamples':len(samples)-len(complete),
            'identitySets':[[dict(zip(keys,item)) for item in group] for group in sorted(sets)]}


def compare_identity(first, second):
    """Compare stable sampled identities, with no inference through gaps."""
    a, b = first['identitySets'], second['identitySets']
    if first['incompleteSamples'] or second['incompleteSamples'] or len(a)!=1 or len(b)!=1:
        return 'indeterminate'
    return 'same_sampled_identity_set' if a==b else 'different_sampled_identity_set'


def stable_single_identity(summary):
    sets = summary['identitySets']
    return (summary['completeSamples']>=2 and summary['incompleteSamples']==0 and
            len(sets)==1 and len(sets[0])==1)


def observe_release(result, observe, previous):
    """A USB observation failure cannot change the completed retirement result."""
    result['usbReadyForNextAcquire'] = False
    try:
        after = observe('after', POST_RELEASE_SECONDS)
        result['postReleaseIdentity'] = after
        if previous is not None:
            result['beforeToAfter'] = compare_identity(previous['before'], after)
            result['duringToAfter'] = compare_identity(previous['during'], after)
    except (Exception, KeyboardInterrupt) as error:
        result['postReleaseObservationError'] = str(error) or type(error).__name__


def finish_trial(result, startup, owned_session, require_idle, retire, request_restore, observe):
    try:
        previous = json.loads(startup.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError):
        previous = None
        require(owned_session.is_file(), 'No completed startup or retained broker ownership record')
    else:
        require(previous['schema']==result['schema'] and previous['action']=='start' and
                previous['outcome']=='broker_ready', 'Desktop startup report differs')

    require_idle()
    try:
        result['retirement'] = retire()
        result['retirementObservedUtc'] = datetime.now(timezone.utc).isoformat()
        result['outcome'] = 'retired_after_interruption' if previous is None else 'retired'
    finally:
        request_restore()
    observe_release(result, observe, previous.get('usbIdentity') if previous is not None else None)
    return result


@contextmanager
def open_window(folder, expected, process_handle, minimum_seconds=0):
    window = json.loads((folder/'window.json').read_bytes())
    require(window['schema']=='sl3.retained-setup-window.v1' and window['experimentSha256']==expected,
            'Expected the current retained handoff window')
    receipt = json.loads(matches((folder/'setup-stdout.json').read_bytes(), window['setupReceiptSha256'], 'Setup receipt'))
    require(receipt['schema']=='sl3.on-demand-test-action.v1' and receipt['action']=='setup' and
            receipt['successful'] is True and receipt['after']['archive']=='installed' and
            receipt['after']['native']['state']=='installed', 'Successful installed setup receipt required')
    require(type(window['pid']) is int and 0 < window['pid'] <= 0xffffffff and
            type(window['deadlineMonotonicNs']) is int, 'Invalid handoff window fields')
    with process_handle(window['pid']) as process:
        def check(seconds=0):
            require(process and str(process[0])==window['creationFileTimeUtc'] and not process[1](0),
                    'The exact administrator handoff is no longer running')
            require(not (folder/'restore.request').exists() and
                    window['deadlineMonotonicNs']-time.monotonic_ns() > seconds*10**9,
                    'The administrator handoff is closing or too close to restoration')
        check(minimum_seconds)
        yield check


def start_trial(snapshot, start, retire, request_restore, record_ready):
    """One acquisition at most. On failure always give the handoff an idle-check opportunity."""
    started = None
    try:
        before = snapshot('before')
        require(before, 'Need two complete pre-acquisition snapshots of one unchanged SL3 and no incomplete samples')
        started = start()
        during = snapshot('during')
        result = {'outcome':'broker_ready','broker':started,'sl3VisibleBefore':before,'sl3VisibleDuring':during}
        record_ready(result)
        return result
    except (Exception, KeyboardInterrupt) as error:
        result = {'outcome':'startup_failed','error':str(error) or type(error).__name__}
        try:
            if started is not None:
                result['retirement'] = retire()
        except Exception as cleanup_error:
            result['retirementError'] = str(cleanup_error)
        try:
            request_restore()
        except OSError as signal_error:
            result['restoreRequestError'] = str(signal_error)
        return result


def run(args):
    api = runpy.run_path(str(ROOT/'scripts/serato-on-demand-test.py'))
    experiment = args.experiment.absolute()
    folder = experiment.parent
    handoff = folder/'attended-setup'
    output = folder/'desktop-start'
    with ExitStack() as held:
        record = api['verify'](experiment, args.expected_experiment_sha256, held)
        require(record.get('retainedBroker') is True, 'Prepared retained experiment required')
        native = api['Native'](Path(record['bundle']['directory']), record['bundle']['sha256'], True)
        require(not native.s.elevated(), 'Run under the ordinary Windows desktop account')

        def pinned(path, expected, description):
            handle = held.enter_context(native.s.open_file(path))
            return matches(native.s.read_handle(handle, 65536), expected, description)

        launch = json.loads(pinned(folder/'retained-launch.json', args.expected_launch_sha256, 'Launch record'))
        controller, source, session, pointer = map(Path, (launch[key] for key in ('controller','input','session','pointer')))
        controller_sha = native.manifest['files']['sl3_broker_controller.exe']['sha256']
        require(launch['schema']=='sl3.retained-client-observation-preparation.v1' and
                launch['reviewedExperimentSha256']==args.expected_experiment_sha256 and
                launch['bundleManifestSha256']==record['bundle']['sha256'] and
                launch['controllerSha256']==controller_sha and
                controller==native.destination/'sl3_broker_controller.exe' and pointer==Path(native.plan['pointerPath']) and
                source==folder/'sl3-worker.conf' and session==folder/'broker', 'Retained launch record differs')
        pinned(source, launch['inputSha256'], 'Worker configuration')
        pinned(folder/'sl3-timing.conf', launch['timingSha256'], 'Timing record')
        result = {'schema':'sl3.retained-desktop-trial.v1','action':args.action,
                  'applicationLaunched':False,'elevationRequested':False}
        if args.action=='plan':
            return {**result,'outcome':'inputs_verified'}

        broker = api['module']('asio-diagnostic-session.py')

        def require_idle_serato():
            command = [sys.executable,'-I','-B',str(ROOT/'scripts/serato-on-demand-test.py'),'plan',
                       '--experiment',str(experiment),'--expected-experiment-sha256',args.expected_experiment_sha256]
            child = subprocess.run(command,capture_output=True,check=True,timeout=100)
            state = json.loads(child.stdout)['after']
            require(state['seratoRunning'] is False and state['archive']=='installed' and
                    state['native']['state']=='installed', 'Close Serato and verify the temporary setup first')

        def retire():
            with broker['handoff_lock'](session):
                return broker['close_handoff'](controller, session, pointer, controller_sha)

        def request_restore():
            try:
                with (handoff/'restore.request').open('xb'):
                    pass
            except FileExistsError:
                pass

        def observe(phase, seconds):
            path = output/phase
            command = [sys.executable,'-I','-B',str(ROOT/'scripts/supervise-usb-identity.py'),
                       '--run','--seconds',str(seconds),'--result-directory',str(path)]
            subprocess.run(command,capture_output=True,check=True,timeout=seconds+30)
            checked = api['module']('supervise-usb-identity.py')['validate_supervised_run'](path)
            rows = (json.loads(line) for line in (path/'observations.jsonl').read_text(encoding='utf-8').splitlines())
            return {**identity_samples(rows),'startedUtc':checked['started_utc'],'closedUtc':checked['closed_utc']}

        if args.action=='finish':
            held.enter_context(broker['handoff_lock'](output/'lifecycle'))
            require(not (output/'finish.json').exists(), 'A desktop finish report already exists')
            finish_trial(result, output/'startup.json', session.with_suffix('.pointer.json'),
                         require_idle_serato, retire, request_restore, observe)
            write_report(output/'finish.json',result)
            return result

        minimum_start = MINIMUM_BROKER_WINDOW_SECONDS + USB_OBSERVER_TIMEOUT_SECONDS
        with open_window(handoff, args.expected_experiment_sha256, broker['process_handle'], minimum_start) as check:
            require_idle_serato()
            check(minimum_start)
            output.mkdir()
            held.enter_context(broker['handoff_lock'](output/'lifecycle'))
            identities = {}

            def snapshot(phase):
                summary = observe(phase, IDENTITY_SECONDS)
                identities[phase] = summary
                if phase=='before':
                    return stable_single_identity(summary)
                return any(summary['identitySets']) if summary['completeSamples'] else None

            def start():
                with broker['handoff_lock'](session):
                    check(MINIMUM_BROKER_WINDOW_SECONDS)
                    return broker['start'](controller, source, session, pointer, controller_sha, BROKER_LIMIT_MS)

            def record_ready(ready):
                check()
                owner = broker['read'](session.with_suffix('.pointer.json'))
                pid = ready['broker']['controllerPid']
                require(pid==owner['controllerPid'] and broker['digest'](pointer)==owner['pointerSha256'],
                        'Broker pointer no longer identifies this startup')
                with broker['process_handle'](pid) as process:
                    require(process and str(process[0])==owner['controllerCreatedFileTime'] and not process[1](0),
                            'The retained controller exited during the USB observation')
                    ready.update(usbIdentity=identities,
                                 beforeToDuring=compare_identity(identities['before'],identities['during']))
                    write_report(output/'startup.json',{**result,**ready})

            trial = start_trial(snapshot,start,retire,request_restore,record_ready)
            result.update(trial)
            if result['outcome']=='startup_failed':
                result['usbIdentity'] = identities
                write_report(output/'failure.json',result)
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',choices=('plan','start','finish'),default='plan')
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--expected-experiment-sha256',required=True)
    parser.add_argument('--expected-launch-sha256',required=True)
    parser.add_argument('--recovery-confirmed',action='store_true')
    args = parser.parse_args()
    if args.action=='start' and not args.recovery_confirmed:
        parser.error('Confirm the attended SL3 recovery before starting one acquisition')
    try:
        result = run(args)
    except (KeyError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    print(json.dumps(result,indent=2))
    return 1 if result['outcome']=='startup_failed' else 0


if __name__=='__main__':
    raise SystemExit(main())
