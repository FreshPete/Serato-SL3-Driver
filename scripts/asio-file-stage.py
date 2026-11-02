"""Explicit owned file staging/cleanup. No registration, process launch or USB."""
import argparse
from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes as W
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import uuid

SYSTEM = 'S-1-5-18'
ADMINS = 'S-1-5-32-544'
USERS = 'S-1-5-32-545'
FULL = 0x1f01ff
RX = 0x1200a9
INVALID = ctypes.c_void_p(-1).value
P = ctypes.c_void_p
TOTAL_LIMIT = 64*1024*1024


def require(value, message):
    if not value:
        raise ValueError(message)


def api(dll, name, result, args):
    function = getattr(ctypes.WinDLL(dll, use_last_error=True, winmode=0x800), name)
    function.restype = result; function.argtypes = args
    return function


def check(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


def free(pointer):
    if pointer:
        api('kernel32.dll', 'LocalFree', P, [P])(pointer)


class Handle:
    def __init__(self, value):
        if value is None or value == INVALID:
            raise ctypes.WinError(ctypes.get_last_error())
        self.value = value
    def __enter__(self):
        return self.value
    def __exit__(self, *ignored):
        self.close()
    def close(self):
        if self.value is None:
            return
        value = self.value; self.value = None
        check(api('kernel32.dll', 'CloseHandle', W.BOOL, [W.HANDLE])(value))


class Attributes(ctypes.Structure):
    _fields_ = [('size', W.DWORD), ('descriptor', P), ('inherit', W.BOOL)]


class Information(ctypes.Structure):
    _fields_ = [('attributes', W.DWORD), ('created', W.FILETIME), ('accessed', W.FILETIME), ('written', W.FILETIME),
                ('volume', W.DWORD), ('sizeHigh', W.DWORD), ('sizeLow', W.DWORD), ('links', W.DWORD),
                ('indexHigh', W.DWORD), ('indexLow', W.DWORD)]


@dataclass(frozen=True)
class Policy:
    owner: str
    full: tuple
    def aces(self, directory):
        flags = 3 if directory else 0
        return sorted([{'sid': sid, 'mask': FULL, 'flags': flags, 'type': 0} for sid in self.full]+
                      [{'sid': USERS, 'mask': RX, 'flags': flags, 'type': 0}], key=lambda x: x['sid'])
    def sddl(self, directory):
        flags = 'OICI' if directory else ''
        return 'O:'+self.owner+'D:P'+''.join(f'(A;{flags};0x{ace["mask"]:x};;;{ace["sid"]})' for ace in self.aces(directory))
    def record(self):
        return {'owner': self.owner, 'fullControlSids': list(self.full), 'usersReadExecute': True, 'protectedDacl': True}


PRODUCTION = Policy(ADMINS, (SYSTEM, ADMINS))


@contextmanager
def descriptor(sddl):
    pointer = P()
    check(api('advapi32.dll', 'ConvertStringSecurityDescriptorToSecurityDescriptorW', W.BOOL,
              [W.LPCWSTR, W.DWORD, ctypes.POINTER(P), ctypes.POINTER(W.DWORD)])(sddl, 1, ctypes.byref(pointer), None))
    try:
        yield Attributes(ctypes.sizeof(Attributes), pointer, False)
    finally:
        free(pointer)


def sid_text(sid):
    require(sid and api('advapi32.dll', 'IsValidSid', W.BOOL, [P])(sid), 'Valid SID required')
    value = P()
    check(api('advapi32.dll', 'ConvertSidToStringSidW', W.BOOL, [P, ctypes.POINTER(P)])(sid, ctypes.byref(value)))
    try:
        return ctypes.wstring_at(value)
    finally:
        free(value)


def token_info(kind):
    value = W.HANDLE(); needed = W.DWORD()
    check(api('advapi32.dll', 'OpenProcessToken', W.BOOL, [W.HANDLE, W.DWORD, ctypes.POINTER(W.HANDLE)])(
        api('kernel32.dll', 'GetCurrentProcess', W.HANDLE, [])(), 8, ctypes.byref(value)))
    query = api('advapi32.dll', 'GetTokenInformation', W.BOOL, [W.HANDLE, W.DWORD, P, W.DWORD, ctypes.POINTER(W.DWORD)])
    with Handle(value.value) as handle:
        query(handle, kind, None, 0, ctypes.byref(needed))
        require(0 < needed.value <= 65536, 'Bounded token information required')
        buffer = ctypes.create_string_buffer(needed.value)
        check(query(handle, kind, buffer, needed.value, ctypes.byref(needed)))
        return buffer


def user_sid():
    buffer = token_info(1)
    return sid_text(ctypes.cast(buffer, ctypes.POINTER(P))[0])


def account_sid(name):
    sid_bytes, domain_chars, kind = W.DWORD(), W.DWORD(), W.DWORD()
    function = api('advapi32.dll', 'LookupAccountNameW', W.BOOL,
                   [W.LPCWSTR, W.LPCWSTR, P, ctypes.POINTER(W.DWORD), W.LPWSTR, ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD)])
    function(None, name, None, ctypes.byref(sid_bytes), None, ctypes.byref(domain_chars), ctypes.byref(kind))
    require(0 < sid_bytes.value <= 1024 and domain_chars.value <= 1024, 'Bounded account SID required')
    sid = ctypes.create_string_buffer(sid_bytes.value); domain = ctypes.create_unicode_buffer(max(1, domain_chars.value))
    check(function(None, name, sid, ctypes.byref(sid_bytes), domain, ctypes.byref(domain_chars), ctypes.byref(kind)))
    return sid_text(sid)


