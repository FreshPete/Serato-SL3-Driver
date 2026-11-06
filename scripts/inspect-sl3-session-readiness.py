"""Read launch prerequisites without loading package binaries or opening USB."""
import argparse
from contextlib import ExitStack
import ctypes
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import runpy
import sys
import winreg

ROOT = Path(__file__).resolve().parents[1]
DRIVER_SHA = 'c92b6c15bd550023312ae4cfe49a39757952a3c2ebdc7d1d143ac5e695f69a63'
ORIGINAL_ARCHIVE_SHA = '872fc4fdad2eab2ddd34387d2d3c04dd9731c84798d9fdc7bd05ca54e1567db8'


def module(name):
    return runpy.run_path(str(ROOT / 'scripts' / name))


def stage():
    return module('asio-install-journal.py')['stage_module']()


def platform_state():
    s = stage(); process = W.USHORT(); native = W.USHORT()
    current = s.api('kernel32.dll', 'GetCurrentProcess', W.HANDLE, [])()
    s.check(s.api('kernel32.dll', 'IsWow64Process2', W.BOOL,
                  [W.HANDLE, ctypes.POINTER(W.USHORT), ctypes.POINTER(W.USHORT)])(current, ctypes.byref(process), ctypes.byref(native)))
    version = sys.getwindowsversion()
    return {'nativeX64': ctypes.sizeof(ctypes.c_void_p) == 8 and native.value == 0x8664 and process.value == 0,
            'elevated': s.elevated(), 'windowsBuild': version.build}


def running_serato():
    s = stage()
    class Entry(ctypes.Structure):
        _fields_ = [('size', W.DWORD), ('usage', W.DWORD), ('pid', W.DWORD), ('heap', ctypes.c_size_t),
                    ('module', W.DWORD), ('threads', W.DWORD), ('parent', W.DWORD), ('priority', W.LONG),
                    ('flags', W.DWORD), ('name', W.WCHAR * 260)]
    count = 0; matches = 0
    with s.Handle(s.api('kernel32.dll', 'CreateToolhelp32Snapshot', W.HANDLE, [W.DWORD, W.DWORD])(2, 0)) as snapshot:
        entry = Entry(); entry.size = ctypes.sizeof(entry)
        first = s.api('kernel32.dll', 'Process32FirstW', W.BOOL, [W.HANDLE, ctypes.POINTER(Entry)])
        following = s.api('kernel32.dll', 'Process32NextW', W.BOOL, [W.HANDLE, ctypes.POINTER(Entry)])
        available = first(snapshot, ctypes.byref(entry))
        while available:
            count += 1; s.require(count <= 32768, 'Process inventory exceeds bound')
            matches += entry.name.casefold() == 'serato dj pro.exe'
            available = following(snapshot, ctypes.byref(entry))
        s.require(ctypes.get_last_error() == 18, 'Process inventory query failed')
    return {'running': matches != 0, 'matchingProcesses': matches}


