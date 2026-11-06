"""Assemble a host-bound development kit; no installer, application or device start."""
import argparse
import json
from pathlib import Path
import runpy
import shutil

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise ValueError(message)


def module(name):
    return runpy.run_path(str(ROOT / 'scripts' / name))


def assemble(plan, expected, release, expected_release, powershell, output=None):
    api = module('prepare-serato-session-plan.py')
    saved = api['verify'](Path(plan).absolute(), expected)
    release = Path(release).absolute()
    require(release.stat().st_size <= 512 * 1024 and api['sha'](release) == expected_release,
            'Reviewed launcher release identity differs')
    selected = json.loads(release.read_bytes())
    require(selected['schema'] == 'sl3.native-launcher-release.v1' and selected['sessionWrapperSupported'] is True,
            'Reviewed native session launcher release required')
    for name, identity in selected['sourcePins'].items():
        require(api['sha'](ROOT / name) == identity, 'Launcher release source differs: ' + name)
    runtime = Path(saved['python']['path']).parent
    py_sha = selected['runtimePins']['runtime-manifest.json']
    py = module('prepare-embedded-python.py')['verify'](runtime, py_sha)
    require(saved['python']['sha256'] == selected['pythonSha256'] and
            {name: row['sha256'] for name, row in py['files'].items()} ==
            {name: identity for name, identity in selected['runtimePins'].items() if name != 'runtime-manifest.json'},
            'Python release binding differs')
    powershell = Path(powershell).absolute()
    ps_sha = selected['powershellPins']['runtime-manifest.json']
    ps = module('prepare-portable-powershell.py')['verify'](powershell, ps_sha)
    require({name: row['sha256'] for name, row in ps['files'].items()} ==
            {name: identity for name, identity in selected['powershellPins'].items() if name != 'runtime-manifest.json'},
            'PowerShell release binding differs')
    archive = module('prepare-serato-installed-phase-archive.py')
    sources = set(selected['sourcePins']) | set(archive['SOURCES']) | {
        'scripts/assemble-portable-serato-kit.py', 'scripts/prepare-portable-serato-kit.py', 'LICENSE'}
    files = {}

    def add(name, path, identity=None):
        require(name not in files, 'Duplicate kit member')
        path = Path(path)
        observed = api['sha'](path)
        require(identity is None or observed == identity, 'Reviewed kit input differs: ' + name)
        files[name] = (path, observed, path.stat().st_size)

    for name in sorted(sources):
        add(name, ROOT / name)
    for name, identity in selected['runtimePins'].items():
        add('runtime/python/' + name, runtime / name, identity)
    for name, identity in selected['powershellPins'].items():
        add('runtime/powershell/' + name, powershell / name, identity)
    bundle = Path(saved['nativeBundle']['path'])
    bundle_record = json.loads((bundle / 'bundle-manifest.json').read_bytes())
    add('native-package/bundle-manifest.json', bundle / 'bundle-manifest.json', saved['nativeBundle']['sha256'])
    for name, details in bundle_record['files'].items():
        add('native-package/' + name, bundle / name, details['sha256'])
    add('SL3_Rebuild_Development_x64.exe', saved['launcher']['path'], saved['launcher']['sha256'])
    add('installer-resource.bin', saved['installerResource']['path'], saved['installerResource']['sha256'])
    add('release-source.json', release, expected_release)
    result = {'schema': 'sl3.portable-kit-assembly.v1', 'planOnly': output is None, 'filesSelected': len(files),
              'selectedBytes': sum(row[2] for row in files.values()), 'applicationStarted': False,
              'registryWritten': False, 'deviceAccess': False, 'deploymentScope': 'destinations-bound-at-preparation'}
    if output is None:
        return result
    output = Path(output).absolute()
    require(output.parent.resolve() == (ROOT / 'artifacts/build').resolve() and
            output.name.startswith('portable-serato-kit-') and not output.exists() and ';' not in str(output),
            'Fresh artifacts/build/portable-serato-kit-* directory without semicolons required')
    output.mkdir()
    inventory = {}
    for name, (source, identity, size) in sorted(files.items()):
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also preserves partial output on a later failure.
        with source.open('rb') as incoming, destination.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
        require(api['sha'](destination) == identity and destination.stat().st_size == size,
                'Kit input changed during copy: ' + name)
        inventory[name] = {'sha256': identity, 'bytes': size}
    with (output / 'kit-inventory.json').open('x', encoding='utf-8') as stream:
        json.dump({'schema': 'sl3.portable-kit-inventory.v1', 'files': inventory}, stream, sort_keys=True, indent=2)
        stream.write('\n')
    manifest = {'schema': 'sl3.portable-serato-kit.v1', 'inventorySha256': api['sha'](output / 'kit-inventory.json'),
                'launcherSha256': saved['launcher']['sha256'], 'installerResourceSha256': saved['installerResource']['sha256'],
                'sourceReleaseSha256': expected_release, 'pythonManifestSha256': py_sha,
                'powershellManifestSha256': ps_sha, 'nativeBundleSha256': saved['nativeBundle']['sha256'],
                'deploymentScope': result['deploymentScope'], 'seratoApplicationIncluded': False,
                'derivedSeratoArchiveIncluded': False, 'kernelDriverIncluded': False, 'liveValidated': False}
    path = output / 'kit-manifest.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, sort_keys=True, indent=2)
        stream.write('\n')
    identity = api['sha'](path)
    module('prepare-portable-serato-kit.py')['verify'](path, identity)
    return {**result, 'prepared': True, 'directory': str(output), 'kitManifestSha256': identity,
            'filesWritten': True, 'liveValidated': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-plan', type=Path, required=True)
    parser.add_argument('--expected-session-plan-sha256', required=True)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--expected-release-sha256', required=True)
    parser.add_argument('--portable-powershell', type=Path, required=True)
    parser.add_argument('--prepare', type=Path)
    args = parser.parse_args()
    print(json.dumps(assemble(args.session_plan, args.expected_session_plan_sha256, args.release,
                              args.expected_release_sha256, args.portable_powershell, args.prepare), indent=2))
