"""Verify actual unregistered ASIO object recreation with simulated transport."""
import hashlib
import json
from pathlib import Path
import re

import pefile

ROOT = Path(__file__).resolve().parents[1]


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def exports(path):
    image = pefile.PE(str(path), fast_load=True)
    image.parse_data_directories(directories=[0])
    return {row.name.decode('ascii') for row in image.DIRECTORY_ENTRY_EXPORT.symbols if row.name}


def main():
    results = {}
    for config in ('Release', 'Debug'):
        folder = ROOT/'artifacts/build/native'
        manifest = folder/f'native-build-{config}.json'
        build = read(manifest)
        for name, expected in build['inputs'].items():
            require(sha(ROOT/name) == expected.lower(), 'Stale tested source: '+name)
        require(sha(ROOT/'scripts/build-native.ps1') == build['buildScriptSha256'].lower(), 'Build runner differs')
        log = folder/f'ctest-{config}.log'
        text = log.read_text(encoding='utf-8-sig')
        require(sha(log) == build['ctestLogSha256'].lower() and len(build['ctestTests']) == 40 and
                '100% tests passed, 0 tests failed out of 40' in text and
                re.search(r'sl3_asio_retained_session_tests\s+\.+\s+Passed', text), 'Retained COM test did not pass')
        feature = build['asioComponent']['driverFacade']
        files = {'sl3_asio_session_tests.exe': feature['sessionAbiTestExecutableSha256'],
                 'sl3_asio_session_fixture.dll': feature['sessionFixtureDllSha256'],
                 'sl3_asio.dll': build['asioComponent']['comDllSha256'],
                 'sl3_device_session_fixture.exe': build['deviceSession']['fixtureSha256']}
        for name, expected in files.items():
            require(sha(folder/config/name) == expected.lower(), 'Tested binary differs: '+name)
        fixture_exports = exports(folder/config/'sl3_asio_session_fixture.dll')
        native_exports = exports(folder/config/'sl3_asio.dll')
        audit_export = 'sl3_test_configure_retained_audit'
        require(audit_export in fixture_exports and not any(x.startswith('sl3_test_') for x in native_exports),
                'Test provider absent or leaked into production')
        previous = ROOT/'artifacts/build/checkpoints/controls-probe-20261030'
        old = read(previous/f'native-build-{config}.json')
        current_sources = {name: value for name, value in build['inputs'].items() if name.startswith('src/')}
        old_sources = {name: value for name, value in old['inputs'].items() if name.startswith('src/')}
        changed = sorted(name for name in current_sources.keys() | old_sources.keys() if current_sources.get(name) != old_sources.get(name))
        require(set(changed) <= {'src/core/control_frames.hpp', 'src/core/audio_control_selection.hpp',
                                 'src/core/audio_control_selection_io.hpp','src/core/audio_control_selection_wire.hpp',
                                 'src/core/device_session_protocol.hpp','src/core/device_session_protocol.cpp',
                                 'src/windows/device_session.hpp','src/windows/device_session.cpp',
                                 'src/asio/host_session.hpp','src/asio/host_session.cpp',
                                 'src/windows/usbdk_main.cpp','src/windows/control_transfer_io.hpp',
                                 'src/windows/control_baseline.hpp','src/windows/control_selection_diagnostic.hpp',
                                 'src/core/control_test_target.hpp','src/windows/host_probe_main.cpp'},
                'Runtime implementation changed beyond separately reviewed controls IPC/native adapter')
        identities = {}
        for name in ('sl3_asio.dll', 'sl3_usbdk.exe', 'sl3_host_probe.exe'):
            identities[name] = {'sha256': sha(folder/config/name),
                                'matchesControlsCheckpoint': sha(folder/config/name) == sha(previous/config/name)}
        results[config] = {'testsPassed': 40, 'manifestSha256': sha(manifest), 'ctestLogSha256': sha(log),
                           'testedBinaries': files, 'productionSourcesUnchangedFromControlsCheckpoint': not changed,
                           'sourceChangesFromControlsCheckpoint': changed, 'runtimeBinaries': identities,
                           'testOnlyAuditExportAbsentFromProduction': True,
                           'testSourceSha256': build['inputs']['tests/native/asio_session_tests.cpp'],
                           'providerSourceSha256': build['inputs']['tests/native/asio_session_provider.cpp']}
    output = {'scope': 'Actual unregistered COM/IASIO DLL with isolated simulated workers; no native USB or Serato execution',
              'builds': results,
              'newAuditedScenario': {'objects': 3, 'metadataOnlyEnumerationObjects': 1,
                                    'recreatedObjects': 2, 'streamsPerRecreatedObject': 2,
                                    'setupHoldMilliseconds': 80, 'bankFrames': 128,
                                    'expectedAcquisitions': 3, 'expectedClockReads': 7,
                                    'expectedAudioBeginEndPairs': 4, 'expectedFinalReleases': 3,
                                    'auditComparedAfterEveryStage': True},
              'limits': ['Transport/rate/input and timing profile are explicitly simulated',
                         'Setup delay mirrors an observed application call shape; it is not a device-readiness barrier',
                         'No actual Serato callback/reset dispatch or physical reacquisition is proved',
                         'Existing native evidence remains pinned to its own binaries; deployment and DVS remain incomplete']}
    (ROOT/'docs/evidence/asio-recreation-build.json').write_text(json.dumps(output, indent=2)+'\n', encoding='utf-8')
    print('Verified 40/40 Release and Debug, COM recreation audits and explicit source/runtime identity differences; native reacquisition remains open')


if __name__ == '__main__':
    main()
