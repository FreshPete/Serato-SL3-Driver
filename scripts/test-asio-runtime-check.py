"""Actual native system import resolution; no SL3 package code is loaded."""
from contextlib import ExitStack
import ctypes
from ctypes import wintypes as W
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/asio-runtime-check.py'


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    spec = importlib.util.spec_from_file_location('sl3_runtime_under_test', TOOL)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); s = m.stage_module()
    require(not s.elevated(), 'Unattended test requires ordinary token')
    pointer = json.loads((ROOT/'artifacts/build/deployment-tests-last.json').read_text()); index = Path(pointer['directory'])/'index.json'
    sha = lambda p: m.hashlib.sha256(p.read_bytes()).hexdigest()
    require(sha(index) == pointer['indexSha256'], 'Reviewed package test index')
    package = json.loads(index.read_text()); bundle = ROOT/package['positiveBundle']; expected = package['bundleManifestSha256']
    s.reader().verify(bundle, expected); before_bundle = {p.name: sha(p) for p in bundle.iterdir()}
    plan = json.loads((bundle/'deployment-plan.json').read_text()); locations = [Path(plan['installationDirectory']), Path(plan['pointerPath']).parent]
    before_locations = [p.exists() for p in locations]
    folder = ROOT/'artifacts/build/runtime-check-tests'/uuid.uuid4().hex; folder.mkdir(parents=True)
    cases = []; details = {}
    def case(name, action):
        value = action(); cases.append({'name': name, 'passed': True}); details[name] = value; return value
    def refused(action):
        try:
            action()
        except (ValueError, OSError) as error:
            return {'refused': True, 'error': str(error)}
        raise AssertionError('Expected runtime admission refusal')
    def command(name, args, exit_code):
        result = subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True,
                                encoding='utf-8', timeout=30)
        (folder/(name+'-stdout.txt')).write_text(result.stdout, encoding='utf-8')
        (folder/(name+'-stderr.txt')).write_text(result.stderr, encoding='utf-8')
        require(result.returncode == exit_code, name+': '+result.stderr)
        return {'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    for name, args in [('default', []), ('plan', ['--plan'])]:
        result = case(name, lambda name=name, args=args: command(name, args, 0))
        require(json.loads(result['stdout'])['planOnly'], 'Inert default/plan')
    case('explicit-check-requires-hash-and-bundle', lambda: command('missing-arguments', ['--check'], 2))
    system = case('native-system-directory', lambda: {'path': str(m.system_directory())})
    system = Path(system['path'])
    def resolve(requirements, directory=system):
        with ExitStack() as stack:
            return m.resolve(requirements, directory, stack)

    real_api = s.api; requests = []; writer_denied = []
    def audited_api(dll, name, result, args):
        function = real_api(dll, name, result, args)
        if name != 'LoadLibraryExW':
            return function
        def load(path, file, flags):
            require(flags == 0x800 and file is None, 'Normal System32 loader flags only')
            candidate = Path(path)
            require(candidate.parent == system if candidate.is_absolute() else path.startswith(('api-', 'ext-')),
                    'Only System32 paths/API contracts are loaded')
            requests.append({'request': path, 'flags': flags})
            return function(path, file, flags)
        return load
    def payload_modules():
        return {name: bool(real_api('kernel32.dll', 'GetModuleHandleW', W.HMODULE, [W.LPCWSTR])(str(bundle/name)))
                for name in ('sl3_asio.dll', 'UsbDkHelper.dll', 'sl3_usbdk.exe', 'sl3_broker_controller.exe')}
    modules_before = payload_modules(); require(not any(modules_before.values()), 'No package modules loaded before test')
    real_resolve = m.resolve
    def held_source_probe(requirements, directory, stack):
        try:
            with (bundle/'sl3_asio.dll').open('r+b'):
                pass
        except PermissionError:
            writer_denied.append(True)
        require(writer_denied, 'Source bytes remain pinned while checking runtime')
        return real_resolve(requirements, directory, stack)
    try:
        s.api = audited_api; m.resolve = held_source_probe
        value = case('actual-reviewed-bundle-runtime-resolution', lambda: m.check(bundle, expected))
    finally:
        s.api = real_api; m.resolve = real_resolve
    require(value['passed'] and value['directImportsResolved'] and len(requests) == len(value['dependencies']) and
            not value['packageBinaryLoaded'] and payload_modules() == modules_before, 'Actual system-only resolution, package remains unloaded')
    require({'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}.issubset({x['importName'] for x in value['dependencies']}), 'VC runtime imports included')
    (folder/'loader-requests.json').write_text(json.dumps(requests, indent=2)+'\n', encoding='utf-8')
    cli = case('actual-reviewed-bundle-cli', lambda: command('actual-check', ['--check', '--bundle', bundle, '--expected-bundle-sha256', expected], 0))
    require(json.loads(cli['stdout'])['packageId'] == plan['packageId'], 'Actual CLI bound to reviewed package')
    called = []
    try:
        m.resolve = lambda *args: called.append(True)
        case('wrong-bundle-hash-before-system-load', lambda: refused(lambda: m.check(bundle, '0'*64)))
    finally:
        m.resolve = real_resolve
    require(not called, 'Bad bundle never reaches system loading')
    changed = folder/'changed-bundle'; shutil.copytree(bundle, changed); (changed/'README.txt').write_bytes(b'changed')
    case('changed-bundle-refused', lambda: refused(lambda: m.check(changed, expected)))
    case('missing-system-dll-no-fallback', lambda: refused(lambda: resolve({'sl3_runtime_deliberately_absent_7d62401e.dll': ['Missing']})))
    case('missing-named-export-refused', lambda: refused(lambda: resolve({'kernel32.dll': ['SL3_Deliberately_Absent_7d62401e']})))
    case('missing-ordinal-refused', lambda: refused(lambda: resolve({'kernel32.dll': [65535]})))
    case('unsafe-import-path-refused', lambda: refused(lambda: resolve({'../kernel32.dll': ['GetCurrentProcessId']})))
    case('non-system-directory-refused', lambda: refused(lambda: resolve({'kernel32.dll': ['GetCurrentProcessId']}, folder)))
    case('missing-api-contract-refused', lambda: refused(lambda: resolve({'api-ms-win-sl3-deliberately-absent-l1-1-0.dll': ['Missing']})))
    import pefile
    pe = pefile.PE(str(system/'kernel32.dll'))
    ordinal = next(x.ordinal for x in pe.DIRECTORY_ENTRY_EXPORT.symbols if x.name == b'GetCurrentProcessId')
    case('actual-present-ordinal-resolves', lambda: resolve({'kernel32.dll': [ordinal]}))
    payload = {name: (bundle/name).read_bytes() for name in ('sl3_asio.dll', 'sl3_broker_controller.exe', 'sl3_usbdk.exe', 'UsbDkHelper.dll')}
    local = dict(payload); local['kernel32.dll'] = b'not loaded'
    case('local-import-needs-explicit-supported-gate', lambda: refused(lambda: m.imports(local)))
    bad_import = dict(payload); require(b'ADVAPI32.dll' in bad_import['sl3_asio.dll'], 'First-party fixture import string')
    bad_import['sl3_asio.dll'] = bad_import['sl3_asio.dll'].replace(b'ADVAPI32.dll', b'../evil!.dll')
    case('first-party-pe-import-traversal-refused', lambda: refused(lambda: m.imports(bad_import)))
    require(before_bundle == {p.name: sha(p) for p in bundle.iterdir()}, 'Source bundle unchanged')
    require([p.exists() for p in locations] == before_locations, 'Planned installation/profile locations unchanged')
    require(payload_modules() == modules_before, 'No package module remains loaded')
    (folder/'case-details.json').write_text(json.dumps(details, indent=2)+'\n', encoding='utf-8')
    result = {'schema': 'sl3.runtime-check-tests.v1', 'cases': cases,
              'files': {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob('*') if p.is_file()},
              'sourceSha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in [TOOL, Path(__file__), ROOT/'scripts/asio-file-stage.py']},
              'nonElevated': True, 'systemDependencyNames': len(value['dependencies']), 'uniqueSystemFiles': len(value['systemFiles']),
              'resolvedDirectSymbolReferences': sum(x['resolvedSymbolCount'] for x in value['dependencies']),
              'sourceBundleUnchanged': True, 'plannedLocationsUnchanged': True, 'packageModulesAbsentBeforeAndAfter': True,
              'systemDllInitializationAllowed': True, 'packageBinaryExecuted': False, 'packageBinaryLoaded': False,
              'dependencyFunctionsInvoked': False, 'registryWritten': False, 'deviceAccess': False}
    index = folder/'index.json'; index.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/runtime-check-tests-last.json').write_text(json.dumps(
        {'directory': str(folder), 'indexSha256': sha(index)}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'dependencies': result['systemDependencyNames'],
                      'resolvedDirectSymbols': result['resolvedDirectSymbolReferences'], 'evidenceDirectory': str(folder)}))


if __name__ == '__main__':
    main()