def driver_state():
    s = stage()
    class Status(ctypes.Structure):
        _fields_ = [(name, W.DWORD) for name in ('kind', 'state', 'controls', 'exit', 'specificExit', 'checkpoint', 'wait', 'pid', 'flags')]
    class Config(ctypes.Structure):
        _fields_ = [('kind', W.DWORD), ('start', W.DWORD), ('error', W.DWORD), ('binary', W.LPWSTR),
                    ('group', W.LPWSTR), ('tag', W.DWORD), ('dependencies', W.LPWSTR), ('account', W.LPWSTR), ('display', W.LPWSTR)]
    close = s.api('advapi32.dll', 'CloseServiceHandle', W.BOOL, [W.HANDLE])
    with ExitStack() as stack:
        manager = s.check(s.api('advapi32.dll', 'OpenSCManagerW', W.HANDLE, [W.LPCWSTR, W.LPCWSTR, W.DWORD])(None, None, 1))
        stack.callback(lambda: s.check(close(manager)))
        service = s.api('advapi32.dll', 'OpenServiceW', W.HANDLE, [W.HANDLE, W.LPCWSTR, W.DWORD])(manager, 'UsbDk', 5)
        if not service and ctypes.get_last_error() == 1060:
            return {'installed': False, 'running': False, 'reviewedImageOnDisk': False}
        s.check(service); stack.callback(lambda: s.check(close(service)))
        status = Status(); count = W.DWORD()
        s.check(s.api('advapi32.dll', 'QueryServiceStatusEx', W.BOOL,
                      [W.HANDLE, W.DWORD, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD)])(
                          service, 0, ctypes.byref(status), ctypes.sizeof(status), ctypes.byref(count)))
        config_query = s.api('advapi32.dll', 'QueryServiceConfigW', W.BOOL,
                             [W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD)])
        config_query(service, None, 0, ctypes.byref(count))
        s.require(ctypes.get_last_error() == 122 and ctypes.sizeof(Config) <= count.value <= 65536, 'Service configuration size differs')
        buffer = ctypes.create_string_buffer(count.value)
        s.check(config_query(service, buffer, len(buffer), ctypes.byref(count)))
        config = ctypes.cast(buffer, ctypes.POINTER(Config)).contents
        s.require(config.kind == 1 and config.binary, 'Expected kernel driver service configuration')
        source = config.binary
        if source.startswith('"') and source.endswith('"'):
            source = source[1:-1]
        if source.startswith('\\SystemRoot\\'):
            windows = ctypes.create_unicode_buffer(32768)
            copied = s.api('kernel32.dll', 'GetWindowsDirectoryW', W.UINT, [W.LPWSTR, W.UINT])(windows, len(windows))
            s.require(0 < copied < len(windows), 'Windows directory query failed')
            source = windows.value + '\\' + source[12:]
        elif source.startswith('\\??\\'):
            source = source[4:]
        expanded = ctypes.create_unicode_buffer(32768)
        copied = s.api('kernel32.dll', 'ExpandEnvironmentStringsW', W.DWORD, [W.LPCWSTR, W.LPWSTR, W.DWORD])(
            source, expanded, len(expanded))
        s.require(0 < copied <= len(expanded), 'Driver path expansion failed')
        path = s.local(Path(expanded.value))
        with s.open_file(path) as handle:
            actual = hashlib.sha256(s.read_handle(handle, 16 * 1024 * 1024)).hexdigest()
        return {'installed': True, 'running': status.state == 4, 'serviceState': status.state,
                'reviewedImageOnDisk': actual == DRIVER_SHA, 'imageSha256': actual,
                'loadedImageAttested': False, 'serviceChanged': False}


def sl3_presence():
    s = stage()
    # SDK 10.0.19041 cfgmgr32.h: ENUMERATOR=1, PRESENT=0x100.
    flags = 0x101
    size_query = s.api('cfgmgr32.dll', 'CM_Get_Device_ID_List_SizeW', W.DWORD, [ctypes.POINTER(W.ULONG), W.LPCWSTR, W.ULONG])
    read = s.api('cfgmgr32.dll', 'CM_Get_Device_ID_ListW', W.DWORD, [W.LPCWSTR, W.LPWSTR, W.ULONG, W.ULONG])
    for _ in range(3):
        count = W.ULONG()
        s.require(size_query(ctypes.byref(count), 'USB', flags) == 0 and 1 <= count.value <= 1024 * 1024,
                  'USB identity inventory size query failed')
        buffer = ctypes.create_unicode_buffer(count.value)
        result = read('USB', buffer, len(buffer), flags)
        if result == 0x1a:  # CR_BUFFER_SMALL: the present list changed; requery.
            continue
        s.require(result == 0, 'USB identity inventory query failed')
        identifiers = [value for value in buffer[:].split('\0') if value]
        matches = [value for value in identifiers if value.upper().startswith('USB\\VID_1CC5&PID_0001\\')]
        return {'matchingPresentIdentities': len(matches), 'pnpMetadataOnly': True, 'deviceOpened': False,
                'descriptorsReadFromHardware': False}
    raise ValueError('USB identity inventory changed repeatedly')


