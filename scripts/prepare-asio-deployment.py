"""Prepare/verify a local review bundle. Never installs, executes or registers it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
CLSID = '{5A551CD0-F83E-48EB-8B9D-8614E07852FE}'
NAME = 'SL3 Rebuild Development'
HELPER_SHA = '66bbfe6f99b417f97c7a9e97816e24af7dde0e01b8e535c41e91e1c6c19cfeda'
PROPOSED_ACL = {'owner': 'BUILTIN\\Administrators', 'protected': True,
                'fullControl': ['SYSTEM', 'BUILTIN\\Administrators'], 'readExecute': ['BUILTIN\\Users']}
LIMIT = 16*1024*1024
REQUIRED = {'sl3_asio.dll', 'sl3_broker_controller.exe', 'sl3_usbdk.exe', 'UsbDkHelper.dll',
            'sl3-asio.conf', 'PROJECT-LICENSE.txt', 'USBDK-LICENSE.txt', 'THIRD-PARTY-NOTICES.txt',
            'deployment-plan.json', 'provenance.json', 'README.txt'}
ACTIVATION_REQUIRED = REQUIRED | {'sl3-worker.conf', 'sl3-timing.conf'}
ACTIVATION_MODE = 'asio-init-v1'


def required_files(manifest):
    """Select a fixed inventory before using any manifest-controlled filename."""
    if manifest.get('schema') == 'sl3.deployment-bundle.v1':
        require('activationMode' not in manifest, 'Legacy bundle cannot select activation')
        return REQUIRED
    require(manifest.get('schema') == 'sl3.deployment-bundle.v2' and
            manifest.get('activationMode') == ACTIVATION_MODE and
            manifest.get('timingMode') == 'unmeasured-diagnostic-44100-128', 'Unsupported deployment bundle mode/version')
    return ACTIVATION_REQUIRED


def allowed_receipt_inventory(names):
    # Receipts are read before their captured manifest can be verified. Admit
    # only these two complete fixed sets, never arbitrary receipt filenames.
    return set(names) in (REQUIRED | {'bundle-manifest.json'}, ACTIVATION_REQUIRED | {'bundle-manifest.json'})


def require_session_locator(plan):
    require(plan.get('activationMode') is None and plan.get('automaticStart') is False and
            plan.get('rateProfileIncluded') is False, 'Temporary session requires its externally owned locator package')


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha_value(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'Expected lowercase SHA256')
    return value


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True)+'\n').encode('utf-8')


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicate JSON field')
        result[key] = value
    return result


def record(data):
    return json.loads(data.decode('utf-8-sig'), object_pairs_hook=pairs)


def read(path, maximum=LIMIT):
    require(path.is_file(), f'Missing regular input: {path.name}')
    with path.open('rb') as stream:
        data = stream.read(maximum+1)
    require(0 < len(data) <= maximum, f'Input size limit: {path.name}')
    return data


def inside(path, parent):
    require(path.is_absolute(), 'Absolute paths required')
    require('..' not in path.parts, 'Parent traversal is not a deployment destination')
    result = path.resolve()
    require(result.is_relative_to(parent.resolve()) and result != parent.resolve(), 'Path escapes intended directory')
    return path


def pointer_destination(path, parent):
    """Validate the logical pointer name without canonicalizing its file leaf.

    Packaged Windows callers can see a regular file through a redirected leaf
    while its directory resolves to the native Local AppData path. Parent
    containment still follows junctions; a reparse leaf is never admitted.
    Actual pointer withdrawal independently verifies ownership and contents.
    """
    require(path.is_absolute(), 'Absolute paths required')
    require('..' not in path.parts, 'Parent traversal is not a deployment destination')
    require(path.parent.resolve().is_relative_to(parent.resolve()), 'Path escapes intended directory')
    try:
        info = path.lstat()
    except FileNotFoundError:
        pass
    else:
        require(stat.S_ISREG(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 0x400),
                'Pointer must be a regular non-reparse file')
    return path


def pe_info(data, role):
    import pefile  # Analysis/build dependency only; no binary is executed or loaded.
    pe = pefile.PE(data=data)
    require(pe.FILE_HEADER.Machine == 0x8664 and pe.OPTIONAL_HEADER.Magic == 0x20b, 'Windows x64 PE required')
    library = bool(pe.FILE_HEADER.Characteristics & 0x2000)
    require(library == (role in ('asio', 'helper')), 'Wrong executable/DLL role')
    exports = sorted(x.name.decode('ascii') for x in getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', []) if x.name)
    require(not any(x.startswith('sl3_test_') for x in exports), 'Simulated-provider exports cannot be packaged')
    if role == 'asio':
        require(exports == ['DllCanUnloadNow', 'DllGetClassObject'], 'Production ASIO export contract')
    imports = sorted({entry.dll.decode('ascii') for attr in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT') for entry in getattr(pe, attr, [])})
    return {'machine': 'amd64', 'dll': library, 'exports': exports, 'imports': imports}


def destinations(installation, pointer):
    require(os.name == 'nt', 'Windows deployment preparation only')
    program_files = Path(os.environ['ProgramFiles']).resolve()/'SL3 Rebuild'
    user_data = Path(os.environ['LOCALAPPDATA']).resolve()/'SL3Rebuild'
    installation = inside(installation, program_files)
    pointer = pointer_destination(pointer, user_data)
    require(pointer.name not in ('', '.', '..'), 'Pointer filename required')
    for path in (installation, pointer):
        require(len(path.drive) == 2 and path.drive[1] == ':' and ':' not in str(path)[2:] and
                not any(ord(c) < 32 for c in str(path)), 'Local drive paths without streams/control characters required')
    return installation, pointer


def registry_entries(installation, identity):
    com = 'SOFTWARE\\Classes\\CLSID\\'+CLSID
    return [{'key': com, 'strings': {'': NAME, 'SL3PackageId': identity}},
            {'key': com+'\\InprocServer32', 'strings': {'': str(installation/'sl3_asio.dll'), 'ThreadingModel': 'Both'}},
            {'key': 'SOFTWARE\\ASIO\\'+NAME, 'strings': {'CLSID': CLSID, 'Description': NAME, 'SL3PackageId': identity}}]


def locator_text(installation, pointer, controller_sha, worker_sha):
    return ('SL3-ASIO-LOCATOR-1\nsession_pointer='+str(pointer)+'\nbroker='+str(installation/'sl3_broker_controller.exe')+
            '\nbroker_sha256='+controller_sha+'\nworker_sha256='+worker_sha+'\n').encode('utf-8')


def activation_records(installation, controller_sha, worker_sha):
    """Records bind final protected destinations, without a session pointer."""
    timing = ('SL3-ASIO-DIAGNOSTIC-TIMING-1\nworker_sha256=' + worker_sha + '\nhelper_sha256=' + HELPER_SHA +
              '\nrate_hz=44100\nbuffer_frames=128\n').encode('utf-8')
    worker = ('SL3-ASIO-CONFIG-1\nworker=' + str(installation/'sl3_usbdk.exe') + '\nworker_sha256=' + worker_sha +
              '\nhelper=' + str(installation/'UsbDkHelper.dll') + '\ntiming_record=' + str(installation/'sl3-timing.conf') +
              '\ntiming_record_sha256=' + digest(timing) + '\n').encode('utf-8')
    entry = ('SL3-ASIO-ACTIVATION-1\ncontroller=' + str(installation/'sl3_broker_controller.exe') +
             '\ncontroller_sha256=' + controller_sha + '\ninput=' + str(installation/'sl3-worker.conf') +
             '\ninput_sha256=' + digest(worker) + '\nstartup_timeout_ms=15000\nstartup_failure_grace_ms=5000\nlifetime_ms=600000\n').encode('utf-8')
    return {'sl3-asio.conf': entry, 'sl3-worker.conf': worker, 'sl3-timing.conf': timing}


def prepare(manifest, expected, helper, output, installation, pointer, unmeasured=False):
    installation, pointer = destinations(installation, pointer)
    output = inside(output, ROOT/'artifacts/build/deployment-bundles')
    require(not output.exists(), 'Bundle directory must be new; existing bytes are preserved')
    require(helper.is_absolute() and len(helper.drive) == 2 and helper.drive[1] == ':' and ':' not in str(helper)[2:], 'Absolute local helper path required')
    manifest = inside(manifest, ROOT/'artifacts/build')
    raw = read(manifest); require(digest(raw) == sha_value(expected), 'Reviewed build manifest hash mismatch')
    build = record(raw)
    require(build['configuration'] == 'Release' and build['architecture'] == 'x64' and build['coreTestsPassed'] is True,
            'A tested Windows x64 Release build is required')
    require(build['asioComponent']['built'] is True and build['asioComponent']['testsPassed'] is True, 'ASIO component tests required')
    for name, expected_sha in build['inputs'].items():
        source = inside(ROOT/name, ROOT)
        require(digest(read(source)) == expected_sha.lower(), f'Build source pin changed: {name}')
    require(digest(read(ROOT/'scripts/build-native.ps1')) == build['buildScriptSha256'].lower(), 'Build script changed')
    require(digest(read(ROOT/'scripts/test-broker-controller.py')) == build['brokerController']['testScriptSha256'].lower(), 'Controller test script changed')
    log = read(manifest.parent/'ctest-Release.log')
    require(digest(log) == build['ctestLogSha256'].lower(), 'CTest log hash changed')
    count = re.findall(rb'100% tests passed, 0 tests failed out of (\d+)', log)
    require(len(count) == 1 and int(count[0]) == len(build['ctestTests']), 'Complete successful CTest log required')
    require({'sl3_driver_configuration_tests', 'sl3_asio_activation_sta', 'sl3_asio_activation_mta',
             'sl3_broker_controller_lifecycle'}.issubset(build['ctestTests']), 'Required COM/locator/controller coverage missing')
    sources = {
        'sl3_asio.dll': ('asio', manifest.parent/'Release/sl3_asio.dll', build['asioComponent']['comDllSha256'].lower()),
        'sl3_broker_controller.exe': ('controller', manifest.parent/'Release/sl3_broker_controller.exe', build['brokerController']['executableSha256'].lower()),
        'sl3_usbdk.exe': ('worker', manifest.parent/'Release/sl3_usbdk.exe', build['usbdk']['executableSha256'].lower()),
        'UsbDkHelper.dll': ('helper', helper, HELPER_SHA),
    }
    if unmeasured:
        diagnostic = build.get('unmeasuredAsioDiagnostic', {})
        require(diagnostic.get('rateHz') == 44100 and diagnostic.get('bufferFrames') == 128
                and diagnostic.get('maximumLifetimeMs') == 600000 and diagnostic.get('latencyAvailable') is False
                and diagnostic.get('simulatedCallbacksPassed') is True and diagnostic.get('nativePositiveRun') is False
                and diagnostic.get('installed') is False, 'Tested unmeasured diagnostic build required')
        require({'sl3_asio_unmeasured_absent', 'sl3_broker_unmeasured_plan',
                 'sl3_broker_unmeasured_rejects_long_lifetime', 'sl3_broker_unmeasured_lifecycle'}.issubset(build['ctestTests']),
                'Required unmeasured diagnostic coverage missing')
        dll_sha = sha_value(diagnostic['dllSha256'].lower())
        broker_sha = sha_value(diagnostic['brokerSha256'].lower())
        require(dll_sha != sources['sl3_asio.dll'][2] and broker_sha not in (
            sources['sl3_broker_controller.exe'][2], sha_value(diagnostic['simulatedBrokerSha256'].lower())),
            'Expected distinct native diagnostic DLL and controller')
        sources['sl3_asio.dll'] = ('asio', manifest.parent/'unmeasured/Release/sl3_asio.dll', dll_sha)
        sources['sl3_broker_controller.exe'] = (
            'controller', manifest.parent/'Release/sl3_broker_controller_unmeasured.exe', broker_sha)
    payload = {}; images = {}
    for name, (role, path, expected_sha) in sources.items():
        data = read(path); require(digest(data) == expected_sha, f'Payload hash mismatch: {name}')
        require(role != 'controller' or expected_sha != build['brokerController']['simulatedExecutableSha256'].lower(), 'Simulated controller refused')
        images[name] = pe_info(data, role); payload[name] = data
    payload['PROJECT-LICENSE.txt'] = read(ROOT/'LICENSE')
    payload['USBDK-LICENSE.txt'] = read(ROOT/'third_party/usbdk/LICENSE')
    seed = {'builderSha256': digest(read(Path(__file__))), 'buildManifestSha256': digest(raw),
            'payloadHashes': {k: digest(v) for k, v in payload.items()},
            'installationDirectory': str(installation), 'pointerPath': str(pointer)}
    diagnostic_label = {'timingMode': 'unmeasured-diagnostic-44100-128'} if unmeasured else {}
    seed.update(diagnostic_label)
    identity = digest(encoded(seed))
    payload['sl3-asio.conf'] = locator_text(installation, pointer, digest(payload['sl3_broker_controller.exe']), digest(payload['sl3_usbdk.exe']))
    payload['provenance.json'] = encoded({'schema': 'sl3.deployment-provenance.v1', 'identitySeed': seed,
                                         'nativeTestsPassed': len(build['ctestTests']), 'ctestLogSha256': digest(log), 'images': images})
    payload['THIRD-PARTY-NOTICES.txt'] = ("UsbDkHelper.dll: unchanged Daynix/Red Hat UsbDk 1.0.22 helper.\n"
        "SHA256: "+HELPER_SHA+"\nApache-2.0 text: USBDK-LICENSE.txt.\n"
        "A separately installed signed UsbDk filter is required and is not included.\n"
        "The official ASIO SDK and Serato/Rane installers or binaries are not bundled.\n").encode('utf-8')
    payload['deployment-plan.json'] = encoded({'schema': 'sl3.deployment-plan.v1', 'packageId': identity,
        'installationDirectory': str(installation), 'pointerPath': str(pointer), 'requiresAdministratorAtInstall': True,
        'proposedAcl': PROPOSED_ACL,
        'registryView': 64, 'registryHive': 'HKEY_LOCAL_MACHINE', 'registryEntries': registry_entries(installation, identity),
        'requiredInstallChecks': ['new destination', 'protected administrator-owned executable files', 'no registry conflicts',
                                 'all payload hashes', 'VC runtime availability', 'separate user-owned session pointer',
                                 'owned-entry uninstall and conflict preservation'],
        'automaticStart': False, 'serviceCreated': False, 'rateProfileIncluded': False, 'registryApplied': False,
        **diagnostic_label})
    notice = "UNMEASURED 44.1 kHz DIAGNOSTIC ONLY. Broker lifetime is limited to ten minutes.\n" if unmeasured else ""
    payload['README.txt'] = (notice+"LOCAL REVIEW BUNDLE - NOT INSTALLED; NOT A WORKING DRIVER RELEASE.\n"
        "Copy/ACL/registration installation and owned-entry uninstall still need implementation.\n"
        "The proposed locator references the reviewed future installation, not this bundle.\n"
        "No measured timing/profile, current Serato admission, physical audio or DVS is certified.\n"
        "First-party PE import tables list required VC runtime DLLs in provenance.json.\n"
        "No runtime installer, driver SYS, firmware or vendor application is included.\n"
        "Do not register the DLL in this writable review directory.\n").encode('utf-8')
    require(set(payload) == REQUIRED, 'Internal package inventory mismatch')
    result = {'schema': 'sl3.deployment-bundle.v1', 'packageId': identity,
              'files': {name: {'bytes': len(data), 'sha256': digest(data)} for name, data in payload.items()},
              'installed': False, 'registryWritten': False, 'binaryExecuted': False, 'protectedInstallationCreated': False,
              'physicalAudioTested': False, 'currentSeratoAdmissionTested': False, **diagnostic_label}
    output.parent.mkdir(parents=True, exist_ok=True); output.mkdir()
    for name, data in payload.items():
        with (output/name).open('xb') as stream:
            stream.write(data)
    with (output/'bundle-manifest.json').open('xb') as stream:
        stream.write(encoded(result))  # Published last; partial output is retained on I/O failure.
    expected_bundle = digest(encoded(result)); verify(output, expected_bundle)
    return {'prepared': True, 'directory': str(output), 'bundleManifestSha256': expected_bundle,
            'files': len(payload), 'installed': False, 'registryWritten': False, 'binaryExecuted': False, **diagnostic_label}


def capture_bundle(bundle, expected):
    """Capture hash-bound bytes only; this does not admit deployment paths."""
    require(bundle.is_absolute() and bundle.is_dir(), 'Absolute existing bundle directory required')
    for path in (bundle, bundle/'bundle-manifest.json'):
        require(not path.is_symlink() and not (getattr(path.stat(), 'st_file_attributes', 0) & 0x400), 'Reparse bundle/manifest refused')
    raw = read(bundle/'bundle-manifest.json'); require(digest(raw) == sha_value(expected), 'Bundle manifest hash mismatch')
    manifest = record(raw)
    inventory = required_files(manifest)
    require(set(manifest['files']) == inventory, 'Bundle schema/inventory mismatch')
    require(all(manifest[k] is False for k in ('installed', 'registryWritten', 'binaryExecuted', 'protectedInstallationCreated', 'physicalAudioTested', 'currentSeratoAdmissionTested')), 'Review bundle cannot claim installation or hardware validation')
    require({x.name for x in bundle.iterdir()} == inventory | {'bundle-manifest.json'}, 'Unexpected or missing bundle file')
    payload = {}
    for name, details in manifest['files'].items():
        path = bundle/name
        require(not path.is_symlink() and not (getattr(path.stat(), 'st_file_attributes', 0) & 0x400), 'Reparse payload refused')
        data = read(path); require(len(data) == details['bytes'] and digest(data) == sha_value(details['sha256']), f'Payload changed: {name}')
        payload[name] = data
    return manifest, payload


def verify(bundle, expected):
    manifest, payload = capture_bundle(bundle, expected)
    return verify_payloads(manifest, payload)


def verify_payloads(manifest, payload):
    """Verify captured bytes; privileged staging must not re-open source paths."""
    inspection = inspect_portable_payloads(manifest, payload)
    destinations(Path(inspection['installationDirectory']), Path(inspection['pointerPath']))
    return {'verified': True, 'files': len(payload), 'installed': False, 'registryWritten': False, 'binaryExecuted': False}


def inspect_portable_payloads(manifest, payload):
    """Check portable metadata/PE bytes; never authorizes staging or old paths."""
    inventory = required_files(manifest)
    require(set(manifest['files']) == inventory and set(payload) == inventory, 'Bundle schema/inventory mismatch')
    require(all(manifest[k] is False for k in ('installed', 'registryWritten', 'binaryExecuted', 'protectedInstallationCreated', 'physicalAudioTested', 'currentSeratoAdmissionTested')), 'Review bundle cannot claim installation or hardware validation')
    for name, data in payload.items():
        details = manifest['files'][name]
        require(0 < len(data) <= LIMIT and len(data) == details['bytes'] and digest(data) == sha_value(details['sha256']), 'Captured payload hash/size mismatch: '+name)
    provenance = record(payload['provenance.json']); seed = provenance['identitySeed']
    require(provenance['schema'] == 'sl3.deployment-provenance.v1', 'Provenance schema mismatch')
    require(set(seed['payloadHashes']) == {'sl3_asio.dll', 'sl3_broker_controller.exe', 'sl3_usbdk.exe', 'UsbDkHelper.dll',
                                         'PROJECT-LICENSE.txt', 'USBDK-LICENSE.txt'}, 'Provenance seed inventory mismatch')
    sha_value(seed['builderSha256']); sha_value(seed['buildManifestSha256'])
    require(digest(encoded(seed)) == manifest['packageId'], 'Package identity mismatch')
    for name, expected_sha in seed['payloadHashes'].items():
        require(name in payload and digest(payload[name]) == expected_sha, 'Seed payload mismatch')
    for name, role in [('sl3_asio.dll', 'asio'), ('sl3_broker_controller.exe', 'controller'), ('sl3_usbdk.exe', 'worker'), ('UsbDkHelper.dll', 'helper')]:
        require(pe_info(payload[name], role) == provenance['images'][name], 'PE metadata mismatch')
    require(digest(payload['UsbDkHelper.dll']) == HELPER_SHA, 'Unreviewed helper payload')
    plan = record(payload['deployment-plan.json'])
    timing_mode = seed.get('timingMode')
    require(timing_mode in (None, 'unmeasured-diagnostic-44100-128') and
            timing_mode == manifest.get('timingMode') == plan.get('timingMode'), 'Bundle timing mode mismatch')
    activation = manifest['schema'] == 'sl3.deployment-bundle.v2'
    require(seed.get('activationMode') == manifest.get('activationMode') == plan.get('activationMode'), 'Activation mode mismatch')
    if activation:
        sha_value(seed['activationToolSha256']); sha_value(seed['activationOriginBundleSha256']); sha_value(seed['activationContractSha256'])
    installation = Path(seed['installationDirectory'])
    pointer = Path(seed['pointerPath'])
    # Inspect foreign destination text without opening or following those paths.
    # Production verification above always applies the current user's containment.
    for path in (installation, pointer):
        require(path.is_absolute() and len(path.drive) == 2 and path.drive[1] == ':' and
                '..' not in path.parts and ':' not in str(path)[2:] and
                not any(ord(char) < 32 for char in str(path)), 'Local portable destination syntax required')
    if activation:
        expected_records = activation_records(installation, digest(payload['sl3_broker_controller.exe']), digest(payload['sl3_usbdk.exe']))
        require(all(payload[name] == data for name, data in expected_records.items()), 'Activation records do not bind protected destinations/binaries/timing')
    else:
        require(payload['sl3-asio.conf'] == locator_text(installation, pointer, digest(payload['sl3_broker_controller.exe']), digest(payload['sl3_usbdk.exe'])), 'Locator does not bind planned binaries/pointer')
    require(plan['schema'] == 'sl3.deployment-plan.v1' and plan['packageId'] == manifest['packageId'] and
            plan['registryView'] == 64 and plan['registryHive'] == 'HKEY_LOCAL_MACHINE' and plan['registryApplied'] is False and
            plan['registryEntries'] == registry_entries(installation, manifest['packageId']) and
            plan['installationDirectory'] == str(installation) and plan['pointerPath'] == str(pointer), 'Plan identity/view/entries mismatch')
    require(plan['proposedAcl'] == PROPOSED_ACL and plan['requiresAdministratorAtInstall'] is True and
            plan['serviceCreated'] is False and plan['automaticStart'] is activation and
            plan['rateProfileIncluded'] is activation, 'Unsafe installation policy proposed')
    if activation:
        require(plan.get('activationTrigger') == 'IASIO.init' and plan.get('maximumLifetimeMs') == 600000 and
                plan.get('sessionPointerUsed') is False and plan.get('latencyAvailable') is False,
                'Explicit bounded diagnostic activation policy required')
    return {'portableContractVerified': True, 'installationDirectory': str(installation), 'pointerPath': str(pointer),
            'productionDestinationsAdmitted': False, 'binaryExecuted': False}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv == ['--plan']:
        print(json.dumps({'schema': 'sl3.deployment-builder-plan.v1', 'planOnly': True, 'filesWritten': False,
                          'binaryExecuted': False, 'registryWritten': False, 'deviceAccess': False})); return
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_const', const='prepare', dest='mode')
    mode.add_argument('--verify', action='store_const', const='verify', dest='mode')
    parser.add_argument('--unmeasured-diagnostic', action='store_true')
    for name in ['manifest', 'expected-build-sha256', 'helper', 'output', 'install-directory', 'pointer', 'bundle', 'expected-bundle-sha256']:
        parser.add_argument('--'+name)
    args = vars(parser.parse_args(argv)); operation = args.pop('mode')
    unmeasured = args.pop('unmeasured_diagnostic')
    require(not unmeasured or operation == 'prepare', 'Diagnostic selection applies only to preparation')
    fields = ({'manifest', 'expected_build_sha256', 'helper', 'output', 'install_directory', 'pointer'} if operation == 'prepare'
              else {'bundle', 'expected_bundle_sha256'})
    require({k for k, v in args.items() if v is not None} == fields, 'Exactly the selected operation options are required')
    if operation == 'prepare':
        result = prepare(Path(args['manifest']), args['expected_build_sha256'], Path(args['helper']), Path(args['output']),
                         Path(args['install_directory']), Path(args['pointer']), unmeasured)
    else:
        result = verify(Path(args['bundle']), args['expected_bundle_sha256'])
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