def elevated():
    return bool(struct.unpack('<I', token_info(20).raw[:4])[0])


def known_folder(guid):
    identifier = (ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID(guid).bytes_le); value = P()
    result = api('shell32.dll', 'SHGetKnownFolderPath', W.LONG, [P, W.DWORD, W.HANDLE, ctypes.POINTER(P)])(
        identifier, 0, None, ctypes.byref(value))
    require(result >= 0 and value.value, 'Windows known-folder resolution failed')
    try:
        return local(Path(ctypes.wstring_at(value)))
    finally:
        api('ole32.dll', 'CoTaskMemFree', None, [P])(value)


def local(path):
    require(path.is_absolute() and len(path.drive) == 2 and path.drive[1] == ':' and
            ':' not in str(path)[2:] and '..' not in path.parts and len(str(path)) <= 240 and
            not any(ord(c) < 32 for c in str(path)), 'Bounded absolute local drive path required')
    require(api('kernel32.dll', 'GetDriveTypeW', W.UINT, [W.LPCWSTR])(path.anchor) == 3, 'Fixed drive required')
    return path


def open_file(path, directory=False, access=0x80000000, share=1, create=3, security=None):
    local(path)
    if directory:
        # Metadata-only directory opens do not enforce the intended delete-share
        # exclusion against rename. Request FILE_LIST_DIRECTORY as a read lease.
        access |= 1
    flags = 0x200000 | (0x2000000 if directory else 0)  # OPEN_REPARSE_POINT, BACKUP_SEMANTICS
    value = api('kernel32.dll', 'CreateFileW', W.HANDLE,
                [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.POINTER(Attributes), W.DWORD, W.DWORD, W.HANDLE])(
        str(path), access, share, ctypes.byref(security) if security is not None else None, create, flags, None)
    return Handle(value)


def information(handle, directory):
    data = Information()
    check(api('kernel32.dll', 'GetFileInformationByHandle', W.BOOL, [W.HANDLE, ctypes.POINTER(Information)])(handle, ctypes.byref(data)))
    require(not data.attributes & 0x400 and bool(data.attributes & 0x10) == directory, 'Reparse point or wrong file type refused')
    require(api('kernel32.dll', 'GetFileType', W.DWORD, [W.HANDLE])(handle) == 1, 'Disk file required')
    buffer = ctypes.create_unicode_buffer(32768)
    count = api('kernel32.dll', 'GetFinalPathNameByHandleW', W.DWORD, [W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD])(handle, buffer, len(buffer), 0)
    require(4 < count < len(buffer) and buffer.value.startswith('\\\\?\\'), 'Resolved local file path required')
    path = local(Path(buffer.value[4:]))
    return {'path': str(path), 'size': (data.sizeHigh << 32) | data.sizeLow, 'links': data.links,
            'identity': {'volume': data.volume, 'high': data.indexHigh, 'low': data.indexLow}}


