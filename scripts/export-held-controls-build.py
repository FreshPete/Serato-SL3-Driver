"""Bind held-device read-only control inspection to actual build/test records."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    builds = {}
    observer_refs = {}
    for configuration in ('Release', 'Debug'):
        folder = ROOT/'artifacts/build/native'
        manifest = folder/f'native-build-{configuration}.json'
        build = read(manifest)
        for name, expected in build['inputs'].items():
            require(sha(ROOT/name) == expected.lower(), 'Build input changed: '+name)
        require(sha(ROOT/'scripts/build-native.ps1') == build['buildScriptSha256'].lower(), 'Build script changed')
        feature = build['deviceSession']['controls']
        diagnostic = build['hostProbe']['controls']
        observer_refs[configuration]=diagnostic['stateObserverReferences']
        require(diagnostic['simulatedLifecyclePassed'] is True and diagnostic['nativeQueryRunDuringBuild'] is False
                and diagnostic['audioStartAttempts'] == 0 and diagnostic['getter'] == '0x32'
                and len(diagnostic['scriptInputs']) == 18, 'Controls diagnostic not tested/pinned')
        for name, expected in diagnostic['scriptInputs'].items():
            require(sha(ROOT/'scripts'/name) == expected.lower(), 'Controls diagnostic dependency changed: '+name)
        require(build['deviceSession']['protocolVersion'] == 3 and
                all(feature[k] is True for k in ('readOnly', 'explicitIdleHeldDeviceOnly', 'nativeQueryConnected',
                                               'hostApiConnected', 'simulatedInspectionAndFailureTestsPassed')) and
                feature['maximumWrites'] == 1 and feature['maximumReceivedFrames'] == 4 and
                feature['controlBudgetMilliseconds'] == 1500 and feature['physicalQueryRunDuringBuild'] is False,
                'Unexpected held-control scope or contract')
        log = folder/f'ctest-{configuration}.log'
        require(sha(log) == build['ctestLogSha256'].lower() and
                '100% tests passed, 0 tests failed out of 40' in log.read_text(encoding='utf-8-sig') and
                {'sl3_control_frames_tests', 'sl3_device_session_tests', 'sl3_retained_host_tests', 'sl3_controls_probe_lifecycle'} <= set(build['ctestTests']),
                'Required query/IPC/host checks did not pass')
        identities = {'sl3_control_frames_tests.exe': build['controlFrames']['testExecutableSha256'],
                      'sl3_device_session_tests.exe': build['deviceSession']['testExecutableSha256'],
                      'sl3_device_session_fixture.exe': build['deviceSession']['fixtureSha256'],
                      'sl3_retained_host_tests.exe': build['asioComponent']['hostSession']['retained']['testExecutableSha256'],
                      'sl3_usbdk.exe': build['usbdk']['executableSha256'],
                      'sl3_host_probe.exe': build['hostProbe']['executableSha256'],
                      'sl3_asio.dll': build['asioComponent']['comDllSha256']}
        for name, expected in identities.items():
            require(sha(folder/configuration/name) == expected.lower(), 'Tested binary changed: '+name)
        builds[configuration] = {'testsPassed': 40, 'manifestSha256': sha(manifest), 'logSha256': sha(log),
                                 'binaryHashes': identities, 'sourceHashes': build['inputs'], 'controlsScriptInputs': diagnostic['scriptInputs']}
    require(builds['Release']['sourceHashes'] == builds['Debug']['sourceHashes'], 'Build source sets differ')
    engine = (ROOT/'src/core/audio_controls_query.hpp').read_text(encoding='utf-8-sig')
    native = (ROOT/'src/windows/usbdk_main.cpp').read_text(encoding='utf-8-sig')
    host = (ROOT/'src/asio/host_session.cpp').read_text(encoding='utf-8-sig')
    require('Exchange exchange(audio_controls_query())' in engine and 'controls_budget_ms=1500' in engine
            and 'operation<=maximum_received_frames' in engine, 'Bounded fixed getter construction changed')
    adapter = (ROOT/'src/windows/control_transfer_io.hpp').read_text(encoding='utf-8-sig')
    require('if(getter_sent_ || frame!=control::audio_controls_query().frame())' in adapter
            and 'const auto result=controls_.inspect();' in native
            and 'Held control inspection requires idle device' in native
            and 'if(wait(2000)==sl3::Completion::pending)fail_stop()' in native, 'Native idle/getter/drain guard changed')
    method = host.split('HostSession::inspect_controls() noexcept {', 1)[1].split('\nbool HostSession::acquire_retained()', 1)[0]
    require(method.index('state_.io_retired=false;') < method.index('device_call(device_session::Command::controls')
            and '!quiescent()' in method and 'reentrant()' in method
            and 'device_session::Command::controls,{},5000' in method, 'Host admission/retirement handling changed')
    require('inspect_controls(' not in (ROOT/'src/asio/driver_facade.cpp').read_text(encoding='utf-8-sig'),
            'Automatic production-facade control queries need separate review')
    markers = sorted(set(re.findall(r'"(audio_controls(?:_write|_read)?\.(?:enter|return))"', native+adapter)))
    require(len(markers) == 6, 'Control journal stages differ')
    sdk = ROOT/'artifacts/build/native-without-sdk'
    cache = (sdk/'CMakeCache.txt').read_text(encoding='utf-8-sig')
    require('SL3_BUILD_ASIO_COMPONENT:BOOL=OFF' in cache and 'SL3_ASIO_SDK_ROOT:PATH=C:/definitely-absent-sl3-sdk' in cache
            and not Path('C:/definitely-absent-sl3-sdk').exists(), 'SDK-free isolation differs')
    sdk_log = ROOT/'analysis/selection-probe-sdk-free-ctest.log'
    require('100% tests passed, 0 tests failed out of 25' in sdk_log.read_text(encoding='utf-8-sig'), 'SDK-free tests failed')
    python_log = ROOT/'analysis/selection-probe-python-tests.log'
    text = python_log.read_text(encoding='utf-8-sig')
    require('Ran 140 tests' in text and text.rstrip().endswith('OK'), 'Python consistency/plan checks failed')
    capture_plan=ROOT/'analysis/live-state-capture-plan.json';context_plan=ROOT/'analysis/live-state-context-plan.json'
    preflight_path=ROOT/'analysis/live-state-capture-preflight.json';preflight=read(preflight_path)
    require(read(capture_plan)['withStateObserver'] is True and read(capture_plan)['realTimeDelivery'] is True and
            read(context_plan)['withStateObserver'] is True and read(context_plan)['launchesProbe'] is False,
            'Optional state-observer plans differ')
    require(observer_refs['Release']==observer_refs['Debug'] and preflight['valid'] is True and
            preflight['buildManifestSha256']==sha(ROOT/'artifacts/build/native/native-build-Release.json') and
            preflight['observerManifestSha256']==observer_refs['Release']['manifestSha256'].lower(),
            'Observer references/preflight differ')
    physical_path = ROOT/'docs/evidence/retained-physical-20261030.json'
    physical = read(physical_path)
    physical_worker = physical['retainedRun']['workerSha256']
    historical_path = ROOT/'analysis/held-controls-historical-prerequisites.json'
    rejection_path = ROOT/'analysis/control-selection-old-prerequisite-rejection.json'
    historical, rejection = read(historical_path), read(rejection_path)
    require(historical['valid'] is True and historical['workerSha256'] == physical_worker.lower()
            and rejection['valid'] is False and rejection['error'] == 'Build/security mismatch',
            'Historical/current prerequisite identity checks differ')
    output = {'scope': 'Bounded read-only held-device control query; simulated positive/native absent-helper tests only',
              'deviceProtocolVersion': 3, 'command': '0x305', 'wireGetter': '0x32', 'maximumWrites': 1,
              'maximumReads': 4, 'controlBudgetMs': 1500, 'cancellationDrainBudgetMs': 2000,
              'hostReplyBudgetMs': 5000, 'journalMarkers': markers, 'builds': builds,
              'sdkFree': {'testsPassed': 25, 'logSha256': sha(sdk_log)},
              'python': {'testsPassed': 140, 'logSha256': sha(python_log)},
              'physicalEvidenceReference': {'path': physical_path.relative_to(ROOT).as_posix(), 'sha256': sha(physical_path),
                                           'priorWorkerSha256': physical_worker,
                                           'currentWorkerMatchesPriorPhysical': builds['Release']['binaryHashes']['sl3_usbdk.exe'].lower() == physical_worker.lower(),
                                           'historicalPrerequisitesValidUnderOwnHash': True, 'rejectedForCurrentWorker': True,
                                           'historicalValidationSha256': sha(historical_path), 'currentRejectionSha256': sha(rejection_path)},
              'nativeQueryRunDuringBuild': False, 'nativeControlsPhysicallyValidated': False,
              'controlsProbePrepared': True, 'tracedRunnerPrepared': True,
              'splitUserContext': {'prepared': True, 'selfElevation': False, 'collectorLaunchesProbe': False,
                                   'parentProbeWorkerTokensRequired': True, 'liveCollectorIdentityRequired': True,
                                   'nativeOwnershipTestRun': False, 'testsSha256': sha(ROOT/'tests/test_controls_user_probe.py')},
              'optionalLifecycleTrace': {'flag': '-WithUsbDkLifecycle', 'sameUsbStackSession': True,
                                         'providerFlags': '0x650', 'selectedFormats': 32,
                                         'emissionVerified': False, 'physicalCaptureRunDuringBuild': False},
              'optionalLiveStateObserver': {'prepared': True, 'flag': '-WithStateObserver', 'enabledByDefault': False,
                                           'readerReferences': observer_refs['Release'], 'preflightSha256': sha(preflight_path),
                                           'capturePlanSha256': sha(capture_plan), 'contextPlanSha256': sha(context_plan),
                                           'validatorSourceSha256': sha(ROOT/'scripts/validate-usb-state-capture.py'),
                                           'syntheticTestsSha256': sha(ROOT/'tests/test_usb_state_capture.py'),
                                           'livePositiveValidated': False, 'readinessAdmission': False},
              'optionalUsbIdentity': {'flag': '-WithUsbIdentity', 'seconds': 45, 'intervalMilliseconds': 50,
                                      'completeBeforeAndAfterRequired': True, 'independentSupervisor': True,
                                      'heldDeviceCoverageVerified': False, 'seratoCoexistenceVerified': False,
                                      'physicalObservationRunDuringBuild': False},
              'controlsEvidenceTestsSha256': sha(ROOT/'tests/test_controls_probe_evidence.py'),
              'limits': ['A fresh explicit getter is framed/tag checked, without a USB transaction nonce or electrical calibration',
                         'Reply rate metadata is the preceding clock observation; this command does not query or change rate',
                         'Interleaved notifications count toward the query budget; this snapshot API does not dispatch their callbacks',
                         'No running-audio/callback controls, implicit acquisition, automatic refresh, setter, UI deployment or Serato integration added',
                         'Transfer retirement is separate from helper closure, Windows recovery and kernel reacquisition readiness',
                         'New worker/protocol needs fresh physical prerequisites; previous native passes retain their own hash bindings']}
    (ROOT/'docs/evidence/held-controls-build.json').write_text(json.dumps(output, indent=2)+'\n', encoding='utf-8')
    print('Verified bounded held controls, split-role preparation, 40/40/25 native suites and 140 Python checks; no physical control query')


if __name__ == '__main__':
    main()
