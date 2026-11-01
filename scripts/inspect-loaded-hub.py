"""Read loaded hub metadata without USB access, elevation or privilege adjustment.

Uses a private x64 Windows information class for diagnostics only. Missing or
changed layouts fail rather than guessing. A metadata match never admits USB.
"""
import argparse
import ctypes as C
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import struct

MAX_BYTES = 1024 * 1024
KERNEL_PATH = r'\SystemRoot\System32\drivers\UsbHub3.sys'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def parse_modules(raw):
    """Strict inspected RTL_PROCESS_MODULE_INFORMATION_EX x64 layout."""
    require(2 <= len(raw) <= MAX_BYTES, 'Module buffer size exceeds bound')
    rows, at = [], 0
    while True:
        require(at + 2 <= len(raw), 'Missing module terminator')
        step = struct.unpack_from('<H', raw, at)[0]
        if step == 0:
            require(at + 2 == len(raw) and rows, 'Unexpected terminal extent or empty list')
            return rows
        require(step == 320 and at + step <= len(raw), 'Unknown or truncated module layout')
        name = raw[at + 48:at + 304]
        require(b'\0' in name, 'Unterminated module path')
        name = name.split(b'\0', 1)[0]
        offset = struct.unpack_from('<H', raw, at + 46)[0]
        require(0 < offset < len(name) and name[offset - 1:offset] == b'\\' and b'\\' not in name[offset:],
                'Invalid basename offset')
        size = struct.unpack_from('<I', raw, at + 32)[0]
        require(size > 0, 'Missing module image size')
        rows.append({'kernelPathBytes': name, 'sizeOfImage': size,
                     'imageBaseRedacted': struct.unpack_from('<Q', raw, at + 24)[0] == 0,
                     'imageChecksum': struct.unpack_from('<I', raw, at + 304)[0],
                     'timeDateStamp': struct.unpack_from('<I', raw, at + 308)[0]})
        require(len(rows) <= 4096, 'Module count exceeds bound')
        at += step


def compare(rows, expected):
    matches = [row for row in rows if row['kernelPathBytes'].lower() == KERNEL_PATH.encode('ascii').lower()]
    require(len(matches) <= 1, 'Ambiguous loaded hub path')
    row = matches[0] if matches else None
    available = bool(row and row['imageChecksum'] and all(row[k] == expected[k]
                     for k in ('sizeOfImage', 'imageChecksum')) and
                     (not row['timeDateStamp'] or row['timeDateStamp'] == expected['timeDateStamp']))
    complete = bool(row and row['timeDateStamp'] and row['imageChecksum'])
    return {'targetPresent': row is not None,
            'loaded': {k: v for k, v in row.items() if k != 'kernelPathBytes'} if row else None,
            'kernelPath': row['kernelPathBytes'].decode('ascii') if row else None,
            'disk': expected, 'availableMetadataMatches': available,
            'identityMetadataComplete': complete, 'completeMetadataMatches': available and complete,
            'loadedMemoryIdentityVerified': False, 'usbWindowQualified': False, 'readinessAdmission': False}


def own_token():
    kernel = C.WinDLL('kernel32.dll', winmode=0x800)
    adv = C.WinDLL('advapi32.dll', winmode=0x800)
    kernel.GetCurrentProcess.restype = C.c_void_p
    adv.OpenProcessToken.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_void_p)]
    adv.OpenProcessToken.restype = C.c_int
    adv.GetTokenInformation.argtypes = [C.c_void_p, C.c_uint, C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong)]
    adv.GetTokenInformation.restype = C.c_int
    kernel.CloseHandle.argtypes = [C.c_void_p]
    kernel.CloseHandle.restype = C.c_int
    handle = C.c_void_p()
    require(adv.OpenProcessToken(kernel.GetCurrentProcess(), 8, C.byref(handle)), 'Cannot query own token')
    try:
        def get(kind):
            result, needed = C.c_ulong(), C.c_ulong()
            require(adv.GetTokenInformation(handle, kind, C.byref(result), 4, C.byref(needed)) and needed.value == 4,
                    'Cannot read own token field')
            return result.value
        elevated, kind = get(20), get(18)
        require(elevated in (0, 1) and kind in (1, 2, 3), 'Unknown token field')
        return {'queried': True, 'elevated': bool(elevated), 'elevationType': kind, 'pid': os.getpid()}
    finally:
        kernel.CloseHandle(handle)


def query():
    require(os.name == 'nt' and C.sizeof(C.c_void_p) == 8 and platform.machine().lower() in ('amd64', 'x86_64'),
            'Expected native x64 Windows')
    token = own_token()
    native = C.WinDLL('ntdll.dll', winmode=0x800)
    get = native.NtQuerySystemInformation
    get.argtypes = [C.c_uint, C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong)]
    get.restype = C.c_long
    buffer, needed = C.create_string_buffer(MAX_BYTES), C.c_ulong()
    start = datetime.now(timezone.utc).isoformat()
    status = get(77, buffer, len(buffer), C.byref(needed))
    finish = datetime.now(timezone.utc).isoformat()
    require(status == 0, f'Module query failed: 0x{status & 0xffffffff:08x}')
    require(2 <= needed.value <= MAX_BYTES, 'Invalid module query return length')
    raw = buffer.raw[:needed.value]
    rows = parse_modules(raw)
    return rows, {'producerToken': token, 'queryStartedUtc': start, 'queryFinishedUtc': finish,
                  'informationClass': 77, 'ntStatus': '0x00000000', 'returnedBytes': needed.value,
                  'bufferSha256': hashlib.sha256(raw).hexdigest(), 'moduleCount': len(rows),
                  'allImageBasesRedacted': all(row['imageBaseRedacted'] for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True, help='Installed or copied USBHUB3 PE for comparison')
    parser.add_argument('--output', type=Path, required=True, help='New diagnostic JSON file')
    args = parser.parse_args()
    require(not args.output.exists() and args.output.parent.is_dir(), 'Expected new output in an existing directory')
    path = Path(__file__).with_name('inspect-kernel-image-rundown.py')
    spec = importlib.util.spec_from_file_location('hub_image_metadata', path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    expected = helper.image_metadata(args.image.resolve(), KERNEL_PATH)
    rows, evidence = query()
    result = {'scope': 'Read-only loaded-module metadata at query time; no memory hash, USB operation or readiness decision',
              **evidence, **compare(rows, expected), 'privilegesAdjusted': False,
              'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'imageHelperSha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'limits': ['Information class/layout is private and can change; unsupported data is rejected.',
                        'Available metadata can agree while a timestamp is missing; that is incomplete identity evidence.',
                        'A disk hash belongs to the supplied file, not the loaded memory image.',
                        'This query does not establish which module was loaded during a past or intervening USB window.']}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('producerToken', 'moduleCount', 'allImageBasesRedacted', 'loaded',
                      'availableMetadataMatches', 'identityMetadataComplete', 'completeMetadataMatches', 'readinessAdmission')}))


if __name__ == '__main__':
    main()
