"""Prepare/check native activation records in a fresh review folder; never installs or activates."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = runpy.run_path(str(ROOT / 'scripts/prepare-asio-deployment.py'))
require = BASE['require']
read = BASE['read']
digest = BASE['digest']
encoded = BASE['encoded']
record = BASE['record']
INVENTORY = {'sl3-asio.conf', 'sl3-worker.conf', 'sl3-timing.conf', 'review.json'}
INSPECTION = {'schema': 'sl3.activation-config-inspection.v1', 'accepted': True, 'nativeKind': True,
              'unmeasuredDiagnostic': True, 'activationAttempted': False, 'helperLoaded': False, 'deviceAccess': False}


def inspect(checker, expected, entry):
    require(digest(read(checker)) == expected, 'Native configuration inspector hash changed')
    result = subprocess.run([str(checker), '--inspect-activation', str(entry)], capture_output=True, timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0, 'Native configuration parser refused the review records')
    require(record(result.stdout) == INSPECTION, 'Unexpected native configuration inspection result')
    require(digest(read(checker)) == expected, 'Native configuration inspector changed while running')
    return INSPECTION.copy()


def records(output, bundle, controller_sha, worker_sha):
    # Native loader rechecks these hashes and holds read-only file leases.
    timing = ('SL3-ASIO-DIAGNOSTIC-TIMING-1\nworker_sha256=' + worker_sha + '\nhelper_sha256=' + BASE['HELPER_SHA'] +
              '\nrate_hz=44100\nbuffer_frames=128\n').encode('utf-8')
    worker = ('SL3-ASIO-CONFIG-1\nworker=' + str(bundle / 'sl3_usbdk.exe') + '\nworker_sha256=' + worker_sha +
              '\nhelper=' + str(bundle / 'UsbDkHelper.dll') + '\ntiming_record=' + str(output / 'sl3-timing.conf') +
              '\ntiming_record_sha256=' + digest(timing) + '\n').encode('utf-8')
    entry = ('SL3-ASIO-ACTIVATION-1\ncontroller=' + str(bundle / 'sl3_broker_controller.exe') +
             '\ncontroller_sha256=' + controller_sha + '\ninput=' + str(output / 'sl3-worker.conf') +
             '\ninput_sha256=' + digest(worker) + '\nstartup_timeout_ms=15000\nstartup_failure_grace_ms=5000\nlifetime_ms=600000\n').encode('utf-8')
    return {'sl3-asio.conf': entry, 'sl3-worker.conf': worker, 'sl3-timing.conf': timing}


def sources(build, expected):
    raw = read(build)
    require(digest(raw) == BASE['sha_value'](expected), 'Native build manifest hash mismatch')
    native = record(raw)
    require(native['configuration'] == 'Release' and native['architecture'] == 'x64' and native['coreTestsPassed'] is True,
            'Tested x64 Release build required')
    require({'sl3_activation_asio_lifecycle', 'sl3_driver_configuration_tests'}.issubset(native['ctestTests']),
            'Lazy ASIO entry lifecycle coverage required')
    for name, sha in native['inputs'].items():
        require(digest(read(BASE['inside'](ROOT / name, ROOT))) == sha.lower(), 'Native build source changed: ' + name)
    require(digest(read(ROOT / 'scripts/build-native.ps1')) == native['buildScriptSha256'].lower(), 'Build script changed')
    log = read(build.parent / 'ctest-Release.log')
    require(digest(log) == native['ctestLogSha256'].lower() and
            ('100% tests passed, 0 tests failed out of ' + str(len(native['ctestTests']))).encode() in log, 'Complete CTest result required')
    return native


def prepare(bundle, bundle_sha, build, build_sha, output):
    bundle, build, output = (Path(p).absolute() for p in (bundle, build, output))
    output = BASE['inside'](output, ROOT / 'artifacts/build/activation-reviews')
    require(len(output.drive) == 2 and output.drive[1] == ':' and ':' not in str(output)[2:] and
            not any(ord(c) < 32 for c in str(output)), 'Local review path without streams/control characters required')
    require(not output.exists(), 'Fresh activation review directory required')
    native = sources(build, build_sha)
    manifest, payload = BASE['capture_bundle'](bundle, bundle_sha)
    BASE['verify_payloads'](manifest, payload)
    require(manifest.get('timingMode') == 'unmeasured-diagnostic-44100-128', 'Explicit diagnostic review bundle required')
    provenance = record(payload['provenance.json'])
    require(provenance['identitySeed']['buildManifestSha256'] == build_sha, 'Bundle must originate from this exact build')
    require(digest(payload['sl3_asio.dll']) == native['unmeasuredAsioDiagnostic']['dllSha256'].lower() and
            digest(payload['sl3_broker_controller.exe']) == native['unmeasuredAsioDiagnostic']['brokerSha256'].lower(),
            'Native diagnostic DLL/controller identity mismatch')
    checker = build.parent / 'Release/sl3_driver_configuration_tests.exe'
    checker_sha = native['asioComponent']['activationConfigurationInspectorSha256'].lower()
    require(digest(read(checker)) == checker_sha, 'Reviewed native inspector required')
    data = records(output, bundle, digest(payload['sl3_broker_controller.exe']), digest(payload['sl3_usbdk.exe']))
    output.mkdir(parents=True)
    for name, content in data.items():
        with (output / name).open('xb') as stream:
            stream.write(content)
    # Only the passive parser branch runs. It never constructs a DriverSession.
    result = inspect(checker, checker_sha, output / 'sl3-asio.conf')
    report = {'schema': 'sl3.activation-configuration-review.v1', 'builderSha256': digest(read(Path(__file__))),
              'bundle': str(bundle), 'bundleSha256': bundle_sha, 'nativeBuildManifestSha256': build_sha,
              'inspector': str(checker), 'inspectorSha256': checker_sha, 'inspection': result,
              'files': {name: {'sha256': digest(content), 'bytes': len(content)} for name, content in data.items()},
              'maximumLifetimeMs': 600000, 'rateHz': 44100, 'bufferFrames': 128,
              'installed': False, 'registrationChanged': False, 'activationAttempted': False, 'deviceAccess': False,
              'seratoLaunched': False, 'installableBySessionEngine': False, 'relocatable': False}
    with (output / 'review.json').open('xb') as stream:
        stream.write(encoded(report))
    review_sha = digest(encoded(report))
    verify(output, review_sha)
    return {'prepared': True, 'directory': str(output), 'reviewSha256': review_sha, 'inspection': result, 'installed': False}


def verify(output, expected):
    output = Path(output).absolute()
    for path in (output, *(output / name for name in INVENTORY)):
        require(not path.is_symlink() and not (getattr(path.stat(), 'st_file_attributes', 0) & 0x400), 'Reparse review path refused')
    raw = read(output / 'review.json')
    require(digest(raw) == BASE['sha_value'](expected), 'Activation review identity mismatch')
    meta = record(raw)
    require(meta['schema'] == 'sl3.activation-configuration-review.v1' and set(p.name for p in output.iterdir()) == INVENTORY,
            'Unexpected activation review inventory')
    require(meta['maximumLifetimeMs'] == 600000 and meta['rateHz'] == 44100 and meta['bufferFrames'] == 128,
            'Diagnostic review limits changed')
    require(set(meta['files']) == INVENTORY - {'review.json'} and meta['inspection'] == INSPECTION and
            all(meta[k] is False for k in ('installed', 'registrationChanged', 'activationAttempted', 'deviceAccess',
                                           'seratoLaunched', 'installableBySessionEngine', 'relocatable')),
            'Activation review cannot claim installation or device validation')
    for name, details in meta['files'].items():
        data = read(output / name)
        require(len(data) == details['bytes'] and digest(data) == details['sha256'], 'Activation review record changed: ' + name)
    manifest, payload = BASE['capture_bundle'](Path(meta['bundle']), meta['bundleSha256'])
    BASE['verify_payloads'](manifest, payload)
    require(manifest.get('timingMode') == 'unmeasured-diagnostic-44100-128', 'Diagnostic origin required')
    require(record(payload['provenance.json'])['identitySeed']['buildManifestSha256'] == meta['nativeBuildManifestSha256'],
            'Review origin build mismatch')
    expected_records = records(output, Path(meta['bundle']), digest(payload['sl3_broker_controller.exe']), digest(payload['sl3_usbdk.exe']))
    require(all(read(output / name) == data for name, data in expected_records.items()), 'Record contract or location mismatch')
    result = inspect(Path(meta['inspector']), meta['inspectorSha256'], output / 'sl3-asio.conf')
    return {'verified': True, 'inspection': result, 'installed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    create = sub.add_parser('prepare')
    for name in ('bundle', 'bundle-sha256', 'native-build', 'build-sha256', 'output'):
        create.add_argument('--' + name, required=True)
    check = sub.add_parser('verify')
    check.add_argument('--output', required=True)
    check.add_argument('--review-sha256', required=True)
    args = parser.parse_args()
    if args.operation == 'prepare':
        answer = prepare(args.bundle, args.bundle_sha256, args.native_build, args.build_sha256, args.output)
    else:
        answer = verify(args.output, args.review_sha256)
    print(json.dumps(answer, indent=2))
