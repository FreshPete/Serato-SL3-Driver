"""Rebind reviewed native package metadata offline; never installs or executes it."""
import argparse
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
BINARIES = ('sl3_asio.dll', 'sl3_broker_controller.exe', 'sl3_usbdk.exe', 'UsbDkHelper.dll')


def module(name):
    return runpy.run_path(str(ROOT / 'scripts' / name))


def current_destinations():
    stage = module('asio-install-journal.py')['stage_module']()
    installation = stage.known_folder('905e63b6-c1bf-494e-b29c-65b732d3d21a') / 'SL3 Rebuild' / 'phase-diagnostic-v1'
    pointer = stage.known_folder('f1b32785-6fba-4fcf-9d55-7b8e7f157091') / 'SL3Rebuild' / 'phase-session.txt'
    return installation, pointer


def rebind(bundle, expected, output=None, installation=None, pointer=None):
    api = module('prepare-asio-deployment.py')
    manifest, payload = api['capture_bundle'](Path(bundle).absolute(), expected)
    api['inspect_portable_payloads'](manifest, payload)
    api['require'](manifest.get('timingMode') == 'unmeasured-diagnostic-44100-128', 'Reviewed diagnostic package required')
    api['require']((installation is None) == (pointer is None), 'Select both destinations or neither')
    if installation is None:
        installation, pointer = current_destinations()
    installation, pointer = api['destinations'](Path(installation).absolute(), Path(pointer).absolute())
    provenance = api['record'](payload['provenance.json'])
    seed = provenance['identitySeed']
    seed['originalBundleSha256'] = seed.get('originalBundleSha256', expected)
    seed.update(installationDirectory=str(installation), pointerPath=str(pointer), reboundFromBundleSha256=expected,
                rebindToolSha256=api['digest'](api['read'](Path(__file__))))
    identity = api['digest'](api['encoded'](seed))
    plan = api['record'](payload['deployment-plan.json'])
    plan.update(packageId=identity, installationDirectory=str(installation), pointerPath=str(pointer),
                registryEntries=api['registry_entries'](installation, identity))
    updated = dict(payload)
    updated['provenance.json'] = api['encoded'](provenance)
    updated['deployment-plan.json'] = api['encoded'](plan)
    if manifest['schema'] == 'sl3.deployment-bundle.v2':
        updated.update(api['activation_records'](installation,
            api['digest'](payload['sl3_broker_controller.exe']), api['digest'](payload['sl3_usbdk.exe']),
            manifest['activationMode'], playback_keepalive=manifest.get('playbackKeepalive', False),
            buffer_frames=manifest.get('diagnosticBufferFrames', 128)))
    else:
        updated['sl3-asio.conf'] = api['locator_text'](installation, pointer,
            api['digest'](payload['sl3_broker_controller.exe']), api['digest'](payload['sl3_usbdk.exe']))
    rebound = {**manifest, 'packageId': identity, 'files': {
        name: {'bytes': len(data), 'sha256': api['digest'](data)} for name, data in updated.items()}}
    # This is the same mandatory current-account verifier used by installation.
    # Portable origin inspection never substitutes for destination admission.
    api['verify_payloads'](rebound, updated)
    api['require'](all(updated[name] == payload[name] for name in BINARIES), 'Native payload bytes must remain unchanged')
    report = {'schema': 'sl3.deployment-rebinding.v1', 'planOnly': output is None,
              'originBundleSha256': expected, 'installationDirectory': str(installation), 'pointerPath': str(pointer),
              'packageId': identity, 'nativeBinarySha256': {name: api['digest'](updated[name]) for name in BINARIES},
              'nativeBinariesUnchanged': True, 'nativeTestProvenancePreserved': True,
              'productionDestinationsVerified': True, 'installed': False, 'registryWritten': False,
              'binaryExecuted': False, 'deviceAccess': False, 'liveValidated': False}
    if output is None:
        return report
    output = Path(output).absolute()
    api['require'](output.parent.resolve() == (ROOT / 'analysis').resolve() and
                   output.name.startswith('sl3-deployment-rebound-') and not output.exists(),
                   'Fresh analysis/sl3-deployment-rebound-* directory required')
    output.mkdir()
    for name, data in updated.items():
        with (output / name).open('xb') as stream:
            stream.write(data)
    raw = api['encoded'](rebound)
    with (output / 'bundle-manifest.json').open('xb') as stream:
        stream.write(raw)
    result_sha = api['digest'](raw)
    api['verify'](output, result_sha)
    return {**report, 'prepared': True, 'directory': str(output), 'bundleManifestSha256': result_sha}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--expected-bundle-sha256', required=True)
    parser.add_argument('--prepare', type=Path)
    parser.add_argument('--installation', type=Path)
    parser.add_argument('--pointer', type=Path)
    args = parser.parse_args()
    print(json.dumps(rebind(args.bundle, args.expected_bundle_sha256, args.prepare,
                            args.installation, args.pointer), indent=2))