def residue(installation, pointer, application):
    s = stage()
    paths = {'nativeInstallation': installation, 'sessionPointer': pointer, 'pendingPointer': Path(str(pointer) + '.pending'),
             'installerResource': application.parent / 'bundles/8c7758f23375cee18a9cf3be4a3acc15.bin',
             'installerPermit': application.parent / 'bundles/8c7758f23375cee18a9cf3be4a3acc15.bin.sl3-permit'}
    occupied = [name for name, path in paths.items() if not s.absent(path)]
    registry = []
    for name in ('SOFTWARE\\ASIO\\SL3 Rebuild Development',
                 'SOFTWARE\\Classes\\CLSID\\{5A551CD0-F83E-48EB-8B9D-8614E07852FE}'):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, name, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
                registry.append(name)
        except FileNotFoundError:
            pass
    archive = application.with_name('userio_resources.bin')
    with s.open_file(archive) as handle:
        archive_sha = hashlib.sha256(s.read_handle(handle, 16 * 1024 * 1024)).hexdigest()
    return {'occupiedPaths': occupied, 'registrationPresent': bool(registry),
            'originalResources': archive_sha == ORIGINAL_ARCHIVE_SHA}


def requirements(payload):
    runtime = module('asio-runtime-check.py')
    per_image = runtime['imports'](payload); combined = {}
    for values in per_image.values():
        for name, symbols in values.items():
            combined.setdefault(name, set()).update(symbols)
    with ExitStack() as stack:
        resolved = runtime['resolve']({name: sorted(symbols, key=str) for name, symbols in combined.items()},
                                      runtime['system_directory'](), stack)
        return {'directImportsResolved': True, 'systemModulesChecked': len(resolved['dependencies']),
                'systemFilesChecked': len(resolved['systemFiles']), 'packageBinaryLoaded': False,
                'systemDependenciesLoaded': True, 'transitiveBehaviorVerified': False}


def classify(name, value):
    if name == 'platform':
        return value['nativeX64'] and not value['elevated'], 'Use the normal Windows x64 desktop session.'
    if name == 'application':
        return not value['running'], 'Close Serato before starting this session.'
    if name == 'filter':
        return value['installed'] and value['running'] and value['reviewedImageOnDisk'], 'The reviewed UsbDk filter must be installed and running.'
    if name == 'device':
        return value['matchingPresentIdentities'] == 1, 'Connect exactly one SL3 by USB.'
    if name == 'state':
        return not value['occupiedPaths'] and not value['registrationPresent'] and value['originalResources'], 'Previous session state needs review or recovery.'
    if name == 'dependencies':
        return value['directImportsResolved'], 'A required Windows runtime dependency is unavailable.'
    raise ValueError('Unknown readiness check')


def inspect(bundle, expected, application):
    api = module('prepare-asio-deployment.py'); manifest, payload = api['capture_bundle'](Path(bundle).absolute(), expected)
    api['inspect_portable_payloads'](manifest, payload)
    binding = module('rebind-asio-deployment.py')['rebind'](bundle, expected)
    application = Path(application).absolute()
    capsule = module('serato-session-capsule.py')
    api['require'](application.name == 'Serato DJ Pro.exe' and capsule['sha'](application) == capsule['APP_SHA'],
                   'Reviewed Serato application required')
    checks = []
    for name, query in (
        ('platform', platform_state), ('application', running_serato), ('filter', driver_state), ('device', sl3_presence),
        ('state', lambda: residue(Path(binding['installationDirectory']), Path(binding['pointerPath']), application)),
        ('dependencies', lambda: requirements(payload)),
    ):
        try:
            value = query(); passed, message = classify(name, value)
            checks.append({'id': name, 'status': 'pass' if passed else 'blocked',
                           'message': 'Check passed.' if passed else message, 'evidence': value})
        except Exception as error:
            checks.append({'id': name, 'status': 'unknown', 'message': str(error)})
    return {'schema': 'sl3.session-readiness.v1', 'readyForAttempt': all(row['status'] == 'pass' for row in checks),
            'checks': checks, 'filesWritten': False, 'registryWritten': False, 'elevationRequested': False,
            'packageBinaryLoaded': False, 'systemDependenciesMayLoad': True, 'deviceOpened': False,
            'usbIoSubmitted': False, 'driverChanged': False, 'audioStarted': False, 'liveStartupValidated': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--expected-bundle-sha256', required=True)
    parser.add_argument('--app', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.bundle, args.expected_bundle_sha256, args.app)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['readyForAttempt'] else 3)
