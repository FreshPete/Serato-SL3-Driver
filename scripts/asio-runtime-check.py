"""Reviewed-package direct import resolution using only native System32 DLLs."""
import argparse
from contextlib import ExitStack
import ctypes
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

MAX_SYSTEM_IMAGE = 32*1024*1024


def stage_module():
    name = 'sl3_runtime_check_stage'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name('asio-file-stage.py'))
        module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return sys.modules[name]


def system_directory():
    s = stage_module(); s.require(ctypes.sizeof(s.P) == 8, 'Native x64 runtime checker required')
    value = ctypes.create_unicode_buffer(32768)
    count = s.api('kernel32.dll', 'GetSystemDirectoryW', W.UINT, [W.LPWSTR, W.UINT])(value, len(value))
    s.require(0 < count < len(value), 'Native system directory query failed')
    return s.local(Path(value.value))


def imports(payload):
    import pefile
    s = stage_module(); result = {}
    for name in ('sl3_asio.dll', 'sl3_broker_controller.exe', 'sl3_usbdk.exe', 'UsbDkHelper.dll'):
        pe = pefile.PE(data=payload[name]); s.require(pe.FILE_HEADER.Machine == 0x8664, 'AMD64 package image required')
        symbols = {}
        for attr in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT'):
            for entry in getattr(pe, attr, []):
                library = entry.dll.decode('ascii').lower()
                s.require(re.fullmatch(r'[a-z0-9_.-]+\.dll', library) is not None and '..' not in library, 'Plain DLL import basename required')
                s.require(library not in {n.lower() for n in payload}, 'Local imported dependencies need a separate nonexecuting gate')
                for item in entry.imports:
                    symbol = item.name.decode('ascii') if item.name else item.ordinal
                    s.require((isinstance(symbol, str) and 0 < len(symbol) <= 512 and '\0' not in symbol) or
                              (type(symbol) is int and 1 <= symbol <= 65535), 'Bounded imported name/ordinal required')
                    symbols.setdefault(library, set()).add(symbol)
        result[name] = {dll: sorted(values, key=str) for dll, values in sorted(symbols.items())}
    s.require(len({dll for image in result.values() for dll in image}) <= 64 and
              sum(len(values) for image in result.values() for values in image.values()) <= 4096, 'Import count limits')
    return result


def safe_system_file(handle, trusted):
    s = stage_module(); file = s.information(handle, False); data = s.security_info(handle)
    s.require(data['owner'] in trusted and not data['nullDacl'], 'System DLL owner/DACL not trusted')
    mutation = 0x50000000 | 2 | 4 | 0x10 | 0x100 | 0x10000 | 0x40000 | 0x80000
    for ace in data['aces']:
        if ace['type'] == 1 or ace['flags'] & 8:
            continue
        sid = data['owner'] if ace['sid'] in ('S-1-3-0', 'S-1-3-4') else ace['sid']
        s.require(sid in trusted or not ace['mask'] & mutation, 'Untrusted mutation rights on System32 dependency')
    raw = s.read_handle(handle, MAX_SYSTEM_IMAGE)
    import pefile
    pe = pefile.PE(data=raw)
    s.require(pe.FILE_HEADER.Machine == 0x8664 and pe.OPTIONAL_HEADER.Magic == 0x20b and
              pe.FILE_HEADER.Characteristics & 0x2000, 'Native AMD64 system DLL required')
    exports = getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', [])
    return {'file': file, 'sha256': hashlib.sha256(raw).hexdigest(), 'security': data,
            'exports': {x.name.decode('ascii') for x in exports if x.name}, 'ordinals': {x.ordinal for x in exports}}


