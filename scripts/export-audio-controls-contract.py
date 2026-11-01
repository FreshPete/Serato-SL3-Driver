"""Verify original SL3 control-table consumers and tested read-only C++ views."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('controls_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
require = helper.require


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    driver = helper.Image('artifacts/extracted/rane-windows/x64/RaneAsioSL3.dll', helper.DRIVER_SHA)
    kernel = helper.Image('artifacts/extracted/rane-windows/x64/strmdrv.sys',
                          'e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5')
    checks = [
        (0x1800047de, 'xor', 'edx, edx'), (0x1800047e6, 'xor', 'eax, eax'),
        (0x1800047eb, 'lea', 'r9d, [rax + 0x16]'),
        (0x180004806, 'call', 'qword ptr [rip + 0x20ce14]'),
        (0x18000481d, 'lea', 'rsi, [rip + 0x1b12e4]'),
        (0x180004830, 'movsxd', 'rax, dword ptr [rsi - 8]'),
        (0x18000483b, 'cmp', 'byte ptr [rsp + rax + 0x40], 0'),
        (0x180004846, 'movsxd', 'rax, dword ptr [rsi]'),
        (0x180004849, 'cmp', 'byte ptr [rsp + rax + 0x40], 0'),
        (0x180004856, 'movsxd', 'rax, dword ptr [rsi - 4]'),
        (0x18000485a, 'movzx', 'ecx, byte ptr [rsp + rax + 0x40]'),
        (0x180004877, 'mulss', 'xmm6, dword ptr [rip + 0x1b1d91]'),
        (0x18000487f, 'addss', 'xmm6, dword ptr [rip + 0x1b1d95]'),
        (0x18000488f, 'lea', 'rdx, [rip + 0x1b19da]'),
        (0x1800048a5, 'add', 'rsi, 0x30'), (0x1800048ad, 'cmp', 'ebp, 3'),
        (0x180003830, 'lea', 'rdi, [rip + 0x1b22d1]'),
        (0x1800038e6, 'mov', 'edx, dword ptr [rdi]'),
        (0x1800038f6, 'mov', 'r9d, 1'), (0x1800038fc, 'mov', 'byte ptr [rbp - 0x58], 1'),
        (0x180003900, 'call', 'qword ptr [rip + 0x20dd22]'),
        (0x18000395d, 'mov', 'edx, dword ptr [rdi]'),
        (0x180003953, 'mov', 'r14d, 1'), (0x18000396d, 'mov', 'r9d, r14d'),
        (0x180003970, 'mov', 'byte ptr [rbp - 0x58], 0'),
        (0x180003974, 'call', 'qword ptr [rip + 0x20dcae]'),
        (0x1800039c0, 'add', 'rdi, 0x30'), (0x1800039c8, 'cmp', 'r15d, 3'),
        (0x180001cd7, 'xor', 'esi, esi'), (0x180001d28, 'mov', 'r14d, esi'),
        (0x180001dd4, 'mulss', 'xmm0, dword ptr [rip + 0x1b4834]'),
        (0x180001ddc, 'addss', 'xmm0, dword ptr [rip + 0x1b4838]'),
        (0x180001dec, 'lea', 'rdx, [rip + 0x1b44fd]'),
        (0x180001e1e, 'mov', 'edx, 0x143'),
        (0x180001e27, 'call', 'qword ptr [rip + 0x1b32eb]'),
        (0x180002044, 'inc', 'r14d'), (0x180002047, 'cmp', 'r14d, 0xf'),
        (0x180002052, 'jle', '0x180001d30'),
        (0x1800019ce, 'mov', 'edx, 0x147'),
        (0x1800019dc, 'call', 'qword ptr [rip + 0x1b3736]'),
        (0x180001a69, 'lea', 'rax, [rsi + rsi*2]'), (0x180001a6d, 'add', 'rax, rax'),
        (0x180001a70, 'mov', 'r9d, 1'),
        (0x180001a79, 'mov', 'edx, dword ptr [r14 + rax*8 + 0x1b5b04]'),
        (0x180001a81, 'call', 'qword ptr [rip + 0x20fba1]'),
        (0x1800046bf, 'lea', 'rdx, [rip - 0x2c6]'),
        (0x1800046c9, 'call', 'qword ptr [rip + 0x20cf61]'),
        (0x1800046cf, 'lea', 'rdx, [rip - 0x1b6]'),
        (0x1800046d9, 'call', 'qword ptr [rip + 0x20cf69]'),
        (0x180007757, 'mov', 'qword ptr [rbx + 0x48], rdi'),
        (0x180007da7, 'mov', 'qword ptr [rbx + 0x50], rdi'),
        (0x18000e90a, 'movzx', 'eax, byte ptr [rdx + 0x389]'),
        (0x18000e915, 'movzx', 'eax, byte ptr [rdx + 0x38a]'),
        (0x18000e920, 'movzx', 'eax, byte ptr [rdx + 0x38b]'),
        (0x18000e92b, 'call', 'qword ptr [r8 + 0x48]'),
        (0x18000e9ce, 'movzx', 'eax, byte ptr [rdx + 0x390]'),
        (0x18000e9ef, 'movzx', 'eax, byte ptr [rdx + 0x393]'),
        (0x18000e9fa, 'call', 'qword ptr [r8 + 0x50]'),
    ]
    evidence = []
    for va, mnemonic, operands in checks:
        row = driver.at(va, mnemonic, operands)
        evidence.append({'va': hex(va), 'bytes': bytes(row.bytes).hex(), 'instruction': f'{mnemonic} {operands}'})
    table = [struct.unpack('<3I', driver.data(0x1801b5b00+i*0x30, 12)) for i in range(3)]
    require(table == [(0, 3, 8), (1, 9, 14), (2, 15, 20)], 'Original table interpretation changed')
    require(driver.rip(driver.at(0x18000481d)) == driver.rip(driver.at(0x180003830)) == 0x1801b5b08,
            'Read and through-write table bases differ')
    for slot, target in [(0x180211620, 0x1800074f0), (0x180211628, 0x1800075f0),
                         (0x180211630, 0x180007730), (0x180211648, 0x180007d80)]:
        require(struct.unpack('<Q', driver.data(slot, 8))[0] == target, 'Original export pointer differs')
    require(driver.rip(driver.at(0x1800046bf)) == 0x180004400
            and driver.rip(driver.at(0x1800046cf)) == 0x180004520, 'UI callback addresses differ')
    require(driver.text(driver.rip(driver.at(0x180004483))) == 'Phono switch callback (%d, %d, %d)'
            and driver.text(driver.rip(driver.at(0x1800045a3))) == 'Thru state callback (%d, %d, %d)',
            'Original callback labels differ')
    require(driver.text(driver.rip(driver.at(0x180001dec))) == '%.1f mV', 'Combo sensitivity units differ')
    require(driver.data(driver.rip(driver.at(0x18000488f)), 16).decode('utf-16le') == '%.1f mV\0',
            'Readback sensitivity label differs')
    for mul, add in [(0x180001dd4, 0x180001ddc), (0x180004877, 0x18000487f)]:
        require(struct.unpack('<f', driver.data(driver.rip(driver.at(mul)), 4))[0] == 0.5
                and struct.unpack('<f', driver.data(driver.rip(driver.at(add)), 4))[0] == 2.5, 'UI scale differs')
    driver.pe.parse_data_directories(directories=[0, 1])
    exports = {e.name.decode(): driver.base+e.address for e in driver.pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
    require(all(exports[name] == address for name, address in [('sl3_get_audio_controls', 0x1800074f0),
                ('sl3_set_audio_controls', 0x1800075f0), ('sl3_set_phonoswitch_callback', 0x180007730),
                ('sl3_set_thrustate_callback', 0x180007d80)]), 'Named exports differ')
    imports = {e.address: (d.dll.decode(), e.name.decode() if e.name else '')
               for d in driver.pe.DIRECTORY_ENTRY_IMPORT for e in d.imports}
    require(imports[driver.rip(driver.at(0x1800019dc))] == ('USER32.dll', 'SendMessageA')
            and driver.rip(driver.at(0x180001e27)) == driver.rip(driver.at(0x1800019dc)), 'Combo messages use a different import')
    # Fully decoded original leaf, previously recovered at this explicit extent.
    leaf = list(kernel.dis.disasm(kernel.data(0x115c0, 0xd8), 0x115c0))
    require(leaf[0].address == 0x115c0 and leaf[-1].address+leaf[-1].size == 0x11698, 'Kernel notification leaf extent differs')
    by_va = {row.address: row for row in leaf}
    for va, mnemonic, operands in [(0x115c5, 'cmp', 'al, 0x38'), (0x115c9, 'cmp', 'dword ptr [rdx + 1], 0x2000000'),
            (0x115dd, 'mov', 'word ptr [r8 + 0x389], ax'), (0x115e8, 'mov', 'byte ptr [r8 + 0x38b], al'),
            (0x11656, 'cmp', 'al, 0x39'), (0x1165a, 'cmp', 'dword ptr [rdx + 1], 0x3000000'),
            (0x1166d, 'mov', 'dword ptr [rcx + 0x390], eax')]:
        row = by_va[va]
        require(row.mnemonic == mnemonic and row.op_str == operands, 'Kernel notification link changed')
        evidence.append({'va': hex(va), 'bytes': bytes(row.bytes).hex(), 'instruction': f'{mnemonic} {operands}', 'image': 'kernel'})
    windows = Path('C:/Program Files (x86)/Windows Kits/10/Include/10.0.19041.0/um/WinUser.h')
    sdk = windows.read_text(encoding='utf-8-sig')
    require('#define CB_ADDSTRING                0x0143' in sdk and '#define CB_GETCURSEL                0x0147' in sdk,
            'SDK combo message values differ')
    builds = {}
    for config in ('Release', 'Debug'):
        folder = ROOT/'artifacts/build/native'
        manifest = folder/f'native-build-{config}.json'
        build = json.loads(manifest.read_text(encoding='utf-8-sig'))
        for name, expected in build['inputs'].items():
            require(sha(ROOT/name) == expected.lower(), 'Stale build input '+name)
        require('src/core/audio_controls.hpp' in build['inputs'] and 'sl3_control_frames_tests' in build['ctestTests'],
                'New view missing from tested build')
        log = folder/f'ctest-{config}.log'
        require(sha(log) == build['ctestLogSha256'].lower()
                and '100% tests passed, 0 tests failed out of 40' in log.read_text(encoding='utf-8-sig'), 'Build checks incomplete')
        executable = folder/config/'sl3_control_frames_tests.exe'
        require(sha(executable) == build['controlFrames']['testExecutableSha256'].lower(), 'Test executable changed')
        builds[config] = {'testsPassed': 40, 'manifestSha256': sha(manifest), 'ctestLogSha256': sha(log),
                          'controlTestSha256': sha(executable)}
    callers = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT/'src').rglob('*')
                     if p.suffix in ('.cpp','.hpp') and p.name!='audio_controls_query.hpp'
                     and 'inspect_audio_controls(' in p.read_text(encoding='utf-8-sig'))
    require(callers == ['src/windows/control_selection_diagnostic.hpp'], 'Runtime control-query caller inventory needs review')
    sdk_free = ROOT/'artifacts/build/native-without-sdk'
    cache = (sdk_free/'CMakeCache.txt').read_text(encoding='utf-8-sig')
    require('SL3_BUILD_ASIO_COMPONENT:BOOL=OFF' in cache
            and 'SL3_ASIO_SDK_ROOT:PATH=C:/definitely-absent-sl3-sdk' in cache
            and not Path('C:/definitely-absent-sl3-sdk').exists(), 'SDK-free boundary differs')
    sdk_log = ROOT/'analysis/selection-probe-sdk-free-ctest.log'
    require('100% tests passed, 0 tests failed out of 25' in sdk_log.read_text(encoding='utf-8-sig'),
            'Updated SDK-free suite failed')
    output = {'scope': 'Original binary control-table recovery, typed views and explicit held-query caller inventory; no new physical query',
              'asioSha256': driver.sha, 'kernelSha256': kernel.sha, 'instructions': evidence,
              'tableVa': '0x1801b5b00', 'tableStride': 48, 'inputFields': [{'phono': p, 'sensitivity': s, 'through': t} for p, s, t in table],
              'sensitivity': {'originalUiCodes': [0, 15], 'displayTenthsMv': '25 + 5*code', 'measuredCalibration': False},
              'notifications': {'0x38': {'callback': 'sl3_set_phonoswitch_callback', 'bytes': 3},
                                '0x39': {'callback': 'sl3_set_thrustate_callback', 'bytes': 4, 'fourthByteMeaning': 'unestablished'}},
              'sdkHeaderSha256': sha(windows), 'builds': builds,
              'sdkFree': {'testsPassed': 25, 'sdkAbsent': True, 'logSha256': sha(sdk_log),
                          'controlTestSha256': sha(sdk_free/'Release/sl3_control_frames_tests.exe')},
              'viewSourceSha256': sha(ROOT/'src/core/audio_controls.hpp'),
              'viewTestSourceSha256': sha(ROOT/'tests/native/control_frames_tests.cpp'),
              'runtimeQueryCallers': callers, 'explicitHeldQueryConnected': True, 'physicalQueryRunDuringBuild': False,
              'limits': ['Original UI range/display is not hardware calibration, measured gain or guaranteed electrical behavior',
                         'Physical jack order and switch polarity remain unverified',
                         'Unknown table fields and fourth through-notification byte remain opaque',
                         'Opt-in native setting diagnostic is separate evidence; controls command remains read-only and no control panel is deployed',
                         'Earlier silent transport passes are separate, hash-pinned physical evidence; no new native test ran']}
    (ROOT/'docs/evidence/audio-controls-contract.json').write_text(json.dumps(output, indent=2)+'\n', encoding='utf-8')
    print('Verified original control table, mV UI scale and notification links; read-only views pass both 40-test configurations')


if __name__ == '__main__':
    main()
