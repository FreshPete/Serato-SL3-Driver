"""Check real package rebinding and synthetic foreign metadata without installation."""
import argparse
import json
from pathlib import Path
import runpy
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def exercise(bundle, expected):
    api = runpy.run_path(str(ROOT / 'scripts/prepare-asio-deployment.py'))
    tool = runpy.run_path(str(ROOT / 'scripts/rebind-asio-deployment.py'))
    original_manifest, original_payload = api['capture_bundle'](bundle, expected)
    cases = []

    def passed(name):
        cases.append({'name': name, 'passed': True})

    def refused(name, action, message):
        try:
            action()
        except ValueError as error:
            assert message in str(error), (name, str(error))
        else:
            raise AssertionError('Unexpected acceptance: ' + name)
        passed(name)

    api['verify'](bundle, expected)
    passed('original-package-production-verification')
    with tempfile.TemporaryDirectory(prefix='sl3-rebind-tests-', dir=ROOT / 'analysis') as temporary:
        directory = Path(temporary)
        foreign = directory / 'foreign-origin'
        foreign.mkdir()
        payload = dict(original_payload)
        provenance = api['record'](payload['provenance.json'])
        provenance['identitySeed']['pointerPath'] = 'C:\\SL3-Rebind-Foreign-Origin\\OtherAccount\\SL3Rebuild\\session.txt'
        seed = provenance['identitySeed']
        identity = api['digest'](api['encoded'](seed))
        plan = api['record'](payload['deployment-plan.json'])
        plan.update(packageId=identity, pointerPath=seed['pointerPath'],
                    registryEntries=api['registry_entries'](Path(seed['installationDirectory']), identity))
        payload['provenance.json'] = api['encoded'](provenance)
        payload['deployment-plan.json'] = api['encoded'](plan)
        payload['sl3-asio.conf'] = api['locator_text'](Path(seed['installationDirectory']), Path(seed['pointerPath']),
            api['digest'](payload['sl3_broker_controller.exe']), api['digest'](payload['sl3_usbdk.exe']))

        def write_origin(values):
            manifest = {**original_manifest, 'packageId': identity, 'files': {
                name: {'bytes': len(data), 'sha256': api['digest'](data)} for name, data in values.items()}}
            for name, data in values.items():
                (foreign / name).write_bytes(data)
            raw = api['encoded'](manifest)
            (foreign / 'bundle-manifest.json').write_bytes(raw)
            return api['digest'](raw), manifest

        foreign_sha, manifest = write_origin(payload)
        inspection = api['inspect_portable_payloads'](manifest, payload)
        assert inspection['productionDestinationsAdmitted'] is False
        passed('portable-inspection-does-not-admit-foreign-pointer')
        refused('production-verifier-still-rejects-foreign-pointer', lambda: api['verify'](foreign, foreign_sha),
                'Path escapes intended directory')
        before = set((ROOT / 'analysis').glob('sl3-deployment-rebound-*'))
        planned = tool['rebind'](foreign, foreign_sha)
        assert planned['planOnly'] is True
        assert set((ROOT / 'analysis').glob('sl3-deployment-rebound-*')) == before
        passed('foreign-origin-read-only-rebinding-plan')
        output = ROOT / 'analysis' / ('sl3-deployment-rebound-test-' + uuid.uuid4().hex)
        rebound = tool['rebind'](foreign, foreign_sha, output)
        api['verify'](output, rebound['bundleManifestSha256'])
        _, actual = api['capture_bundle'](output, rebound['bundleManifestSha256'])
        assert all(actual[name] == original_payload[name] for name in tool['BINARIES'])
        changed = {name for name in actual if actual[name] != payload[name]}
        assert changed == {'provenance.json', 'deployment-plan.json', 'sl3-asio.conf'}
        new_provenance = api['record'](actual['provenance.json'])
        for name in ('nativeTestsPassed', 'ctestLogSha256', 'images'):
            assert new_provenance[name] == provenance[name]
        assert new_provenance['identitySeed']['payloadHashes'] == seed['payloadHashes']
        assert new_provenance['identitySeed']['reboundFromBundleSha256'] == foreign_sha
        assert new_provenance['identitySeed']['originalBundleSha256'] == foreign_sha
        assert not Path(rebound['installationDirectory']).exists() and not Path(rebound['pointerPath']).exists()
        passed('foreign-origin-rebound-and-production-verified-with-identical-binaries')
        refused('existing-output-preserved', lambda: tool['rebind'](foreign, foreign_sha, output), 'Fresh analysis/')
        assert api['digest']((output / 'bundle-manifest.json').read_bytes()) == rebound['bundleManifestSha256']
        refused('destination-outside-production-base-refused', lambda: tool['rebind'](foreign, foreign_sha,
            installation=directory / 'unsafe-installation', pointer=directory / 'unsafe-pointer.txt'), 'Path escapes intended directory')
        changed_payload = dict(payload)
        changed_payload['sl3_usbdk.exe'] += b'changed'
        changed_sha, _ = write_origin(changed_payload)
        refused('changed-native-payload-rejected', lambda: tool['rebind'](foreign, changed_sha), 'Seed payload mismatch')
        changed_payload = dict(payload)
        unsafe_plan = api['record'](payload['deployment-plan.json'])
        unsafe_plan['proposedAcl']['readExecute'] = ['Everyone']
        changed_payload['deployment-plan.json'] = api['encoded'](unsafe_plan)
        changed_sha, _ = write_origin(changed_payload)
        refused('unsafe-origin-policy-rejected', lambda: tool['rebind'](foreign, changed_sha), 'Unsafe installation policy proposed')
        write_origin(payload)
        (foreign / 'unexpected.txt').write_bytes(b'not executed')
        refused('extra-origin-file-rejected', lambda: tool['rebind'](foreign, foreign_sha), 'Unexpected or missing bundle file')
    assert api['digest']((bundle / 'bundle-manifest.json').read_bytes()) == expected
    api['verify'](bundle, expected)
    return {'schema': 'sl3.deployment-rebinding-tests.v1', 'cases': cases,
            'originBundleSha256': expected, 'reboundBundleSha256': rebound['bundleManifestSha256'],
            'nativeBinarySha256': rebound['nativeBinarySha256'], 'nativeBinariesUnchanged': True,
            'testProvenancePreserved': True, 'syntheticForeignPointerUsed': True,
            'otherAccountActuallyTested': False, 'secondPcTested': False,
            'installed': False, 'registryWritten': False, 'binaryExecuted': False, 'deviceAccess': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--expected-bundle-sha256', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = exercise(args.bundle.absolute(), args.expected_bundle_sha256)
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps(result, indent=2))
