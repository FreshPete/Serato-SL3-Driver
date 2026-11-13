"""Exercise the extracted watcher's driver actions in isolated Windows fixtures."""

import argparse
import json
from pathlib import Path
import runpy
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4
import winreg


ACCESS = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY


def require(value, message):
    if not value:
        raise ValueError(message)


def delete_fixture(parent, name):
    with winreg.OpenKey(parent, name, 0, ACCESS) as key:
        children = [winreg.EnumKey(key, index) for index in range(winreg.QueryInfoKey(key)[0])]
        for child in children:
            delete_fixture(key, child)
    winreg.DeleteKeyEx(parent, name, winreg.KEY_WOW64_64KEY, 0)


def exercise(kit, expected):
    setup = runpy.run_path(str(kit / 'scripts/setup-serato-native-watcher.py'))
    payload = setup['read_payload'](kit, expected)
    native = setup['WATCH']['PROBE']['driver']()
    native.check_action_dependencies()
    stage = native.s
    require(not stage.elevated(), 'Use an ordinary Windows session for the isolated fixture')
    require(Path(sys.executable).resolve() == (kit / 'runtime/python/python.exe').resolve(),
            'Run the fixture using the extracted kit Python')
    initial = native.observe()
    sid = stage.user_sid()
    policy = stage.Policy(sid, (stage.SYSTEM, stage.ADMINS, sid))
    name = r'Software\SL3RebuildWatcherDriverTest-' + uuid4().hex
    loader = native.remove.__globals__['module']
    root_created = False
    try:
        with tempfile.TemporaryDirectory(prefix='SL3 Driver Fixture ') as temp, \
                winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, name, 0, ACCESS) as fixture:
            root_created = True
            base = Path(temp).resolve() / 'base'
            destination = base / 'stage'
            with winreg.CreateKeyEx(fixture, 'machine-model', 0, ACCESS) as registry, \
                    winreg.CreateKeyEx(fixture, 'overlay-model', 0, ACCESS) as overlay:
                for key in (r'SOFTWARE\Classes\CLSID', r'SOFTWARE\ASIO'):
                    with winreg.CreateKeyEx(registry, key, 0, ACCESS):
                        pass

                def install(bundle, identity):
                    return native.install_api['install_owned'](bundle, identity, base, destination, policy, registry, overlay)

                def fixture_module(module):
                    api = loader(module)
                    require(module == 'asio-uninstall.py', 'Unexpected removal module')
                    return {**api, 'uninstall_production': lambda _base, _destination, receipt:
                            api['uninstall_owned'](base, destination, receipt, policy, registry, overlay)}

                prepare = native.install_api['sibling']('asio-install-base').prepared_base
                with prepare(base, policy) as prepared, patch.dict(native.install_api, {'install_production': install}):
                    installed = native.install()
                    require(prepared['policyVerified'] and installed['successful'] and
                            installed['runtimeDirectImportsResolved'] and installed['registrationOwnedObserved'],
                            'Packaged installer did not stage and register the isolated driver')
                    receipt = installed['stageResult']['stageRecordSha256']
                    with patch.dict(native.remove.__globals__, {'module': fixture_module}):
                        removed = native.remove(receipt)
                    require(removed['successful'] and removed['finalRegistryAbsentObserved'] and
                            removed['directoryAbsentObserved'], 'Packaged uninstaller left isolated state behind')
    finally:
        if root_created:
            delete_fixture(winreg.HKEY_CURRENT_USER, name)
    require(native.observe() == initial, 'Live driver stage or registration changed')
    return {'schema': 'sl3.private-watcher-driver-package-fixture.v1', 'payloadSha256': expected,
            'bundleSha256': native.expected, 'bufferFrames': payload['diagnosticBufferFrames'],
            'actionDependenciesVerified': True, 'runtimeDirectImportsResolved': True,
            'isolatedBasePrepared': True, 'isolatedRegistrationOwnedThenRemoved': True,
            'isolatedFilesStagedThenRemoved': True, 'liveDriverStage': initial['state'],
            'liveRegistrationChanged': False, 'privilegedActionsExecuted': False, 'deviceAccess': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit', type=Path, required=True)
    parser.add_argument('--expected-payload-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(exercise(args.kit.resolve(), args.expected_payload_sha256), indent=2))