def security_info(handle):
    owner, dacl, sd = P(), P(), P()
    code = api('advapi32.dll', 'GetSecurityInfo', W.DWORD,
               [W.HANDLE, W.DWORD, W.DWORD, ctypes.POINTER(P), ctypes.POINTER(P), ctypes.POINTER(P), ctypes.POINTER(P), ctypes.POINTER(P)])(
        handle, 1, 5, ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(sd))
    if code:
        raise ctypes.WinError(code)
    try:
        control = W.WORD(); revision = W.DWORD()
        check(api('advapi32.dll', 'GetSecurityDescriptorControl', W.BOOL, [P, ctypes.POINTER(W.WORD), ctypes.POINTER(W.DWORD)])(
            sd, ctypes.byref(control), ctypes.byref(revision)))
        result = {'owner': sid_text(owner), 'protected': bool(control.value & 0x1000), 'nullDacl': not bool(dacl.value), 'aces': []}
        if dacl.value:
            data = (W.DWORD*3)()
            check(api('advapi32.dll', 'GetAclInformation', W.BOOL, [P, P, W.DWORD, W.DWORD])(dacl, data, ctypes.sizeof(data), 2))
            require(data[0] <= 64, 'ACL entry limit')
            for n in range(data[0]):
                ace = P(); check(api('advapi32.dll', 'GetAce', W.BOOL, [P, W.DWORD, ctypes.POINTER(P)])(dacl, n, ctypes.byref(ace)))
                kind, flags, size, mask = struct.unpack('<BBHI', ctypes.string_at(ace, 8))
                require(kind in (0, 1) and 20 <= size <= 1024, 'Unsupported ACL entry form')
                result['aces'].append({'sid': sid_text(ace.value+8), 'mask': mask, 'flags': flags, 'type': kind})
        result['aces'].sort(key=lambda x: (x['sid'], x['type'], x['mask'], x['flags']))
        return result
    finally:
        free(sd)


def inspect_policy(handle, policy, directory):
    file = information(handle, directory); security = security_info(handle)
    require(security['owner'] == policy.owner and security['protected'] and not security['nullDacl'] and
            security['aces'] == policy.aces(directory), 'Owner/protected DACL/ACE policy mismatch')
    require(directory or file['links'] == 1, 'Staged file must have one link')
    return {'file': file, 'security': security}


def read_handle(handle, maximum):
    size = information(handle, False)['size']; require(0 < size <= maximum, 'Bounded nonempty file required')
    check(api('kernel32.dll', 'SetFilePointerEx', W.BOOL, [W.HANDLE, ctypes.c_longlong, P, W.DWORD])(handle, 0, None, 0))
    buffer = ctypes.create_string_buffer(size); received = W.DWORD()
    check(api('kernel32.dll', 'ReadFile', W.BOOL, [W.HANDLE, P, W.DWORD, ctypes.POINTER(W.DWORD), P])(
        handle, buffer, size, ctypes.byref(received), None))
    require(received.value == size, 'Complete file read required')
    return buffer.raw


