"""Actual interrupted removal/recovery, private HKCU and workspace stages only."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as W
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import uuid
import winreg

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/asio-recover-uninstall.py'
BASE = 'Software\\SL3RebuildRecoveryTests'
ACCESS = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    spec = importlib.util.spec_from_file_location('sl3_recovery_under_test', TOOL)
    recovery = importlib.util.module_from_spec(spec); spec.loader.exec_module(recovery)
    u = recovery.uninstall; j = u.sibling('asio-install-journal'); s = j.stage_module(); r = u.sibling('asio-registry')
    require(not s.elevated(), 'Unattended suite must be non-elevated')
    sid = s.user_sid(); policy = s.Policy(sid, (s.SYSTEM, s.ADMINS, sid))
    pointer = json.loads((Path(sys.argv[1]).absolute() if len(sys.argv) == 2 else ROOT/'artifacts/build/deployment-tests-last.json').read_text()); index = Path(pointer['directory'])/'index.json'
    require(j.digest(index.read_bytes()) == pointer['indexSha256'], 'Reviewed package test index')
    package = json.loads(index.read_text()); bundle = ROOT/package['positiveBundle']; expected = package['bundleManifestSha256']
    staged_files = len(json.loads((bundle/'bundle-manifest.json').read_text())['files']) + 3
    s.reader().verify(bundle, expected); plan = json.loads((bundle/'deployment-plan.json').read_text())
    before_bundle = {p.name: j.digest(p.read_bytes()) for p in bundle.iterdir()}
    locations = [Path(plan['installationDirectory']), Path(plan['pointerPath']).parent]; before_locations = [p.exists() for p in locations]
    def live():
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, '', 0, r.READ) as root:
            machine = r.inspect(root, plan)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, r.READ) as root:
            overlay = r.inspect_overlay(root, plan)
        return machine, overlay
    before_live = live(); identity = uuid.uuid4().hex; namespace = BASE+'\\'+identity
    folder = ROOT/'artifacts/build/recover-uninstall-tests'/identity; folder.mkdir(parents=True)
    cases = []; details = {}; removed = False
    def case(name, action):
        value = action(); cases.append({'name': name, 'passed': True}); details[name] = value; return value
    def fail(action):
        try:
            action()
        except recovery.RecoveryFailure as error:
            require(not error.report['successful'], 'Failure cannot certify recovery')
            return error.report
        raise AssertionError('Expected recovery refusal')
    @contextmanager
    def fixture(name, deleted=1, file_interruption=False):
        base = folder/name
        with s.descriptor(policy.sddl(True)) as attributes:
            s.check(s.api('kernel32.dll', 'CreateDirectoryW', W.BOOL, [W.LPCWSTR, ctypes.POINTER(s.Attributes)])(str(base), ctypes.byref(attributes)))
        destination = base/'stage'; receipt = s.stage_new(bundle, expected, destination, policy)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, namespace+'\\'+name, 0, ACCESS) as parent:
            with winreg.CreateKeyEx(parent, 'machine-model', 0, ACCESS) as root, winreg.CreateKeyEx(parent, 'overlay-model', 0, ACCESS) as overlay:
                for container in ['SOFTWARE\\Classes\\CLSID', 'SOFTWARE\\ASIO']:
                    with winreg.CreateKeyEx(root, container, 0, ACCESS):
                        pass
                with winreg.CreateKeyEx(root, 'UnrelatedVendor', 0, ACCESS) as foreign:
                    winreg.SetValueEx(foreign, 'Preserve', 0, winreg.REG_SZ, identity)
                foreign_before = r.snapshot(root, 'UnrelatedVendor'); r.register_new(root, plan)
                real_unregister = r.unregister_owned; real_cleanup = s.remove_stage; seen = []
                def interrupted_registry(root, plan, journal):
                    def callback(event):
                        journal(event)
                        if event['event'] == 'deleted':
                            seen.append(event)
                        if (deleted == 0 and event['event'] == 'before_delete') or (deleted > 0 and len(seen) == deleted):
                            raise OSError('Simulated interruption during original unregister')
                    return real_unregister(root, plan, callback)
                def interrupted_files(destination, digest, policy, journal):
                    def callback(event):
                        journal(event)
                        if event['event'] == 'deleted':
                            raise OSError('Simulated original cleanup interruption after first file')
                    return real_cleanup(destination, digest, policy, callback)
                try:
                    if file_interruption:
                        s.remove_stage = interrupted_files
                    else:
                        r.unregister_owned = interrupted_registry
                    try:
                        u.uninstall_owned(base, destination, receipt['stageRecordSha256'], policy, root, overlay)
                    except u.UninstallFailure as error:
                        original_report = error.report
                    else:
                        raise AssertionError('Expected original interrupted removal')
                finally:
                    r.unregister_owned = real_unregister; s.remove_stage = real_cleanup
                source = Path(original_report['journal']); source_hash = j.digest(source.read_bytes())
                (folder/(name+'-original-report.json')).write_text(json.dumps(original_report, indent=2)+'\n', encoding='utf-8')
                yield base, destination, receipt['stageRecordSha256'], source, source_hash, root, overlay
                require(j.digest(source.read_bytes()) == source_hash, 'Original reviewed journal remains byte-identical')
                require(r.snapshot(root, 'UnrelatedVendor') == foreign_before, 'Foreign registry sibling preserved')
                (folder/(name+'-registry-final.json')).write_text(json.dumps(r.inspect(root, plan), indent=2)+'\n', encoding='utf-8')
    def run(f):
        return recovery.recover_owned(*f[:5], policy, *f[5:])
    def no_mutation(f, action):
        before = r.inspect(f[5], plan); files = {p.name: j.digest(p.read_bytes()) for p in f[1].iterdir()}
        value = fail(action)
        require(before == r.inspect(f[5], plan) and files == {p.name: j.digest(p.read_bytes()) for p in f[1].iterdir()}, 'Refusal preserves all remaining registry/files')
        return value
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
        for deleted in range(4):
            with fixture('after-'+str(deleted), deleted) as f:
                value = case('recover-after-'+str(deleted)+'-registry-deletions', lambda: run(f))
                require(value['successful'] and len(value['deletedRegistryKeys']) == 3-deleted and
                        len(value['initiallyAbsentKeys']) == deleted and len(value['fileResult']['absentObservedFiles']) == staged_files and
                        not f[1].exists() and r.inspect(f[5], plan)['allAbsent'], 'Recovery reflects fresh absence and only remaining exact keys')
                journal = j.inspect_journal(f[0], Path(value['journal']), policy)
                require(journal['records'][-1]['payload']['event'] == 'recovery_completed', 'New completion record flushed')
        with fixture('wrong-journal-sha') as f:
            case('wrong-reviewed-journal-hash-refused', lambda: no_mutation(f, lambda: recovery.recover_owned(*f[:4], '0'*64, policy, *f[5:])))
        with fixture('wrong-stage-sha') as f:
            case('wrong-stage-hash-refused', lambda: no_mutation(f, lambda: recovery.recover_owned(f[0], f[1], '0'*64, f[3], f[4], policy, *f[5:])))
        with fixture('foreign-value') as f:
            with winreg.OpenKey(f[5], r.entries(plan)[2]['key'], 0, ACCESS) as key:
                winreg.SetValueEx(key, 'Foreign', 0, winreg.REG_SZ, 'preserve')
            case('foreign-remaining-value-preserved', lambda: no_mutation(f, lambda: run(f)))
        with fixture('foreign-child') as f:
            with winreg.CreateKeyEx(f[5], r.entries(plan)[0]['key']+'\\ForeignChild', 0, ACCESS):
                pass
            case('foreign-remaining-child-preserved', lambda: no_mutation(f, lambda: run(f)))
        with fixture('wrong-value-type') as f:
            with winreg.OpenKey(f[5], r.entries(plan)[2]['key'], 0, ACCESS) as key:
                winreg.SetValueEx(key, 'SL3PackageId', 0, winreg.REG_DWORD, 1)
            case('wrong-remaining-value-type-preserved', lambda: no_mutation(f, lambda: run(f)))
        with fixture('overlay') as f:
            with winreg.CreateKeyEx(f[6], r.entries(plan)[0]['key'], 0, ACCESS):
                pass
            case('current-user-overlay-preserved', lambda: no_mutation(f, lambda: run(f)))
        with fixture('changed-file') as f:
            (f[1]/'README.txt').write_bytes(b'changed after interruption')
            case('changed-stage-refused-before-registry-repair', lambda: no_mutation(f, lambda: run(f)))
        with fixture('partial-files', file_interruption=True) as f:
            require(len(list(f[1].iterdir())) == (staged_files - 1), 'Original interruption removed exactly one file')
            case('partially-removed-stage-refused-without-guessing', lambda: no_mutation(f, lambda: run(f)))
        with fixture('same-byte-journal-replacement') as f:
            data = f[3].read_bytes(); saved = f[0]/'saved-original.jsonl'; f[3].replace(saved)
            try:
                with s.descriptor(policy.sddl(False)) as attributes:
                    with s.open_file(f[3], access=0xc0000000, share=0, create=1, security=attributes) as handle:
                        j.write_flush(handle, data)
                case('same-byte-journal-new-identity-refused', lambda: no_mutation(f, lambda: run(f)))
            finally:
                saved.replace(f[3])
        with fixture('wrong-original-action') as f:
            with j.transaction(f[0], policy, 'install', {'packageId': plan['packageId']}) as writer:
                other = writer.path
            case('install-journal-cannot-authorize-uninstall-recovery', lambda: no_mutation(f, lambda: recovery.recover_owned(
                f[0], f[1], f[2], other, j.digest(other.read_bytes()), policy, *f[5:])))
        with fixture('lock-conflict') as f:
            with j.transaction(f[0], policy, 'uninstall', {'packageId': plan['packageId']}):
                case('active-installer-lock-preserves-state', lambda: no_mutation(f, lambda: run(f)))
        with fixture('initial-journal-failure') as f:
            real_write = j.write_flush
            def fail_validation(handle, raw):
                if b'"event":"recovery_validated"' in raw:
                    raise OSError('Simulated recovery validation flush failure')
                real_write(handle, raw)
            try:
                j.write_flush = fail_validation
                value = case('recovery-journal-failure-before-mutation', lambda: no_mutation(f, lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(not value['deletedRegistryKeys'] and not value['fileCleanupAttempted'] and not value['failureJournalPersisted'], 'No mutation after poisoned journal')
        with fixture('interrupted-recovery') as f:
            real_write = j.write_flush
            def fail_after_delete(handle, raw):
                if b'"event":"recovery_registry_deleted"' in raw:
                    raise OSError('Simulated journal failure after one recovery deletion')
                real_write(handle, raw)
            try:
                j.write_flush = fail_after_delete
                value = case('interrupted-recovery-reports-exact-additional-deletion', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(len(value['deletedRegistryKeys']) == 1 and not value['fileCleanupAttempted'] and len(list(f[1].iterdir())) == staged_files,
                    'One additional key removed, complete stage retained')
            value = case('explicit-retry-uses-original-reviewed-journal-and-fresh-state', lambda: run(f))
            require(value['successful'] and len(value['initiallyAbsentKeys']) == 2 and len(value['deletedRegistryKeys']) == 1, 'Retry acts only on last remaining key')
        try:
            recovery.recover_production(folder, folder/'stage', '0'*64, folder/'journal', '0'*64)
        except ValueError as error:
            require('administrator token' in str(error), 'Production elevation gate before action')
            case('production-refuses-normal-token', lambda: {'refused': True, 'error': str(error)})
        else:
            raise AssertionError('Production must refuse ordinary token')
        require(live() == before_live, 'Live machine/current-user registrations unchanged')
        require(before_bundle == {p.name: j.digest(p.read_bytes()) for p in bundle.iterdir()}, 'Reviewed source bundle unchanged')
        require([p.exists() for p in locations] == before_locations, 'Planned production/profile locations unchanged')
    finally:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, ACCESS) as marker:
            require(winreg.QueryValueEx(marker, 'SL3TestOwner')[0] == identity, 'Exact namespace owner marker')
        require(namespace == BASE+'\\'+identity, 'Private UUID registry cleanup boundary')
        remove_tree(winreg.HKEY_CURRENT_USER, namespace)
        try:
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, r.READ)
        except FileNotFoundError:
            removed = True
        require(removed, 'Private registry namespace independently observed absent')
    (folder/'case-details.json').write_text(json.dumps(details, indent=2)+'\n', encoding='utf-8')
    paths = [TOOL, Path(__file__), ROOT/'scripts/asio-uninstall.py', ROOT/'scripts/asio-install-journal.py', ROOT/'scripts/asio-file-stage.py', ROOT/'scripts/asio-registry.py']
    value = {'schema': 'sl3.uninstall-recovery-tests.v1', 'cases': cases,
             'files': {p.relative_to(folder).as_posix(): j.digest(p.read_bytes()) for p in folder.rglob('*') if p.is_file()},
             'sourceSha256': {p.relative_to(ROOT).as_posix(): j.digest(p.read_bytes()) for p in paths},
             'privateRegistryNamespaceRemoved': removed, 'liveRegistrationsUnchanged': True, 'sourceBundleUnchanged': True,
             'plannedLocationsUnchanged': True, 'originalJournalsUnchanged': True, 'nonElevated': True,
             'productionOperationExecuted': False, 'partialFileRecoverySupported': False,
             'testRegistrationPointsAtPlannedPathNotWorkspaceStage': True, 'installedAsioActivationTested': False,
             'packageBinaryExecuted': False, 'deviceAccess': False}
    index = folder/'index.json'; index.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/recover-uninstall-tests-last.json').write_text(json.dumps(
        {'directory': str(folder), 'indexSha256': j.digest(index.read_bytes())}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'privateRegistryNamespaceRemoved': removed, 'evidenceDirectory': str(folder)}))


if __name__ == '__main__':
    main()