def resolve(requirements, system, stack):
    """Only the verified package parser supplies requirements in production."""
    s = stage_module(); actual = system_directory()
    s.require(system == actual, 'Only the native system directory is supported')
    trusted = {s.SYSTEM, s.ADMINS, s.account_sid('NT SERVICE\\TrustedInstaller')}
    parents = stack.enter_context(s.pinned_parents(system/'runtime-check-anchor'))
    ancestors = [s.safe_parent(handle, trusted) for handle in parents]
    system_handle = parents[-1]
    s.require(Path(s.information(system_handle, True)['path']) == system, 'Pinned native system directory mismatch')
    files = {}; modules = {}; checked = []
    def pin(path):
        key = str(path).casefold()
        if key not in files:
            s.require(path.parent == system, 'Resolved module outside native system directory')
            handle = stack.enter_context(s.open_file(path))
            value = safe_system_file(handle, trusted)
            s.require(Path(value['file']['path']) == path, 'System dependency final path mismatch')
            files[key] = value
        return files[key]
    for dll, symbols in sorted(requirements.items()):
        s.require(re.fullmatch(r'[a-z0-9_.-]+\.dll', dll) is not None and '..' not in dll, 'Plain lowercase DLL basename required')
        contract = dll.startswith(('api-', 'ext-'))
        if not contract:
            pin(system/dll)  # Lease the exact checked file before loading.
        request = dll if contract else str(system/dll)
        module = s.check(s.api('kernel32.dll', 'LoadLibraryExW', W.HMODULE, [W.LPCWSTR, W.HANDLE, W.DWORD])(request, None, 0x800))
        stack.callback(lambda module=module: s.check(s.api('kernel32.dll', 'FreeLibrary', W.BOOL, [W.HMODULE])(module)))
        path = ctypes.create_unicode_buffer(32768)
        count = s.api('kernel32.dll', 'GetModuleFileNameW', W.DWORD, [W.HMODULE, W.LPWSTR, W.DWORD])(module, path, len(path))
        s.require(0 < count < len(path), 'Loaded system module path query failed')
        host = s.local(Path(path.value)); info = pin(host)
        s.require(contract or host == system/dll, 'Direct dependency resolved to another path')
        for symbol in symbols:
            if type(symbol) is int:
                s.require(1 <= symbol <= 65535 and symbol in info['ordinals'], 'Absent ordinal export: '+dll+'!'+str(symbol))
                pointer = s.P(symbol)
            else:
                s.require(isinstance(symbol, str) and symbol in info['exports'], 'Absent named export: '+dll+'!'+str(symbol))
                buffer = ctypes.create_string_buffer(symbol.encode('ascii')); pointer = ctypes.cast(buffer, s.P)
            address = s.api('kernel32.dll', 'GetProcAddress', s.P, [W.HMODULE, s.P])(module, pointer)
            s.require(bool(address), 'Loader could not resolve '+dll+'!'+str(symbol))
        modules[dll] = module
        checked.append({'importName': dll, 'apiSetContract': contract, 'resolvedHost': str(host),
                        'resolvedSymbols': symbols, 'resolvedSymbolCount': len(symbols), 'hostSha256': info['sha256']})
    return {'dependencies': checked, 'systemFiles': [{k: v for k, v in value.items() if k not in ('exports', 'ordinals')}
                                                   for _, value in sorted(files.items())],
            'ancestorChecks': ancestors}


def check(bundle, expected):
    s = stage_module()
    with ExitStack() as stack:
        module, manifest, payload = s.snapshot_bundle(bundle, expected, stack)
        per_image = imports(payload); required = {}
        for image in per_image.values():
            for dll, symbols in image.items():
                required.setdefault(dll, set()).update(symbols)
        required = {dll: sorted(symbols, key=str) for dll, symbols in required.items()}
        result = resolve(required, system_directory(), stack)
        result.update(schema='sl3.runtime-check.v1', passed=True, packageId=manifest['packageId'],
                      bundleManifestSha256=expected, perImageImports=per_image, systemDirectory=str(system_directory()),
                      directImportsResolved=True, packageBinaryExecuted=False, packageBinaryLoaded=False,
                      systemDllInitializationAllowed=True, systemDependenciesLoaded=True,
                      dependencyFunctionsInvoked=False, loadedMemoryAttested=False, wholeRuntimeBehaviorVerified=False,
                      delayedTransitiveImportsExercised=False, installedAsioActivationTested=False,
                      filesWritten=False, registryWritten=False, deviceAccess=False)
    return result  # Own library references and file leases have been released.


def main():
    if sys.argv[1:] in ([], ['--plan']):
        print(json.dumps({'schema': 'sl3.runtime-check-plan.v1', 'planOnly': True, 'filesWritten': False,
                          'registryWritten': False, 'deviceAccess': False, 'packageBinaryExecuted': False})); return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--expected-bundle-sha256', required=True)
    args = parser.parse_args(); print(json.dumps(check(args.bundle, args.expected_bundle_sha256)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
