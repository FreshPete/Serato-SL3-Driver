"""Convert a reviewed native diagnostic bundle into a bounded on-demand package; no installation or execution."""
import argparse
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
CONFIG = runpy.run_path(str(ROOT/'scripts/prepare-asio-activation-config.py'))
API = CONFIG['BASE']


def prepare(bundle, expected, build, build_sha, output):
    bundle, build, output = (Path(p).absolute() for p in (bundle, build, output))
    output = API['inside'](output, ROOT/'artifacts/build/deployment-bundles')
    API['require'](not output.exists(), 'New deployment bundle directory required')
    native = CONFIG['sources'](build, build_sha)
    origin, payload = API['capture_bundle'](bundle, expected)
    API['verify_payloads'](origin, payload)
    API['require'](origin['schema'] == 'sl3.deployment-bundle.v1' and
                   origin.get('timingMode') == 'unmeasured-diagnostic-44100-128', 'Native diagnostic locator origin required')
    provenance = API['record'](payload['provenance.json'])
    seed = provenance['identitySeed']
    API['require'](seed['buildManifestSha256'] == build_sha and
                   API['digest'](payload['sl3_asio.dll']) == native['unmeasuredAsioDiagnostic']['dllSha256'].lower() and
                   API['digest'](payload['sl3_broker_controller.exe']) == native['unmeasuredAsioDiagnostic']['brokerSha256'].lower(),
                   'Exact tested native activation build required')
    seed.update(activationMode=API['ACTIVATION_MODE'], activationToolSha256=API['digest'](API['read'](Path(__file__))),
                activationContractSha256=API['digest'](API['read'](ROOT/'scripts/prepare-asio-deployment.py')),
                activationOriginBundleSha256=expected)
    identity = API['digest'](API['encoded'](seed))
    installation = Path(seed['installationDirectory'])
    plan = API['record'](payload['deployment-plan.json'])
    plan.update(packageId=identity, registryEntries=API['registry_entries'](installation, identity),
                activationMode=API['ACTIVATION_MODE'], activationTrigger='IASIO.init', maximumLifetimeMs=600000,
                sessionPointerUsed=False, latencyAvailable=False, automaticStart=True, rateProfileIncluded=True)
    plan['requiredInstallChecks'] = [item for item in plan['requiredInstallChecks'] if item != 'separate user-owned session pointer'] + [
        'three exact protected activation records', 'no active audio owner during removal', 'explicit ten-minute unmeasured diagnostic limit']
    updated = dict(payload)
    updated.update(API['activation_records'](installation, API['digest'](payload['sl3_broker_controller.exe']), API['digest'](payload['sl3_usbdk.exe'])))
    updated['provenance.json'] = API['encoded'](provenance)
    updated['deployment-plan.json'] = API['encoded'](plan)
    updated['README.txt'] = (
        'LOCAL ON-DEMAND DIAGNOSTIC PACKAGE - PREPARED, NOT INSTALLED OR A PUBLIC RELEASE.\n'
        'Initialization can start the native USB owner. Do not register this writable bundle.\n'
        '44.1 kHz / 128 frames, unmeasured latency, maximum ten minutes per owner.\n'
        'Configuration binds final protected installation paths; no session pointer is used at runtime.\n'
        'pointerPath is retained only as legacy installer metadata; it is not written or read by this audio mode.\n'
        'No scheduled task, login startup or service is added. No Serato admission/profile is included.\n'
        'Real native startup/reopen, normal Serato selection and persistent product installation remain unverified.\n'
        'Licenses and original runtime requirements remain in this bundle.\n').encode('utf-8')
    result = {**origin, 'schema': 'sl3.deployment-bundle.v2', 'packageId': identity,
              'activationMode': API['ACTIVATION_MODE'], 'files': {
                  name: {'bytes': len(data), 'sha256': API['digest'](data)} for name, data in updated.items()}}
    API['verify_payloads'](result, updated)
    output.mkdir(parents=True)
    for name, data in updated.items():
        with (output/name).open('xb') as stream:
            stream.write(data)
    with (output/'bundle-manifest.json').open('xb') as stream:
        stream.write(API['encoded'](result))
    result_sha = API['digest'](API['encoded'](result))
    API['verify'](output, result_sha)
    return {'prepared': True, 'directory': str(output), 'bundleManifestSha256': result_sha,
            'activationMode': API['ACTIVATION_MODE'], 'installed': False, 'binaryExecuted': False,
            'registryWritten': False, 'deviceAccess': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bundle', 'expected-bundle-sha256', 'native-build', 'expected-build-sha256', 'output'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.bundle, args.expected_bundle_sha256, args.native_build,
                             args.expected_build_sha256, args.output), indent=2))