def reader():
    spec = importlib.util.spec_from_file_location('sl3_stage_bundle_reader', Path(__file__).with_name('prepare-asio-deployment.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def snapshot_bundle(bundle, expected, stack):
    module = reader(); module.sha_value(expected)
    directory = stack.enter_context(open_file(bundle, True, access=0x20080, share=3)); information(directory, True)
    handle = stack.enter_context(open_file(bundle/'bundle-manifest.json'))
    raw = read_handle(handle, module.LIMIT); require(hashlib.sha256(raw).hexdigest() == expected, 'Reviewed bundle manifest mismatch')
    manifest = module.record(raw)
    require(set(manifest['files']) == module.REQUIRED and {p.name for p in bundle.iterdir()} == module.REQUIRED | {'bundle-manifest.json'}, 'Exact source inventory required')
    require(sum(item['bytes'] for item in manifest['files'].values()) <= TOTAL_LIMIT, 'Total stage payload limit')
    payload = {}
    for name in sorted(module.REQUIRED):
        handle = stack.enter_context(open_file(bundle/name))
        payload[name] = read_handle(handle, module.LIMIT)
    module.verify_payloads(manifest, payload)
    return module, manifest, payload | {'bundle-manifest.json': raw}


@contextmanager
def pinned_parents(path):
    with ExitStack() as stack:
        handles = []
        for parent in reversed(path.parents):
            handle = stack.enter_context(open_file(parent, True, access=0x20080, share=3))
            data = information(handle, True)
            require(Path(data['path']) == parent, 'Parent path resolves to a different location')
            handles.append(handle)
        yield handles


def stage_new(bundle, expected, destination, policy, journal=None):
    """Trusted-caller primitive. Production uses only the fixed policy below."""
    local(destination)
    with ExitStack() as stack:
        module, manifest, payload = snapshot_bundle(bundle, expected, stack)
        stack.enter_context(pinned_parents(destination))
        with descriptor(policy.sddl(True)) as attributes:
            check(api('kernel32.dll', 'CreateDirectoryW', W.BOOL, [W.LPCWSTR, ctypes.POINTER(Attributes)])(str(destination), ctypes.byref(attributes)))
        directory = stack.enter_context(open_file(destination, True, access=0x20080, share=3))
        root = inspect_policy(directory, policy, True)
        require(Path(root['file']['path']) == destination, 'Staged directory identity/path mismatch')
        record = {'schema': 'sl3.file-stage.v1', 'packageId': manifest['packageId'], 'bundleManifestSha256': expected,
                  'directory': root['file'], 'policy': policy.record(), 'productionPolicy': policy == PRODUCTION,
                  'files': {}, 'registered': False, 'binaryPayloadExecuted': False, 'deviceAccess': False}
        intent = module.encoded({'schema': 'sl3.file-stage-intent.v1', 'packageId': manifest['packageId'],
                                 'bundleManifestSha256': expected, 'directory': root['file'], 'policy': policy.record(),
                                 'complete': False, 'plannedFiles': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)} for name, data in payload.items()}})
        if journal is not None:
            journal({'event': 'stage_root_created', 'directory': root['file'],
                     'packageId': manifest['packageId'], 'bundleManifestSha256': expected, 'policy': policy.record()})

        def write_owned(name, data):
            with descriptor(policy.sddl(False)) as attributes:
                with open_file(destination/name, access=0xc0000000, create=1, security=attributes) as handle:
                    created = inspect_policy(handle, policy, False)['file']
                    require(created['size'] == 0 and Path(created['path']) == destination/name, 'New empty stage file required')
                    details = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'identity': created['identity']}
                    # Witness identity before writing. The unavoidable create-to-
                    # witness gap is preserved, never guessed during recovery.
                    if journal is not None:
                        journal({'event': 'stage_file_created', 'name': name, 'details': details})
                    written = W.DWORD()
                    check(api('kernel32.dll', 'WriteFile', W.BOOL, [W.HANDLE, P, W.DWORD, ctypes.POINTER(W.DWORD), P])(
                        handle, data, len(data), ctypes.byref(written), None))
                    require(written.value == len(data), 'Complete staged write required')
                    check(api('kernel32.dll', 'FlushFileBuffers', W.BOOL, [W.HANDLE])(handle))
                    inspected = inspect_policy(handle, policy, False)['file']
                    require(inspected['identity'] == created['identity'] and read_handle(handle, module.LIMIT) == data,
                            'Staged readback/identity differs from captured bytes')
                    if journal is not None:
                        journal({'event': 'stage_file_completed', 'name': name, 'details': details})
                    return details

        record['intent'] = write_owned('stage-intent.json', intent)
        for name, data in payload.items():
            if journal is not None:
                journal({'event': 'before_file', 'name': name})
            record['files'][name] = write_owned(name, data)
        receipt = module.encoded(record)
        write_owned('stage-record.json', receipt)
        return {'staged': True, 'productionPolicy': policy == PRODUCTION, 'directory': str(destination),
                'stageRecordSha256': hashlib.sha256(receipt).hexdigest(), 'registered': False, 'deviceAccess': False}


