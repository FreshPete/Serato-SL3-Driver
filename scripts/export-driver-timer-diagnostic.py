"""Verify the isolated timer build and export software-only evidence. No device I/O."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'artifacts/build/timer-diagnostic'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def main():
    manifest_path = BUILD / 'native-build-Release.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    for name, expected in manifest['inputs'].items():
        require(sha(ROOT / name) == expected.lower(), f'Build input changed: {name}')
    require(sha(ROOT / 'scripts/build-native.ps1') == manifest['buildScriptSha256'].lower(), 'Build script changed')
    log = BUILD / 'ctest-Release.log'
    require(sha(log) == manifest['ctestLogSha256'].lower(), 'CTest log changed')
    text = log.read_text(encoding='utf-8-sig')
    passed = re.findall(r'Test\s+#\d+:\s+(\S+)\s+\.+\s+Passed\s', text)
    require(len(passed) == len(set(passed)) == len(manifest['ctestTests']) == 47
            and set(passed) == set(manifest['ctestTests'])
            and '100% tests passed, 0 tests failed out of 47' in text, 'Incomplete native test pass')
    executable = BUILD / 'Release/sl3_usbdk.exe'
    require(sha(executable) == manifest['usbdk']['executableSha256'].lower(), 'Worker changed')
    diagnostic = manifest['driverTimerDiagnostic']
    for name, field in (('sl3_driver_timer_query_tests.exe', 'queryTestExecutableSha256'),
                        ('sl3_driver_timer_io_tests.exe', 'adapterTestExecutableSha256')):
        require(sha(BUILD / 'Release' / name) == diagnostic[field].lower(), f'Test changed: {name}')
    require(diagnostic['nativeQueryRunDuringBuild'] is False
            and diagnostic['automaticStartupExchange'] is False
            and diagnostic['responseVerified'] is False
            and manifest['physicalCaptureTested'] is False, 'Unexpected physical evidence claim')
    plan_run = subprocess.run([str(executable), '--plan', '--challenge', '0123456789ABCDEF'],
                              capture_output=True, check=True, text=True, timeout=5)
    plan = json.loads(plan_run.stdout)
    require(plan == {'plan_only': True, 'helper_loaded': False, 'device_access': False,
                     'driver_changes': False, 'timer_command': '0x37', 'maximum_writes': 1,
                     'maximum_reads': 4, 'budget_ms': 1500, 'audio_submissions': 0,
                     'response_verified': False, 'challenge_hex': '0123456789abcdef'}, 'Unexpected timer plan')
    primary = ROOT / 'artifacts/build/checkpoints/native-controls-build-20261101'
    preserved = {
        'native-build-Release.json': '0d875f3d3e438e1f296cfc3b73e9f14c80b656df1e78bd0a8825a341461ab3da',
        'Release/sl3_usbdk.exe': '5fe2a44f1020032994c2b2e1a5ea868f87650caa9e23bc2077913760d0e88fe5',
        'Release/sl3_host_probe.exe': '6d876c8383992f298535e91eda3b5ffd3734c0e10829ecca39e038e24af61f8d',
    }
    for name, expected in preserved.items():
        require(sha(primary / name) == expected, f'Physical-capture build changed: {name}')
    cli_path = ROOT / 'analysis/driver-timer-cli-20261101.json'
    cli = json.loads(cli_path.read_text(encoding='utf-8'))
    require(cli['passed'] == len(cli['cases']) == 8 and cli['workerSha256'] == sha(executable)
            and cli['scriptSha256'] == sha(ROOT / 'scripts/test-driver-timer-cli.py')
            and cli['physicalTimerQueryTested'] is False, 'CLI evidence changed')
    result = {'scope': 'Isolated native timer diagnostic; software tests and actual plan only',
              'buildDirectory': str(BUILD.relative_to(ROOT)), 'manifestSha256': sha(manifest_path),
              'workerSha256': sha(executable), 'ctestLogSha256': sha(log), 'nativeTestsPassed': len(passed),
              'exporterSha256': sha(Path(__file__)), 'timerPlan': plan,
              'actualCliFailureCasesPassed': cli['passed'], 'cliRecordSha256': sha(cli_path),
              'cliScriptSha256': cli['scriptSha256'],
              'diagnostic': diagnostic, 'preservedPhysicalCaptureBuild': preserved,
              'preservedPhysicalCaptureDirectory': str(primary.relative_to(ROOT)),
              'physicalTimerQueryTested': False, 'currentSeratoAdmissionVerified': False,
              'limits': ['The transfer budget excludes device opening, cancellation/drain and redirect release.',
                         'A parsed reply is not key verification, safe reopening or current Serato admission.',
                         'The older physical controls pass does not validate this new executable.']}
    output = ROOT / 'docs/evidence/driver-timer-diagnostic-build.json'
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Verified 47 native tests, actual no-device timer plan and preserved physical-capture binaries')


if __name__ == '__main__':
    main()
