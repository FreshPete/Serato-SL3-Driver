"""Runtime-gated staging/registration coordination in private Windows fixtures."""
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
TOOL = ROOT/'scripts/asio-install.py'
BASE = 'Software\\SL3RebuildInstallTests'
ACCESS = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    spec = importlib.util.spec_from_file_location('sl3_install_under_test', TOOL)
    i = importlib.util.module_from_spec(spec); spec.loader.exec_module(i)
    j = i.sibling('asio-install-journal'); s = j.stage_module(); r = i.sibling('asio-registry'); runtime = i.sibling('asio-runtime-check')
    require(not s.elevated(), 'Unattended tests must run non-elevated')
    sid = s.user_sid(); policy = s.Policy(sid, (s.SYSTEM, s.ADMINS, sid))
    pointer = json.loads((ROOT/'artifacts/build/deployment-tests-last.json').read_text()); index = Path(pointer['directory'])/'index.json'
    require(j.digest(index.read_bytes()) == pointer['indexSha256'], 'Reviewed package test index')
    package = json.loads(index.read_text()); bundle = ROOT/package['positiveBundle']; expected = package['bundleManifestSha256']
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
    folder = ROOT/'artifacts/build/install-tests'/identity; folder.mkdir(parents=True)
    cases = []; details = {}; removed = False
    def case(name, action):
        value = action(); cases.append({'name': name, 'passed': True}); details[name] = value; return value
    def fail(action):
        try:
            action()
        except i.InstallFailure as error:
            require(not error.report['successful'], 'Failure cannot certify installation')
            return error.report
        raise AssertionError('Expected install refusal')
    @contextmanager
    def fixture(name, containers=True):
        base = folder/name
        with s.descriptor(policy.sddl(True)) as attributes:
            s.check(s.api('kernel32.dll', 'CreateDirectoryW', W.BOOL, [W.LPCWSTR, ctypes.POINTER(s.Attributes)])(str(base), ctypes.byref(attributes)))
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, namespace+'\\'+name, 0, ACCESS) as parent:
            with winreg.CreateKeyEx(parent, 'machine-model', 0, ACCESS) as root, winreg.CreateKeyEx(parent, 'overlay-model', 0, ACCESS) as overlay:
                if containers:
                    for path in ['SOFTWARE\\Classes\\CLSID', 'SOFTWARE\\ASIO']:
                        with winreg.CreateKeyEx(root, path, 0, ACCESS):
                            pass
                with winreg.CreateKeyEx(root, 'UnrelatedVendor', 0, ACCESS) as foreign:
                    winreg.SetValueEx(foreign, 'Preserve', 0, winreg.REG_SZ, identity)
                before = r.snapshot(root, 'UnrelatedVendor')
                yield base, base/'stage', root, overlay
                require(before == r.snapshot(root, 'UnrelatedVendor'), 'Foreign registration sibling preserved')
                (folder/(name+'-registry-final.json')).write_text(json.dumps(r.inspect(root, plan), indent=2)+'\n', encoding='utf-8')
    def run(f):
        return i.install_owned(bundle, expected, f[0], f[1], policy, f[2], f[3])
    def remove_tree(parent, name):
        with winreg.OpenKey(parent, name, 0, ACCESS) as handle:
            children = [winreg.EnumKey(handle, n) for n in range(winreg.QueryInfoKey(handle)[0])]
            for child in children:
                remove_tree(handle, child)
        winreg.DeleteKeyEx(parent, name, winreg.KEY_WOW64_64KEY, 0)
    for name, args in [('default', []), ('plan', ['--plan']), ('no-machine-mutation-cli', ['--install'])]:
        value = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=20)
        require(value.returncode == (2 if args == ['--install'] else 0), 'Inert CLI')
        case(name, lambda value=value: {'exit': value.returncode, 'stdout': value.stdout, 'stderr': value.stderr})
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, namespace, 0, ACCESS) as marker:
            winreg.SetValueEx(marker, 'SL3TestOwner', 0, winreg.REG_SZ, identity)
        with fixture('roundtrip') as f:
            real_register = r.register_new; denied = []
            def probe(root, plan, journal):
                for target in [bundle/'sl3_asio.dll', f[1]/'sl3_asio.dll']:
                    try:
                        with target.open('r+b'):
                            pass
                    except PermissionError:
                        denied.append(str(target))
                require(len(denied) == 2, 'Source and stage handles deny writers across registration')
                return real_register(root, plan, journal)
            try:
                r.register_new = probe
                value = case('runtime-gated-stage-registration', lambda: run(f))
            finally:
                r.register_new = real_register
            require(value['successful'] and value['runtimeDirectImportsResolved'] and value['stageVerifiedObserved'] and
                    value['registrationOwnedObserved'] and not value['productionPolicy'] and len(list(f[1].iterdir())) == 14,
                    'Actual isolated stage/registry observations, not production protection')
            case('source-and-stage-leased-across-registration', lambda: {'writeOpensDenied': len(denied)})
            journal = case('installation-completion-journal', lambda: j.inspect_journal(f[0], Path(value['journal']), policy))
            require(journal['records'][-1]['payload']['event'] == 'install_completed', 'Flushed completion')
            stage_receipt = value['stageResult']['stageRecordSha256']
            uninstall = i.sibling('asio-uninstall')
            result = case('actual-isolated-install-remove-roundtrip', lambda: uninstall.uninstall_owned(f[0], f[1], stage_receipt, policy, f[2], f[3]))
            require(result['successful'] and not f[1].exists() and r.inspect(f[2], plan)['allAbsent'], 'Composed roundtrip ends absent')
        with fixture('bad-hash') as f:
            value = case('wrong-bundle-hash-before-stage', lambda: fail(lambda: i.install_owned(bundle, '0'*64, f[0], f[1], policy, f[2], f[3])))
            require(value['journal'] is None and not value['stageAttempted'] and not f[1].exists(), 'No stage/journal after admission failure')
        with fixture('runtime-failure') as f:
            real_check = runtime.check
            def runtime_failure(*args):
                raise OSError('Simulated dependency admission failure')
            try:
                runtime.check = runtime_failure
                value = case('runtime-failure-prevents-all-mutations', lambda: fail(lambda: run(f)))
            finally:
                runtime.check = real_check
            require(not value['runtimeDirectImportsResolved'] and value['journal'] is None and not f[1].exists() and
                    r.inspect(f[2], plan)['allAbsent'], 'Runtime failure has no installation side effect')
        with fixture('existing') as f:
            f[1].mkdir(); (f[1]/'foreign.txt').write_bytes(b'preserve existing')
            value = case('existing-destination-preserved', lambda: fail(lambda: run(f)))
            require(value['journal'] is None and (f[1]/'foreign.txt').read_bytes() == b'preserve existing', 'Existing bytes never overwritten')
        with fixture('foreign-registration') as f:
            with winreg.CreateKeyEx(f[2], r.entries(plan)[0]['key'], 0, ACCESS) as key:
                winreg.SetValueEx(key, '', 0, winreg.REG_SZ, 'foreign')
            before = r.inspect(f[2], plan)
            value = case('foreign-registration-blocks-staging', lambda: fail(lambda: run(f)))
            require(value['failureJournalPersisted'] and not value['stageAttempted'] and not f[1].exists() and
                    r.inspect(f[2], plan) == before, 'Conflict journaled before any stage creation')
        with fixture('missing-containers', False) as f:
            value = case('missing-shared-containers-preserved', lambda: fail(lambda: run(f)))
            require(not value['stageAttempted'] and not f[1].exists(), 'No implicit shared registry containers')
        with fixture('overlay') as f:
            with winreg.CreateKeyEx(f[3], r.entries(plan)[0]['key'], 0, ACCESS):
                pass
            value = case('user-overlay-blocks-staging', lambda: fail(lambda: run(f)))
            require(not value['stageAttempted'] and not f[1].exists(), 'Overlay is not overwritten')
        with fixture('copy-failure') as f:
            real_stage = s.stage_new; seen = []
            def interrupted_stage(bundle, digest, destination, policy, journal):
                def callback(event):
                    journal(event); seen.append(event)
                    if len(seen) == 2:
                        raise OSError('Simulated interrupted copy')
                return real_stage(bundle, digest, destination, policy, callback)
            try:
                s.stage_new = interrupted_stage
                value = case('interrupted-copy-retains-intent-no-registration', lambda: fail(lambda: run(f)))
            finally:
                s.stage_new = real_stage
            require(value['stageAttempted'] and not value['registrationAttempted'] and (f[1]/'stage-intent.json').exists() and
                    not (f[1]/'stage-record.json').exists() and r.inspect(f[2], plan)['allAbsent'], 'Partial stage preserved without completion')
        with fixture('stage-journal-failure') as f:
            real_write = j.write_flush
            def fail_stage_record(handle, raw):
                if b'"event":"stage_completed"' in raw:
                    raise OSError('Simulated stage completion journal failure')
                real_write(handle, raw)
            try:
                j.write_flush = fail_stage_record
                value = case('stage-journal-failure-blocks-registration', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(value['stageResult'] and not value['registrationAttempted'] and not value['failureJournalPersisted'] and
                    r.inspect(f[2], plan)['allAbsent'], 'Complete stage retained, no unjournaled registration')
            s.inspect_stage(f[1], value['stageResult']['stageRecordSha256'], policy)
        with fixture('registration-interruption') as f:
            real_register = r.register_new
            def interrupted(root, plan, journal):
                def callback(event):
                    journal(event)
                    if event['event'] == 'written':
                        raise OSError('Simulated registry write interruption')
                return real_register(root, plan, callback)
            try:
                r.register_new = interrupted
                value = case('registration-failure-rolls-back-own-keys-retains-stage', lambda: fail(lambda: run(f)))
            finally:
                r.register_new = real_register
            require(value['registrationAttempted'] and value['registrationResult']['rolledBackKeys'] and
                    r.inspect(f[2], plan)['allAbsent'] and len(list(f[1].iterdir())) == 14, 'Engine rollback remains scoped; complete stage retained')
        with fixture('late-registration-conflict') as f:
            real_stage = s.stage_new
            def late_conflict(*args, **kwargs):
                result = real_stage(*args, **kwargs)
                with winreg.CreateKeyEx(f[2], r.entries(plan)[0]['key'], 0, ACCESS) as key:
                    winreg.SetValueEx(key, '', 0, winreg.REG_SZ, 'preserve late foreign registration')
                return result
            try:
                s.stage_new = late_conflict
                value = case('post-stage-registration-conflict-preserves-both', lambda: fail(lambda: run(f)))
            finally:
                s.stage_new = real_stage
            require(value['stageResult'] and not value['registrationAttempted'] and len(list(f[1].iterdir())) == 14 and
                    r.snapshot(f[2], r.entries(plan)[0]['key'])['values']['']['data'] == 'preserve late foreign registration',
                    'Conflict after staging is not overwritten or used to delete the stage')
        with fixture('completion-journal-failure') as f:
            real_write = j.write_flush
            def fail_completed(handle, raw):
                if b'"event":"install_completed"' in raw:
                    raise OSError('Simulated final completion write failure')
                real_write(handle, raw)
            try:
                j.write_flush = fail_completed
                value = case('completion-journal-failure-does-not-certify-install', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(value['stageVerifiedObserved'] and value['registrationOwnedObserved'] and
                    not value['successful'] and not value['failureJournalPersisted'], 'Observed state and transaction completion differ')
        with fixture('lock-conflict') as f:
            with j.transaction(f[0], policy, 'install', {'packageId': plan['packageId']}):
                value = case('competing-install-lock-blocks-staging', lambda: fail(lambda: run(f)))
            require(value['journal'] is None and not f[1].exists() and r.inspect(f[2], plan)['allAbsent'], 'Competing caller mutates nothing')
        try:
            i.install_production(bundle, expected)
        except ValueError as error:
            require('administrator token' in str(error), 'Production gate precedes staging')
            case('production-refuses-normal-token', lambda: {'refused': True, 'error': str(error)})
        else:
            raise AssertionError('Production call must refuse ordinary token')
        require(live() == before_live, 'Live machine/current-user registration unchanged')
        require(before_bundle == {p.name: j.digest(p.read_bytes()) for p in bundle.iterdir()}, 'Source bundle unchanged')
        require([p.exists() for p in locations] == before_locations, 'Planned production/profile paths unchanged')
    finally:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, ACCESS) as marker:
            require(winreg.QueryValueEx(marker, 'SL3TestOwner')[0] == identity, 'Exact namespace marker before cleanup')
        require(namespace == BASE+'\\'+identity, 'Private registry cleanup boundary')
        remove_tree(winreg.HKEY_CURRENT_USER, namespace)
        try:
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, r.READ)
        except FileNotFoundError:
            removed = True
        require(removed, 'Private registry namespace observed absent')
    (folder/'case-details.json').write_text(json.dumps(details, indent=2)+'\n', encoding='utf-8')
    paths = [TOOL, Path(__file__), ROOT/'scripts/asio-runtime-check.py', ROOT/'scripts/asio-uninstall.py', ROOT/'scripts/asio-install-journal.py', ROOT/'scripts/asio-file-stage.py', ROOT/'scripts/asio-registry.py']
    value = {'schema': 'sl3.install-tests.v1', 'cases': cases,
             'files': {p.relative_to(folder).as_posix(): j.digest(p.read_bytes()) for p in folder.rglob('*') if p.is_file()},
             'sourceSha256': {p.relative_to(ROOT).as_posix(): j.digest(p.read_bytes()) for p in paths},
             'privateRegistryNamespaceRemoved': removed, 'liveRegistrationsUnchanged': True, 'plannedLocationsUnchanged': True,
             'sourceBundleUnchanged': True, 'nonElevated': True, 'productionOperationExecuted': False,
             'testRegistrationPointsAtPlannedPathNotWorkspaceStage': True, 'installedAsioActivationTested': False,
             'systemDllInitializationAllowed': True, 'packageBinaryExecuted': False, 'deviceAccess': False}
    index = folder/'index.json'; index.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/install-tests-last.json').write_text(json.dumps({'directory': str(folder), 'indexSha256': j.digest(index.read_bytes())}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'privateRegistryNamespaceRemoved': removed, 'evidenceDirectory': str(folder)}))


if __name__ == '__main__':
    main()
