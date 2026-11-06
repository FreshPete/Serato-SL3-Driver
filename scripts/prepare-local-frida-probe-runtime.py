"""Stage a separate candidate SDK for owned-process tests; never import Frida."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    return runpy.run_path(str(ROOT / 'scripts' / name))


def payload(base, manifest, generated):
    require = module('prepare-embedded-python.py')['require']
    # Copy interpreter files only. No installed wheel binary/metadata is carried over.
    files = {name: (base / name).read_bytes() for name in manifest['files'] if '/' not in name}
    require(all(name in files for name in ('python.exe', 'python3.dll', 'LICENSE.txt')), 'Embedded interpreter required')
    for name in ('__init__.py', 'aio.py', '_frida.pyi'):
        data = (generated / name).read_bytes()
        require(data == (base / 'packages/frida' / name).read_bytes(), 'Generated Python binding differs: ' + name)
        files['packages/frida/' + name] = data
    files['packages/frida/_frida.pyd'] = (generated / '_frida.pyd').read_bytes()
    return files


def inspection_dependencies(base, manifest):
    api = module('prepare-embedded-python.py'); files, records = {}, {}
    for dependency in ('capstone', 'pefile'):
        candidates = [name for name in manifest['files'] if name.startswith('packages/' + dependency + '-') and
                      name.endswith('.dist-info/RECORD')]
        api['require'](len(candidates) == 1, 'Unique reviewed dependency record required: ' + dependency)
        name, identity, added = api['wheel_files'](base / candidates[0])
        api['require'](name == dependency and not set(files) & set(added) and
                       not any(path.startswith(('packages/frida/', 'packages/frida-')) for path in added),
                       'Unexpected inspection dependency payload')
        files.update(added); records[name] = {'recordSha256': identity}
    return files, records


def prepare(base, base_sha, build, candidate_sha, publics, summary, output, integration_dependencies=False):
    api = module('prepare-embedded-python.py'); require = api['require']
    base, build, output = Path(base).resolve(), Path(build).resolve(), Path(output).absolute()
    manifest = api['verify'](base, base_sha)
    inspection = module('inspect-frida-local-build.py')['inspect'](build.parents[1] / 'references/frida-local-only-17.25.2',
                                                                 build, False, True)
    require(inspection['candidateSha256'] == candidate_sha, 'Reviewed candidate differs')
    assets = module('inspect-frida-embedded-assets.py')['inspect'](build, candidate_sha, Path(publics), Path(summary))
    require(output.parent.resolve() == (ROOT / 'artifacts/build').resolve() and
            output.name.startswith('embedded-python-local-frida-') and not output.exists(), 'Fresh private runtime required')
    generated = build / 'subprojects/frida-python/frida'
    files = payload(base, manifest, generated)
    dependencies = {}
    if integration_dependencies:
        added, dependencies = inspection_dependencies(base, manifest)
        require(not set(files) & set(added), 'Inspection dependencies collide with candidate payload')
        files.update(added)
    source = ROOT / 'artifacts/references/frida-local-only-17.25.2'
    for component in ('frida-core', 'frida-gum', 'frida-python', 'efni'):
        files['licenses/' + component + '/COPYING'] = (source / 'subprojects' / component / 'COPYING').read_bytes()
    sha = lambda value: hashlib.sha256(value).hexdigest()
    result = {'schema': 'sl3.embedded-python.v1', 'scope': 'owned-process-local-frida-candidate-only',
              'baseManifestSha256': base_sha, 'candidateSha256': candidate_sha,
              'bindingsMatchReviewedWheel': True, 'sourceCommits': inspection['sourceCommits'],
              'listedNativeAssetsMatchFinalImage': assets['listedNativeAssetsMatchFinalImage'],
              'files': {name: {'bytes': len(data), 'sha256': sha(data)} for name, data in sorted(files.items())},
              'moduleSearch': 'embedded standard library, runtime directory, packages; site disabled',
              'stockSessionKitChanged': False, 'securityHoldCleared': False, 'systemPythonModified': False,
              'liveSeratoValidated': False, 'interpreterExecutedDuringPreparation': False}
    if integration_dependencies:
        result.update(scope='local-frida-startup-integration-candidate', dependencyProfile='startup-inspection',
                      dependencies={**dependencies, 'frida': {'kind': 'reviewed-local-build', 'sha256': candidate_sha}})
    output.mkdir()
    for name, data in files.items():
        target = output / name; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream: stream.write(data)
    with (output / 'runtime-manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, sort_keys=True); stream.write('\n')
    identity = sha((output / 'runtime-manifest.json').read_bytes())
    api['verify'](output, identity)
    return {'prepared': True, 'manifestSha256': identity, 'fileCount': len(files), 'candidateSha256': candidate_sha,
            'scope': result['scope'], 'fridaImported': False, 'sessionKitChanged': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'build', 'public-symbols', 'pdb-summary', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-base-manifest-sha256', required=True)
    parser.add_argument('--expected-candidate-sha256', required=True)
    parser.add_argument('--integration-dependencies', action='store_true',
                        help='Also include the reviewed Capstone/pefile wheel payloads for offline startup inspection')
    args = parser.parse_args()
    print(json.dumps(prepare(args.base, args.expected_base_manifest_sha256, args.build, args.expected_candidate_sha256,
                             args.public_symbols, args.pdb_summary, args.output, args.integration_dependencies), indent=2))
