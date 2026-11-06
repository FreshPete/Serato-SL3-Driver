"""Verify a copied development kit and prepare a local session; never start it."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import runpy
import stat
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular(path, limit=256 * 1024 * 1024):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400 and
            0 <= info.st_size <= limit, 'Bounded regular kit file required')
    return info


def member(root, name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name and
            not name.startswith('/') and all(part not in ('', '.', '..') for part in name.split('/')),
            'Relative kit member required')
    path = root.joinpath(*PurePosixPath(name).parts)
    require(path.resolve().is_relative_to(root.resolve()), 'Kit member escaped its directory')
    return path


def module(name):
    return runpy.run_path(str(ROOT / 'scripts' / name))


def verify(manifest, expected):
    manifest = Path(manifest).absolute()
    require(manifest.name == 'kit-manifest.json' and re.fullmatch('[0-9a-f]{64}', expected), 'Expected kit identity')
    root = manifest.parent
    require(root.is_dir() and not getattr(root.lstat(), 'st_file_attributes', 0) & 0x400,
            'Ordinary kit directory required')
    require(regular(manifest, 65536).st_size > 0 and sha(manifest) == expected, 'Kit manifest differs')
    record = json.loads(manifest.read_bytes())
    require(record['schema'] == 'sl3.portable-serato-kit.v1', 'Unsupported kit manifest')
    inventory = root / 'kit-inventory.json'
    regular(inventory, 1024 * 1024)
    require(sha(inventory) == record['inventorySha256'], 'Kit inventory differs')
    files = json.loads(inventory.read_bytes())['files']
    require(1 <= len(files) <= 2048 and len({name.casefold() for name in files}) == len(files) and
            sum(row['bytes'] for row in files.values()) <= 768 * 1024 * 1024, 'Kit inventory bounds or aliases differ')
    for name, details in files.items():
        path = member(root, name)
        require(name.split('/')[0].casefold() != 'analysis', 'Mutable state cannot be a kit payload')
        require(regular(path).st_size == details['bytes'] and sha(path) == details['sha256'], 'Kit file differs: ' + name)
    actual = set()
    for child in root.iterdir():
        require(not getattr(child.lstat(), 'st_file_attributes', 0) & 0x400 and not child.is_symlink(),
                'Kit reparse entry refused')
        if child.name == 'analysis':
            require(child.is_dir(), 'Analysis state must be a directory')
            continue
        paths = [child] if child.is_file() else child.rglob('*')
        for path in paths:
            require(not getattr(path.lstat(), 'st_file_attributes', 0) & 0x400 and not path.is_symlink(),
                    'Kit reparse entry refused')
            if path.is_file():
                actual.add(path.relative_to(root).as_posix())
    require(actual == set(files) | {'kit-manifest.json', 'kit-inventory.json'}, 'Unexpected kit files')
    for name, expected_hash in (
        ('SL3_Rebuild_Development_x64.exe', record['launcherSha256']),
        ('installer-resource.bin', record['installerResourceSha256']),
        ('release-source.json', record['sourceReleaseSha256']),
        ('runtime/python/runtime-manifest.json', record['pythonManifestSha256']),
        ('runtime/powershell/runtime-manifest.json', record['powershellManifestSha256']),
        ('native-package/bundle-manifest.json', record['nativeBundleSha256']),
    ):
        require(files[name]['sha256'] == expected_hash, 'Kit component binding differs')
    return record


def prepare(manifest, expected, application, write=False):
    record = verify(manifest, expected)
    require(Path(manifest).absolute().parent == ROOT, 'Execute the preparer from the selected kit')
    python = ROOT / 'runtime/python/python.exe'
    import sys
    require(Path(sys.executable).absolute() == python, 'Use the kit private Python interpreter')
    module('prepare-embedded-python.py')['verify'](python.parent, record['pythonManifestSha256'])
    powershell = ROOT / 'runtime/powershell'
    module('prepare-portable-powershell.py')['verify'](powershell, record['powershellManifestSha256'])
    origin_bundle = ROOT / 'native-package'
    rebind_api = module('rebind-asio-deployment.py')
    rebinding = rebind_api['rebind'](origin_bundle, record['nativeBundleSha256'])
    capsule_builder = module('prepare-serato-session-capsule.py')
    capsule_api = module('serato-session-capsule.py')
    application = Path(application).absolute()
    require(application.name == 'Serato DJ Pro.exe' and sha(application) == capsule_api['APP_SHA'],
            'Reviewed Serato application required')
    if not write:
        return {'planOnly': True, 'kitVerified': True, 'filesWritten': False, 'applicationStarted': False,
                'registryWritten': False, 'deviceAccess': False, 'deploymentScope': record['deploymentScope']}
    state = ROOT / 'analysis'
    state.mkdir(exist_ok=True)
    tag = uuid.uuid4().hex
    bundle = state / ('sl3-deployment-rebound-kit-' + tag)
    rebinding = rebind_api['rebind'](origin_bundle, record['nativeBundleSha256'], bundle)
    bundle_sha = rebinding['bundleManifestSha256']
    deployment = json.loads((bundle / 'deployment-plan.json').read_bytes())
    archive_directory = state / ('sl3-archive-candidate-kit-' + tag)
    phase = module('prepare-serato-installed-phase-archive.py')['prepare'](
        application, powershell, record['powershellManifestSha256'], archive_directory)
    shim = state / ('sl3-startup-shim-kit-' + tag)
    module('prepare-serato-startup-shim.py')['prepare'](
        application, str(Path(deployment['installationDirectory']) / 'sl3_asio.dll'), shim)
    capsule_directory = state / ('sl3-session-capsule-kit-' + tag)
    capsule = capsule_builder['prepare'](application, bundle, bundle_sha, capsule_directory)
    plan_api = module('prepare-serato-session-plan.py')
    # The existing binder requires the canonical installer resource basename.
    resource_directory = state / ('sl3-installer-resource-kit-' + tag)
    resource_directory.mkdir()
    resource = resource_directory / '8c7758f23375cee18a9cf3be4a3acc15.bin'
    with resource.open('xb') as stream:
        stream.write((ROOT / 'installer-resource.bin').read_bytes())
    plan = plan_api['construct'](capsule['capsule'], capsule['capsuleSha256'], shim, sha(shim / 'preparation.json'),
                                  archive_directory / 'userio_resources.bin', resource,
                                  ROOT / 'SL3_Rebuild_Development_x64.exe', python.parent / 'packages')
    path = capsule_directory / 'session-plan.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(plan, stream, sort_keys=True, indent=2)
        stream.write('\n')
    identity = sha(path)
    plan_api['verify'](path, identity)
    result = {'schema': 'sl3.portable-kit-preparation.v1', 'prepared': True, 'kitManifestSha256': expected,
              'sessionPlan': str(path), 'sessionPlanSha256': identity, 'archiveSha256': phase['archiveSha256'],
              'projectRoot': str(ROOT), 'deploymentScope': record['deploymentScope'],
              'nativePackageRebound': True, 'nativeBinariesUnchanged': rebinding['nativeBinariesUnchanged'],
              'originBundleSha256': record['nativeBundleSha256'], 'reboundBundleSha256': bundle_sha,
              'applicationStarted': False, 'registryWritten': False, 'deviceAccess': False, 'liveValidated': False,
              'planArguments': [str(ROOT / 'SL3_Rebuild_Development_x64.exe'), '--plan-session', '--session-plan', str(path),
                                '--expected-session-plan-sha256', identity, '--powershell-directory', str(powershell)]}
    result['startArguments'] = [*result['planArguments']]
    result['startArguments'][1] = '--start-session'
    result['stopArguments'] = [*result['planArguments']]
    result['stopArguments'][1] = '--stop-session'
    result['statusArguments'] = [*result['planArguments']]
    result['statusArguments'][1] = '--status-session'
    result['recoveryCheckArguments'] = [*result['planArguments']]
    result['recoveryCheckArguments'][1] = '--check-recovery'
    result['recoveryArguments'] = [*result['planArguments']]
    result['recoveryArguments'][1] = '--recover-session'
    with (capsule_directory / 'kit-preparation-complete.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit-manifest', type=Path, required=True)
    parser.add_argument('--expected-kit-manifest-sha256', required=True)
    parser.add_argument('--app', type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--start', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    require(not args.check or (args.app is not None and not args.prepare and not args.start),
            'Readiness checking requires an application and is separate from preparation/start')
    require(not args.start or (args.prepare and args.app is not None),
            'Starting requires explicit preparation and application selection')
    if args.check or args.start:
        # Complete static verification precedes host queries. Startup performs
        # the same check before creating state or requesting any elevation.
        prepare(args.kit_manifest, args.expected_kit_manifest_sha256, args.app, False)
        selected = verify(args.kit_manifest, args.expected_kit_manifest_sha256)
        readiness = module('inspect-sl3-session-readiness.py')['inspect'](
            ROOT / 'native-package', selected['nativeBundleSha256'], args.app)
        print(json.dumps(readiness, indent=2), flush=True)
        if not readiness['readyForAttempt']:
            raise SystemExit(3)
        if args.check:
            raise SystemExit(0)
    if args.app is None:
        require(not args.prepare, 'Application selection required for preparation')
        record = verify(args.kit_manifest, args.expected_kit_manifest_sha256)
        result = {'kitVerified': True, 'filesWritten': False, 'applicationStarted': False, 'deviceAccess': False}
    else:
        result = prepare(args.kit_manifest, args.expected_kit_manifest_sha256, args.app, args.prepare)
    print(json.dumps(result, indent=2), flush=True)
    if args.start:
        # The native entry verifies the complete generated session again. The
        # preparation receipt above is not a claim about the resulting live run.
        raise SystemExit(subprocess.run(result['startArguments'], creationflags=subprocess.CREATE_NO_WINDOW).returncode)
