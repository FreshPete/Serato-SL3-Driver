"""Real Windows workspace-only installer exclusion, journal and cleanup tests."""
import ctypes
from ctypes import wintypes as W
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/asio-install-journal.py'


def load():
    spec = importlib.util.spec_from_file_location('sl3_journal_under_test', TOOL)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def require(value, text):
    if not value:
        raise AssertionError(text)


def main():
    j = load(); s = j.stage_module()
    require(not s.elevated(), 'Unattended tests must run non-elevated')
    sid = s.user_sid(); policy = s.Policy(sid, (s.SYSTEM, s.ADMINS, sid)); bindings = {'packageId': 'a'*64}
    test_root = ROOT/'artifacts/build/install-journal-tests'
    if len(sys.argv) > 1:
        mode, base = sys.argv[1], Path(sys.argv[2])
        require(mode in ('--child-conflict', '--child-crash') and base.is_relative_to(test_root), 'Private child fixture only')
        if mode == '--child-conflict':
            try:
                with j.transaction(base, policy, 'install', bindings):
                    raise AssertionError('Competing process acquired lock')
            except OSError as error:
                require(error.winerror == 32, 'Cross-process sharing violation')
                print(json.dumps({'refused': True, 'winerror': error.winerror})); return
        with j.transaction(base, policy, 'install', bindings) as writer:
            writer.append({'event': 'before_simulated_mutation'})
            print(json.dumps({'journal': str(writer.path)}), flush=True)
            import os
            os._exit(17)  # Intentionally skip context/finally to test OS handle release.

    folder = test_root/uuid.uuid4().hex; folder.mkdir(parents=True)
    cases = []; details = {}
    def case(name, action):
        value = action(); cases.append({'name': name, 'passed': True}); details[name] = value; return value
    def refused(action):
        try:
            action()
        except (ValueError, OSError, KeyError, TypeError) as error:
            return {'refused': True, 'error': str(error)}
        raise AssertionError('Expected refusal')
    def base(name):
        path = folder/name
        with s.descriptor(policy.sddl(True)) as attributes:
            s.check(s.api('kernel32.dll', 'CreateDirectoryW', W.BOOL, [W.LPCWSTR, ctypes.POINTER(s.Attributes)])(str(path), ctypes.byref(attributes)))
        return path
    def enter(path, p=policy, action='install', pins=bindings):
        with j.transaction(path, p, action, pins):
            return True
    for name, args in [('default', []), ('plan', ['--plan']), ('no-cli-mutation', ['--install'])]:
        def command(args=args):
            result = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=20)
            require(result.returncode == (2 if args == ['--install'] else 0), 'Inert CLI result')
            return {'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        case(name, command)

    path = base('roundtrip'); journal_path = None
    with j.transaction(path, policy, 'install', bindings) as writer:
        journal_path = writer.path
        case('same-process-exclusive-lock', lambda: refused(lambda: enter(path)))
        result = subprocess.run([sys.executable, str(Path(__file__)), '--child-conflict', str(path)],
                                capture_output=True, text=True, timeout=20)
        require(result.returncode == 0, result.stderr)
        case('real-competing-process-refused', lambda: json.loads(result.stdout))
        writer({'event': 'before_file', 'name': 'synthetic.txt'})
        writer.append({'event': 'caller_result', 'observed': 'no mutation requested'})
    result = case('flushed-journal-roundtrip', lambda: j.inspect_journal(path, journal_path, policy))
    require(len(result['records']) == 3 and result['tornTailBytes'] == 0 and not result['operationCompletionVerified'], 'Journal facts do not certify installation')
    case('closed-writer-refuses-append', lambda: refused(lambda: writer.append({'event': 'late'})))
    lock_bytes = (path/j.LOCK_NAME).read_bytes()
    case('persistent-lock-file-reused-after-close', lambda: enter(path))
    require((path/j.LOCK_NAME).read_bytes() == lock_bytes, 'Existing lock never rewritten')

    crashed = base('crashed-owner')
    result = subprocess.run([sys.executable, str(Path(__file__)), '--child-crash', str(crashed)],
                            capture_output=True, text=True, timeout=20)
    require(result.returncode == 17, result.stderr)
    crash_path = Path(json.loads(result.stdout)['journal'])
    observed = case('process-death-retains-flushed-prefix', lambda: j.inspect_journal(crashed, crash_path, policy))
    require(len(observed['records']) == 2 and observed['tornTailBytes'] == 0, 'Abrupt exit retained read-back records')
    case('process-death-releases-lock', lambda: enter(crashed))

    foreign = base('foreign-lock'); foreign_lock = foreign/j.LOCK_NAME
    with s.descriptor(policy.sddl(False)) as attributes:
        with s.open_file(foreign_lock, access=0xc0000000, share=0, create=1, security=attributes) as handle:
            j.write_flush(handle, b'foreign')
    case('foreign-lock-preserved', lambda: refused(lambda: enter(foreign)))
    require(foreign_lock.read_bytes() == b'foreign' and len(list(foreign.iterdir())) == 1, 'No journal and no foreign overwrite')
    case('production-refuses-normal-token', lambda: refused(lambda: enter(path, s.PRODUCTION)))
    case('invalid-action-before-write', lambda: refused(lambda: enter(path, action='repair')))
    case('invalid-bindings-before-write', lambda: refused(lambda: enter(path, pins={'packageId': 'A'*64})))

    raw = journal_path.read_bytes(); lines = raw.splitlines(keepends=True)
    tampered = raw.replace(b'synthetic.txt', b'tampered!.txt')
    case('changed-record-hash-refused', lambda: refused(lambda: j.parse(tampered)))
    case('reordered-records-refused', lambda: refused(lambda: j.parse(lines[0]+lines[2]+lines[1])))
    case('duplicated-record-refused', lambda: refused(lambda: j.parse(raw+lines[-1])))
    case('malformed-complete-line-refused', lambda: refused(lambda: j.parse(raw+b'not-json\n')))
    tail = case('incomplete-tail-reported-not-replayed', lambda: j.parse(raw+b'{"unfinished":'))
    require(tail['tornTailBytes'] == 14 and len(tail['records']) == 3 and not tail['automaticallyReplayed'], 'Only complete verified prefix accepted')
    case('incomplete-header-refused', lambda: refused(lambda: j.parse(lines[0][:-2])))
    case('oversized-tail-refused', lambda: refused(lambda: j.parse(raw+b'x'*(j.MAX_RECORD+1))))
    saved = path/'saved-journal.jsonl'; journal_path.replace(saved); journal_path.write_bytes(raw)
    try:
        case('same-byte-journal-replacement-refused', lambda: refused(lambda: j.inspect_journal(path, journal_path, policy)))
    finally:
        saved.replace(journal_path)

    fail_base = base('flush-failure'); real_write = j.write_flush
    with j.transaction(fail_base, policy, 'uninstall', bindings) as writer:
        def fail_flush(handle, data):
            raise OSError('Simulated flush failure; no caller mutation allowed')
        try:
            j.write_flush = fail_flush
            case('flush-failure-propagates', lambda: refused(lambda: writer({'event': 'before_delete'})))
        finally:
            j.write_flush = real_write
        case('failed-writer-poisoned', lambda: refused(lambda: writer({'event': 'retry'})))
        fail_path = writer.path
    require(len(j.inspect_journal(fail_base, fail_path, policy)['records']) == 1, 'Only header persisted')

    torn_base = base('torn-write')
    with j.transaction(torn_base, policy, 'uninstall', bindings) as writer:
        def torn_write(handle, data):
            real_write(handle, data[:len(data)//2])
            raise OSError('Simulated incomplete record write')
        try:
            j.write_flush = torn_write
            case('partial-write-propagates', lambda: refused(lambda: writer({'event': 'before_delete'})))
        finally:
            j.write_flush = real_write
        torn_path = writer.path
    value = case('actual-file-torn-tail-preserved', lambda: j.inspect_journal(torn_base, torn_path, policy))
    require(len(value['records']) == 1 and value['tornTailBytes'] > 0, 'Incomplete bytes retained without replay/repair')

    package_pointer = json.loads((ROOT/'artifacts/build/deployment-tests-last.json').read_text())
    index = Path(package_pointer['directory'])/'index.json'
    require(j.digest(index.read_bytes()) == package_pointer['indexSha256'], 'Reviewed package index')
    package = json.loads(index.read_text()); bundle = ROOT/package['positiveBundle']
    source_before = {p.name: j.digest(p.read_bytes()) for p in bundle.iterdir()}
    plan = json.loads((bundle/'deployment-plan.json').read_text()); locations = [Path(plan['installationDirectory']), Path(plan['pointerPath']).parent]
    before = [p.exists() for p in locations]
    integration = base('cleanup-integration'); destination = integration/'stage'
    receipt = s.stage_new(bundle, package['bundleManifestSha256'], destination, policy)
    with j.transaction(integration, policy, 'uninstall', {'packageId': json.loads((destination/'stage-record.json').read_text())['packageId'],
            'stageRecordSha256': receipt['stageRecordSha256']}) as writer:
        case('actual-owned-cleanup-with-flushed-journal', lambda: s.remove_stage(destination, receipt['stageRecordSha256'], policy, writer))
        recovery_path = writer.path
    recovery = case('recovery-journal-survives-stage-removal', lambda: j.inspect_journal(integration, recovery_path, policy))
    steps = [r['payload']['data'] for r in recovery['records'][1:]]
    require(steps[0]['event'] == 'validated' and len(steps[0]['stageRecord']['files']) == 12 and
            len([e for e in steps if e['event'] == 'deleted']) == 14 and not destination.exists(), 'Complete external recovery record survives cleanup')

    interrupted = base('interrupted-cleanup'); destination = interrupted/'stage'
    receipt = s.stage_new(bundle, package['bundleManifestSha256'], destination, policy)
    with j.transaction(interrupted, policy, 'uninstall', bindings) as writer:
        def stop_after_first(event):
            writer(event)
            if event['event'] == 'deleted':
                raise OSError('Simulated installer interruption after a flushed deletion observation')
        def interrupted_cleanup():
            try:
                s.remove_stage(destination, receipt['stageRecordSha256'], policy, stop_after_first)
            except s.CleanupFailure as error:
                require(error.report['absentObservedFiles'] == ['sl3_asio.dll'] and
                        error.report['stageRecordStillPresent'], 'Exact partial removal report')
                return error.report
            raise AssertionError('Expected interrupted cleanup')
        case('actual-interrupted-cleanup-exact-partial', interrupted_cleanup)
        partial_path = writer.path
    partial = case('interrupted-cleanup-has-external-recovery-prefix', lambda: j.inspect_journal(interrupted, partial_path, policy))
    steps = [r['payload']['data'] for r in partial['records'][1:]]
    require(steps[0]['event'] == 'validated' and steps[-1] == {'event': 'deleted', 'name': 'sl3_asio.dll'} and
            len(list(destination.iterdir())) == 13, 'External prefix and retained recovery records agree')

    failed_cleanup = base('failed-cleanup-journal'); destination = failed_cleanup/'stage'
    receipt = s.stage_new(bundle, package['bundleManifestSha256'], destination, policy)
    with j.transaction(failed_cleanup, policy, 'uninstall', bindings) as writer:
        try:
            j.write_flush = fail_flush
            def fail_before_cleanup():
                try:
                    s.remove_stage(destination, receipt['stageRecordSha256'], policy, writer)
                except s.CleanupFailure as error:
                    require(not error.report['deleteMarkedFiles'] and len(list(destination.iterdir())) == 14 and
                            writer.poisoned, 'Journal failure prevents first mutation and poisons writer')
                    return error.report
                raise AssertionError('Expected journal failure before cleanup')
            case('actual-journal-failure-prevents-cleanup-mutation', fail_before_cleanup)
        finally:
            j.write_flush = real_write

    require(source_before == {p.name: j.digest(p.read_bytes()) for p in bundle.iterdir()}, 'Reviewed bundle unchanged')
    require([p.exists() for p in locations] == before, 'Planned installation/profile locations unchanged')
    (folder/'case-details.json').write_text(json.dumps(details, indent=2)+'\n', encoding='utf-8')
    files = {p.relative_to(folder).as_posix(): j.digest(p.read_bytes()) for p in folder.rglob('*') if p.is_file()}
    result = {'schema': 'sl3.install-journal-tests.v1', 'cases': cases, 'files': files,
              'sourceSha256': {p.relative_to(ROOT).as_posix(): j.digest(p.read_bytes()) for p in [TOOL, Path(__file__), ROOT/'scripts/asio-file-stage.py']},
              'nonElevated': True, 'testPolicyOwnerCurrentUser': True, 'productionOperationExecuted': False,
              'plannedLocationsUnchanged': True, 'sourceBundleUnchanged': True, 'registryWritten': False,
              'deviceAccess': False, 'binaryPayloadExecuted': False, 'powerLossDurabilityTested': False}
    index = folder/'index.json'; index.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/install-journal-tests-last.json').write_text(json.dumps(
        {'directory': str(folder), 'indexSha256': j.digest(index.read_bytes())}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'evidenceDirectory': str(folder)}))


if __name__ == '__main__':
    main()
