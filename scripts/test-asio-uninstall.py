"""Isolated HKCU and workspace files: no machine registration or deployment."""
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
TOOL = ROOT/'scripts/asio-uninstall.py'
BASE = 'Software\\SL3RebuildUninstallTests'
ACCESS = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    spec = importlib.util.spec_from_file_location('sl3_uninstall_under_test', TOOL)
    u = importlib.util.module_from_spec(spec); spec.loader.exec_module(u)
    j = u.sibling('asio-install-journal'); s = j.stage_module(); r = u.sibling('asio-registry')
    require(not s.elevated(), 'Unattended suite requires an ordinary token')
    sid = s.user_sid(); policy = s.Policy(sid, (s.SYSTEM, s.ADMINS, sid))
    pointer = json.loads((ROOT/'artifacts/build/deployment-tests-last.json').read_text()); index = Path(pointer['directory'])/'index.json'
    require(j.digest(index.read_bytes()) == pointer['indexSha256'], 'Reviewed package index')
    package = json.loads(index.read_text()); bundle = ROOT/package['positiveBundle']; bundle_hash = package['bundleManifestSha256']
    s.reader().verify(bundle, bundle_hash); plan = json.loads((bundle/'deployment-plan.json').read_text())
    before_bundle = {p.name: j.digest(p.read_bytes()) for p in bundle.iterdir()}
    def live():
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, '', 0, r.READ) as root:
            machine = r.inspect(root, plan)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, r.READ) as root:
            overlay = r.inspect_overlay(root, plan)
        return machine, overlay
    live_before = live(); locations = [Path(plan['installationDirectory']), Path(plan['pointerPath']).parent]
    locations_before = [p.exists() for p in locations]
    identity = uuid.uuid4().hex; namespace = BASE+'\\'+identity
    folder = ROOT/'artifacts/build/uninstall-tests'/identity; folder.mkdir(parents=True)
    cases = []; details = {}; namespace_removed = False
    def case(name, action):
        value = action(); cases.append({'name': name, 'passed': True}); details[name] = value; return value
    def fail(action):
        try:
            action()
        except u.UninstallFailure as error:
            require(not error.report['successful'], 'Failure report cannot certify success')
            return error.report
        raise AssertionError('Expected uninstall refusal')
    def files(path):
        return {p.name: j.digest(p.read_bytes()) for p in path.iterdir() if p.is_file()}
    @contextmanager
    def fixture(name, registered=True):
        base = folder/name
        with s.descriptor(policy.sddl(True)) as attributes:
            s.check(s.api('kernel32.dll', 'CreateDirectoryW', W.BOOL, [W.LPCWSTR, ctypes.POINTER(s.Attributes)])(str(base), ctypes.byref(attributes)))
        destination = base/'stage'; receipt = s.stage_new(bundle, bundle_hash, destination, policy)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, namespace+'\\'+name, 0, ACCESS) as parent:
            with winreg.CreateKeyEx(parent, 'machine-model', 0, ACCESS) as root, winreg.CreateKeyEx(parent, 'overlay-model', 0, ACCESS) as overlay:
                for container in ['SOFTWARE\\Classes\\CLSID', 'SOFTWARE\\ASIO']:
                    with winreg.CreateKeyEx(root, container, 0, ACCESS):
                        pass
                sibling_path = 'SOFTWARE\\ASIO\\UnrelatedVendor'
                with winreg.CreateKeyEx(root, sibling_path, 0, ACCESS) as foreign:
                    winreg.SetValueEx(foreign, 'Preserve', 0, winreg.REG_SZ, identity)
                before = r.snapshot(root, sibling_path)
                if registered:
                    r.register_new(root, plan)
                yield base, destination, receipt['stageRecordSha256'], root, overlay
                require(before == r.snapshot(root, sibling_path), 'Unrelated registration sibling preserved')
                (folder/(name+'-registry-final.json')).write_text(json.dumps(r.inspect(root, plan), indent=2)+'\n', encoding='utf-8')
    def run(f):
        base, destination, digest, root, overlay = f
        return u.uninstall_owned(base, destination, digest, policy, root, overlay)
    def remove_tree(parent, child):
        # Registry-only recursive cleanup, confined to the marked UUID root.
        with winreg.OpenKey(parent, child, 0, ACCESS) as handle:
            children = [winreg.EnumKey(handle, n) for n in range(winreg.QueryInfoKey(handle)[0])]
            for name in children:
                remove_tree(handle, name)
        winreg.DeleteKeyEx(parent, child, winreg.KEY_WOW64_64KEY, 0)

    for name, args in [('default', []), ('plan', ['--plan']), ('no-mutation-cli', ['--uninstall'])]:
        value = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=20)
        require(value.returncode == (2 if args == ['--uninstall'] else 0), 'Inert CLI')
        case(name, lambda value=value: {'exit': value.returncode, 'stdout': value.stdout, 'stderr': value.stderr})
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, namespace, 0, ACCESS) as marker:
            winreg.SetValueEx(marker, 'SL3TestOwner', 0, winreg.REG_SZ, identity)
        with fixture('complete') as f:
            value = case('isolated-complete-uninstall', lambda: run(f))
            require(value['successful'] and value['finalRegistryAbsentObserved'] and value['directoryAbsentObserved'] and
                    len(value['registryResult']['deletedKeys']) == 3 and len(value['fileResult']['absentObservedFiles']) == 14,
                    'Both independently observed removals')
            journal = case('complete-uninstall-retained-journal', lambda: j.inspect_journal(f[0], Path(value['journal']), policy))
            require(journal['records'][-1]['payload']['event'] == 'uninstall_completed', 'Flushed completion observation')
            require(journal['records'][0]['payload']['bindings'] == {'packageId': plan['packageId'],
                    'bundleManifestSha256': bundle_hash, 'stageRecordSha256': f[2]}, 'Journal binds reviewed actual stage/package pins')
        with fixture('absent', registered=False) as f:
            value = case('already-absent-registration-cleanup', lambda: run(f))
            require(value['successful'] and not value['registryRemovalAttempted'], 'No invented registry deletions')
        with fixture('bad-hash') as f:
            original = files(f[1]); state = r.inspect(f[3], plan)
            value = case('wrong-stage-hash-preserves-all', lambda: fail(lambda: u.uninstall_owned(f[0], f[1], '0'*64, policy, f[3], f[4])))
            require(value['journal'] is None and files(f[1]) == original and r.inspect(f[3], plan) == state, 'No transaction/mutation on hash refusal')
        with fixture('changed-file') as f:
            (f[1]/'README.txt').write_bytes(b'changed fixture')
            value = case('changed-stage-before-registry-removal', lambda: fail(lambda: run(f)))
            require(not value['registryRemovalAttempted'] and r.inspect(f[3], plan)['exactOwned'], 'Stage validation precedes registry mutation')
        with fixture('foreign-registration') as f:
            with winreg.OpenKey(f[3], r.entries(plan)[2]['key'], 0, ACCESS) as key:
                winreg.SetValueEx(key, 'Foreign', 0, winreg.REG_SZ, 'preserve')
            before = r.inspect(f[3], plan); original = files(f[1])
            value = case('foreign-registration-preserved', lambda: fail(lambda: run(f)))
            require(value['failureJournalPersisted'] and not value['registryRemovalAttempted'] and
                    before == r.inspect(f[3], plan) and original == files(f[1]), 'Conflict preserved with durable failure event')
        with fixture('partial-registration') as f:
            winreg.DeleteKeyEx(f[3], r.entries(plan)[1]['key'], winreg.KEY_WOW64_64KEY, 0)
            before = r.inspect(f[3], plan)
            value = case('partial-registration-preserved', lambda: fail(lambda: run(f)))
            require(not value['registryRemovalAttempted'] and before == r.inspect(f[3], plan) and len(files(f[1])) == 14, 'Partial state requires reconciliation')
        with fixture('overlay') as f:
            with winreg.CreateKeyEx(f[4], r.entries(plan)[0]['key'], 0, ACCESS) as key:
                winreg.SetValueEx(key, '', 0, winreg.REG_SZ, 'foreign overlay')
            value = case('current-user-overlay-blocks-removal', lambda: fail(lambda: run(f)))
            require(not value['registryRemovalAttempted'] and r.inspect(f[3], plan)['exactOwned'] and len(files(f[1])) == 14, 'Overlay conflict preserves both')
        with fixture('busy-file') as f:
            with s.open_file(f[1]/'README.txt'):
                value = case('busy-file-after-registration-removal-reports-partial', lambda: fail(lambda: run(f)))
                require(value['registryResult']['successful'] and value['fileCleanupAttempted'] and
                        not value['fileResult']['deleteMarkedFiles'] and r.inspect(f[3], plan)['allAbsent'] and len(files(f[1])) == 14,
                        'Registration removed but busy stage retained, without fake rollback')
            value = case('busy-reader-release-resumes-absent-registration', lambda: run(f))
            require(value['successful'] and not value['registryRemovalAttempted'], 'Explicit retry removes remaining owned stage')
        with fixture('lock-conflict') as f:
            with j.transaction(f[0], policy, 'uninstall', {'packageId': plan['packageId']}):
                value = case('competing-transaction-preserves-state', lambda: fail(lambda: run(f)))
                require(value['journal'] is None and r.inspect(f[3], plan)['exactOwned'] and len(files(f[1])) == 14, 'Lock refusal before mutations')
        with fixture('wrong-base') as f:
            value = case('stage-outside-serialized-base-refused', lambda: fail(lambda: u.uninstall_owned(folder, f[1], f[2], policy, f[3], f[4])))
            require(value['journal'] is None and r.inspect(f[3], plan)['exactOwned'] and len(files(f[1])) == 14, 'Base scope refusal before mutations')
        with fixture('late-foreign-file') as f:
            real_unregister = r.unregister_owned
            def add_unknown(root, plan, journal):
                result = real_unregister(root, plan, journal)
                (f[1]/'foreign.txt').write_bytes(b'preserve late foreign data')
                return result
            try:
                r.unregister_owned = add_unknown
                value = case('late-unknown-file-after-unregister-preserved', lambda: fail(lambda: run(f)))
            finally:
                r.unregister_owned = real_unregister
            require(value['registryResult']['successful'] and not value['fileResult']['deleteMarkedFiles'] and
                    len(files(f[1])) == 15 and (f[1]/'foreign.txt').read_bytes() == b'preserve late foreign data',
                    'Full cleanup revalidation preserves unknown data after registration phase')
        with fixture('journal-failure') as f:
            real_write = j.write_flush; count = []
            def fail_second(handle, raw):
                count.append(True)
                if len(count) == 2:
                    raise OSError('Simulated flush failure before unregister')
                real_write(handle, raw)
            try:
                j.write_flush = fail_second
                value = case('journal-failure-before-registry-preserves-state', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(not value['registryRemovalAttempted'] and not value['failureJournalPersisted'] and
                    r.inspect(f[3], plan)['exactOwned'] and len(files(f[1])) == 14, 'No mutation after journal failure')
        with fixture('interrupted-registry') as f:
            real_unregister = r.unregister_owned
            def interrupted(root, plan, journal):
                def callback(event):
                    journal(event)
                    if event['event'] == 'deleted':
                        raise OSError('Simulated interruption after first registry deletion')
                return real_unregister(root, plan, callback)
            try:
                r.unregister_owned = interrupted
                value = case('interrupted-registry-removal-retains-files', lambda: fail(lambda: run(f)))
            finally:
                r.unregister_owned = real_unregister
            require(len(value['registryResult']['deletedKeys']) == 1 and not value['fileCleanupAttempted'] and
                    len(files(f[1])) == 14 and value['failureJournalPersisted'], 'Exact partial registry receipt, all stage files retained')
        with fixture('final-journal-failure') as f:
            real_write = j.write_flush
            def fail_completion(handle, raw):
                if b'"event":"uninstall_completed"' in raw:
                    raise OSError('Simulated completion-record failure')
                real_write(handle, raw)
            try:
                j.write_flush = fail_completion
                value = case('completion-journal-failure-keeps-honest-final-observations', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(value['finalRegistryAbsentObserved'] and value['directoryAbsentObserved'] and
                    not value['successful'] and not value['failureJournalPersisted'], 'Observed removals differ from durable completion')
        try:
            u.uninstall_production(folder, folder/'stage', '0'*64)
        except ValueError as error:
            require('administrator token' in str(error), 'Production elevation gate precedes all operations')
            case('production-refuses-normal-token', lambda: {'refused': True, 'error': str(error)})
        else:
            raise AssertionError('Production gate must refuse ordinary token')
        require(live() == live_before, 'Live HKLM registration/current-user overlay unchanged')
        require([p.exists() for p in locations] == locations_before, 'Planned install/profile paths unchanged')
        require(before_bundle == {p.name: j.digest(p.read_bytes()) for p in bundle.iterdir()}, 'Reviewed bundle unchanged')
    finally:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, ACCESS) as marker:
            require(winreg.QueryValueEx(marker, 'SL3TestOwner')[0] == identity, 'Exact private UUID marker before cleanup')
        require(namespace.startswith(BASE+'\\') and namespace.rsplit('\\', 1)[1] == identity, 'Private registry cleanup boundary')
        remove_tree(winreg.HKEY_CURRENT_USER, namespace)
        try:
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, r.READ)
        except FileNotFoundError:
            namespace_removed = True
        require(namespace_removed, 'Private registry namespace independently observed absent')
    (folder/'case-details.json').write_text(json.dumps(details, indent=2)+'\n', encoding='utf-8')
    source_paths = [TOOL, Path(__file__), ROOT/'scripts/asio-install-journal.py', ROOT/'scripts/asio-registry.py', ROOT/'scripts/asio-file-stage.py']
    result = {'schema': 'sl3.uninstall-tests.v1', 'cases': cases,
              'files': {p.relative_to(folder).as_posix(): j.digest(p.read_bytes()) for p in folder.rglob('*') if p.is_file()},
              'sourceSha256': {p.relative_to(ROOT).as_posix(): j.digest(p.read_bytes()) for p in source_paths},
              'privateRegistryNamespaceRemoved': namespace_removed, 'liveRegistrationsUnchanged': True,
              'plannedLocationsUnchanged': True, 'sourceBundleUnchanged': True, 'nonElevated': True,
              'productionOperationExecuted': False, 'testRegistrationPointsAtPlannedPathNotWorkspaceStage': True,
              'installedAsioActivationTested': False, 'deviceAccess': False, 'binaryPayloadExecuted': False}
    index = folder/'index.json'; index.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/uninstall-tests-last.json').write_text(json.dumps(
        {'directory': str(folder), 'indexSha256': j.digest(index.read_bytes())}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'privateRegistryNamespaceRemoved': namespace_removed, 'evidenceDirectory': str(folder)}))


if __name__ == '__main__':
    main()
