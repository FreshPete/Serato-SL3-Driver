"""Bind the native control adapter and fake-transfer checks to current builds."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def text(path):
    return path.read_text(encoding='utf-8-sig')


def transfer(source):
    return source.split('struct Transfer {', 1)[1].split('struct NativeRateIo final:', 1)[0]


def main():
    native = text(ROOT/'src/windows/usbdk_main.cpp')
    adapter = text(ROOT/'src/windows/control_transfer_io.hpp')
    diagnostic = text(ROOT/'src/windows/control_selection_diagnostic.hpp')
    held = native.split('class NativeHeldDevice final:', 1)[1].split('int serve_native_device', 1)[0]
    interface = text(ROOT/'src/windows/device_session.hpp')
    require('using NativeControlDiagnostic=sl3::worker::ControlSelectionDiagnostic<Device,Transfer>;' in native
            and 'const auto result=controls_.inspect();' in held
            and 'supports_selection() const noexcept override' in held and 'select_control(' in held
            and 'if(controls_.enabled())throw' in held
            and 'virtual bool supports_selection() const noexcept{return false;}' in interface,
            'Native production selection admission differs')
    uses = {p.relative_to(ROOT).as_posix(): text(p).count('NativeControlsIo')
            for p in (ROOT/'src').rglob('*') if p.suffix in ('.cpp', '.hpp')
            and p.name not in ('control_transfer_io.hpp','control_baseline.hpp') and 'NativeControlsIo' in text(p)}
    require(uses == {'src/windows/control_selection_diagnostic.hpp': 1}, 'Native adapter caller inventory changed')
    require(native.count('control_baseline.invalidate();') == 2 and 'baseline_=io.take_baseline();' in diagnostic
            and 'Baseline&& baseline' in adapter and 'prepared,baseline_max_age_ms' in adapter
            and 'selection_->initial_controls()->raw!=reservation_->controls.raw' in adapter,
            'Baseline lifetime/freshness/table admission differs')
    require('bool attempted_=false;' in diagnostic and 'const bool ready=supported();attempted_=true;' in diagnostic
            and 'if(!ready || !matched)' in diagnostic and 'control::select_audio_control(io,' in diagnostic,
            'One-target/one-attempt native diagnostic admission differs')
    host=text(ROOT/'src/asio/host_session.cpp')
    require('if(spec_.diagnostic_control_target)return false;' in host
            and '--control-test-target' in host and 'spec_.diagnostic_directory.is_absolute()' in host
            and 'control_target && (!device_worker || startup_log.empty())' in native
            and 'diagnostic_control_target' not in text(ROOT/'src/asio/driver_configuration.cpp'),
            'Default configuration/journal/native diagnostic boundary changed')
    require('if(getter_sent_ || frame!=control::audio_controls_query().frame())' in adapter
            and 'if(!selection_->take_request(expected) || frame!=expected)' in adapter
            and 'completed-entered_>=budget_' in adapter,
            'Exact frame/deadline guard differs')
    old_folder = ROOT/'artifacts/build/checkpoints/selection-ipc-20261031'
    old_native = old_folder/'src/windows/usbdk_main.cpp'
    old_manifest = read(old_folder/'artifacts/build/native/native-build-Release.json')
    require(sha(old_native) == old_manifest['inputs']['src/windows/usbdk_main.cpp'].lower(), 'Old transfer reference differs')
    require(transfer(native) == transfer(text(old_native)), 'Production transfer retirement implementation changed')
    require('if(wait(2000)==sl3::Completion::pending)fail_stop()' in transfer(native), 'Drain/fail-stop guard absent')
    builds = {}
    for config in ('Release', 'Debug'):
        folder = ROOT/'artifacts/build/native'
        manifest = folder/f'native-build-{config}.json'
        build = read(manifest)
        for name, expected in build['inputs'].items():
            require(sha(ROOT/name) == expected.lower(), 'Build source differs: '+name)
        require(sha(ROOT/'scripts/build-native.ps1') == build['buildScriptSha256'].lower(), 'Build script differs')
        log = folder/f'ctest-{config}.log'
        require(sha(log) == build['ctestLogSha256'].lower()
                and '100% tests passed, 0 tests failed out of 40' in text(log), 'Full suite did not pass')
        executable = folder/config/'sl3_control_frames_tests.exe'
        worker = folder/config/'sl3_usbdk.exe'
        require(sha(executable) == build['controlFrames']['testExecutableSha256'].lower(), 'Adapter test binary differs')
        require(sha(worker) == build['usbdk']['executableSha256'].lower(), 'Worker binary differs')
        builds[config] = {'manifestSha256': sha(manifest), 'ctestLogSha256': sha(log), 'testsPassed': 40,
                          'adapterTestExecutableSha256': sha(executable), 'workerSha256': sha(worker)}
    sdk = ROOT/'analysis/selection-probe-sdk-free-ctest.log'
    require('100% tests passed, 0 tests failed out of 25' in text(sdk), 'SDK-free suite did not pass')
    rejection_path = ROOT/'analysis/selection-probe-prerequisite-rejection.json'
    rejection = read(rejection_path)
    require(rejection['accepted'] is False and rejection['error'] == 'Build/security mismatch'
            and rejection['workerSha256'] == builds['Release']['workerSha256'], 'Old hardware admission rejection differs')
    result = {
        'scope': 'Default getter-only production configuration and explicit single-target native diagnostic; fake positives and safe native negatives only',
        'adapterSha256': sha(ROOT/'src/windows/control_transfer_io.hpp'),
        'baselineOwnerSha256': sha(ROOT/'src/windows/control_baseline.hpp'),
        'baseline': {'moveOnly': True, 'sameLiveOwnerRequired': True, 'singleUse': True,
                     'maximumAgeBeforeSetterMilliseconds': 1500, 'fullInitialTableMatchBeforeSetter': True,
                     'recheckedAfterPreparation': True, 'audioActivationAndCloseInvalidate': True,
                     'persistedPermit': False, 'nativeSelectionEnabled': 'Explicit diagnostic target only'},
        'diagnosticSourceSha256': sha(ROOT/'src/windows/control_selection_diagnostic.hpp'),
        'diagnostic': {'nativeWorkerFlag': '--control-test-target', 'hostSpecField': 'diagnostic_control_target',
                       'defaultEnabled': False, 'freshJournalRequired': True, 'oneTarget': True,
                       'oneAttempt': True, 'audioStartRefused': True, 'hostProbeCliConnected': True,
                       'nativeSettingPhysicallyTested': False},
        'diagnosticTests': ['Same wrapper used by native device tested with fake transfers for default refusal, baseline admission and typed result',
                            'Different target, expired baseline and repeat attempt refuse without transfer; inspection cannot rearm',
                            'Parser round-trips all 54 canonical targets and rejects malformed ranges/strings',
                            'Actual simulated process capability changes after controls and is rechecked before repeat selection',
                            'Native standard/target-journal modes with absent helper and invalid mode/target/journal arguments',
                            'Host rejects non-native/non-retained/no-journal/invalid-target specs before launch and refuses audio'],
        'testSourceSha256': sha(ROOT/'tests/native/control_transfer_io_tests.hpp'),
        'builds': builds, 'sdkFreeTestsPassed': 25, 'sdkFreeLogSha256': sha(sdk),
        'productionTransferRetirementSourceUnchanged': True,
        'oldNativeReferenceSha256': sha(old_native),
        'selectedConstructorRuntimeCaller': True, 'nativeCapabilityEnabled': 'Explicit diagnostic after fresh getter only',
        'adapterRuntimeCallerInventory': uses,
        'oldHardwarePrerequisiteRejection': rejection,
        'oldHardwarePrerequisiteRejectionSha256': sha(rejection_path),
        'fakeTransferChecks': ['All 54 targets: inspect/set/readback and getter-only no-op',
                               'Every setter frame byte independently mutated and refused before native preparation',
                               'Setter before observation, read before request, invalid target and completed reuse refused',
                               'Failure/short/late completion at all six transfer boundaries',
                               'Native error preserved despite destructor changing GetLastError',
                               'Preparation consumes timeout; zero/excess timeout and clock regression refuse'],
        'baselineChecks': ['Unissued/wrong-owner/reused/expired/regressed tokens refuse before preparation',
                           'New observation and explicit invalidation revoke older tokens/reservations',
                           'Destroyed device cannot admit old token even with reused object storage',
                           'Full-table mismatch preserves observation/possible-write uncertainty without native setter submission',
                           'Expiry during inspection or setter preparation prevents submission',
                           'Timely setter may finish readback after baseline freshness interval',
                           'Fresh observed no-op remains write-free; malformed getter issues no token'],
        'limits': ['Fake transfers do not validate driver cancellation, hardware behaviour or physical settings',
                   'Production retirement code is unchanged, not newly exercised on hardware',
                   'Native setting probe CLI is diagnostic-only; no ASIO panel/deployed configuration or physical setting validation',
                   'Current-worker read-only baseline and supervised target/result/trace/recovery validation remain before a physical setting test',
                   'Safe reacquisition, analogue mapping, measured timing, sustained operation and current Serato/DVS remain incomplete'],
    }
    (ROOT/'docs/evidence/native-control-adapter.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified native single-target diagnostic admission, default getter-only configuration, unchanged retirement and fake-transfer tests')


if __name__ == '__main__':
    main()
