"""Real isolated install/registry interruptions and reviewed abort recovery."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as W
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import winreg

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/asio-recover-install.py'
BASE = 'Software\\SL3RebuildInstallRecoveryTests'
ACCESS = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY


def require(value, message):
    if not value:
        raise AssertionError(message)


class Interrupted(BaseException):
    """Bypass Exception rollback, while releasing Python contexts (not a crash)."""


def main():
    spec = importlib.util.spec_from_file_location('sl3_install_recovery_under_test', TOOL)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    i = m.install; j = i.sibling('asio-install-journal'); s = j.stage_module(); r = i.sibling('asio-registry')
    require(not s.elevated(), 'Ordinary token required for unattended suite')
    sid = s.user_sid(); policy = s.Policy(sid, (s.SYSTEM, s.ADMINS, sid))
    pointer = json.loads((ROOT/'artifacts/build/deployment-tests-last.json').read_text()); index = Path(pointer['directory'])/'index.json'
    require(j.digest(index.read_bytes()) == pointer['indexSha256'], 'Reviewed package index')
    package = json.loads(index.read_text()); bundle = ROOT/package['positiveBundle']; expected = package['bundleManifestSha256']
    s.reader().verify(bundle, expected); plan = json.loads((bundle/'deployment-plan.json').read_text())
    source_before = {p.name: j.digest(p.read_bytes()) for p in bundle.iterdir()}
    locations = [Path(plan['installationDirectory']), Path(plan['pointerPath']).parent]; before_locations = [p.exists() for p in locations]
    def live():
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, '', 0, r.READ) as root:
            machine = r.inspect(root, plan)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, r.READ) as root:
            overlay = r.inspect_overlay(root, plan)
        return machine, overlay
    live_before = live(); identity = uuid.uuid4().hex; namespace = BASE+'\\'+identity
    folder = ROOT/'artifacts/build/recover-install-tests'/identity; folder.mkdir(parents=True)
    cases = []; details = {}; removed = False
    def case(name, action):
        value = action(); cases.append({'name': name, 'passed': True}); details[name] = value; return value
    def fail(action):
        try:
            action()
        except m.InstallRecoveryFailure as error:
            require(not error.report['successful'], 'Failure cannot certify recovery')
            return error.report
        raise AssertionError('Expected recovery refusal')
    def inventory(path):
        return {p.name: j.digest(p.read_bytes()) for p in path.iterdir()} if path.exists() else None
    def unchanged(f, action):
        before = inventory(f[1]), r.inspect(f[5], plan)
        value = fail(action)
        require(before == (inventory(f[1]), r.inspect(f[5], plan)), 'Stage/registration preserved')
        require(not value['deletedRegistryKeys'] and not value['fileCleanupAttempted'], 'No premature deletion')
        return value
    @contextmanager
    def fixture(name, boundary=10, completed=False, copy_failure=False):
        base = folder/name
        with s.descriptor(policy.sddl(True)) as attributes:
            s.check(s.api('kernel32.dll', 'CreateDirectoryW', W.BOOL, [W.LPCWSTR, ctypes.POINTER(s.Attributes)])(str(base), ctypes.byref(attributes)))
        destination = base/'stage'
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, namespace+'\\'+name, 0, ACCESS) as parent:
            with winreg.CreateKeyEx(parent, 'machine-model', 0, ACCESS) as root, winreg.CreateKeyEx(parent, 'overlay-model', 0, ACCESS) as overlay:
                for container in ['SOFTWARE\\Classes\\CLSID', 'SOFTWARE\\ASIO']:
                    with winreg.CreateKeyEx(root, container, 0, ACCESS):
                        pass
                with winreg.CreateKeyEx(root, 'UnrelatedVendor', 0, ACCESS) as foreign:
                    winreg.SetValueEx(foreign, 'Preserve', 0, winreg.REG_SZ, identity)
                foreign_before = r.snapshot(root, 'UnrelatedVendor')
                real_write = j.write_flush; seen = []
                def interrupt(handle, raw):
                    real_write(handle, raw)
                    event = json.loads(raw).get('payload', {})
                    if event.get('event') == 'step' and event['data']['event'] in ('created', 'written'):
                        seen.append(event)
                    if (copy_failure and event.get('event') == 'step' and event['data']['event'] == 'before_file') or (
                        not copy_failure and ((boundary == 0 and event.get('event') == 'stage_completed') or
                                              boundary > 0 and len(seen) == boundary)):
                        raise Interrupted('Injected interruption after durable event; no Exception rollback')
                try:
                    if not completed:
                        j.write_flush = interrupt
                    try:
                        result = i.install_owned(bundle, expected, base, destination, policy, root, overlay)
                    except Interrupted:
                        require(not completed, 'Unexpected interruption')
                    else:
                        require(completed and result['successful'], 'Original install should have stopped')
                finally:
                    j.write_flush = real_write
                journals = list(base.glob('transaction-*.jsonl')); require(len(journals) == 1, 'One original journal')
                original = journals[0]; digest = j.digest(original.read_bytes())
                receipt_sha = j.digest((destination/'stage-record.json').read_bytes()) if not copy_failure else '0'*64
                yield base, destination, receipt_sha, original, digest, root, overlay
                require(j.digest(original.read_bytes()) == digest, 'Original reviewed journal unchanged')
                require(r.snapshot(root, 'UnrelatedVendor') == foreign_before, 'Unrelated registry sibling preserved')
                (folder/(name+'-registry-final.json')).write_text(json.dumps(r.inspect(root, plan), indent=2)+'\n', encoding='utf-8')
    def run(f):
        return m.recover_owned(*f[:5], policy, *f[5:])
    def remove_tree(parent, name):
        with winreg.OpenKey(parent, name, 0, ACCESS) as handle:
            children = [winreg.EnumKey(handle, n) for n in range(winreg.QueryInfoKey(handle)[0])]
            for child in children:
                remove_tree(handle, child)
        winreg.DeleteKeyEx(parent, name, winreg.KEY_WOW64_64KEY, 0)
    for name, args in [('default', []), ('plan', ['--plan']), ('no-mutation-cli', ['--recover'])]:
        value = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=20)
        require(value.returncode == (2 if args == ['--recover'] else 0), 'Inert CLI')
        case(name, lambda value=value: {'exit': value.returncode, 'stdout': value.stdout, 'stderr': value.stderr})
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, namespace, 0, ACCESS) as marker:
            winreg.SetValueEx(marker, 'SL3TestOwner', 0, winreg.REG_SZ, identity)
        for boundary in range(11):
            with fixture('boundary-'+str(boundary), boundary) as f:
                count = sum(x is not None for x in r.inspect(f[5], plan)['states'].values())
                value = case('recover-after-'+str(boundary)+'-registration-boundary', lambda: run(f))
                require(value['successful'] and len(value['deletedRegistryKeys']) == count and
                        len(value['initiallyAbsentKeys']) == 3-count and not f[1].exists() and r.inspect(f[5], plan)['allAbsent'],
                        'Actual partial keys removed and all fourteen stage files absent')
                require(j.inspect_journal(f[0], Path(value['journal']), policy)['records'][-1]['payload']['event'] ==
                        'install_recovery_completed', 'Flushed recovery completion')
        with fixture('complete', completed=True) as f:
            case('completed-install-preserved-for-normal-uninstall', lambda: unchanged(f, lambda: run(f)))
        with fixture('copy-failure', copy_failure=True) as f:
            case('interrupted-copy-without-complete-stage-preserved', lambda: unchanged(f, lambda: run(f)))
        with fixture('foreign-value') as f:
            with winreg.OpenKey(f[5], r.entries(plan)[0]['key'], 0, ACCESS) as key:
                winreg.SetValueEx(key, 'Foreign', 0, winreg.REG_SZ, 'preserve')
            case('unknown-registry-value-preserved', lambda: unchanged(f, lambda: run(f)))
        with fixture('wrong-type') as f:
            with winreg.OpenKey(f[5], r.entries(plan)[0]['key'], 0, ACCESS) as key:
                winreg.SetValueEx(key, '', 0, winreg.REG_EXPAND_SZ, r.entries(plan)[0]['strings'][''])
            case('same-text-wrong-registry-type-preserved', lambda: unchanged(f, lambda: run(f)))
        with fixture('foreign-child') as f:
            with winreg.CreateKeyEx(f[5], r.entries(plan)[2]['key']+'\\ForeignChild', 0, ACCESS):
                pass
            case('unknown-registry-child-preserved', lambda: unchanged(f, lambda: run(f)))
        with fixture('unwitnessed', 0) as f:
            with winreg.CreateKeyEx(f[5], r.entries(plan)[0]['key'], 0, ACCESS):
                pass
            case('unwitnessed-empty-key-preserved', lambda: unchanged(f, lambda: run(f)))
        with fixture('overlay') as f:
            with winreg.CreateKeyEx(f[6], r.entries(plan)[0]['key'], 0, ACCESS):
                pass
            case('user-overlay-blocks-recovery', lambda: unchanged(f, lambda: run(f)))
        with fixture('unknown-file') as f:
            (f[1]/'foreign.txt').write_bytes(b'preserve unknown data')
            case('unknown-stage-data-blocks-registry-deletion', lambda: unchanged(f, lambda: run(f)))
        with fixture('changed-file') as f:
            (f[1]/'README.txt').write_bytes(b'changed data')
            case('changed-stage-file-blocks-registry-deletion', lambda: unchanged(f, lambda: run(f)))
        with fixture('missing-file') as f:
            (f[1]/'README.txt').unlink()
            case('partial-stage-blocks-registry-deletion', lambda: unchanged(f, lambda: run(f)))
        with fixture('hardlink') as f:
            alias = f[0]/'readme-link.txt'
            try:
                os.link(f[1]/'README.txt', alias)
                case('hardlinked-payload-preserved', lambda: unchanged(f, lambda: run(f)))
            finally:
                alias.unlink()
        with fixture('replacement-file') as f:
            target = f[1]/'README.txt'; saved = f[0]/'saved-readme.txt'; data = target.read_bytes(); target.replace(saved)
            try:
                with s.descriptor(policy.sddl(False)) as attributes:
                    with s.open_file(target, access=0xc0000000, share=0, create=1, security=attributes) as handle:
                        j.write_flush(handle, data)
                case('same-byte-new-identity-file-preserved', lambda: unchanged(f, lambda: run(f)))
            finally:
                saved.replace(target)
        with fixture('bad-journal-hash') as f:
            case('wrong-journal-review-hash-refused', lambda: unchanged(f, lambda: m.recover_owned(*f[:4], '0'*64, policy, *f[5:])))
        with fixture('bad-stage-hash') as f:
            case('wrong-stage-review-hash-refused', lambda: unchanged(f, lambda: m.recover_owned(f[0], f[1], '0'*64, *f[3:5], policy, *f[5:])))
        with fixture('lock-conflict') as f:
            with j.transaction(f[0], policy, 'install', {'packageId': plan['packageId']}):
                case('competing-transaction-preserves-all-state', lambda: unchanged(f, lambda: run(f)))
        with fixture('journal-before-delete') as f:
            real_write = j.write_flush
            def poisoned(handle, raw):
                if b'"event":"install_recovery_before_registry_delete"' in raw:
                    raise OSError('Injected journal failure before first mutation')
                real_write(handle, raw)
            try:
                j.write_flush = poisoned
                value = case('journal-failure-before-first-delete-preserves-state', lambda: unchanged(f, lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(not value['failureJournalPersisted'], 'Poisoned journal cannot claim failure flush')
        with fixture('journal-after-delete') as f:
            real_write = j.write_flush
            def poisoned(handle, raw):
                if b'"event":"install_recovery_registry_deleted"' in raw:
                    raise OSError('Injected journal failure after one deletion')
                real_write(handle, raw)
            try:
                j.write_flush = poisoned
                value = case('failure-reports-one-additional-key-deletion', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(len(value['deletedRegistryKeys']) == 1 and not value['fileCleanupAttempted'], 'Exact partial registry outcome')
            value = case('explicit-retry-checks-original-and-fresh-remaining-state', lambda: run(f))
            require(value['successful'] and len(value['deletedRegistryKeys']) == 2 and len(value['initiallyAbsentKeys']) == 1,
                    'Retry acts on actual survivors only')
        with fixture('late-foreign') as f:
            real_write = j.write_flush; injected = []
            def foreign(handle, raw):
                real_write(handle, raw)
                if b'"event":"install_recovery_before_registry_delete"' in raw and not injected:
                    with winreg.OpenKey(f[5], r.entries(plan)[0]['key'], 0, ACCESS) as key:
                        winreg.SetValueEx(key, 'Foreign', 0, winreg.REG_SZ, 'preserve late value')
                    injected.append(True)
            try:
                j.write_flush = foreign
                value = case('late-foreign-value-blocks-first-deletion', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(injected and not value['deletedRegistryKeys'] and len(list(f[1].iterdir())) == 14, 'Late foreign state and stage preserved')
        with fixture('busy-stage') as f:
            with s.open_file(f[1]/'sl3_asio.dll'):
                value = case('busy-stage-refuses-file-removal-after-registry-removal', lambda: fail(lambda: run(f)))
            require(r.inspect(f[5], plan)['allAbsent'] and len(list(f[1].iterdir())) == 14 and
                    value['fileCleanupAttempted'] and not value['fileResult']['deleteMarkedFiles'], 'Truthful partial outcome')
            value = case('busy-stage-explicit-retry-completes-after-handle-release', lambda: run(f))
            require(value['successful'] and len(value['initiallyAbsentKeys']) == 3 and not value['deletedRegistryKeys'], 'Registry absence is fresh observation')
        with fixture('partial-file-removal') as f:
            real_write = j.write_flush
            def poisoned(handle, raw):
                event = json.loads(raw).get('payload', {})
                if event.get('event') == 'step' and event['data']['event'] == 'deleted':
                    raise OSError('Injected journal failure after first actual file deletion')
                real_write(handle, raw)
            try:
                j.write_flush = poisoned
                value = case('interrupted-cleanup-retains-file-recovery-snapshot', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(value['fileRecoverySnapshotPersisted'] and len(value['fileResult']['absentObservedFiles']) == 1 and
                    r.inspect(f[5], plan)['allAbsent'], 'Exact partial file result and durable recovery snapshot')
            file_recovery = i.sibling('asio-recover-files'); recovery_journal = Path(value['journal'])
            recovered = case('reviewed-new-recovery-journal-finishes-partial-files', lambda: file_recovery.recover_owned(
                bundle, expected, f[0], f[1], f[2], recovery_journal, j.digest(recovery_journal.read_bytes()), policy, *f[5:]))
            require(recovered['successful'] and len(recovered['initiallyAbsentFiles']) == 1 and
                    len(recovered['absentObservedFiles']) == 13 and not f[1].exists(), 'Composed file recovery uses fresh survivor state')
        with fixture('completion-failure') as f:
            real_write = j.write_flush
            def poisoned(handle, raw):
                if b'"event":"install_recovery_completed"' in raw:
                    raise OSError('Injected final completion journal failure')
                real_write(handle, raw)
            try:
                j.write_flush = poisoned
                value = case('completion-journal-failure-does-not-certify-recovery', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(value['directoryAbsentObserved'] and value['finalRegistryAbsentObserved'] and
                    not value['failureJournalPersisted'], 'Absence observations differ from durable completion')
            file_recovery = i.sibling('asio-recover-files'); recovery_journal = Path(value['journal'])
            recovered = case('file-recovery-reconciles-already-absent-stage', lambda: file_recovery.recover_owned(
                bundle, expected, f[0], f[1], f[2], recovery_journal, j.digest(recovery_journal.read_bytes()), policy, *f[5:]))
            require(recovered['successful'] and recovered['directoryAlreadyAbsentObserved'] and
                    not recovered['absentObservedFiles'], 'No files recreated or historical success invented')
        with fixture('late-cleanup-overlay') as f:
            real_write = j.write_flush; injected = []
            def overlay_change(handle, raw):
                real_write(handle, raw)
                event = json.loads(raw).get('payload', {})
                if event.get('event') == 'step' and event['data']['event'] == 'before_delete' and not injected:
                    with winreg.CreateKeyEx(f[6], r.entries(plan)[0]['key'], 0, ACCESS):
                        pass
                    injected.append(True)
            try:
                j.write_flush = overlay_change
                value = case('late-overlay-blocks-first-file-deletion', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(injected and value['fileCleanupAttempted'] and not value['fileResult']['deleteMarkedFiles'] and
                    len(list(f[1].iterdir())) == 14, 'Late overlay and full stage preserved')
        try:
            m.recover_production(folder, folder/'stage', '0'*64, folder/'journal', '0'*64)
        except ValueError as error:
            require('administrator token' in str(error), 'Production token gate')
            case('production-refuses-normal-token', lambda: {'refused': True, 'error': str(error)})
        else:
            raise AssertionError('Production must refuse ordinary token')
        require(live() == live_before, 'Live machine/current-user registration unchanged')
        require(source_before == {p.name: j.digest(p.read_bytes()) for p in bundle.iterdir()}, 'Reviewed source bundle unchanged')
        require([p.exists() for p in locations] == before_locations, 'Planned production/profile locations unchanged')
    finally:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, ACCESS) as marker:
            require(winreg.QueryValueEx(marker, 'SL3TestOwner')[0] == identity, 'Exact UUID namespace marker')
        require(namespace == BASE+'\\'+identity, 'Private registry cleanup boundary')
        remove_tree(winreg.HKEY_CURRENT_USER, namespace)
        try:
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, r.READ)
        except FileNotFoundError:
            removed = True
        require(removed, 'Private namespace observed absent')
    (folder/'case-details.json').write_text(json.dumps(details, indent=2)+'\n', encoding='utf-8')
    paths = [TOOL, Path(__file__), ROOT/'scripts/asio-install.py', ROOT/'scripts/asio-install-journal.py',
             ROOT/'scripts/asio-file-stage.py', ROOT/'scripts/asio-registry.py', ROOT/'scripts/asio-recover-files.py',
             ROOT/'scripts/asio-uninstall.py', ROOT/'scripts/asio-runtime-check.py']
    value = {'schema': 'sl3.install-recovery-tests.v1', 'cases': cases,
             'files': {p.relative_to(folder).as_posix(): j.digest(p.read_bytes()) for p in folder.rglob('*') if p.is_file()},
             'sourceSha256': {p.relative_to(ROOT).as_posix(): j.digest(p.read_bytes()) for p in paths},
             'privateRegistryNamespaceRemoved': removed, 'liveRegistrationsUnchanged': True, 'sourceBundleUnchanged': True,
             'originalJournalsUnchanged': True, 'plannedLocationsUnchanged': True, 'nonElevated': True,
             'productionOperationExecuted': False, 'partialCopyRecoverySupported': False, 'partialFileRecoverySupported': False,
             'exceptionInterruptionReleasesContexts': True, 'actualProcessTerminationTested': False,
             'testRegistrationPointsAtPlannedPathNotWorkspaceStage': True, 'installedAsioActivationTested': False,
             'packageBinaryExecuted': False, 'deviceAccess': False}
    index = folder/'index.json'; index.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/recover-install-tests-last.json').write_text(json.dumps({'directory': str(folder),
        'indexSha256': j.digest(index.read_bytes())}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'privateRegistryNamespaceRemoved': removed, 'evidenceDirectory': str(folder)}))


if __name__ == '__main__':
    main()
