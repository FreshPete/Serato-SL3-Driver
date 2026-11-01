"""Bind offline timer comparison to original instructions and tested builds."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sl3_image', ROOT/'scripts/export-serato-clock-handshake-evidence.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference(challenge, key):
    # Variable-word reference follows the published corrected-block operation.
    # Only synthetic values are supplied; no vendor key is read here.
    words = list(struct.unpack('>2I', bytes.fromhex(challenge)))
    keys = struct.unpack('>4I', bytes.fromhex(key))
    total = 0
    previous = words[-1]
    for _ in range(6+52//len(words)):
        total = (total+0x9e3779b9) & 0xffffffff
        selection = (total>>2) & 3
        for position in range(len(words)):
            following = words[(position+1) % len(words)]
            operation = (((previous>>5) ^ (following<<2))+((following>>3) ^ (previous<<4))) ^ ((total^following)+(keys[(position & 3)^selection]^previous))
            words[position] = (words[position]+operation) & 0xffffffff
            previous = words[position]
    return struct.pack('>2I', *words).hex()


def main():
    app = h.Image('artifacts/extracted/Serato DJ Pro 2.5.5/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe', h.OLD_SHA)
    checks = (
        (0x140691a68, 'mov', 'edx, 8'), (0x140691a90, 'call', '0x14054f520'),
        (0x140691aa2, 'cmp', 'rcx, qword ptr [rsp + 0x88]'), (0x140691ab6, 'cmove', 'eax, edx'),
        (0x14054f27e, 'mov', 'eax, 0x34'), (0x14054f283, 'div', 'r9d'),
        (0x14054f29b, 'lea', 'esi, [rax + 6]'), (0x14054f2c0, 'add', 'r11d, 0x9e3779b9'),
        (0x14054f37e, 'jg', '0x14054f2c0'),
        (0x14054f565, 'movzx', 'eax, byte ptr [rsi + 3]'),
        (0x14054f569, 'mov', 'byte ptr [rdi], al'),
        (0x14054f579, 'movzx', 'eax, byte ptr [rsi]'),
        (0x14054f57c, 'mov', 'byte ptr [rdi + 3], al'),
        (0x14054f5ed, 'movzx', 'ecx, byte ptr [rdx + r14 + 3]'),
        (0x14054f65f, 'movzx', 'eax, byte ptr [rdx + rbx + 3]'),
    )
    assembly = []
    for va, opcode, operands in checks:
        row = app.at(va, opcode, operands)
        assembly.append(f'{va:x}: {row.mnemonic} {row.op_str}')
    h.require(app.rip(app.at(0x140691a7a, 'lea')) == 0x14054f250, 'Original transform callback changed')
    h.require(app.rip(app.at(0x140691a5a, 'lea')) == 0x144738040, 'Original key argument changed')
    focused_path = ROOT/'analysis/serato255-timer-transform-01.json'
    focused = json.loads(focused_path.read_text(encoding='utf-8-sig'))
    h.require(focused['binary_sha256'] == app.sha and all(row['complete'] and
              (int(row['start'], 16), int(row['end_exclusive'], 16)) in app.spans
              for row in focused['functions']), 'Focused original transform evidence differs')
    sources = ('src/core/timer_verification.hpp', 'src/core/timer_verification.cpp', 'tests/native/timer_verification_tests.cpp')
    callers = []
    for path in (ROOT/'src').rglob('*.cpp'):
        if path.name != 'timer_verification.cpp' and 'matches_driver_timer_reply(' in path.read_text():
            callers.append(path.relative_to(ROOT).as_posix())
    h.require(not callers, 'An unreviewed runtime verification caller was introduced')
    fixtures = (
        ('0000000000000000', '00000000000000000000000000000000', '053704ab575d8c80'),
        ('0001020304050607', '000102030405060708090a0b0c0d0e0f', '121a0f715f2550ed'),
        ('0123456789abcdef', '00112233445566778899aabbccddeeff', '34354989dd7d1a7a'),
        ('ffffffffffffffff', 'ffffffffffffffffffffffffffffffff', '09b03d2ab3560cb2'),
    )
    test_source = (ROOT/sources[-1]).read_text()
    for challenge, key, expected in fixtures:
        h.require(reference(challenge, key) == expected and all(v in test_source for v in (challenge, key, expected)), 'Synthetic reference fixture mismatch')
    builds = []
    for configuration in ('Release', 'Debug'):
        folder = ROOT/'artifacts/build/native'
        manifest = folder/f'native-build-{configuration}.json'
        build = json.loads(manifest.read_text(encoding='utf-8-sig'))
        for name, expected in build['inputs'].items():
            h.require(digest(ROOT/name).upper() == expected.upper(), 'Native input changed: '+name)
        h.require(digest(ROOT/'scripts/build-native.ps1').upper() == build['buildScriptSha256'].upper(), 'Build script changed')
        log = folder/f'ctest-{configuration}.log'
        h.require(digest(log).upper() == build['ctestLogSha256'].upper() and '100% tests passed, 0 tests failed out of 29' in log.read_text(), 'Incomplete native tests')
        h.require(len(build['ctestTests']) == 29 and 'sl3_timer_verification_tests' in build['ctestTests'], 'Missing verifier test')
        builds.append({'configuration': configuration, 'testsPassed': 29, 'manifestSha256': digest(manifest),
                       'ctestLogSha256': digest(log), 'timerTestSha256': digest(folder/configuration/'sl3_timer_verification_tests.exe')})
    sdk = ROOT/'artifacts/build/native-without-sdk'
    sdk_log = sdk/'ctest-timer-verification.log'
    cache = (sdk/'CMakeCache.txt').read_text()
    h.require('SL3_BUILD_ASIO_COMPONENT:BOOL=OFF' in cache and 'SL3_ASIO_SDK_ROOT:PATH=C:/definitely-absent-sl3-sdk' in cache, 'SDK-free configuration differs')
    h.require('100% tests passed, 0 tests failed out of 21' in sdk_log.read_text(), 'SDK-free tests incomplete')
    python_log = ROOT/'analysis/timer-python-tests.log'
    h.require('Ran 42 tests' in python_log.read_text() and python_log.read_text().rstrip().endswith('OK'), 'Python suite incomplete')
    report = {'generatedUtc': datetime.now(timezone.utc).isoformat(), 'scope': 'Offline parsed-reply comparison only',
              'originalApplicationSha256': app.sha, 'originalInstructionChecks': assembly,
              'focusedTransformReportSha256': digest(focused_path),
              'sourceSha256': {p: digest(ROOT/p) for p in sources}, 'syntheticReferenceVectors': len(fixtures),
              'nativeBuilds': builds, 'sdkFreeTestsPassed': 21, 'sdkFreeLogSha256': digest(sdk_log),
              'pythonTestsPassed': 42, 'pythonLogSha256': digest(python_log),
              'algorithmReference': 'https://www.cl.cam.ac.uk/ftp/users/djw3/xxtea.ps',
              'runtimeCallers': callers, 'vendorKeyEmbedded': False, 'deviceResponseEmitted': False,
              'physicalTimerExchangeTested': False, 'currentSeratoHandshakeImplemented': False,
              'limits': ['Synthetic vectors verify arithmetic and byte order, not firmware behavior',
                         'Caller supplies the appropriate key; no original key is read or redistributed by this verifier',
                         'An Event match does not establish physical provenance, product/account entitlement or audio readiness',
                         'No runtime/IPC/CLI hook, driver install, USB command or security change was introduced']}
    output = ROOT/'docs/evidence/timer-verification-build.json'
    output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
