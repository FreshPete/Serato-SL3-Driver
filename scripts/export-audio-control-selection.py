"""Verify offline indexed setting selection against original driver bytes."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('selection_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
require = helper.require


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    driver = helper.Image('artifacts/extracted/rane-windows/x64/RaneAsioSL3.dll', helper.DRIVER_SHA)
    kernel = helper.Image('artifacts/extracted/rane-windows/x64/strmdrv.sys',
                          'e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5')
    instructions = []
    checks = [
        (driver, 0x180007611, 'movsxd', 'rsi, r9d'), (driver, 0x180007614, 'mov', 'rdi, r8'),
        (driver, 0x180007617, 'mov', 'ebx, edx'),
        (driver, 0x180007630, 'lea', 'rcx, [rsp + 0x42]'),
        (driver, 0x18000763a, 'mov', 'r8, rsi'), (driver, 0x18000763d, 'mov', 'rdx, rdi'),
        (driver, 0x18000764f, 'mov', 'byte ptr [rsp + 0x41], sil'),
        (driver, 0x180007670, 'mov', 'byte ptr [rsp + 0x40], bl'),
        (driver, 0x180007674, 'call', '0x180189e40'),
        (driver, 0x180007679, 'xor', 'ebx, ebx'),
        (driver, 0x18000767b, 'lea', 'r9, [rsp + 0x40]'),
        (driver, 0x180007683, 'lea', 'edx, [rbx + 3]'),
        (driver, 0x180007686, 'lea', 'r8d, [rbx + 1]'),
        (driver, 0x18000768f, 'call', '0x180009ac0'),
        (driver, 0x180007699, 'test', 'al, al'), (driver, 0x18000769b, 'sete', 'bl'),
        (driver, 0x1800076a3, 'mov', 'eax, ebx'),
        (kernel, 0x1210d, 'mov', 'edi, 1'), (kernel, 0x12112, 'cmp', 'dword ptr [rdx + 4], edi'),
        (kernel, 0x12117, 'mov', 'eax, dword ptr [rdx]'),
        (kernel, 0x12130, 'lea', 'r13d, [rdi + 1]'), (kernel, 0x12134, 'sub', 'eax, r13d'),
        (kernel, 0x1213d, 'sub', 'eax, edi'), (kernel, 0x1213f, 'je', '0x1219f'),
        (kernel, 0x121a5, 'lea', 'r8, [rdx + 8]'), (kernel, 0x121a9, 'mov', 'dl, 0x33'),
        (kernel, 0x121ab, 'call', '0x116a0'), (kernel, 0x121b8, 'mov', 'r9d, r13d'),
        (kernel, 0x121c3, 'mov', 'dl, 0x33'), (kernel, 0x121c5, 'jmp', '0x120b5'),
        (kernel, 0x120c1, 'call', '0x118c4'),
        (kernel, 0x1175c, 'xor', 'edx, edx'), (kernel, 0x1175e, 'lea', 'r8d, [rdx + 0x40]'),
        (kernel, 0x11762, 'call', '0x143b0'), (kernel, 0x1176c, 'mov', 'r8d, 0x3b'),
        (kernel, 0x116e2, 'mov', 'rdi, r8'), (kernel, 0x116e5, 'mov', 'sil, dl'),
        (kernel, 0x1177a, 'mov', 'rdx, rdi'),
        (kernel, 0x11772, 'mov', 'byte ptr [r11], sil'),
        (kernel, 0x1177d, 'mov', 'dword ptr [rax + 1], 0x100c51c'),
        (kernel, 0x11789, 'add', 'rcx, 5'), (kernel, 0x1178d, 'call', '0x144b0'),
    ]
    for image, va, opcode, operands in checks:
        row = image.at(va, opcode, operands)
        instructions.append({'binary': 'ASIO' if image is driver else 'kernel', 'va': hex(va),
                             'bytes': row.bytes.hex(), 'instruction': opcode+' '+operands})
    contract_path = ROOT/'docs/evidence/audio-controls-contract.json'
    contract = read(contract_path)
    require(contract['inputFields'] == [{'phono': 0, 'sensitivity': 3, 'through': 8},
                                       {'phono': 1, 'sensitivity': 9, 'through': 14},
                                       {'phono': 2, 'sensitivity': 15, 'through': 20}]
            and contract['sensitivity']['originalUiCodes'] == [0, 15], 'Original UI contract differs')
    builds = {}
    for configuration in ('Release', 'Debug'):
        folder = ROOT/'artifacts/build/native'
        path = folder/f'native-build-{configuration}.json';build = read(path)
        for name, expected in build['inputs'].items():
            require(sha(ROOT/name) == expected.lower(), 'Build source differs: '+name)
        require(sha(ROOT/'scripts/build-native.ps1') == build['buildScriptSha256'].lower(), 'Build script differs')
        log = folder/f'ctest-{configuration}.log'
        require(sha(log) == build['ctestLogSha256'].lower() and '100% tests passed, 0 tests failed out of 40' in log.read_text(encoding='utf-8-sig'), 'Native suite failed')
        executable = folder/configuration/'sl3_control_frames_tests.exe'
        require(sha(executable) == build['controlFrames']['testExecutableSha256'].lower(), 'Test binary differs')
        feature = build['controlSelectionIo']
        require(feature == {'injectedIoTestsPassed': True, 'budgetMilliseconds': 4500,
                            'maximumWrites': 3, 'maximumReads': 12, 'maximumSetters': 1,
                            'runtimeAdapterConnected': True, 'physicalSettingsTested': False,
                            'testExecutableSha256': build['controlFrames']['testExecutableSha256']},
                'Injected selection I/O feature differs')
        require(build['controlSelectionWire'] == {'testsPassed': True, 'version': 1, 'requestBytes': 24, 'replyBytes': 132,
                    'targetCorrelationRequired': True, 'optionalFieldsCanonical': True, 'workerCommandConnected': True,
                    'physicalSettingsTested': False, 'testExecutableSha256': build['controlFrames']['testExecutableSha256']},
                'Control selection evidence codec differs')
        builds[configuration] = {'testsPassed': 40, 'manifestSha256': sha(path), 'logSha256': sha(log),
                                 'controlTestSha256': sha(executable), 'workerSha256': build['usbdk']['executableSha256']}
    runtime_callers = [p.relative_to(ROOT).as_posix() for p in (ROOT/'src').rglob('*.cpp')
                       if 'AudioControlSelection' in p.read_text(encoding='utf-8-sig') or
                       'audio_control_selection.hpp' in p.read_text(encoding='utf-8-sig')]
    require(not runtime_callers, 'Unexpected direct selection-engine implementation caller')
    io_callers = [p.relative_to(ROOT).as_posix() for p in (ROOT/'src').rglob('*')
                  if p.suffix in ('.cpp','.hpp') and p.name!='audio_control_selection_io.hpp'
                  and 'select_audio_control(' in p.read_text(encoding='utf-8-sig')]
    require(io_callers==['src/windows/control_selection_diagnostic.hpp'], 'Selection I/O diagnostic caller differs')
    wire_callers = [p.relative_to(ROOT).as_posix() for p in (ROOT/'src').rglob('*.cpp')
                    if 'selection_wire::' in p.read_text(encoding='utf-8-sig') or
                    'audio_control_selection_wire.hpp' in p.read_text(encoding='utf-8-sig')]
    require(set(wire_callers)=={'src/core/device_session_protocol.cpp','src/windows/device_session.cpp','src/asio/host_session.cpp','src/windows/usbdk_main.cpp','src/windows/host_probe_main.cpp'},
            'Selection evidence codec runtime callers differ')
    native = (ROOT/'src/windows/usbdk_main.cpp').read_text(encoding='utf-8-sig')
    adapter = (ROOT/'src/windows/control_transfer_io.hpp').read_text(encoding='utf-8-sig')
    require('if(getter_sent_ || frame!=control::audio_controls_query().frame())' in adapter
            and 'const auto result=controls_.inspect();' in native, 'Native getter-only inspection changed')
    sdk_log = ROOT/'analysis/selection-probe-sdk-free-ctest.log'
    require('100% tests passed, 0 tests failed out of 25' in sdk_log.read_text(encoding='utf-8-sig'), 'SDK-free checks failed')
    result = {'scope': 'Original-byte contract and tested native diagnostic-only selection wiring; no physical setting test',
              'asioSha256': driver.sha, 'kernelSha256': kernel.sha, 'checkedInstructions': instructions,
              'originalUiContractSha256': sha(contract_path), 'builds': builds,
              'selectionSourceSha256': sha(ROOT/'src/core/audio_control_selection.hpp'),
              'selectionIoSourceSha256': sha(ROOT/'src/core/audio_control_selection_io.hpp'),
              'selectionWireSourceSha256': sha(ROOT/'src/core/audio_control_selection_wire.hpp'),
              'selectionWire': {'version': 1, 'requestBytes': 24, 'replyBytes': 132, 'exactTargetRequired': True,
                                'initialObservedVerifiedAndReceiptDistinct': True, 'nativeErrorPreserved': True,
                                'workerCommandConnected': True, 'nativeAdapterConnected': True, 'nativeDiagnosticOnly': True,
                                'deviceOwnershipProved': False, 'runtimeCallers': wire_callers},
              'selectionIo': {'totalBudgetMilliseconds': 4500, 'maximumTransfers': 15,
                              'maximumSetterAttempts': 1, 'runtimeCallers': io_callers,
                              'cancellationAfterWritePreservesUncertainty': True,
                              'lateReadbackCannotVerify': True, 'automaticRetry': False, 'rollback': False},
              'selectionTestSha256': sha(ROOT/'tests/native/control_frames_tests.cpp'),
              'sdkFree': {'testsPassed': 25, 'logSha256': sha(sdk_log),
                          'controlTestSha256': sha(ROOT/'artifacts/build/native-without-sdk/Release/sl3_control_frames_tests.exe')},
              'allowedSettings': {'sensitivity': {'indexes': [3, 9, 15], 'codes': [0, 15]},
                                  'through': {'indexes': [8, 14, 20], 'codes': [0, 1]}},
              'maximumRequests': 3, 'maximumReceivedFrames': 12, 'acknowledgementBytes': 2,
              'acknowledgementValuesInterpreted': False, 'runtimeCallers': runtime_callers,
              'limits': ['Phono switches, other table bytes and physical jack order are not writable contracts',
                         'Byte readback is not calibration, routing or analogue validation; the ABI has no transaction nonce',
                         'Any future native owner must enforce idle exclusivity, wall-clock/cancellation/drain budgets and recovery',
                         'No retry, rollback, physical native write, panel deployment or Serato integration tested; explicit native diagnostic target only']}
    (ROOT/'docs/evidence/audio-control-selection.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('Verified original indexed setter/opaque receipt and diagnostic-only native setting engine; no physical setting test')


if __name__ == '__main__':
    main()
