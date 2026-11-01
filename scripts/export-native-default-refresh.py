"""Verify the current default build and unstarted capture preparation; no hardware operation."""
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / name)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    capture = module('collect-controls-with-images.py')
    require, read, sha = capture.require, capture.read, capture.sha
    build_dir = ROOT / 'artifacts/build/native'
    manifest_path = build_dir / 'native-build-Release.json'
    build = read(manifest_path)
    for name, expected in build['inputs'].items():
        require(sha(ROOT / name) == expected.lower(), 'Native input changed: ' + name)
    require(sha(ROOT / 'scripts/build-native.ps1') == build['buildScriptSha256'].lower(), 'Build script changed')
    log_path = build_dir / 'ctest-Release.log'
    require(sha(log_path) == build['ctestLogSha256'].lower(), 'CTest log changed')
    log = log_path.read_text(encoding='utf-8-sig')
    passed = re.findall(r'Test\s+#\d+:\s+(\S+)\s+\.+\s+Passed\s', log)
    require(len(passed) == len(set(passed)) == len(build['ctestTests']) == 47
            and set(passed) == set(build['ctestTests'])
            and '100% tests passed, 0 tests failed out of 47' in log, 'Incomplete default-build tests')
    preflight_path = ROOT / 'analysis/native-default-refresh-20261101-preflight.json'
    preflight = read(preflight_path)
    require(preflight['nativeSha256'].lower() == build['usbdk']['executableSha256'].lower()
            and preflight['signature']['kernelVerificationExitCode'] == 0
            and preflight['nativePlan']['helper_loaded'] is False
            and preflight['helperLoaded'] is False and preflight['deviceRedirected'] is False
            and preflight['driverInstalled'] is False and preflight['audioSubmissions'] == 0, 'Preflight scope differs')
    plan_path = ROOT / 'analysis/logging-batch-port-ready-20261101/controls-image.json'
    plan, _ = capture.validate(plan_path)
    observer = module('observe-sl3-hub-port.py')
    job_dir = ROOT / 'analysis/hub-port-observer-ready-v2-20261101'
    job = observer.validate(job_dir)
    require(job['contextDirectory'] == plan['contextDirectory'] and not Path(plan['contextDirectory']).exists()
            and not (job_dir / 'started.json').exists(), 'Prepared roles have started or contexts differ')
    try:
        observer.validate(ROOT / 'analysis/hub-port-observer-ready-20261101')
    except ValueError as error:
        require(str(error) == 'Observer plan/runtime changed', 'Unexpected stale-plan refusal')
    else:
        raise ValueError('Pre-fix observer plan remained admissible')
    tests_path = ROOT / 'analysis/hub-observer-cli-fix-20261101-tests.log'
    tests = tests_path.read_text()
    require('Ran 15 tests' in tests and tests.rstrip().endswith('OK'), 'Observer tests did not pass')
    query_path = ROOT / 'analysis/sl3-hub-port-default-refresh-20261101.json'
    query = read(query_path)
    require(query['sourceSha256'] == sha(ROOT / 'scripts/query-sl3-hub-port.py')
            and query['successful'] is True and query['handleClosed'] is True
            and query['producerToken']['elevated'] is False and query['connection']['targetDescriptorMatches'] is True
            and query['sl3OpensRequested'] == query['usbResetRequests'] == query['audioStarts'] == 0,
            'Cached query evidence differs')
    result = {'scope': __doc__, 'defaultBuildTestsPassed': 47, 'observerSoftwareTestsPassed': 15,
              'manifestSha256': sha(manifest_path), 'ctestLogSha256': sha(log_path),
              'workerSha256': build['usbdk']['executableSha256'].lower(),
              'hostProbeSha256': build['hostProbe']['executableSha256'].lower(),
              'preflightSha256': sha(preflight_path), 'collectorPlanSha256': sha(plan_path),
              'observerPlanSha256': sha(job_dir / 'plan.json'), 'observerTestLogSha256': sha(tests_path),
              'observerSourceSha256': sha(ROOT / 'scripts/observe-sl3-hub-port.py'),
              'observerTestsSourceSha256': sha(ROOT / 'tests/test_sl3_hub_observer.py'),
              'cachedQuerySha256': sha(query_path), 'cachedConnection': query['connection'],
              'preparedOnly': True, 'preFixObserverPlanRefused': True, 'traceStarted': False,
              'sl3Opened': False, 'audioStarted': False, 'securityChanged': False,
              'secureBootFreshRead': preflight['secureBoot'], 'readinessAdmission': False,
              'physicalCurrentBuildTested': False, 'currentSeratoAdmissionVerified': False,
              'exporterSha256': sha(Path(__file__)),
              'limits': ['Read-only preflight could not freshly query Secure Boot from this normal token.',
                         'Connected cached descriptors do not establish readiness to redirect or stream.',
                         'Revalidate both plans and physical port before the attended one-approval launch.']}
    (ROOT / 'docs/evidence/native-default-refresh-20261101.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Verified default 47-test build, read-only preflight, 15 observer tests and two unstarted plans')


if __name__ == '__main__':
    main()
