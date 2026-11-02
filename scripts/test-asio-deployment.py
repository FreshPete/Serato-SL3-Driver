"""Real local bundle preparation and refusal tests; no installation/registry/USB."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/prepare-asio-deployment.py'


def require(value, text):
    if not value:
        raise AssertionError(text)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    identity = uuid.uuid4().hex
    folder = ROOT/'artifacts/build/deployment-tests'/identity
    folder.mkdir(parents=True)
    bundles = ROOT/'artifacts/build/deployment-bundles'
    bundle = bundles/identity
    manifest = ROOT/'artifacts/build/native/native-build-Release.json'
    build = json.loads(manifest.read_text(encoding='utf-8-sig'))
    helper = ROOT/'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10'
    installation = Path(os.environ['ProgramFiles'])/'SL3 Rebuild'/('review-'+identity)
    pointer = Path(os.environ['LOCALAPPDATA'])/'SL3Rebuild'/('session-\u4f1a\u8bdd-'+identity)/'current-session.txt'
    require(not installation.exists() and not pointer.parent.exists(), 'Future install/pointer paths must be absent')
    cases = []; outputs = []

    def call(name, args, expected=0):
        result = subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True, encoding='utf-8', timeout=30)
        (folder/f'{name}-stdout.txt').write_text(result.stdout, encoding='utf-8')
        (folder/f'{name}-stderr.txt').write_text(result.stderr, encoding='utf-8')
        require(result.returncode == expected, f'{name}: {result.returncode}: {result.stdout} {result.stderr}')
        cases.append({'name': name, 'passed': True, 'expectedExit': expected})
        return result

    def preparation(output=bundle, source=manifest, digest=None, helper_file=helper, install=installation):
        return ['--prepare', '--manifest', source, '--expected-build-sha256', digest or sha(source), '--helper', helper_file,
                '--output', output, '--install-directory', install, '--pointer', pointer]

    def verification(path, digest=None):
        return ['--verify', '--bundle', path, '--expected-bundle-sha256', digest or sha(path/'bundle-manifest.json')]

    for name, args in [('default', []), ('plan', ['--plan'])]:
        result = json.loads(call(name, args).stdout)
        require(result['planOnly'] and not result['filesWritten'] and not result['binaryExecuted'] and not result['registryWritten'], 'Inert plan')
    result = json.loads(call('prepare', preparation()).stdout); outputs.append(bundle)
    require(result['prepared'] and not result['installed'] and not result['binaryExecuted'] and not result['registryWritten'], 'Copy-only bundle result')
    bundle_hash = result['bundleManifestSha256']
    require(sha(bundle/'bundle-manifest.json') == bundle_hash, 'Returned manifest digest')
    call('verify', verification(bundle, bundle_hash))
    for name in ['sl3_asio.dll', 'sl3_broker_controller.exe', 'sl3_usbdk.exe']:
        require((manifest.parent/'Release'/name).read_bytes() == (bundle/name).read_bytes(), 'Unchanged first-party payload bytes')
    require(helper.read_bytes() == (bundle/'UsbDkHelper.dll').read_bytes(), 'Unchanged reviewed helper bytes')
    require(not installation.exists() and not pointer.parent.exists(), 'Preparation never writes planned installation or user pointer')
    original = {p.name: sha(p) for p in bundle.iterdir()}
    call('existing-output', preparation(), 1)
    require(original == {p.name: sha(p) for p in bundle.iterdir()}, 'Existing bundle preserved')

    def refused(name, **kwargs):
        output = bundles/(identity+'-'+name)
        response = call(name, preparation(output=output, **kwargs), 1)
        require(not output.exists(), 'Refusal occurs before output creation')
        return response

    refused('build-hash', digest='0'*64)
    refused('helper-hash', helper_file=ROOT/'LICENSE')
    refused('install-scope', install=Path(os.environ['SystemRoot'])/'Unrelated')

    mutations = [
        ('debug-build', lambda m: m.update(configuration='Debug')),
        ('missing-asio', lambda m: m['asioComponent'].update(built=False)),
        ('source-pin', lambda m: m['inputs'].update({'src/asio/com_identity.hpp': '0'*64})),
        ('ctest-hash', lambda m: m.update(ctestLogSha256='0'*64)),
        ('missing-coverage', lambda m: m.update(ctestTests=['unrelated' if x == 'sl3_broker_controller_lifecycle' else x for x in m['ctestTests']])),
        ('controller-kind-collision', lambda m: m['brokerController'].update(simulatedExecutableSha256=m['brokerController']['executableSha256'])),
        ('controller-payload-hash', lambda m: m['brokerController'].update(executableSha256='0'*64)),
    ]
    for name, mutation in mutations:
        modified = json.loads(json.dumps(build)); mutation(modified)
        data = (json.dumps(modified, indent=2)+'\n').encode('utf-8')
        # Same binary/log directory as the real record, distinct create-new name.
        temporary = manifest.parent/f'deployment-test-{identity}-{name}.json'
        with temporary.open('xb') as stream:
            stream.write(data)
        (folder/f'{name}-input.json').write_bytes(data)
        try:
            refused(name, source=temporary)
        finally:
            temporary.unlink()  # Only this test's exact create-new file.

    spec = importlib.util.spec_from_file_location('sl3_deployment_builder', TOOL)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    rejected = False
    try:
        module.pe_info((manifest.parent/'Release/sl3_asio_session_fixture.dll').read_bytes(), 'asio')
    except ValueError:
        rejected = True
    require(rejected, 'Actual simulated-provider DLL rejected by production export guard')
    cases.append({'name': 'actual-fixture-exports', 'passed': True})

    def copy(name):
        target = bundles/(identity+'-'+name)
        shutil.copytree(bundle, target); outputs.append(target)
        return target

    changed = copy('payload-tamper')
    with (changed/'sl3_asio.dll').open('ab') as stream:
        stream.write(b'changed')
    call('payload-tamper', verification(changed, bundle_hash), 1)
    extra = copy('extra-file'); (extra/'EXTRA.dll').write_bytes(b'unexpected')
    call('extra-file', verification(extra, bundle_hash), 1)
    missing = copy('missing-file'); (missing/'sl3_usbdk.exe').unlink()
    call('missing-file', verification(missing, bundle_hash), 1)
    duplicate = copy('duplicate-json')
    raw = (duplicate/'bundle-manifest.json').read_bytes().replace(b'"schema":', b'"schema":"duplicate","schema":', 1)
    (duplicate/'bundle-manifest.json').write_bytes(raw)
    call('duplicate-json', verification(duplicate), 1)

    def update_inventory(path, name, data):
        (path/name).write_bytes(data)
        m = json.loads((path/'bundle-manifest.json').read_text())
        m['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        (path/'bundle-manifest.json').write_bytes(module.encoded(m))

    registry = copy('retarget-registry')
    plan = json.loads((registry/'deployment-plan.json').read_text())
    plan['registryEntries'][0]['key'] = 'SOFTWARE\\Unrelated'
    update_inventory(registry, 'deployment-plan.json', module.encoded(plan))
    call('retarget-registry', verification(registry), 1)
    acl = copy('unsafe-acl')
    plan = json.loads((acl/'deployment-plan.json').read_text())
    plan['proposedAcl']['fullControl'].append('BUILTIN\\Users')
    update_inventory(acl, 'deployment-plan.json', module.encoded(plan))
    call('unsafe-acl', verification(acl), 1)
    scope = copy('retarget-install-scope')
    provenance = json.loads((scope/'provenance.json').read_text())
    bad_install = Path(os.environ['SystemRoot'])/'Unrelated'
    provenance['identitySeed']['installationDirectory'] = str(bad_install)
    new_id = module.digest(module.encoded(provenance['identitySeed']))
    update_inventory(scope, 'provenance.json', module.encoded(provenance))
    plan = json.loads((scope/'deployment-plan.json').read_text())
    plan.update(packageId=new_id, installationDirectory=str(bad_install), registryEntries=module.registry_entries(bad_install, new_id))
    update_inventory(scope, 'deployment-plan.json', module.encoded(plan))
    update_inventory(scope, 'sl3-asio.conf', module.locator_text(bad_install, pointer, sha(scope/'sl3_broker_controller.exe'), sha(scope/'sl3_usbdk.exe')))
    m = json.loads((scope/'bundle-manifest.json').read_text()); m['packageId'] = new_id
    (scope/'bundle-manifest.json').write_bytes(module.encoded(m))
    call('retarget-install-scope', verification(scope), 1)
    locator = copy('retarget-locator')
    data = (locator/'sl3-asio.conf').read_bytes().replace(b'worker_sha256=', b'other_worker=')
    update_inventory(locator, 'sl3-asio.conf', data)
    call('retarget-locator', verification(locator), 1)
    call('verify-manifest-hash', verification(bundle, '0'*64), 1)
    call('unsupported-options', preparation()+['--bundle', bundle], 1)

    require(original == {p.name: sha(p) for p in bundle.iterdir()}, 'Positive review bundle remains unchanged')
    require(not installation.exists() and not pointer.parent.exists(), 'No installation or pointer writes after all tests')
    files = {}
    for parent in [folder, *outputs]:
        for path in parent.rglob('*'):
            if path.is_file():
                files[path.relative_to(ROOT).as_posix()] = sha(path)
    report = {'schema': 'sl3.deployment-preparation-tests.v1', 'cases': cases, 'files': files,
              'positiveBundle': bundle.relative_to(ROOT).as_posix(), 'bundleManifestSha256': bundle_hash,
              'installed': False, 'registryWritten': False, 'binaryExecuted': False, 'deviceAccess': False,
              'plannedDestinationsRemainAbsent': True}
    index = folder/'index.json'; index.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/deployment-tests-last.json').write_text(json.dumps({'directory': str(folder), 'indexSha256': sha(index)}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'evidenceDirectory': str(folder), 'bundle': str(bundle), 'installed': False}))


if __name__ == '__main__':
    main()
