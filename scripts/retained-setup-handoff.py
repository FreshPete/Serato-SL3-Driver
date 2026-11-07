"""Run one reviewed retained setup and restoration in an attended administrator session."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/serato-on-demand-test.py'
VIEW_SECONDS = 240
RETIRE_SECONDS = 120
CLEAN = {'archive':'original','seratoRunning':False,'native':{'state':'absent'}}


def require(value, message):
    if not value:
        raise ValueError(message)


def can_restore(state):
    return (isinstance(state, dict) and isinstance(state.get('native'),dict) and state.get('archive') in
            ('original','installed','restored','install-staged','rollback-staged') and
            state['native'].get('state') in ('absent','installed','unregistered'))


def coordinate(invoke, wait_request, wait_idle):
    """Keep unsupported/unknown component states for reviewed recovery."""
    setup = invoke('setup')
    if not setup or not can_restore(setup.get('after')):
        return 'setup_outcome_unverified'
    ready = (setup.get('successful') is True and setup['after']['archive']=='installed' and
             setup['after']['native']['state']=='installed' and setup['after'].get('seratoRunning') is False)
    if ready:
        wait_request()
    if not wait_idle():
        return 'restore_deferred'
    restore = invoke('restore')
    if not restore or restore.get('successful') is not True or restore.get('after')!=CLEAN:
        return 'restore_outcome_unverified'
    return 'restored' if ready else 'restored_after_failed_setup'


def publish_window(output, expected, process_handle):
    deadline = time.monotonic_ns()+VIEW_SECONDS*10**9
    with process_handle(os.getpid()) as process:
        require(process is not None, 'Cannot identify the administrator handoff')
        receipt = (output/'setup-stdout.json').read_bytes()
        with (output/'window.json').open('x', encoding='utf-8') as stream:
            json.dump({'schema':'sl3.retained-setup-window.v1','experimentSha256':expected,
                       'setupReceiptSha256':hashlib.sha256(receipt).hexdigest(),
                       'pid':os.getpid(),'creationFileTimeUtc':str(process[0]),
                       'deadlineMonotonicNs':deadline},stream)
    return deadline


def run(experiment, expected, execute):
    api = runpy.run_path(str(TOOL))
    with ExitStack() as held:
        record = api['verify'](experiment,expected,held)
        require(record.get('retainedBroker') is True,'Reviewed retained experiment required')
        native = api['Native'](Path(record['bundle']['directory']),record['bundle']['sha256'],True)
        if execute:
            require(native.s.elevated(),'Run the reviewed handoff as administrator; this tool requests no approval')
        output = experiment.parent/'attended-setup'
        require(native.s.absent(output),'Fresh attended-setup record directory required')

        def invoke(action):
            command = [sys.executable,'-I','-B',str(TOOL),action,'--experiment',str(experiment),
                       '--expected-experiment-sha256',expected]
            child = subprocess.run(command,capture_output=True,stdin=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
            if action!='plan':
                for name, data in (('stdout.json',child.stdout),('stderr.txt',child.stderr)):
                    with (output/f'{action}-{name}').open('xb') as stream:
                        stream.write(data)
            try:
                report = json.loads(child.stdout)
            except ValueError:
                return None
            if (not isinstance(report, dict) or report.get('schema')!='sl3.on-demand-test-action.v1' or
                    report.get('action')!=action or type(report.get('successful')) is not bool or
                    child.returncode!=(0 if report['successful'] else 1)):
                return None
            return report

        before = invoke('plan')
        require(before and before['successful'] and before['after']==CLEAN,'Original idle Serato setup required')
        native.require_idle()
        result = {'schema':'sl3.retained-setup-handoff.v1','planOnly':not execute,'experimentSha256':expected,
                  'viewSeconds':VIEW_SECONDS,'retirementWaitSeconds':RETIRE_SECONDS,
                  'before':before['after'],'applicationLaunched':False,'nativeDeviceAccess':False,
                  'elevationRequested':False}
        if not execute:
            return result

        output.mkdir()
        held.enter_context(native.s.pinned_parents(output/'result.json'))

        def wait_window():
            desktop = api['module']('asio-diagnostic-session.py')
            deadline = publish_window(output,expected,desktop['process_handle'])
            while time.monotonic_ns()<deadline and native.s.absent(output/'restore.request'):
                time.sleep(.25)

        def wait_request():
            try:
                wait_window()
            except (OSError, ValueError) as error:
                result['windowError'] = str(error)

        def wait_idle():
            deadline = time.monotonic()+RETIRE_SECONDS
            while time.monotonic()<deadline:
                try:
                    native.require_idle()
                except ValueError:
                    time.sleep(1)
                    continue
                plan = invoke('plan')
                if not plan or not plan['successful'] or not can_restore(plan.get('after')):
                    return False
                if plan['after'].get('seratoRunning') is False:
                    return time.monotonic()<deadline
                time.sleep(1)
            return False

        try:
            result['outcome'] = coordinate(invoke,wait_request,wait_idle)
        except Exception as error:
            result.update(outcome='handoff_outcome_unverified',error=str(error))
        with (output/'result.json').open('x',encoding='utf-8') as stream:
            json.dump(result,stream,indent=2)
            stream.write('\n')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',choices=('plan','run'),default='plan')
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--expected-experiment-sha256',required=True)
    args = parser.parse_args()
    result = run(args.experiment.absolute(),args.expected_experiment_sha256,args.action=='run')
    print(json.dumps(result,indent=2))
    return 0 if result['planOnly'] or (result['outcome']=='restored' and 'windowError' not in result) else 1


if __name__ == '__main__':
    raise SystemExit(main())
