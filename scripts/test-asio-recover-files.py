"""Real interrupted file-removal recovery in private Windows fixtures only."""
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
import os

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/asio-recover-files.py'
BASE = 'Software\\SL3RebuildFileRecoveryTests'
ACCESS = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    spec = importlib.util.spec_from_file_location('sl3_file_recovery_under_test', TOOL)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    u = m.uninstall; j = u.sibling('asio-install-journal'); s = j.stage_module(); r = u.sibling('asio-registry')
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
    folder = ROOT/'artifacts/build/recover-files-tests'/identity; folder.mkdir(parents=True)
    cases = []; details = {}; removed = False
    def case(name, action):
        value = action(); cases.append({'name': name, 'passed': True}); details[name] = value; return value
    def fail(action):
        try:
            action()
        except m.FileRecoveryFailure as error:
            require(not error.report['successful'], 'Failure cannot certify recovery')
            return error.report
        raise AssertionError('Expected recovery refusal')
    def files(path):
        return None if not path.exists() else {p.name: j.digest(p.read_bytes()) for p in path.iterdir()}
    def no_mutation(f, operation):
        before_files = files(f[1]); before_registry = r.inspect(f[5], plan)
        value = fail(operation)
        require(not value['deleteMarkedFiles'] and before_files == files(f[1]) and before_registry == r.inspect(f[5], plan), 'All surviving files/registry preserved on refusal')
        return value
    @contextmanager
    def fixture(name, deleted=1):
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
                real_cleanup = s.remove_stage; real_write = j.write_flush; seen = []
                def interrupted(destination, digest, policy, journal):
                    def callback(event):
                        journal(event)
                        if event['event'] == 'deleted':
                            seen.append(event)
                        if (deleted == 0 and event['event'] == 'validated') or (deleted > 0 and len(seen) == deleted):
                            raise OSError('Simulated original file cleanup interruption')
                    return real_cleanup(destination, digest, policy, callback)
                def fail_completion(handle, raw):
                    if b'"event":"uninstall_completed"' in raw:
                        raise OSError('Simulated original completion-record failure after directory removal')
                    real_write(handle, raw)
                try:
                    if deleted == 15:
                        j.write_flush = fail_completion
                    else:
                        s.remove_stage = interrupted
                    try:
                        u.uninstall_owned(base, destination, receipt['stageRecordSha256'], policy, root, overlay)
                    except u.UninstallFailure as error:
                        original_report = error.report
                    else:
                        raise AssertionError('Original removal must stop at injected failure')
                finally:
                    s.remove_stage = real_cleanup; j.write_flush = real_write
                original = Path(original_report['journal']); digest = j.digest(original.read_bytes())
                (folder/(name+'-original-report.json')).write_text(json.dumps(original_report, indent=2)+'\n', encoding='utf-8')
                yield base, destination, receipt['stageRecordSha256'], original, digest, root, overlay
                require(j.digest(original.read_bytes()) == digest, 'Original reviewed journal unchanged')
                require(foreign_before == r.snapshot(root, 'UnrelatedVendor'), 'Foreign registry sibling unchanged')
                (folder/(name+'-registry-final.json')).write_text(json.dumps(r.inspect(root, plan), indent=2)+'\n', encoding='utf-8')
    def run(f):
        return m.recover_owned(bundle, expected, *f[:5], policy, *f[5:])
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
        for deleted in range(16):
            with fixture('boundary-'+str(deleted), deleted) as f:
                value = case('recover-after-'+str(deleted)+'-file-boundary', lambda: run(f))
                absent = min(deleted, 14)
                require(value['successful'] and len(value['initiallyAbsentFiles']) == absent and
                        len(value['absentObservedFiles']) == 14-absent and not f[1].exists() and
                        value['directoryAlreadyAbsentObserved'] == (deleted == 15), 'Exact existing/missing/new deletion accounting')
                require(j.inspect_journal(f[0], Path(value['journal']), policy)['records'][-1]['payload']['event'] == 'file_recovery_completed', 'Flushed recovery completion')
        with fixture('arbitrary-holes', 0) as f:
            for name in ['README.txt', 'sl3-asio.conf', 'bundle-manifest.json']:
                (f[1]/name).unlink()
            value = case('non-prefix-missing-files-recovered-from-fresh-state', lambda: run(f))
            require(len(value['initiallyAbsentFiles']) == 3 and len(value['absentObservedFiles']) == 11, 'No inferred deletion history')
        with fixture('foreign') as f:
            (f[1]/'foreign.txt').write_bytes(b'preserve unknown data')
            case('unknown-file-preserved-before-mutation', lambda: no_mutation(f, lambda: run(f)))
        with fixture('changed') as f:
            (f[1]/'README.txt').write_bytes(b'changed surviving data')
            case('changed-surviving-file-preserved', lambda: no_mutation(f, lambda: run(f)))
        with fixture('same-byte-new-id') as f:
            target = f[1]/'README.txt'; data = target.read_bytes(); saved = f[0]/'saved-readme.txt'; target.replace(saved)
            try:
                with s.descriptor(policy.sddl(False)) as attributes:
                    with s.open_file(target, access=0xc0000000, share=0, create=1, security=attributes) as handle:
                        j.write_flush(handle, data)
                case('same-byte-payload-replacement-preserved', lambda: no_mutation(f, lambda: run(f)))
            finally:
                saved.replace(target)
        with fixture('hardlink') as f:
            alias = f[0]/'readme-link.txt'
            try:
                os.link(f[1]/'README.txt', alias)
                case('hardlinked-survivor-preserved', lambda: no_mutation(f, lambda: run(f)))
            finally:
                alias.unlink()
        with fixture('reader') as f:
            with s.open_file(f[1]/'README.txt'):
                case('active-reader-refuses-before-new-deletion', lambda: no_mutation(f, lambda: run(f)))
        with fixture('registration-remains') as f:
            r.register_new(f[5], plan)
            case('remaining-registration-blocks-file-recovery', lambda: no_mutation(f, lambda: run(f)))
        with fixture('overlay') as f:
            with winreg.CreateKeyEx(f[6], r.entries(plan)[0]['key'], 0, ACCESS):
                pass
            case('user-overlay-blocks-file-recovery', lambda: no_mutation(f, lambda: run(f)))
        with fixture('bad-bundle-hash') as f:
            case('wrong-bundle-review-hash-refused', lambda: no_mutation(f, lambda: m.recover_owned(bundle, '0'*64, *f[:5], policy, *f[5:])))
        with fixture('bad-journal-hash') as f:
            case('wrong-journal-review-hash-refused', lambda: no_mutation(f, lambda: m.recover_owned(bundle, expected, *f[:4], '0'*64, policy, *f[5:])))
        with fixture('bad-stage-hash') as f:
            case('wrong-stage-review-hash-refused', lambda: no_mutation(f, lambda: m.recover_owned(bundle, expected, f[0], f[1], '0'*64, f[3], f[4], policy, *f[5:])))
        with fixture('recreated-root', 15) as f:
            with s.descriptor(policy.sddl(True)) as attributes:
                s.check(s.api('kernel32.dll', 'CreateDirectoryW', W.BOOL, [W.LPCWSTR, ctypes.POINTER(s.Attributes)])(str(f[1]), ctypes.byref(attributes)))
            case('recreated-empty-directory-preserved', lambda: no_mutation(f, lambda: run(f)))
        with fixture('late-unknown') as f:
            real_write = j.write_flush; injected = []
            def late_unknown(handle, raw):
                if b'"event":"file_recovery_before_delete"' in raw and not injected:
                    (f[1]/'foreign.txt').write_bytes(b'preserve late data'); injected.append(True)
                real_write(handle, raw)
            try:
                j.write_flush = late_unknown
                value = case('late-unknown-data-prevents-first-new-deletion', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(injected and not value['deleteMarkedFiles'] and len(list(f[1].iterdir())) == 14, 'Late unknown and all survivors preserved')
        with fixture('journal-after-delete') as f:
            real_write = j.write_flush
            def fail_after_delete(handle, raw):
                if b'"event":"file_recovery_deleted"' in raw:
                    raise OSError('Simulated recovery journal failure after first observed deletion')
                real_write(handle, raw)
            try:
                j.write_flush = fail_after_delete
                value = case('recovery-failure-reports-one-new-deletion', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(len(value['deleteMarkedFiles']) == len(value['absentObservedFiles']) == 1 and not value['successful'], 'Exact newly observed removal, not success')
            value = case('explicit-retry-rechecks-original-journal-and-current-survivors', lambda: run(f))
            require(value['successful'] and len(value['initiallyAbsentFiles']) == 2 and len(value['absentObservedFiles']) == 12, 'Retry does not repeat earlier deletion')
        try:
            m.recover_production(bundle, expected, folder, folder/'stage', '0'*64, folder/'journal', '0'*64)
        except ValueError as error:
            require('administrator token' in str(error), 'Production gate')
            case('production-refuses-normal-token', lambda: {'refused': True, 'error': str(error)})
        else:
            raise AssertionError('Production must refuse ordinary token')
        require(live() == live_before, 'Live registration unchanged')
        require(source_before == {p.name: j.digest(p.read_bytes()) for p in bundle.iterdir()}, 'Original bundle unchanged')
        require([p.exists() for p in locations] == before_locations, 'Planned production/profile locations unchanged')
    finally:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, ACCESS) as marker:
            require(winreg.QueryValueEx(marker, 'SL3TestOwner')[0] == identity, 'Exact UUID owner marker')
        require(namespace == BASE+'\\'+identity, 'Registry cleanup boundary')
        remove_tree(winreg.HKEY_CURRENT_USER, namespace)
        try:
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, r.READ)
        except FileNotFoundError:
            removed = True
        require(removed, 'Private namespace observed absent')
    (folder/'case-details.json').write_text(json.dumps(details, indent=2)+'\n', encoding='utf-8')
    paths = [TOOL, Path(__file__), ROOT/'scripts/asio-uninstall.py', ROOT/'scripts/asio-install-journal.py', ROOT/'scripts/asio-file-stage.py', ROOT/'scripts/asio-registry.py']
    value = {'schema': 'sl3.file-recovery-tests.v1', 'cases': cases,
        'files': {p.relative_to(folder).as_posix(): j.digest(p.read_bytes()) for p in folder.rglob('*') if p.is_file()},
        'sourceSha256': {p.relative_to(ROOT).as_posix(): j.digest(p.read_bytes()) for p in paths},
        'privateRegistryNamespaceRemoved': removed, 'liveRegistrationsUnchanged': True, 'originalJournalsUnchanged': True,
        'sourceBundleUnchanged': True, 'plannedLocationsUnchanged': True, 'nonElevated': True,
        'productionOperationExecuted': False, 'receiptOriginalIdentityAvailable': False,
        'testRegistrationPointsAtPlannedPathNotWorkspaceStage': True, 'installedAsioActivationTested': False,
        'packageBinaryExecuted': False, 'deviceAccess': False}
    index = folder/'index.json'; index.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/recover-files-tests-last.json').write_text(json.dumps({'directory': str(folder), 'indexSha256': j.digest(index.read_bytes())}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'privateRegistryNamespaceRemoved': removed, 'evidenceDirectory': str(folder)}))


if __name__ == '__main__':
    main()