def inspect_stage(destination, expected, policy=PRODUCTION):
    local(destination); module = reader(); module.sha_value(expected)
    with ExitStack() as stack:
        stack.enter_context(pinned_parents(destination))
        directory = stack.enter_context(open_file(destination, True, access=0x20080, share=3))
        root = inspect_policy(directory, policy, True)['file']
        handle = stack.enter_context(open_file(destination/'stage-record.json'))
        inspect_policy(handle, policy, False); raw = read_handle(handle, module.LIMIT)
        require(hashlib.sha256(raw).hexdigest() == expected, 'Stage receipt hash mismatch')
        record = module.record(raw)
        require(record['schema'] == 'sl3.file-stage.v1' and record['directory']['identity'] == root['identity'] and
                Path(record['directory']['path']) == destination and record['policy'] == policy.record() and
                record['productionPolicy'] == (policy == PRODUCTION) and
                all(record[k] is False for k in ('registered', 'binaryPayloadExecuted', 'deviceAccess')), 'Stage receipt root/policy mismatch')
        require(set(record['files']) == module.REQUIRED | {'bundle-manifest.json'} and
                {p.name for p in destination.iterdir()} == set(record['files']) | {'stage-record.json', 'stage-intent.json'}, 'Staged inventory mismatch')
        require(sum(item['bytes'] for item in record['files'].values()) <= TOTAL_LIMIT, 'Staged payload total limit')
        payload = {}
        for name, details in list(record['files'].items())+[('stage-intent.json', record['intent'])]:
            handle = stack.enter_context(open_file(destination/name))
            file = inspect_policy(handle, policy, False)['file']; data = read_handle(handle, module.LIMIT)
            require(file['identity'] == details['identity'] and len(data) == details['bytes'] and
                    hashlib.sha256(data).hexdigest() == details['sha256'], 'Staged file identity/bytes mismatch: '+name)
            payload[name] = data
        intent = module.record(payload.pop('stage-intent.json'))
        require(intent['schema'] == 'sl3.file-stage-intent.v1' and intent['complete'] is False and
                intent['directory']['identity'] == root['identity'] and intent['packageId'] == record['packageId'] and
                intent['bundleManifestSha256'] == record['bundleManifestSha256'], 'Stage intent mismatch')
        manifest_bytes = payload.pop('bundle-manifest.json')
        require(hashlib.sha256(manifest_bytes).hexdigest() == record['bundleManifestSha256'], 'Staged bundle manifest mismatch')
        manifest = module.record(manifest_bytes); module.verify_payloads(manifest, payload)
        require(manifest['packageId'] == record['packageId'], 'Staged package identity mismatch')
        plan = module.record(payload['deployment-plan.json']); matches = Path(plan['installationDirectory']) == destination
        if policy == PRODUCTION:
            require(matches, 'Production stage differs from registered DLL location')
            base, planned = production_destination(plan)
            trusted = {SYSTEM, ADMINS, account_sid('NT SERVICE\\TrustedInstaller')}
            for handle in stack.enter_context(pinned_parents(base)):
                safe_parent(handle, trusted)
            handle = stack.enter_context(open_file(base, True, access=0x20080, share=3))
            inspect_policy(handle, PRODUCTION, True)
        return {'verified': True, 'productionPolicy': policy == PRODUCTION, 'plannedDestinationMatches': matches,
                'files': len(record['files'])+2, 'registered': False, 'deviceAccess': False, 'binaryPayloadExecuted': False}


def production_destination(plan):
    program = known_folder('905e63b6-c1bf-494e-b29c-65b732d3d21a')
    profile = known_folder('f1b32785-6fba-4fcf-9d55-7b8e7f157091')
    base = program/'SL3 Rebuild'; destination = local(Path(plan['installationDirectory']))
    pointer = local(Path(plan['pointerPath']))
    require(destination.parent == base and pointer.is_relative_to(profile/'SL3Rebuild'), 'Native known-folder installation/profile scope mismatch')
    return base, destination


