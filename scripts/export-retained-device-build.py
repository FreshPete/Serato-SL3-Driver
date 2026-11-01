"""Read-only build verification and metadata export; never launches device workers."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT/'artifacts/build/checkpoints/retained-device-worker-20261030'
SOURCE_COMMIT = 'abd4586f1a9a1d34025962ffebbb5ec3149b208f'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def main():
    builds = {}
    for config in ('Release', 'Debug'):
        folder = CHECKPOINT
        manifest_path = folder/f'native-build-{config}.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        require(manifest['coreTestsPassed'] is True and manifest['planOnlyPassed'] is True, 'Build did not pass')
        for name, expected in manifest['inputs'].items():
            if (ROOT/name).exists() and sha(ROOT/name) == expected.lower():
                continue
            recorded = subprocess.run(['git', 'show', SOURCE_COMMIT+':'+name], cwd=ROOT, capture_output=True, timeout=10)
            require(recorded.returncode == 0, 'Archived source unavailable: '+name)
            lf = recorded.stdout.replace(b'\r\n', b'\n')
            require(any(hashlib.sha256(raw).hexdigest() == expected.lower() for raw in (recorded.stdout, lf, lf.replace(b'\n', b'\r\n'))),
                    'Archived source/dependency differs: '+name)
        require(sha(CHECKPOINT/'build-native.ps1') == manifest['buildScriptSha256'].lower(), 'Archived build script differs')
        tests = manifest['ctestTests']
        require(len(tests) == 35 and {'sl3_device_session_tests', 'sl3_usbdk_rejects_device_modes'} <= set(tests), 'Missing retained-device checks')
        log = folder/f'ctest-{config}.log'
        require(sha(log) == manifest['ctestLogSha256'].lower(), 'CTest log differs')
        require('100% tests passed, 0 tests failed out of 35' in log.read_text(encoding='utf-8-sig'), 'CTest not successful')
        session = manifest['deviceSession']
        require(session['nativeWorkerImplemented'] is True and session['simulatedRetainedLifetimeTested'] is True
                and session['nativeAbsentHelperRejected'] is True and session['freshAudioChannelPerStart'] is True
                and session['physicalRetainedLifetimeTested'] is False and session['asioSessionOwnerConnected'] is False,
                'Unexpected retained-device scope')
        binaries = {}
        for filename, expected in [('sl3_usbdk.exe', manifest['usbdk']['executableSha256']),
                                   ('sl3_device_session_fixture.exe', session['fixtureSha256']),
                                   ('sl3_device_session_tests.exe', session['testExecutableSha256'])]:
            path = folder/config/filename
            require(sha(path) == expected.lower(), 'Binary differs: '+filename)
            binaries[filename] = sha(path)
        builds[config] = {'testsPassed': 35, 'manifestSha256': sha(manifest_path), 'ctestLogSha256': sha(log),
                          'binaries': binaries, 'inputs': manifest['inputs']}
    require(builds['Release']['inputs'] == builds['Debug']['inputs'], 'Configurations used different source inputs')
    sdk_free = CHECKPOINT/'sdk-free'
    cache = (sdk_free/'CMakeCache.txt').read_text(encoding='utf-8-sig')
    require('SL3_BUILD_ASIO_COMPONENT:BOOL=OFF' in cache and 'SL3_ASIO_SDK_ROOT:PATH=C:/definitely-absent-sl3-sdk' in cache
            and not Path('C:/definitely-absent-sl3-sdk').exists(), 'SDK-free boundary differs')
    log = sdk_free/'ctest.log'
    text = log.read_text(encoding='utf-8-sig')
    require('100% tests passed, 0 tests failed out of 25' in text and 'sl3_device_session_tests' in text, 'SDK-free tests did not pass')
    python_log = CHECKPOINT/'python-tests.log'
    python_text = python_log.read_text(encoding='utf-8-sig')
    require('Ran 56 tests' in python_text and python_text.rstrip().endswith('OK'), 'Python suite did not pass')
    result = {'scope': 'New retained-device native implementation; simulated positive lifetime, real native absent-helper negative only',
              'builds': builds, 'sdkFree': {'testsPassed': 25, 'ctestLogSha256': sha(log), 'sdkAbsent': True,
                                          'workerSha256': sha(sdk_free/'sl3_usbdk.exe')},
              'python': {'testsPassed': 56, 'logSha256': sha(python_log)},
              'physicalRetainedLifetimeTested': False, 'asioHostIntegrated': False,
              'limits': ['Earlier eight-interval hardware result belongs to archived F297 worker, not this build',
                         'Fresh same-build capture/duplex and a dedicated retained-lifetime probe are needed before new audio hardware validation',
                         'Production ASIO, sustained timing, analogue mapping, Serato and two-deck DVS remain incomplete']}
    (ROOT/'docs/evidence/retained-device-worker-build.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified 35 Release, 35 Debug, 25 SDK-free and 56 Python checks; no retained-device hardware claim')


if __name__ == '__main__':
    main()
