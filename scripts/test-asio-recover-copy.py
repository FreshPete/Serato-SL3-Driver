"""Real journalled staging interruptions and copy-abort recovery in private roots."""
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
TOOL = ROOT/'scripts/asio-recover-copy.py'
BASE = 'Software\\SL3RebuildCopyRecoveryTests'
ACCESS = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY


def require(value, message):
    if not value:
        raise AssertionError(message)


class Interrupted(BaseException):
    pass


def main():
    spec = importlib.util.spec_from_file_location('sl3_copy_recovery_under_test', TOOL)
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
    folder = ROOT/'artifacts/build/recover-copy-tests'/identity; folder.mkdir(parents=True)
    cases = []; details = {}; removed = False
    def case(name, action):
        value = action(); cases.append({'name': name, 'passed': True}); details[name] = value; return value
    def fail(action):
        try:
            action()
        except m.CopyRecoveryFailure as error:
            require(not error.report['successful'], 'Failure cannot certify recovery')
            return error.report
        raise AssertionError('Expected recovery refusal')
    def inventory(path):
        return {p.name: j.digest(p.read_bytes()) for p in path.iterdir()} if path.exists() else None
    def unchanged(f, action):
        before = inventory(f[1]), r.inspect(f[4], plan)
        value = fail(action)
        require(before == (inventory(f[1]), r.inspect(f[4], plan)), 'Stage and registry preserved')
        require(not value['deleteMarkedFiles'], 'No premature file deletion')
        return value
    @contextmanager
    def fixture(name, boundary=10, partial=False, gap=None, complete_stage=False):
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
                real_write = j.write_flush; real_open = s.open_file; seen = []; opened = {}
                def capture(path, *args, **kwargs):
                    owner = real_open(path, *args, **kwargs)
                    if path.parent == destination:
                        opened[path.name] = owner
                    return owner
                def interrupt(handle, raw):
                    event = json.loads(raw).get('payload', {}); step = event.get('data', {}) if event.get('event') == 'step' else {}
                    if gap == 'root' and step.get('event') == 'stage_root_created' or (
                        gap == 'file' and step.get('event') == 'stage_file_created' and step.get('name') == 'stage-intent.json') or (
                        gap == 'stage-completion' and event.get('event') == 'stage_completed'):
                        raise OSError('Injected before identity/completion journal write')
                    real_write(handle, raw)
                    if partial and step.get('event') == 'stage_file_created' and step.get('name') == 'README.txt':
                        data = (bundle/'README.txt').read_bytes()[:17]; target = opened['README.txt'].value
                        count = W.DWORD()
                        s.check(s.api('kernel32.dll', 'WriteFile', W.BOOL, [W.HANDLE, s.P, W.DWORD, ctypes.POINTER(W.DWORD), s.P])(
                            target, data, len(data), ctypes.byref(count), None))
                        s.check(s.api('kernel32.dll', 'FlushFileBuffers', W.BOOL, [W.HANDLE])(target))
                        require(count.value == len(data) and s.read_handle(target, s.reader().LIMIT) == data, 'Actual partial prefix written/flushed/read back')
                        raise Interrupted('After an actual prefix write, before original full write')
                    if step.get('event') in ('stage_root_created', 'stage_file_created', 'stage_file_completed', 'before_file'):
                        seen.append(step)
                        if not partial and not gap and not complete_stage and len(seen) == boundary+1:
                            raise Interrupted('After durable staging event; contexts release without Exception rollback')
                    if complete_stage and event.get('event') == 'stage_completed':
                        raise Interrupted('After durable stage completion')
                try:
                    j.write_flush = interrupt; s.open_file = capture
                    try:
                        i.install_owned(bundle, expected, base, destination, policy, root, overlay)
                    except Interrupted:
                        pass
                    except i.InstallFailure:
                        require(gap is not None, 'Only deliberate unjournalled gaps use ordinary failure')
                    else:
                        raise AssertionError('Original install should stop before registration')
                finally:
                    j.write_flush = real_write; s.open_file = real_open
                journals = list(base.glob('transaction-*.jsonl')); require(len(journals) == 1, 'One original journal')
                original = journals[0]; digest = j.digest(original.read_bytes())
                require(r.inspect(root, plan)['allAbsent'], 'Original copy phase never registered')
                yield base, destination, original, digest, root, overlay
                require(j.digest(original.read_bytes()) == digest, 'Reviewed original journal unchanged')
                require(r.snapshot(root, 'UnrelatedVendor') == foreign_before, 'Unrelated registry sibling preserved')
                (folder/(name+'-registry-final.json')).write_text(json.dumps(r.inspect(root, plan), indent=2)+'\n', encoding='utf-8')
    def run(f):
        return m.recover_owned(bundle, expected, *f[:4], policy, *f[4:])
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
        for boundary in range(41):
            with fixture('boundary-'+str(boundary), boundary) as f:
                count = len(list(f[1].iterdir()))
                value = case('recover-after-staging-event-'+str(boundary), lambda: run(f))
                require(value['successful'] and len(value['absentObservedFiles']) == count and not f[1].exists() and
                        r.inspect(f[4], plan)['allAbsent'], 'Exact witnessed file cleanup and absent registry')
                require(j.inspect_journal(f[0], Path(value['journal']), policy)['records'][-1]['payload']['event'] ==
                        'copy_recovery_completed', 'Flushed completion')
        with fixture('partial-prefix', partial=True) as f:
            value = case('actual-partial-write-prefix-recovered', lambda: run(f))
            require(value['successful'] and value['partialPrefixFilesObserved'] == ['README.txt'], 'Actual partial bytes recognized')
        with fixture('root-gap', gap='root') as f:
            case('unjournalled-directory-creation-preserved', lambda: unchanged(f, lambda: run(f)))
        with fixture('file-gap', gap='file') as f:
            case('unjournalled-file-creation-preserved', lambda: unchanged(f, lambda: run(f)))
        with fixture('stage-gap', gap='stage-completion') as f:
            value = case('complete-stage-before-completion-journal-recovered', lambda: run(f))
            require(value['successful'] and len(value['absentObservedFiles']) == 14, 'Created receipt witness covers completion-record gap')
        with fixture('completed-stage', complete_stage=True) as f:
            case('journalled-complete-stage-preserved-for-install-recovery', lambda: unchanged(f, lambda: run(f)))
        with fixture('unknown') as f:
            (f[1]/'foreign.txt').write_bytes(b'preserve')
            case('unknown-stage-data-preserved', lambda: unchanged(f, lambda: run(f)))
        with fixture('wrong-prefix', partial=True) as f:
            (f[1]/'README.txt').write_bytes(b'wrong prefix')
            case('nonprefix-partial-file-preserved', lambda: unchanged(f, lambda: run(f)))
        with fixture('truncated-complete', 10) as f:
            (f[1]/'README.txt').write_bytes(b'')
            case('changed-completed-file-preserved', lambda: unchanged(f, lambda: run(f)))
        with fixture('replacement', partial=True) as f:
            target = f[1]/'README.txt'; saved = f[0]/'saved.txt'; data = target.read_bytes(); target.replace(saved)
            try:
                with s.descriptor(policy.sddl(False)) as attributes:
                    with s.open_file(target, access=0xc0000000, share=0, create=1, security=attributes) as handle:
                        j.write_flush(handle, data)
                case('same-prefix-new-file-identity-preserved', lambda: unchanged(f, lambda: run(f)))
            finally:
                saved.replace(target)
        with fixture('hardlink', partial=True) as f:
            alias = f[0]/'link.txt'
            try:
                os.link(f[1]/'README.txt', alias)
                case('hardlinked-partial-file-preserved', lambda: unchanged(f, lambda: run(f)))
            finally:
                alias.unlink()
        with fixture('registry') as f:
            with winreg.CreateKeyEx(f[4], r.entries(plan)[0]['key'], 0, ACCESS):
                pass
            case('any-current-registration-blocks-copy-recovery', lambda: unchanged(f, lambda: run(f)))
        with fixture('overlay') as f:
            with winreg.CreateKeyEx(f[5], r.entries(plan)[0]['key'], 0, ACCESS):
                pass
            case('current-user-overlay-preserved', lambda: unchanged(f, lambda: run(f)))
        with fixture('hash') as f:
            case('wrong-journal-review-hash-refused', lambda: unchanged(f, lambda: m.recover_owned(bundle, expected, *f[:3], '0'*64, policy, *f[4:])))
            case('wrong-bundle-review-hash-refused', lambda: unchanged(f, lambda: m.recover_owned(bundle, '0'*64, *f[:4], policy, *f[4:])))
        with fixture('busy') as f:
            with s.open_file(f[1]/'README.txt'):
                case('busy-survivor-blocks-all-deletion', lambda: unchanged(f, lambda: run(f)))
            value = case('retry-after-busy-handle-release', lambda: run(f))
            require(value['successful'], 'Retry after release')
        with fixture('recovery-interrupted') as f:
            real_write = j.write_flush
            def poisoned(handle, raw):
                if b'"event":"copy_recovery_deleted"' in raw:
                    raise OSError('Injected journal failure after one deletion')
                real_write(handle, raw)
            try:
                j.write_flush = poisoned
                value = case('interrupted-recovery-reports-one-observed-deletion', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(len(value['absentObservedFiles']) == 1, 'Exact newly removed survivor')
            value = case('retry-rechecks-original-witnesses-and-current-survivors', lambda: run(f))
            require(value['successful'] and len(value['initiallyAbsentFiles']) == 1, 'Previously absent file not replayed')
            value = case('already-absent-stage-reconciled-without-recreation', lambda: run(f))
            require(value['successful'] and value['directoryAlreadyAbsentObserved'] and not value['absentObservedFiles'], 'Current absence only')
        with fixture('late-unknown') as f:
            real_write = j.write_flush; injected = []
            def late(handle, raw):
                real_write(handle, raw)
                if b'"event":"copy_recovery_before_delete"' in raw and not injected:
                    (f[1]/'late.txt').write_bytes(b'preserve'); injected.append(True)
            try:
                j.write_flush = late
                value = case('late-unknown-data-stops-first-deletion', lambda: fail(lambda: run(f)))
            finally:
                j.write_flush = real_write
            require(injected and not value['deleteMarkedFiles'], 'Late unknown preserved')
        try:
            m.recover_production(bundle, expected, folder, folder/'stage', folder/'journal', '0'*64)
        except ValueError as error:
            require('administrator token' in str(error), 'Production gate')
            case('production-refuses-normal-token', lambda: {'refused': True, 'error': str(error)})
        else:
            raise AssertionError('Production must refuse ordinary token')
        require(live() == live_before, 'Live registrations unchanged')
        require(source_before == {p.name: j.digest(p.read_bytes()) for p in bundle.iterdir()}, 'Source bundle unchanged')
        require([p.exists() for p in locations] == before_locations, 'Planned production/profile locations unchanged')
    finally:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, ACCESS) as marker:
            require(winreg.QueryValueEx(marker, 'SL3TestOwner')[0] == identity, 'Exact UUID owner marker')
        require(namespace == BASE+'\\'+identity, 'Private registry cleanup boundary')
        remove_tree(winreg.HKEY_CURRENT_USER, namespace)
        try:
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, r.READ)
        except FileNotFoundError:
            removed = True
        require(removed, 'Private namespace observed absent')
    (folder/'case-details.json').write_text(json.dumps(details, indent=2)+'\n', encoding='utf-8')
    paths = [TOOL, Path(__file__), ROOT/'scripts/asio-file-stage.py', ROOT/'scripts/asio-install.py',
             ROOT/'scripts/asio-install-journal.py', ROOT/'scripts/asio-registry.py', ROOT/'scripts/asio-runtime-check.py']
    value = {'schema': 'sl3.copy-recovery-tests.v1', 'cases': cases,
             'files': {p.relative_to(folder).as_posix(): j.digest(p.read_bytes()) for p in folder.rglob('*') if p.is_file()},
             'sourceSha256': {p.relative_to(ROOT).as_posix(): j.digest(p.read_bytes()) for p in paths},
             'privateRegistryNamespaceRemoved': removed, 'liveRegistrationsUnchanged': True, 'sourceBundleUnchanged': True,
             'originalJournalsUnchanged': True, 'plannedLocationsUnchanged': True, 'nonElevated': True,
             'productionOperationExecuted': False, 'registryWrittenByRecovery': False,
             'actualPartialPrefixWrittenFlushedAndReadBack': True, 'actualProcessTerminationTested': False,
             'unwitnessedCreationGapsRecovered': False, 'packageBinaryExecuted': False, 'deviceAccess': False}
    index = folder/'index.json'; index.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/recover-copy-tests-last.json').write_text(json.dumps({'directory': str(folder),
        'indexSha256': j.digest(index.read_bytes())}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'privateRegistryNamespaceRemoved': removed, 'evidenceDirectory': str(folder)}))


if __name__ == '__main__':
    main()