class CleanupFailure(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__(report['error'])


def absent(path):
    attributes = api('kernel32.dll', 'GetFileAttributesW', W.DWORD, [W.LPCWSTR])(str(path))
    error = ctypes.get_last_error()
    return attributes == 0xffffffff and error in (2, 3)


def mark_delete(handle):
    disposition = W.BOOL(True)
    check(api('kernel32.dll', 'SetFileInformationByHandle', W.BOOL, [W.HANDLE, W.DWORD, P, W.DWORD])(
        handle, 4, ctypes.byref(disposition), ctypes.sizeof(disposition)))


def remove_stage(destination, expected, policy=PRODUCTION, journal=None):
    """Trusted-caller cleanup primitive, not a registry/device uninstaller."""
    report = {'schema': 'sl3.file-stage-cleanup.v1', 'successful': False, 'directory': str(destination),
              'stageRecordSha256': expected, 'productionPolicy': policy == PRODUCTION,
              'deleteMarkedFiles': [], 'absentObservedFiles': [], 'directoryDeletionMarked': False,
              'directoryAbsentObserved': False, 'registryWritten': False, 'deviceAccess': False,
              'binaryPayloadExecuted': False, 'error': ''}
    try:
        # Full package/plan/descriptor validation first. Then revalidate all
        # identities, bytes and ACLs through the very handles that can delete.
        inspect_stage(destination, expected, policy)
        module = reader()
        with ExitStack() as stack:
            stack.enter_context(pinned_parents(destination))
            root_owner = open_file(destination, True, access=0x30081, share=3)
            root_handle = stack.enter_context(root_owner)
            root = inspect_policy(root_handle, policy, True)['file']
            handles = {}
            def lock(name):
                owner = open_file(destination/name, access=0x80010000, share=0)
                handle = stack.enter_context(owner); handles[name] = (owner, handle)
                return handle
            receipt_handle = lock('stage-record.json')
            inspect_policy(receipt_handle, policy, False)
            raw = read_handle(receipt_handle, module.LIMIT)
            require(hashlib.sha256(raw).hexdigest() == expected, 'Cleanup receipt changed after inspection')
            record = module.record(raw)
            require(record['directory']['identity'] == root['identity'] and Path(root['path']) == destination and
                    record['policy'] == policy.record(), 'Cleanup root identity/policy changed')
            expected_names = set(record['files']) | {'stage-record.json', 'stage-intent.json'}
            require({p.name for p in destination.iterdir()} == expected_names, 'Cleanup inventory changed')
            require(set(record['files']) == module.REQUIRED | {'bundle-manifest.json'}, 'Cleanup receipt inventory mismatch')
            metadata = dict(record['files']); metadata['stage-intent.json'] = record['intent']
            for name, details in metadata.items():
                handle = lock(name); file = inspect_policy(handle, policy, False)['file']
                data = read_handle(handle, module.LIMIT)
                require(file['identity'] == details['identity'] and len(data) == details['bytes'] and
                        hashlib.sha256(data).hexdigest() == details['sha256'], 'Cleanup file identity/bytes changed: '+name)
            # The caller can durably save this recovery record before mutation.
            if journal is not None:
                journal({'event': 'validated', 'directory': str(destination), 'stageRecord': record,
                         'stageRecordSha256': expected})
            priority = ['sl3_asio.dll', 'sl3_broker_controller.exe', 'sl3_usbdk.exe', 'UsbDkHelper.dll']
            order = priority+sorted(set(record['files'])-set(priority))+['stage-intent.json', 'stage-record.json']
            remaining = set(expected_names)
            for name in order:
                if journal is not None:
                    journal({'event': 'before_delete', 'name': name})
                require({p.name for p in destination.iterdir()} == remaining, 'Unknown/missing files appeared during cleanup')
                owner, handle = handles[name]
                inspect_policy(handle, policy, False)
                mark_delete(handle); report['deleteMarkedFiles'].append(name)
                owner.close()
                require(absent(destination/name), 'Marked file absence not observed: '+name)
                report['absentObservedFiles'].append(name); remaining.remove(name)
                if journal is not None:
                    journal({'event': 'deleted', 'name': name})
            if journal is not None:
                journal({'event': 'before_directory_delete', 'directory': str(destination)})
            require(not list(destination.iterdir()), 'Directory gained unknown data; preserve it')
            inspect_policy(root_handle, policy, True)
            mark_delete(root_handle); report['directoryDeletionMarked'] = True
            root_owner.close()
            report['directoryAbsentObserved'] = absent(destination)
            require(report['directoryAbsentObserved'], 'Directory deletion marked but absence not observed')
        report['successful'] = True
        return report
    except Exception as error:
        report['error'] = str(error)
        report['stageRecordStillPresent'] = (destination/'stage-record.json').exists()
        report['intentStillPresent'] = (destination/'stage-intent.json').exists()
        raise CleanupFailure(report) from error


def remove_production_stage(destination, expected, journal):
    require(elevated(), 'Production cleanup requires an explicitly elevated token; no UAC is requested automatically')
    require(ctypes.sizeof(P) == 8, 'Native x64 installer process required')
    require(callable(journal), 'Privileged caller must provide a durable recovery journal before cleanup')
    inspect_stage(destination, expected, PRODUCTION)
    module = reader()
    with open_file(destination/'deployment-plan.json') as handle:
        plan = module.record(read_handle(handle, module.LIMIT))
    # Removing a stage is not permission to leave a live registration dangling.
    spec = importlib.util.spec_from_file_location('sl3_cleanup_registry_reader', Path(__file__).with_name('asio-registry.py'))
    registry = importlib.util.module_from_spec(spec); spec.loader.exec_module(registry)
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, '', 0, registry.READ) as root:
        require(registry.inspect(root, plan)['allAbsent'], 'Live project registration remains; refuse file cleanup')
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, registry.READ) as root:
        require(not registry.inspect_overlay(root, plan)['present'], 'Current-user COM overlay remains; refuse file cleanup')
    return remove_stage(destination, expected, PRODUCTION, journal)


