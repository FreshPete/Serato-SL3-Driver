"""Convert a reviewed native diagnostic bundle into an on-demand package."""
import argparse
import json
from pathlib import Path
import runpy
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONFIG = runpy.run_path(str(ROOT/'scripts/prepare-asio-activation-config.py'))
API = CONFIG['BASE']


def prepare(bundle, expected, build, build_sha, output, application_bound=False, playback_keepalive=False, buffer_frames=128, application_lifetime=False):
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
    mode = API['APPLICATION_ACTIVATION_MODE'] if application_bound else API['ACTIVATION_MODE']
    API['require'](not playback_keepalive or application_bound, 'Playback keepalive requires application-bound activation')
    API['require'](type(buffer_frames) is int and (buffer_frames == 128 or (buffer_frames in (32, 64) and playback_keepalive)),
                   '32/64-frame diagnostic profile requires playback keepalive')
    controller_sha = API['digest'](payload['sl3_broker_controller.exe'])
    worker_sha = API['digest'](payload['sl3_usbdk.exe'])
    if application_bound:
        # A version 1 build cannot pass the passive version 2 parser check.
        # Keep the check against workspace images, never the future install path.
        checker = build.parent/'Release/sl3_driver_configuration_tests.exe'
        checker_sha = native['asioComponent']['activationConfigurationInspectorSha256'].lower()
        with tempfile.TemporaryDirectory(prefix='sl3-app-activation-') as temporary:
            review = Path(temporary)
            for name, data in API['activation_records'](review, controller_sha, worker_sha, mode, bundle,
                                                        playback_keepalive=playback_keepalive, buffer_frames=buffer_frames,
                                                        application_lifetime=application_lifetime).items():
                with (review/name).open('xb') as stream:
                    stream.write(data)
            CONFIG['inspect'](checker, checker_sha, review/'sl3-asio.conf')
    seed.update(activationMode=mode, activationToolSha256=API['digest'](API['read'](Path(__file__))),
                activationContractSha256=API['digest'](API['read'](ROOT/'scripts/prepare-asio-deployment.py')),
                activationOriginBundleSha256=expected)
    if playback_keepalive:
        seed['playbackKeepalive'] = True
    if buffer_frames != 128:
        seed['diagnosticBufferFrames'] = buffer_frames
    if application_lifetime:
        seed['applicationLifetime'] = True
    identity = API['digest'](API['encoded'](seed))
    installation = Path(seed['installationDirectory'])
    plan = API['record'](payload['deployment-plan.json'])
    plan.update(packageId=identity, registryEntries=API['registry_entries'](installation, identity),
                activationMode=mode, activationTrigger='IASIO.init', maximumLifetimeMs=0 if application_lifetime else 600000,
                sessionPointerUsed=False, latencyAvailable=False, automaticStart=True, rateProfileIncluded=True)
    if playback_keepalive:
        plan['playbackKeepalive'] = True
    if buffer_frames != 128:
        plan['diagnosticBufferFrames'] = buffer_frames
    if application_lifetime:
        plan['applicationLifetime'] = True
    plan['requiredInstallChecks'] = [item for item in plan['requiredInstallChecks'] if item != 'separate user-owned session pointer'] + [
        'three exact protected activation records', 'no active audio owner during removal',
        'application exit ends the audio owner' if application_lifetime else 'explicit ten-minute unmeasured diagnostic limit']
    updated = dict(payload)
    updated.update(API['activation_records'](installation, controller_sha, worker_sha, mode,
                                             playback_keepalive=playback_keepalive, buffer_frames=buffer_frames,
                                             application_lifetime=application_lifetime))
    updated['provenance.json'] = API['encoded'](provenance)
    updated['deployment-plan.json'] = API['encoded'](plan)
    updated['README.txt'] = (
        'ON-DEMAND SL3 PACKAGE - PREPARED, NOT INSTALLED.\n'
        'Initialization can start the native USB owner. Do not register this writable bundle.\n'
        f'44.1 kHz / {buffer_frames} frames, unmeasured latency.\n'
        + ('The audio owner stops when the application exits.\n' if application_lifetime else 'Maximum ten minutes per owner.\n')
        + ('The controller is retained across ASIO opens until the application exits.\n' if application_bound else '') +
        'Configuration binds final protected installation paths; no session pointer is used at runtime.\n'
        'pointerPath is retained only as legacy installer metadata; it is not written or read by this audio mode.\n'
        'No scheduled task, login startup or service is added. No Serato admission/profile is included.\n'
        'Real native startup/reopen, normal Serato selection and persistent product installation remain unverified.\n'
        'Licenses and original runtime requirements remain in this bundle.\n').encode('utf-8')
    result = {**origin, 'schema': 'sl3.deployment-bundle.v2', 'packageId': identity,
              'activationMode': mode, 'files': {
                  name: {'bytes': len(data), 'sha256': API['digest'](data)} for name, data in updated.items()}}
    if playback_keepalive:
        result['playbackKeepalive'] = True
    if buffer_frames != 128:
        result['diagnosticBufferFrames'] = buffer_frames
    if application_lifetime:
        result['applicationLifetime'] = True
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
            'activationMode': mode, 'nativeParserChecked': application_bound, 'installed': False, 'binaryExecuted': False,
            'registryWritten': False, 'deviceAccess': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bundle', 'expected-bundle-sha256', 'native-build', 'expected-build-sha256', 'output'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--application-bound', action='store_true')
    parser.add_argument('--playback-keepalive', action='store_true')
    parser.add_argument('--buffer-frames', type=int, choices=(32, 64, 128), default=128)
    parser.add_argument('--until-application-exit', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare(args.bundle, args.expected_bundle_sha256, args.native_build,
                             args.expected_build_sha256, args.output, args.application_bound, args.playback_keepalive,
                             args.buffer_frames, args.until_application_exit), indent=2))
