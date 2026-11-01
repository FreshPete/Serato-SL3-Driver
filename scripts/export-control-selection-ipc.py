"""Bind idle-only setting IPC/host tests and diagnostic-only native wiring."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def require(value,reason):
    if not value:raise ValueError(reason)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    expected={'testsPassed':True,'protocolVersion':3,'command':'0x306','workerWatchdogMilliseconds':7500,
              'hostReplyMilliseconds':8000,'idleHeldOnly':True,'capabilityRequired':True,'hostApiConnected':True,
              'simulatedProcessTestsPassed':True,'nativeAdapterConnected':True,'nativeDiagnosticOnly':True,
              'nativeSingleTarget':True,'nativeAudioStartRefused':True,'physicalSettingsTested':False}
    builds={}
    for config in ('Release','Debug'):
        folder=ROOT/'artifacts/build/native';manifest=folder/f'native-build-{config}.json';build=read(manifest)
        require(build['controlSelectionIpc']==expected and build['deviceSession']['protocolVersion']==3,'Selection IPC feature differs')
        for name,digest in build['inputs'].items():require(sha(ROOT/name)==digest.lower(),'Build source differs: '+name)
        require(sha(ROOT/'scripts/build-native.ps1')==build['buildScriptSha256'].lower(),'Build script differs')
        log=folder/f'ctest-{config}.log'
        require(sha(log)==build['ctestLogSha256'].lower() and '100% tests passed, 0 tests failed out of 40' in log.read_text(encoding='utf-8-sig') and
                {'sl3_device_session_tests','sl3_retained_host_tests','sl3_controls_probe_lifecycle'}<=set(build['ctestTests']),'Required IPC/host suites failed')
        binaries={'sl3_device_session_tests.exe':build['deviceSession']['testExecutableSha256'],
                  'sl3_device_session_fixture.exe':build['deviceSession']['fixtureSha256'],
                  'sl3_retained_host_tests.exe':build['asioComponent']['hostSession']['retained']['testExecutableSha256'],
                  'sl3_usbdk.exe':build['usbdk']['executableSha256'],'sl3_asio.dll':build['asioComponent']['comDllSha256'],
                  'sl3_host_probe.exe':build['hostProbe']['executableSha256']}
        for name,digest in binaries.items():require(sha(folder/config/name)==digest.lower(),'Tested binary differs: '+name)
        builds[config]={'testsPassed':40,'manifestSha256':sha(manifest),'ctestLogSha256':sha(log),'binaries':binaries}
    native=(ROOT/'src/windows/usbdk_main.cpp').read_text(encoding='utf-8-sig')
    held=native.split('class NativeHeldDevice final:',1)[1].split('int serve_native_device',1)[0]
    interface=(ROOT/'src/windows/device_session.hpp').read_text(encoding='utf-8-sig')
    adapter=(ROOT/'src/windows/control_transfer_io.hpp').read_text(encoding='utf-8-sig')
    require('supports_selection() const noexcept override' in held and 'select_control(' in held and
            'virtual bool supports_selection() const noexcept{return false;}' in interface and
            'if(getter_sent_ || frame!=control::audio_controls_query().frame())' in adapter and
            'const auto result=controls_.inspect();' in held and 'if(controls_.enabled())throw' in held,'Native diagnostic selection guard changed')
    worker=(ROOT/'src/windows/device_session.cpp').read_text(encoding='utf-8-sig')
    require('if(!snapshot_.selection_supported || !device_->supports_selection())' in worker and
            'snapshot_.selection_supported=device_->supports_selection();' in worker and
            'timeouts_.startup_ms,protocol::selection_watchdog_ms' in worker and
            'protocol::encode_selection({snapshot_,outcome})' in worker,'Worker admission/result/watchdog contract changed')
    host=(ROOT/'src/asio/host_session.cpp').read_text(encoding='utf-8-sig')
    method=host.split('ControlSelectionReport HostSession::select_control(',1)[1].split('bool HostSession::acquire_retained()',1)[0]
    require('!quiescent()' in method and '!state_.device_snapshot.selection_supported' in method and
            method.index('state_.io_retired=false;')<method.index('device_call(') and
            'result.outcome_unknown=true;result.device_may_have_changed=true;' in method and
            'device_session::selection_reply_ms' in method and
            method.index('result.outcome=value.outcome')<method.index('usable_=false;close()'),'Host uncertainty/cleanup result contract changed')
    require('select_control(' not in (ROOT/'src/asio/driver_facade.cpp').read_text(encoding='utf-8-sig'),
            'Selection became an implicit production ASIO operation')
    sdk_log=ROOT/'analysis/selection-probe-sdk-free-ctest.log';python_log=ROOT/'analysis/selection-probe-python-tests.log'
    require('100% tests passed, 0 tests failed out of 25' in sdk_log.read_text(encoding='utf-8-sig'),'SDK-free suite failed')
    py=python_log.read_text(encoding='utf-8-sig');require('Ran 140 tests' in py and py.rstrip().endswith('OK'),'Python suite failed')
    rejected_path=ROOT/'analysis/selection-probe-prerequisite-rejection.json';rejected=read(rejected_path)
    require(rejected['workerSha256'].lower()==builds['Release']['binaries']['sl3_usbdk.exe'].lower() and
            rejected['validatorSha256'].lower()==sha(ROOT/'scripts/validate-retained-host-probe.py') and
            rejected['exitCode']==1 and rejected['expectedRateHz']==44100 and
            rejected['result']=={'valid':False,'error':'Build/security mismatch'},'Current-worker old-prerequisite rejection differs')
    result={'scope':'Real process IPC/host tests with simulated device; native target diagnostic connected, no physical setting test',
            'feature':expected,'builds':builds,'sdkFree':{'testsPassed':25,'logSha256':sha(sdk_log)},
            'python':{'testsPassed':140,'logSha256':sha(python_log)},
            'testSources':{name:sha(ROOT/name) for name in ('tests/native/device_session_tests.cpp','tests/native/device_session_fixture.cpp','tests/native/retained_host_tests.cpp')},
            'operationEvidenceSeparateFromFinalRelease':True,'lostReplyPreservesPossibleWrite':True,
            'historicalPrerequisitesRejected':{'workerSha256':rejected['workerSha256'].lower(),'recordSha256':sha(rejected_path)},
            'capabilityRequired':True,'nativeSelectionSupported':'Explicit single-target diagnostic after fresh baseline only','automaticAsioSelection':False,
            'physicalSettingRun':False,'limits':['Setting probe CLI positives are simulated; no panel, deployment or physical control write tested',
                'Version 2 retained workers/results are incompatible with this version 3 protocol',
                'The 5.5-second fixture dispatch delay validates reply policy, not native transfer/drain timing',
                'Real control baseline, native end-to-end budget/cleanup and routing/level verification remain required']}
    (ROOT/'docs/evidence/control-selection-ipc.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Verified protocol-v3 idle/capability selection IPC, dynamic admission and diagnostic-only native wiring; no physical settings run')


if __name__=='__main__':main()