def volume_anchor(handle, file):
    path = Path(file['path'])
    if path != Path(path.anchor):
        return None
    name = ctypes.create_unicode_buffer(64)
    check(api('kernel32.dll', 'GetVolumeNameForVolumeMountPointW', W.BOOL, [W.LPCWSTR, W.LPWSTR, W.DWORD])(
        str(path), name, len(name)))
    require(name.value.startswith('\\\\?\\Volume{') and name.value.endswith('}\\'), 'Native volume GUID required')
    actual = ctypes.create_unicode_buffer(32768)
    count = api('kernel32.dll', 'GetFinalPathNameByHandleW', W.DWORD, [W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD])(
        handle, actual, len(actual), 1)  # VOLUME_NAME_GUID
    require(0 < count < len(actual) and actual.value.casefold() == name.value.casefold(), 'Mount namespace differs from held volume-root handle')
    fs = ctypes.create_unicode_buffer(32); flags = W.DWORD(); serial = W.DWORD()
    check(api('kernel32.dll', 'GetVolumeInformationW', W.BOOL,
              [W.LPCWSTR, W.LPWSTR, W.DWORD, ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD), W.LPWSTR, W.DWORD])(
        name.value, None, 0, ctypes.byref(serial), None, ctypes.byref(flags), fs, len(fs)))
    require(fs.value.upper() == 'NTFS' and flags.value & 8 and serial.value == file['identity']['volume'],
            'Held NTFS volume anchor with persistent ACLs required')
    return {'volumeGuid': name.value, 'fileSystem': fs.value, 'persistentAcls': True, 'heldHandleGuidAndSerialMatched': True}


