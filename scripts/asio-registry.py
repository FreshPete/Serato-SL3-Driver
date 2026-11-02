"""Constrained ASIO registration engine; CLI offers plan/read-only inspection only.

Mutating library operations require an explicit open root handle from a trusted
installer. Tests supply a fresh private HKCU subtree, never a live class root.
"""
import argparse
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys
import winreg

READ = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
WRITE = winreg.KEY_READ | winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY


def builder():
    spec = importlib.util.spec_from_file_location('sl3_registry_bundle_reader', Path(__file__).with_name('prepare-asio-deployment.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class RegistryFailure(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__(report['error'])


def entries(plan):
    module = builder()
    module.require(plan['schema'] == 'sl3.deployment-plan.v1' and plan['registryView'] == 64 and
                   plan['registryHive'] == 'HKEY_LOCAL_MACHINE' and plan['registryApplied'] is False,
                   'Only the unapplied Windows x64 machine registration schema is supported')
    module.sha_value(plan['packageId'])
    installation, pointer = module.destinations(Path(plan['installationDirectory']), Path(plan['pointerPath']))
    expected = module.registry_entries(installation, plan['packageId'])
    module.require(plan['registryEntries'] == expected, 'Registry keys/values differ from own project identity')
    return expected


def snapshot(root, path):
    try:
        handle = winreg.OpenKey(root, path, 0, READ)
    except FileNotFoundError:
        return None
    with handle:
        return snapshot_handle(handle)


def snapshot_handle(handle):
    children, values, _ = winreg.QueryInfoKey(handle)
    result = {'values': {}, 'subkeys': sorted(winreg.EnumKey(handle, n) for n in range(children))}
    for n in range(values):
        name, data, kind = winreg.EnumValue(handle, n)
        result['values'][name] = {'type': kind, 'data': {'hex': data.hex()} if isinstance(data, bytes) else data}
    return result


def model(item, subkeys=()):
    return {'values': {name: {'type': winreg.REG_SZ, 'data': value} for name, value in item['strings'].items()},
            'subkeys': sorted(subkeys)}


def parent_present(root, path):
    try:
        with winreg.OpenKey(root, path, 0, READ):
            return True
    except FileNotFoundError:
        return False


def inspect(root, plan):
    items = entries(plan)
    states = {item['key']: snapshot(root, item['key']) for item in items}
    expected = {}
    for item in items:
        prefix = item['key']+'\\'
        children = [other['key'][len(prefix):] for other in items if other['key'].startswith(prefix) and '\\' not in other['key'][len(prefix):]]
        expected[item['key']] = model(item, children)
    parents = {items[0]['key'].rsplit('\\', 1)[0], items[2]['key'].rsplit('\\', 1)[0]}
    containers = {path: parent_present(root, path) for path in sorted(parents)}
    return {'schema': 'sl3.registry-inspection.v1', 'registryView': 64, 'states': states,
            'containersPresent': containers, 'allAbsent': all(x is None for x in states.values()),
            'exactOwned': states == expected,
            'newRegistrationAllowed': all(x is None for x in states.values()) and all(containers.values()),
            'registryWritten': False}


def inspect_overlay(root, plan):
    # The caller supplies the current-user root (or an isolated test root).
    paths = [item['key'] for item in entries(plan)[:2]]
    states = {path: snapshot(root, path) for path in paths}
    return {'states': states, 'present': any(x is not None for x in states.values())}


@contextmanager
def create_new(root, path):
    """Only create the final leaf below an existing parent; never open-and-set."""
    parent, _, leaf = path.rpartition('\\')
    if not leaf or '\0' in leaf:
        raise ValueError('New leaf name required')
    api = ctypes.WinDLL('advapi32.dll', use_last_error=True, winmode=0x800).RegCreateKeyExW
    api.argtypes = [wintypes.HKEY, wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD,
                    wintypes.DWORD, wintypes.LPVOID, ctypes.POINTER(wintypes.HKEY), ctypes.POINTER(wintypes.DWORD)]
    api.restype = wintypes.LONG
    result = wintypes.HKEY(); disposition = wintypes.DWORD()
    with winreg.OpenKey(root, parent, 0, WRITE) as base:
        code = api(int(base), leaf, 0, None, 0, WRITE, None, ctypes.byref(result), ctypes.byref(disposition))
    if code:
        raise ctypes.WinError(code)
    if disposition.value != 1:  # REG_CREATED_NEW_KEY
        winreg.CloseKey(result.value)
        raise FileExistsError('Registry leaf already exists; no value was written')
    try:
        yield result.value
    finally:
        winreg.CloseKey(result.value)


def emit(journal, event, path, name=None):
    if journal is not None:
        journal({'event': event, 'key': path, 'value': name})


def register_new(root, plan, journal=None):
    items = entries(plan)
    report = {'schema': 'sl3.registry-operation.v1', 'action': 'register', 'successful': False,
              'createdKeys': [], 'rolledBackKeys': [], 'preservedKeys': [], 'error': ''}
    written = {}
    try:
        state = inspect(root, plan)
        if not state['newRegistrationAllowed']:
            raise ValueError('Existing registration or missing shared container; preserve all existing keys')
        for item in items:
            path = item['key']; emit(journal, 'before_create', path)
            with create_new(root, path) as handle:
                report['createdKeys'].append(path); written[path] = {'values': {}, 'subkeys': []}
                emit(journal, 'created', path)
                for name, value in item['strings'].items():
                    winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, value)
                    written[path]['values'][name] = {'type': winreg.REG_SZ, 'data': value}
                    emit(journal, 'written', path, name)
                winreg.FlushKey(handle)
        if not inspect(root, plan)['exactOwned']:
            raise ValueError('Registered state changed before final validation')
        report['successful'] = True
        return report
    except Exception as error:
        report['error'] = str(error)
        # Only keys created by this invocation, only their actually recorded
        # successful writes, and only empty leaves after child rollback.
        for path in reversed(report['createdKeys']):
            try:
                if snapshot(root, path) != written[path]:
                    report['preservedKeys'].append(path)
                    continue
                winreg.DeleteKeyEx(root, path, winreg.KEY_WOW64_64KEY, 0)
                report['rolledBackKeys'].append(path)
            except OSError:
                report['preservedKeys'].append(path)
        raise RegistryFailure(report) from error


def unregister_owned(root, plan, journal=None):
    items = entries(plan)
    report = {'schema': 'sl3.registry-operation.v1', 'action': 'unregister', 'successful': False,
              'deletedKeys': [], 'error': ''}
    try:
        if not inspect(root, plan)['exactOwned']:
            raise ValueError('Registration ownership/values/types/subkeys differ; no deletion permitted')
        # InprocServer32 first, then its now-empty CLSID parent, then ASIO leaf.
        for item in [items[1], items[0], items[2]]:
            path = item['key']; emit(journal, 'before_delete', path)
            with winreg.OpenKey(root, path, 0, READ) as handle:
                if snapshot_handle(handle) != model(item):
                    raise ValueError('Registration changed during removal; preserve remaining keys')
                winreg.DeleteKeyEx(root, path, winreg.KEY_WOW64_64KEY, 0)
            report['deletedKeys'].append(path); emit(journal, 'deleted', path)
        if not inspect(root, plan)['allAbsent']:
            raise ValueError('Registry paths reappeared after removal')
        report['successful'] = True
        return report
    except Exception as error:
        report['error'] = str(error)
        # Deletions are not silently re-created or called an atomic uninstall.
        raise RegistryFailure(report) from error


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv == ['--plan']:
        print(json.dumps({'schema': 'sl3.registry-engine-plan.v1', 'planOnly': True, 'registryWritten': False,
                          'deviceAccess': False, 'machineMutationCliExposed': False})); return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect', action='store_true', required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--expected-bundle-sha256', required=True)
    args = parser.parse_args(argv)
    module = builder(); module.verify(args.bundle, args.expected_bundle_sha256)
    plan = module.record(module.read(args.bundle/'deployment-plan.json'))
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, '', 0, READ) as root:
        result = inspect(root, plan)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, READ) as root:
        result['currentUserComOverlay'] = inspect_overlay(root, plan)
    result['newRegistrationAllowed'] &= not result['currentUserComOverlay']['present']
    result.update(target='HKEY_LOCAL_MACHINE', readOnly=True, installedFilesVerified=False,
                  deviceAccess=False, binaryPayloadExecuted=False)
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
