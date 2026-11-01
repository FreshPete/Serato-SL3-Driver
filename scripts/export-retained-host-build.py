"""Verify archived retained-ASIO builds and export metadata; no live USB/registration."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT/'artifacts/build/checkpoints/retained-asio-host-20261030'
SOURCE_COMMIT = 'ae014a188c2211bb65db7ee7e74214cf0d0c8229'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def main():
    builds = {}
    for config in ('Release', 'Debug'):
        folder = CHECKPOINT
        path = folder/f'native-build-{config}.json'
        b = json.loads(path.read_text(encoding='utf-8-sig'))
        require(b['coreTestsPassed'] is True and b['planOnlyPassed'] is True, 'Build did not pass')
        for name, expected in b['inputs'].items():
            if (ROOT/name).exists() and sha(ROOT/name) == expected.lower():
                continue
            historical = subprocess.run(['git', 'show', SOURCE_COMMIT+':'+name], cwd=ROOT, capture_output=True, timeout=10)
            require(historical.returncode == 0, 'Historical source unavailable: '+name)
            lf = historical.stdout.replace(b'\r\n', b'\n')
            require(any(hashlib.sha256(raw).hexdigest() == expected.lower() for raw in (historical.stdout, lf, lf.replace(b'\n', b'\r\n'))),
                    'Archived source/dependency differs: '+name)
        require(sha(CHECKPOINT/'build-native.ps1') == b['buildScriptSha256'].lower(), 'Archived build script differs')
        required = {'sl3_retained_host_tests', 'sl3_asio_retained_session_tests', 'sl3_host_session_tests', 'sl3_audio_owner_tests',
                    'sl3_driver_configuration_tests', 'sl3_device_session_tests', 'sl3_asio_session_tests'}
        require(len(b['ctestTests']) == 37 and required <= set(b['ctestTests']), 'Required ASIO/ownership checks missing')
        log = folder/f'ctest-{config}.log'
        require(sha(log) == b['ctestLogSha256'].lower() and '100% tests passed, 0 tests failed out of 37' in log.read_text(encoding='utf-8-sig'),
                'CTest evidence differs or failed')
        component = b['asioComponent']
        host = component['hostSession']
        retained = host['retained']
        require(all(retained[k] is True for k in ('productionProviderUsesRetainedDevice', 'freshDataChannelPerStart', 'stopPreservesDevice',
                                                  'callbackIndependentRetirementTested', 'actualAsioVtableTested'))
                and retained['timingProfileInstalled'] is False and retained['physicalRetainedLifecycleTested'] is False,
                'Unexpected retained ASIO claim')
        require(b['deviceSession']['asioSessionOwnerConnected'] is True and component['nativeProvider']['configurationInstalled'] is False
                and not (folder/config/'sl3-asio.conf').exists(), 'Provider integration/configuration boundary differs')
        identities = [('sl3_usbdk.exe', b['usbdk']['executableSha256']), ('sl3_asio.dll', component['comDllSha256']),
                      ('sl3_host_session.lib', host['librarySha256']), ('sl3_retained_host_tests.exe', retained['testExecutableSha256']),
                      ('sl3_asio_session_tests.exe', component['driverFacade']['sessionAbiTestExecutableSha256']),
                      ('sl3_asio_session_fixture.dll', component['driverFacade']['sessionFixtureDllSha256'])]
        binaries = {}
        for name, expected in identities:
            require(sha(folder/config/name) == expected.lower(), 'Binary differs: '+name)
            binaries[name] = sha(folder/config/name)
        builds[config] = {'testsPassed': 37, 'manifestSha256': sha(path), 'ctestLogSha256': sha(log),
                          'binaries': binaries, 'inputs': b['inputs']}
    require(builds['Release']['inputs'] == builds['Debug']['inputs'], 'Configurations used different source')
    sdk = CHECKPOINT/'sdk-free'
    cache = (sdk/'CMakeCache.txt').read_text(encoding='utf-8-sig')
    require('SL3_BUILD_ASIO_COMPONENT:BOOL=OFF' in cache and 'SL3_ASIO_SDK_ROOT:PATH=C:/definitely-absent-sl3-sdk' in cache
            and not Path('C:/definitely-absent-sl3-sdk').exists(), 'SDK-free boundary differs')
    sdk_log = CHECKPOINT/'retained-host-sdk-free-ctest.log'
    require('100% tests passed, 0 tests failed out of 25' in sdk_log.read_text(encoding='utf-8-sig'), 'SDK-free tests failed')
    python_log = CHECKPOINT/'retained-host-python-tests.log'
    text = python_log.read_text(encoding='utf-8-sig')
    require('Ran 56 tests' in text and text.rstrip().endswith('OK'), 'Python checks failed')
    result = {'scope': 'Retained native ASIO owner/provider implemented; actual IASIO/COM positive tests use simulated transport only',
              'builds': builds, 'sdkFree': {'testsPassed': 25, 'sdkAbsent': True, 'ctestLogSha256': sha(sdk_log)},
              'python': {'testsPassed': 56, 'logSha256': sha(python_log)},
              'retainedDeviceHostIntegrated': True, 'actualAsioVtableAndBlockedDllRetirementTested': True,
              'physicalRetainedLifecycleTested': False, 'productionTimingProfileInstalled': False,
              'limits': ['Native positive retained lifetime remains untested on hardware; native negative uses an asserted absent helper',
                         'No measured timing profile, production registration/application run, analogue mapping, Serato or DVS result',
                         'Old physical bridge results remain bound to their archived worker/probe/source checkpoints']}
    (ROOT/'docs/evidence/retained-asio-host-build.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified 37 Release, 37 Debug, 25 SDK-free and 56 Python checks; retained ASIO host implemented, physical lifetime pending')


if __name__ == '__main__':
    main()
