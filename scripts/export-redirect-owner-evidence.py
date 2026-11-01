"""Verify native redirect-overlap exclusion software evidence; no device/helper access."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def require(value, reason):
    if not value:
        raise ValueError(reason)


def main():
    build_dir = ROOT / 'artifacts/build/native'
    manifest_path = build_dir / 'native-build-Release.json'
    manifest = read(manifest_path)
    for name, expected in manifest['inputs'].items():
        require(sha(ROOT / name) == expected.lower(), 'Native input changed: ' + name)
    require(sha(ROOT / 'scripts/build-native.ps1') == manifest['buildScriptSha256'].lower(), 'Build script changed')
    tests_path = build_dir / 'ctest-Release.log'
    tests = tests_path.read_text(encoding='utf-8-sig')
    require(sha(tests_path) == manifest['ctestLogSha256'].lower(), 'CTest log changed')
    passed = re.findall(r'Test\s+#\d+:\s+(\S+)\s+\.+\s+Passed\s', tests)
    require(len(passed) == len(set(passed)) == len(manifest['ctestTests']) == 48
            and set(passed) == set(manifest['ctestTests'])
            and 'sl3_redirect_owner_tests' in passed and '100% tests passed, 0 tests failed out of 48' in tests,
            'Incomplete native test pass')
    guard_test = build_dir / 'Release/sl3_redirect_owner_tests.exe'
    guard = manifest['redirectOwner']
    require(sha(guard_test) == guard['testExecutableSha256'].lower() and guard['softwareTestsPassed'] is True
            and guard['physicalOverlapTested'] is False and guard['safeSuccessiveAcquisitionVerified'] is False,
            'Guard build binding or physical claim differs')
    detail_path = ROOT / 'analysis/redirect-owner-native-testlog-20261101.log'
    detail = detail_path.read_text(encoding='utf-8-sig')
    section = re.search(r'\d+/48 Testing: sl3_redirect_owner_tests\n(.*?)(?=\n\d+/48 Testing:)', detail, re.S)
    require(section and 'Test Passed.' in section[1] and 'private objects only, no USB' in section[1],
            'Missing actual guard process-test output')
    require(str(guard_test).replace('\\', '/') in section[1], 'Guard test command path differs')
    worker = build_dir / 'Release/sl3_usbdk.exe'
    require(sha(worker) == manifest['usbdk']['executableSha256'].lower(), 'Native worker changed')
    preflight_path = ROOT / 'analysis/redirect-owner-preflight-20261101.json'
    preflight = read(preflight_path)
    require(preflight['nativeSha256'].lower() == sha(worker)
            and preflight['signature']['kernelVerificationExitCode'] == 0
            and preflight['nativePlan']['helper_loaded'] is False
            and preflight['helperLoaded'] is False and preflight['deviceRedirected'] is False
            and preflight['driverInstalled'] is False and preflight['audioSubmissions'] == 0, 'Preflight scope differs')
    stale_dir = ROOT / 'analysis/logging-batch-port-ready-20261101'
    abort_path = stale_dir / 'controls-image-started.json'
    abort = read(abort_path)
    require(abort['schema'] == 'sl3.controls-image.aborted-before-start.v1' and abort['startedUtc'] is None
            and abort['planSha256'] == sha(stale_dir / 'controls-image.json')
            and abort['sourceStarted'] is False and abort['deviceOpened'] is False
            and not Path(read(stale_dir / 'controls-image.json')['contextDirectory']).exists(),
            'Superseded preparation was not disarmed without starting capture')
    refusal_path = ROOT / 'analysis/redirect-owner-superseded-plan-refusal-20261101.log'
    require('Collector plan or reviewed inputs changed' in refusal_path.read_text(), 'Missing actual stale-plan refusal')
    result = {'scope': __doc__, 'nativeTestsPassed': 48, 'manifestSha256': sha(manifest_path),
              'ctestLogSha256': sha(tests_path), 'actualGuardTestLogSha256': sha(detail_path),
              'guardTestExecutableSha256': sha(guard_test), 'workerSha256': sha(worker),
              'guardHeaderSha256': sha(ROOT / 'src/windows/redirect_owner.hpp'),
              'guardTestsSourceSha256': sha(ROOT / 'tests/native/redirect_owner_tests.cpp'),
              'preflightSha256': sha(preflight_path), 'supersededPlanAbortSha256': sha(abort_path),
              'supersededPlanRefusalSha256': sha(refusal_path), 'guardContract': guard,
              'secureBootFreshRead': preflight['secureBoot'], 'exporterSha256': sha(Path(__file__)),
              'newPhysicalDeviceOperation': False, 'physicalOverlapTested': False,
              'safeSuccessiveAcquisitionVerified': False, 'currentSeratoAdmissionVerified': False,
              'limits': ['Excludes overlapping cooperating workers while the existence handle survives.',
                         'Object destruction, helper close and process exit are not USB recovery attestations.',
                         'No mixed-integrity, other-user, other-session or native-USB overlap test was run.',
                         'Normal-token preflight could not freshly query Secure Boot; policies were not changed.']}
    (ROOT / 'docs/evidence/redirect-owner-20261101.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Verified 48-test build, real private-process guard tests, read-only preflight and stale-plan refusal')


if __name__ == '__main__':
    main()
