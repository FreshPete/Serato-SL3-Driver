"""Actual Win32 registry tests confined to a fresh, marked private HKCU subtree."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading
import uuid
import winreg

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/asio-registry.py'
BASE = 'Software\\SL3RebuildRegistrationTests'
ACCESS = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    spec = importlib.util.spec_from_file_location('sl3_registry_under_test', TOOL)
    engine = importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)
    pointer = json.loads((ROOT/'artifacts/build/deployment-tests-last.json').read_text())
    index = Path(pointer['directory'])/'index.json'; require(sha(index) == pointer['indexSha256'], 'Pinned bundle test index')
    package_test = json.loads(index.read_text()); bundle = ROOT/package_test['positiveBundle']
    bundle_hash = package_test['bundleManifestSha256']
    module = engine.builder(); module.verify(bundle, bundle_hash)
    plan = module.record(module.read(bundle/'deployment-plan.json')); items = engine.entries(plan)
    identity = uuid.uuid4().hex; namespace = BASE+'\\'+identity
    folder = ROOT/'artifacts/build/registry-tests'/identity; folder.mkdir(parents=True)
    cases = []; created_base = False; cleanup_verified = False
    machine_before = None; overlay_before = None

    def machine_state():
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, '', 0, engine.READ) as root:
            machine = engine.inspect(root, plan)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, engine.READ) as root:
            overlay = engine.inspect_overlay(root, plan)
        return machine, overlay

    machine_before, overlay_before = machine_state()

    def command(name, args, expected=0):
        result = subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True, encoding='utf-8', timeout=20)
        (folder/f'{name}-stdout.txt').write_text(result.stdout, encoding='utf-8')
        (folder/f'{name}-stderr.txt').write_text(result.stderr, encoding='utf-8')
        require(result.returncode == expected, f'{name}: {result.stdout} {result.stderr}')
        cases.append({'name': name, 'passed': True})
        return result

    for name, args in [('default-plan', []), ('explicit-plan', ['--plan'])]:
        result = json.loads(command(name, args).stdout)
        require(result['planOnly'] and not result['registryWritten'] and not result['machineMutationCliExposed'], 'CLI is inert by default')
    read_only = json.loads(command('machine-inspect', ['--inspect', '--bundle', bundle, '--expected-bundle-sha256', bundle_hash]).stdout)
    require(read_only['readOnly'] and not read_only['registryWritten'] and not read_only['installedFilesVerified'], 'Machine inspector reads only')
    command('no-machine-write-cli', ['--register', '--bundle', bundle, '--expected-bundle-sha256', bundle_hash], 2)

    def failure(operation):
        try:
            operation()
        except engine.RegistryFailure as error:
            require(not error.report['successful'], 'Failure report must not certify success')
            return error.report
        raise AssertionError('Expected registry operation refusal')

    @contextmanager
    def scenario(root, name, missing_asio=False):
        child = f'case-{len(cases):03d}'
        with engine.create_new(root, child) as handle:
            winreg.SetValueEx(handle, 'SL3TestOwner', 0, winreg.REG_SZ, identity)
        with winreg.OpenKey(root, child, 0, ACCESS) as handle:
            for parent in ['SOFTWARE\\Classes\\CLSID', 'SOFTWARE\\ASIO']:
                if missing_asio and parent == 'SOFTWARE\\ASIO':
                    continue
                with winreg.CreateKeyEx(handle, parent, 0, ACCESS):
                    pass
            siblings = ['SOFTWARE\\Classes\\CLSID\\OtherVendor', 'SOFTWARE\\ASIO\\OtherVendor']
            for path in siblings:
                if missing_asio and path.startswith('SOFTWARE\\ASIO\\'):
                    continue
                with winreg.CreateKeyEx(handle, path, 0, ACCESS) as sibling:
                    winreg.SetValueEx(sibling, 'Preserve', 0, winreg.REG_SZ, 'foreign fixture; never an engine target')
            before = {path: engine.snapshot(handle, path) for path in siblings}
            records = []
            yield handle, records
            after = {path: engine.snapshot(handle, path) for path in siblings}
            require(before == after, 'Foreign siblings remain byte/type/value identical')
            require(winreg.QueryValueEx(handle, 'SL3TestOwner')[0] == identity, 'Private root marker preserved')
            data = {'name': name, 'receipts': records, 'finalInspection': engine.inspect(handle, plan), 'foreignSiblingsPreserved': True}
            (folder/f'{name}.json').write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
            cases.append({'name': name, 'passed': True, 'temporaryRegistryWritten': True})

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, ACCESS) as user:
            try:
                with engine.create_new(user, BASE):
                    created_base = True
            except FileExistsError:
                pass
            with winreg.OpenKey(user, BASE, 0, ACCESS) as base:
                with engine.create_new(base, identity) as handle:
                    winreg.SetValueEx(handle, 'SL3TestOwner', 0, winreg.REG_SZ, identity)
            with winreg.OpenKey(user, namespace, 0, ACCESS) as private:
                with scenario(private, 'round-trip') as (root, records):
                    require(engine.inspect(root, plan)['newRegistrationAllowed'], 'Fresh private target')
                    records.append(engine.register_new(root, plan))
                    require(engine.inspect(root, plan)['exactOwned'] and engine.inspect_overlay(root, plan)['present'], 'Typed registration and overlay detection')
                    for item in items:
                        require(engine.snapshot(root, item['key'])['values'] == engine.model(item)['values'], 'Actual REG_SZ values through Windows APIs')
                    records.append(failure(lambda: engine.register_new(root, plan)))
                    records.append(engine.unregister_owned(root, plan))
                    require(engine.inspect(root, plan)['allAbsent'] and not engine.inspect_overlay(root, plan)['present'], 'Owned leaves removed; shared containers remain')

                with scenario(private, 'foreign-preexisting') as (root, records):
                    with winreg.CreateKeyEx(root, items[0]['key'], 0, ACCESS) as key:
                        winreg.SetValueEx(key, 'Foreign', 0, winreg.REG_BINARY, b'preserve\x00bytes')
                    before = engine.inspect(root, plan)
                    records.append(failure(lambda: engine.register_new(root, plan)))
                    records.append(failure(lambda: engine.unregister_owned(root, plan)))
                    require(engine.inspect(root, plan) == before, 'Pre-existing foreign registration untouched')

                with scenario(private, 'missing-container', missing_asio=True) as (root, records):
                    records.append(failure(lambda: engine.register_new(root, plan)))
                    require(not records[-1]['createdKeys'] and not engine.parent_present(root, 'SOFTWARE\\ASIO'), 'Engine never implicitly creates shared registry containers')

                with scenario(private, 'different-package-owner') as (root, records):
                    engine.register_new(root, plan); before = engine.inspect(root, plan)
                    other = json.loads(json.dumps(plan)); other['packageId'] = 'f'*64
                    other['registryEntries'] = module.registry_entries(Path(other['installationDirectory']), other['packageId'])
                    records.append(failure(lambda: engine.unregister_owned(root, other)))
                    require(not records[-1]['deletedKeys'] and engine.inspect(root, plan) == before, 'Another schema-valid package cannot unregister this package')

                for changed in ['marker', 'extra-value', 'extra-child', 'type']:
                    with scenario(private, 'ownership-'+changed) as (root, records):
                        engine.register_new(root, plan)
                        with winreg.OpenKey(root, items[2]['key'], 0, ACCESS) as key:
                            if changed == 'marker':
                                winreg.SetValueEx(key, 'SL3PackageId', 0, winreg.REG_SZ, '0'*64)
                            elif changed == 'extra-value':
                                winreg.SetValueEx(key, 'Foreign', 0, winreg.REG_DWORD, 7)
                            elif changed == 'extra-child':
                                with winreg.CreateKeyEx(key, 'Foreign', 0, ACCESS):
                                    pass
                            else:
                                winreg.SetValueEx(key, 'Description', 0, winreg.REG_EXPAND_SZ, module.NAME)
                        before = engine.inspect(root, plan)
                        records.append(failure(lambda: engine.unregister_owned(root, plan)))
                        require(engine.inspect(root, plan) == before and not records[-1]['deletedKeys'], 'Ownership/type conflict causes no deletion')

                for ordinal in range(1, 8):
                    with scenario(private, f'write-failure-{ordinal}') as (root, records):
                        calls = [0]
                        def journal(event):
                            if event['event'] == 'written':
                                calls[0] += 1
                                if calls[0] == ordinal:
                                    raise OSError('Injected journal failure after committed value')
                        records.append(failure(lambda: engine.register_new(root, plan, journal)))
                        require(engine.inspect(root, plan)['allAbsent'] and not records[-1]['preservedKeys'], 'Only invocation-created exact partial keys rolled back')

                with scenario(private, 'create-race') as (root, records):
                    def race(event):
                        if event['event'] == 'before_create' and event['key'] == items[0]['key']:
                            with winreg.CreateKeyEx(root, event['key'], 0, ACCESS) as key:
                                winreg.SetValueEx(key, 'ForeignRace', 0, winreg.REG_SZ, 'untouched')
                    records.append(failure(lambda: engine.register_new(root, plan, race)))
                    require(not records[-1]['createdKeys'] and engine.snapshot(root, items[0]['key'])['values']['ForeignRace']['data'] == 'untouched', 'Native create disposition refuses race without writing values')

                with scenario(private, 'rollback-preserves-mutation') as (root, records):
                    def mutate(event):
                        if event['event'] == 'written' and event['key'] == items[0]['key']:
                            with winreg.OpenKey(root, event['key'], 0, ACCESS) as key:
                                winreg.SetValueEx(key, 'Unexpected', 0, winreg.REG_SZ, 'preserve')
                            raise OSError('Injected foreign mutation and failure')
                    records.append(failure(lambda: engine.register_new(root, plan, mutate)))
                    require(records[-1]['preservedKeys'] == [items[0]['key']] and engine.snapshot(root, items[0]['key'])['values']['Unexpected']['data'] == 'preserve', 'Rollback refuses unknown data in its own partial key')

                with scenario(private, 'late-create-conflict') as (root, records):
                    def conflict(event):
                        if event['event'] == 'before_create' and event['key'] == items[2]['key']:
                            with winreg.CreateKeyEx(root, event['key'], 0, ACCESS) as key:
                                winreg.SetValueEx(key, 'ForeignLate', 0, winreg.REG_SZ, 'preserve')
                    records.append(failure(lambda: engine.register_new(root, plan, conflict)))
                    require(len(records[-1]['rolledBackKeys']) == 2 and engine.snapshot(root, items[2]['key'])['values']['ForeignLate']['data'] == 'preserve', 'Known partial COM entries rolled back; late foreign ASIO conflict preserved')

                for target in [1, 2]:
                    with scenario(private, f'deletion-race-{target}') as (root, records):
                        engine.register_new(root, plan)
                        path = items[target]['key']
                        def mutation(event):
                            if event['event'] == 'before_delete' and event['key'] == path:
                                with winreg.OpenKey(root, path, 0, ACCESS) as key:
                                    winreg.SetValueEx(key, 'Unexpected', 0, winreg.REG_SZ, 'preserve')
                        records.append(failure(lambda: engine.unregister_owned(root, plan, mutation)))
                        require(len(records[-1]['deletedKeys']) == (0 if target == 1 else 2), 'Partial removals reported honestly')
                        require(engine.snapshot(root, path)['values']['Unexpected']['data'] == 'preserve', 'Pre-delete recheck preserves changed remaining leaf')

                with scenario(private, 'concurrent-new-registration') as (root, records):
                    barrier = threading.Barrier(2, timeout=5)
                    def synchronized(event):
                        if event['event'] == 'before_create' and event['key'] == items[0]['key']:
                            barrier.wait()
                    def attempt():
                        try:
                            return engine.register_new(root, plan, synchronized)
                        except engine.RegistryFailure as error:
                            return error.report
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        results = list(executor.map(lambda _: attempt(), range(2)))
                    records.extend(results)
                    require(sum(x['successful'] for x in results) == 1 and engine.inspect(root, plan)['exactOwned'], 'One real create-new winner; competing invocation writes no foreign leaf')
                    records.append(engine.unregister_owned(root, plan))

                with scenario(private, 'wrong-key-plan') as (root, records):
                    forged = json.loads(json.dumps(plan)); forged['registryEntries'][0]['key'] = 'SOFTWARE\\Unrelated'
                    rejected = False
                    try:
                        engine.register_new(root, forged)
                    except ValueError:
                        rejected = True
                    require(rejected and engine.inspect(root, plan)['allAbsent'] and engine.snapshot(root, 'SOFTWARE\\Unrelated') is None, 'Unrelated registry destination rejected before writes')
    finally:
        # Only this exact create-new UUID namespace, after checking its marker.
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, engine.READ) as private:
            require(winreg.QueryValueEx(private, 'SL3TestOwner')[0] == identity, 'Private cleanup ownership marker')
        def remove_private(path):
            require(path == namespace or path.startswith(namespace+'\\'), 'Registry cleanup stays inside exact test namespace')
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, engine.READ) as key:
                children = [winreg.EnumKey(key, n) for n in range(winreg.QueryInfoKey(key)[0])]
            for child in children:
                remove_private(path+'\\'+child)
            winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, path, winreg.KEY_WOW64_64KEY, 0)
        remove_private(namespace)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace, 0, engine.READ):
                pass
        except FileNotFoundError:
            cleanup_verified = True
        if created_base:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BASE, 0, engine.READ) as base:
                children, values, _ = winreg.QueryInfoKey(base)
            if children == 0 and values == 0:
                try:
                    winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, BASE, winreg.KEY_WOW64_64KEY, 0)
                except OSError:
                    pass  # Never remove a shared container after another test entered it.

    require(cleanup_verified, 'Private registry test namespace removed')
    machine_after, overlay_after = machine_state()
    require(machine_before == machine_after and overlay_before == overlay_after, 'Live machine/current-user COM/ASIO entries unchanged')
    files = {path.relative_to(folder).as_posix(): sha(path) for path in folder.iterdir() if path.is_file()}
    report = {'schema': 'sl3.registry-engine-tests.v1', 'cases': cases, 'files': files,
              'temporaryNamespace': 'HKEY_CURRENT_USER\\'+namespace, 'temporaryRegistryWritten': True,
              'temporaryNamespaceRemoved': cleanup_verified, 'liveMachineEntriesUnchanged': True, 'liveCurrentUserOverlayUnchanged': True,
              'machineBefore': machine_before, 'machineAfter': machine_after,
              'binaryPayloadExecuted': False, 'deviceAccess': False, 'installed': False}
    index = folder/'index.json'; index.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/registry-tests-last.json').write_text(json.dumps({'directory': str(folder), 'indexSha256': sha(index)}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'privateNamespaceRemoved': True, 'machineEntriesUnchanged': True, 'evidenceDirectory': str(folder)}))


if __name__ == '__main__':
    main()