def validate_ancestor_acl(file, data, trusted, anchor):
    require(data['owner'] in trusted and not data['nullDacl'], 'Installation ancestor owner/DACL is not trusted')
    if anchor is not None:
        # A native drive root is the trusted OS volume anchor, not a directory
        # entry below an attacker-writable parent. Preserve child replacement
        # and ACL/owner checks; do not equate its own Modify rights with rights
        # on the protected Program Files object. Other ancestors stay strict.
        require(Path(file['path']) == Path(Path(file['path']).anchor), 'Anchor exception only at a drive root')
        mutation = 0x10000000 | 0x40 | 0x40000 | 0x80000
    else:
        mutation = 0x50000000 | 0x2 | 0x10 | 0x40 | 0x100 | 0x10000 | 0x40000 | 0x80000
    for ace in data['aces']:
        if ace['type'] == 1 or ace['flags'] & 8:
            continue
        sid = data['owner'] if ace['sid'] in ('S-1-3-0', 'S-1-3-4') else ace['sid']
        require(sid in trusted or not ace['mask'] & mutation,
                'Untrusted write/replacement rights on installation ancestor '+file['path']+
                ': '+sid+' mask 0x'+format(ace['mask'], 'x'))
    return {'path': file['path'], 'security': data, 'volumeAnchor': anchor, 'untrustedMutationMask': mutation}


def safe_parent(handle, trusted):
    file = information(handle, True)
    return validate_ancestor_acl(file, security_info(handle), trusted, volume_anchor(handle, file))


def check_production(bundle, expected):
    with ExitStack() as stack:
        module, manifest, payload = snapshot_bundle(bundle, expected, stack)
        base, destination = production_destination(module.record(payload['deployment-plan.json']))
        trusted = {SYSTEM, ADMINS, account_sid('NT SERVICE\\TrustedInstaller')}
        handles = stack.enter_context(pinned_parents(base))
        ancestor_checks = [safe_parent(handle, trusted) for handle in handles]
        if base.exists():
            handle = stack.enter_context(open_file(base, True, access=0x20080, share=3))
            inspect_policy(handle, PRODUCTION, True)
        require(not destination.exists(), 'Production destination must be new')
        return {'checked': True, 'destination': str(destination), 'parentPolicyObservedSafe': True,
                'ancestorChecks': ancestor_checks,
                'tokenElevated': elevated(), 'filesWritten': False, 'registryWritten': False,
                'productionStageExecuted': False, 'deviceAccess': False}


def stage_production(bundle, expected):
    require(elevated(), 'Production staging requires an explicitly elevated token; no UAC is requested automatically')
    require(ctypes.sizeof(P) == 8, 'Native x64 installer process required')
    with ExitStack() as stack:
        module, manifest, payload = snapshot_bundle(bundle, expected, stack)
        base, destination = production_destination(module.record(payload['deployment-plan.json']))
        trusted = {SYSTEM, ADMINS, account_sid('NT SERVICE\\TrustedInstaller')}
        handles = stack.enter_context(pinned_parents(base))
        for handle in handles:
            safe_parent(handle, trusted)
        require(not destination.exists(), 'Production destination must be new')
        if not base.exists():
            with descriptor(PRODUCTION.sddl(True)) as attributes:
                check(api('kernel32.dll', 'CreateDirectoryW', W.BOOL, [W.LPCWSTR, ctypes.POINTER(Attributes)])(str(base), ctypes.byref(attributes)))
        handle = stack.enter_context(open_file(base, True, access=0x20080, share=3))
        inspect_policy(handle, PRODUCTION, True)
        return stage_new(bundle, expected, destination, PRODUCTION)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv == ['--plan']:
        print(json.dumps({'schema': 'sl3.file-stage-plan.v1', 'planOnly': True, 'machineStageRequiresExplicitElevation': True,
                          'filesWritten': False, 'registryWritten': False, 'deviceAccess': False})); return
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--stage-production', action='store_true')
    mode.add_argument('--check-production', action='store_true')
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--expected-bundle-sha256', required=True)
    args = parser.parse_args(argv)
    operation = stage_production if args.stage_production else check_production
    print(json.dumps(operation(args.bundle, args.expected_bundle_sha256)))


if __name__ == '__main__':
    try:
        main()
    except CleanupFailure as error:
        print(json.dumps(error.report))
        print(str(error), file=sys.stderr); sys.exit(1)
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
