"""Verify current retained-lifecycle probe builds and export metadata; no live USB/registration."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def main():
    builds = {}
    for config in ('Release', 'Debug'):
        folder = ROOT/'artifacts/build/native'
        path = folder/f'native-build-{config}.json'
        b = json.loads(path.read_text(encoding='utf-8-sig'))
        require(b['coreTestsPassed'] is True and b['planOnlyPassed'] is True, 'Build did not pass')
        for name, expected in b['inputs'].items():
            require(sha(ROOT/name) == expected.lower(), 'Source/dependency changed: '+name)
        require(sha(ROOT/'scripts/build-native.ps1') == b['buildScriptSha256'].lower(), 'Build script differs')
        required = {'sl3_retained_host_tests', 'sl3_asio_retained_session_tests', 'sl3_host_session_tests', 'sl3_audio_owner_tests',
                    'sl3_driver_configuration_tests', 'sl3_device_session_tests', 'sl3_asio_session_tests', 'sl3_retained_probe_lifecycle', 'sl3_controls_probe_lifecycle'}
        require(len(b['ctestTests']) == 40 and required <= set(b['ctestTests']), 'Required ASIO/ownership checks missing')
        log = folder/f'ctest-{config}.log'
        require(sha(log) == b['ctestLogSha256'].lower() and '100% tests passed, 0 tests failed out of 40' in log.read_text(encoding='utf-8-sig'),
                'CTest evidence differs or failed')
        component = b['asioComponent']
        host = component['hostSession']
        retained = host['retained']
        probe = b['hostProbe']['retained']
        require(probe['simulatedLifecyclePassed'] is True and probe['physicalLifecycleTested'] is False
                and probe['streams'] == 2 and probe['streamMilliseconds'] == 1000 and probe['intervals'] == 8 and probe['bankFrames'] == 128,
                'Unexpected retained probe scope/shape')
        require(len(probe['scriptInputs']) == 11, 'Missing probe/runner dependencies')
        for name, expected in probe['scriptInputs'].items():
            require(sha(ROOT/'scripts'/name) == expected.lower(), 'Probe script/dependency changed: '+name)
        require(all(retained[k] is True for k in ('productionProviderUsesRetainedDevice', 'freshDataChannelPerStart', 'stopPreservesDevice',
                                                  'callbackIndependentRetirementTested', 'actualAsioVtableTested'))
                and retained['timingProfileInstalled'] is False and retained['physicalRetainedLifecycleTested'] is False,
                'Unexpected retained ASIO claim')
        require(b['deviceSession']['asioSessionOwnerConnected'] is True and component['nativeProvider']['configurationInstalled'] is False
                and not (folder/config/'sl3-asio.conf').exists(), 'Provider integration/configuration boundary differs')
        identities = [('sl3_host_probe.exe', b['hostProbe']['executableSha256']), ('sl3_host_probe_simulated.exe', b['hostProbe']['simulatedExecutableSha256']), ('sl3_usbdk.exe', b['usbdk']['executableSha256']), ('sl3_asio.dll', component['comDllSha256']),
                      ('sl3_host_session.lib', host['librarySha256']), ('sl3_retained_host_tests.exe', retained['testExecutableSha256']),
                      ('sl3_asio_session_tests.exe', component['driverFacade']['sessionAbiTestExecutableSha256']),
                      ('sl3_asio_session_fixture.dll', component['driverFacade']['sessionFixtureDllSha256'])]
        binaries = {}
        for name, expected in identities:
            require(sha(folder/config/name) == expected.lower(), 'Binary differs: '+name)
            binaries[name] = sha(folder/config/name)
        builds[config] = {'testsPassed': 40, 'manifestSha256': sha(path), 'ctestLogSha256': sha(log),
                          'binaries': binaries, 'inputs': b['inputs'], 'scriptInputs': probe['scriptInputs']}
    require(builds['Release']['inputs'] == builds['Debug']['inputs'], 'Configurations used different source')
    sdk = ROOT/'artifacts/build/native-without-sdk'
    cache = (sdk/'CMakeCache.txt').read_text(encoding='utf-8-sig')
    require('SL3_BUILD_ASIO_COMPONENT:BOOL=OFF' in cache and 'SL3_ASIO_SDK_ROOT:PATH=C:/definitely-absent-sl3-sdk' in cache
            and not Path('C:/definitely-absent-sl3-sdk').exists(), 'SDK-free boundary differs')
    sdk_log = ROOT/'analysis/selection-probe-sdk-free-ctest.log'
    require('100% tests passed, 0 tests failed out of 25' in sdk_log.read_text(encoding='utf-8-sig'), 'SDK-free tests failed')
    python_log = ROOT/'analysis/lifecycle-controls-python-tests.log'
    text = python_log.read_text(encoding='utf-8-sig')
    require('Ran 80 tests' in text and text.rstrip().endswith('OK'), 'Python checks failed')
    result = {'scope': 'Current retained-lifecycle software build checks; physical tests are recorded separately',
              'builds': builds, 'sdkFree': {'testsPassed': 25, 'sdkAbsent': True, 'ctestLogSha256': sha(sdk_log)},
              'python': {'testsPassed': 80, 'logSha256': sha(python_log)},
              'retainedDeviceHostIntegrated': True, 'retainedLifecycleProbeImplemented': True, 'tracedSequencePrepared': True,
              'evidenceTestsSha256': sha(ROOT/'tests/test_retained_probe_evidence.py'), 'actualAsioVtableAndBlockedDllRetirementTested': True,
              'nativePositiveRunDuringBuild': False, 'productionTimingProfileInstalled': False,
              'separatePhysicalEvidence': 'docs/evidence/retained-physical-20261030.json',
              'limits': ['This build performs no positive native USB run; the dated retained physical result has its own binary/source bindings',
                         'No measured timing profile, production registration/application run, analogue mapping, Serato or DVS result',
                         'Old physical bridge results remain bound to their archived worker/probe/source checkpoints']}
    (ROOT/'docs/evidence/retained-lifecycle-probe-build.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified 40 Release, 40 Debug, 25 SDK-free and 80 Python records; physical retained evidence remains separate')


if __name__ == '__main__':
    main()
