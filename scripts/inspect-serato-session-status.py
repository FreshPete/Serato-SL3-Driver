"""Read one selected session's progress and restoration evidence; never repair it."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import winreg

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = '872fc4fdad2eab2ddd34387d2d3c04dd9731c84798d9fdc7bd05ca54e1567db8'


def module(name):
    return runpy.run_path(str(ROOT / 'scripts' / name))


def record(path, issues, name):
    try:
        if not path.exists():
            return None
        if path.is_symlink() or path.is_junction() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Reparse report refused')
        if not 0 < path.stat().st_size <= 2_000_000:
            raise ValueError('Bounded nonempty report required')
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict):
            raise ValueError('Report object required')
        return value
    except (OSError, ValueError) as error:
        issues.append({'record': name, 'message': str(error)})
        return None


def owner_state(owner, image):
    if not isinstance(owner, dict):
        return {'state': 'not_recorded'}
    try:
        with module('serato-session-stop.py')['process_lease'](owner['pid'], image, owner['created']):
            return {'state': 'alive', 'identityMatched': True}
    except OSError as error:
        if getattr(error, 'winerror', None) in (87, 1168):
            return {'state': 'exited'}
        return {'state': 'unknown', 'message': str(error)}
    except (ValueError, KeyError) as error:
        if 'owner has exited' in str(error):
            return {'state': 'exited'}
        if 'owner creation differs' in str(error):
            return {'state': 'replaced', 'recordedOwnerNoLongerActive': True}
        return {'state': 'unknown', 'message': str(error)}


def current_state(plan):
    s = module('asio-install-journal.py')['stage_module']()
    application = Path(plan['application']['path'])
    paths = {'nativeInstallation': Path(plan['nativeInstallation']), 'sessionPointer': Path(plan['pointerPath']),
             'pendingPointer': Path(plan['pointerPath'] + '.pending'),
             'installerResource': application.parent / 'bundles/8c7758f23375cee18a9cf3be4a3acc15.bin',
             'installerPermit': Path(plan['permitPath']),
             'protectedSessionOwner': application.parent / 'bundles/8c7758f23375cee18a9cf3be4a3acc15.bin.sl3-session'}
    local = s.known_folder('f1b32785-6fba-4fcf-9d55-7b8e7f157091')
    paths['cachedLauncher'] = (local / 'Serato/Serato DJ Pro/Drivers/SL3_Rebuild_Development_x64.exe').resolve()
    occupied = [name for name, path in paths.items() if not s.absent(path)]
    registered = False
    for name in ('SOFTWARE\\ASIO\\SL3 Rebuild Development',
                 'SOFTWARE\\Classes\\CLSID\\{5A551CD0-F83E-48EB-8B9D-8614E07852FE}'):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, name, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
                registered = True
        except FileNotFoundError:
            pass
    # Share writes/deletion: status must not prevent the protected owner from
    # restoring or replacing the archive while this snapshot is being taken.
    with s.open_file(application.with_name('userio_resources.bin'), share=7) as handle:
        archive_sha = hashlib.sha256(s.read_handle(handle, 16 * 1024 * 1024)).hexdigest()
    return {'observed': True, 'originalResources': archive_sha == ORIGINAL, 'occupiedPaths': occupied,
            'registrationPresent': registered, 'currentSetupClean': archive_sha == ORIGINAL and not occupied and not registered}


def progress(path, issues):
    if not path.exists():
        return {'startupAndDetachEventReported': False, 'lastCompleteEvent': None}
    try:
        if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400 or path.stat().st_size > 2_000_000:
            raise ValueError('Bounded regular event log required')
        raw = path.read_bytes()
        lines = raw.split(b'\n')[:-1]  # An append in progress is not a complete event.
        if len(lines) > 256:
            raise ValueError('Event inventory exceeds bound')
        names = []
        for line in lines:
            event = json.loads(line)['event']
            if not isinstance(event, str) or not 0 < len(event) <= 128:
                raise ValueError('Bounded event name required')
            names.append(event)
        return {'startupAndDetachEventReported': 'diagnostic_tracer_detached' in names,
                'lastCompleteEvent': names[-1] if names else None}
    except (OSError, ValueError, KeyError, TypeError) as error:
        issues.append({'record': 'events', 'message': str(error)})
        return {'startupAndDetachEventReported': False, 'lastCompleteEvent': None}


def summarize(saved, host, stage, owners, current, stop_valid, issues, has_intent, unused_broker=False, startup_reported=False):
    """Classification preserves the distinction between restored and successful."""
    host = host or {}; stage = stage or {}
    alive = any(value.get('state') == 'alive' for value in owners.values())
    owners_retired = all(value.get('state') in ('exited', 'replaced') for value in owners.values())
    checks = saved['checks']
    required = ('intentMatchesReviewedPlan', 'startupAndDetachReported', 'hostShutdownReportedClean',
                'workerAndControllerRetirementReported', 'brokerSessionReportedSuccessful', 'restorationReported')
    deliberate = host.get('endReason') == 'application_exited' or (
        host.get('endReason') == 'manual_stop' and host.get('userStopRequested') is True and stop_valid)
    reported_clean = all(checks.get(key) is True for key in required) and deliberate and not saved['missingOrInvalidReports']
    restored = current.get('currentSetupClean') is True
    complete = reported_clean and restored and owners_retired and not issues
    process = host.get('process', {})
    if not isinstance(process, dict):
        process = {}
    cancelled = (host.get('schema') == 'sl3.startup-supervisor-result.v1' and
        host.get('endReason') == 'manual_stop_during_startup' and host.get('userStopRequested') is True and stop_valid and
        checks.get('intentMatchesReviewedPlan') is True and process.get('processExited') is True and process.get('jobEmpty') is True and
        not host.get('cleanupError') and unused_broker and stage.get('restored') is True and
        stage.get('registrationAbsent') is True and stage.get('error') is None and
        stage.get('receiptState') in ('absent', 'failed', 'success') and restored and owners_retired and not issues)
    if complete:
        phase, message = 'completed', 'Session ended and the original setup is restored.'
    elif cancelled:
        phase, message = 'cancelled_restored', 'Session was cancelled during startup; the original setup is restored.'
    elif alive:
        phase = 'stopping' if stop_valid or host else 'running' if startup_reported and checks.get('intentMatchesReviewedPlan') is True else 'starting'
        message = 'Waiting for the owned session to finish.' if phase == 'stopping' else 'The selected session is active.'
    elif host or stage:
        phase = 'ended_unverified' if restored else 'recovery_review'
        message = 'Session ended; original setup is restored, but clean completion is not verified.' if restored else 'Session results or current setup require review before another test.'
        if restored and process.get('observerForcedTermination') is True:
            message = ('Test reached its limit and the application was forcibly closed; original setup is restored.'
                       if host.get('endReason') == 'viewing_limit' else
                       'Application was forcibly closed; original setup is restored.')
    elif has_intent or issues:
        phase, message = 'unknown', 'Session ownership or progress cannot be established.'
    elif restored:
        phase, message = 'prepared', 'Session is prepared and has not started.'
    else:
        phase, message = 'conflicting_state', 'Current setup is in use or needs review; no changes were made.'
    return {'phase': phase, 'message': message, 'liveOwnerObserved': alive, 'ownersRetiredObserved': owners_retired,
            'stopRequestPresentAndBound': stop_valid, 'normalLifecycleReported': reported_clean,
            'completionEvidenceConsistent': complete, 'originalSetupCurrentlyClean': restored,
            'cancellationRestorationEvidenceConsistent': cancelled,
            'closeKind': 'requested_stop' if host.get('endReason') == 'manual_stop' else host.get('endReason'),
            'recoveryReviewNeeded': not alive and (not restored or (bool(host or stage) and
                checks.get('workerAndControllerRetirementReported') is not True and not cancelled)),
            'hostOutcome': {key: process.get(key) for key in ('processExited', 'exitCode', 'observerForcedTermination')}}


def inspect(plan_path, expected, powershell):
    reader = module('inspect-serato-session-result.py')
    plan_path = Path(plan_path).absolute()
    plan, actual = reader['read_record'](plan_path, 'sl3.serato-session-plan.v1')
    if actual != expected or Path(plan['projectRoot']) != ROOT:
        raise ValueError('Selected status plan binding differs')
    directory = Path(plan['capsule']['path']).parent; output = Path(plan['hostOutput'])
    for path, prefix in ((directory, 'sl3-session-capsule-'), (output, 'sl3-startup-session-')):
        if path.parent.resolve() != (ROOT / 'analysis').resolve() or not path.name.startswith(prefix) or path.is_symlink() or path.is_junction():
            raise ValueError('Status paths must remain inside the selected project')
    if plan_path.parent != directory:
        raise ValueError('Status plan must remain in its capsule directory')
    issues = []
    intent = record(output / 'intent.json', issues, 'intent')
    run = record(directory / 'session-run.lock', issues, 'runner')
    host = record(output / 'result.json', issues, 'host')
    stage = record(directory / 'session-final.json', issues, 'final')
    owners = {'runner': owner_state((run or {}).get('runner'), Path(powershell) / 'pwsh.exe'),
              'supervisor': owner_state((intent or {}).get('supervisorOwner'), plan['python']['path'])}
    saved = reader['inspect'](plan_path, expected)
    events = progress(output / 'events.jsonl', issues)
    broker = record(directory / 'broker-clean.json', issues, 'broker') or {}
    handoff = directory / 'broker-session'
    closed = handoff.with_suffix('.closed')
    unused = (broker == {'controllerExited': True, 'brokerStarted': False} and closed.is_file() and
        not closed.is_symlink() and not getattr(closed.lstat(), 'st_file_attributes', 0) & 0x400 and
        not any(path.exists() for path in (handoff, handoff.with_suffix('.stdout'), handoff.with_suffix('.stderr'),
                                          handoff.with_suffix('.pointer.json'))))
    stop_valid = False
    if (output / 'stop.txt').exists():
        try:
            if not intent or intent.get('launcherCapsuleSha256') != plan['capsule']['sha256']:
                raise ValueError('Stop intent binding unavailable')
            stop_valid = module('serato-session-stop.py')['read_request'](output / 'stop.txt', plan['capsule']['sha256'],
                hashlib.sha256((output / 'intent.json').read_bytes()).hexdigest(), intent.get('supervisorOwner'))
        except (OSError, ValueError, KeyError) as error:
            issues.append({'record': 'stop', 'message': str(error)})
    try:
        current = current_state(plan)
    except (OSError, ValueError, KeyError) as error:
        current = {'observed': False, 'currentSetupClean': False, 'message': str(error)}
        issues.append({'record': 'currentSetup', 'message': str(error)})
    summary = summarize(saved, host, stage, owners, current, stop_valid, issues, bool(intent), unused,
                        events['startupAndDetachEventReported'])
    return {'schema': 'sl3.session-status.v1', 'planSha256': actual, **summary, 'owners': owners,
            'currentSetup': current, 'progress': events, 'savedInspection': saved, 'inspectionIssues': issues,
            'pointInTimeObservation': True, 'repairAttempted': False, 'filesWritten': False,
            'registryWritten': False, 'elevationRequested': False, 'deviceOpened': False,
            'currentUsbReadinessVerified': False, 'physicalAudioVerified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-plan', type=Path, required=True)
    parser.add_argument('--expected-session-plan-sha256', required=True)
    parser.add_argument('--powershell-directory', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.session_plan, args.expected_session_plan_sha256, args.powershell_directory), indent=2))
