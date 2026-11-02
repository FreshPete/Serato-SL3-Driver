"""Read-only ancestor diagnostics. Never changes permissions or enables staging."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as W
import importlib.util
import json
from pathlib import Path
import struct
import sys

RIGHTS = {'writeDataOrAddFile': 2, 'appendDataOrAddDirectory': 4, 'writeEa': 16,
          'writeAttributes': 256, 'deleteThisObject': 0x10000, 'deleteChildren': 64,
          'writeDacl': 0x40000, 'writeOwner': 0x80000}


def stage_module():
    spec = importlib.util.spec_from_file_location('sl3_ancestor_stage_reader', Path(__file__).with_name('asio-file-stage.py'))
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module


class Mapping(ctypes.Structure):
    _fields_ = [('read', W.DWORD), ('write', W.DWORD), ('execute', W.DWORD), ('all', W.DWORD)]


class Luid(ctypes.Structure):
    _fields_ = [('low', W.DWORD), ('high', W.LONG)]


class LuidAttributes(ctypes.Structure):
    _fields_ = [('id', Luid), ('attributes', W.DWORD)]


def token_privileges(stage):
    buffer = stage.token_info(3); count = struct.unpack('<I', buffer.raw[:4])[0]
    stage.require(count <= 128 and 4+count*ctypes.sizeof(LuidAttributes) <= len(buffer), 'Bounded token privilege layout')
    lookup = stage.api('advapi32.dll', 'LookupPrivilegeNameW', W.BOOL,
                       [W.LPCWSTR, ctypes.POINTER(Luid), W.LPWSTR, ctypes.POINTER(W.DWORD)])
    result = {}
    for n in range(count):
        item = LuidAttributes.from_buffer_copy(buffer.raw, 4+n*ctypes.sizeof(LuidAttributes)); size = W.DWORD()
        lookup(None, ctypes.byref(item.id), None, ctypes.byref(size))
        stage.require(0 < size.value < 256, 'Bounded privilege name')
        name = ctypes.create_unicode_buffer(size.value+1); size.value += 1
        stage.check(lookup(None, ctypes.byref(item.id), name, ctypes.byref(size)))
        result[name.value] = {'enabled': bool(item.attributes & 2), 'enabledByDefault': bool(item.attributes & 1),
                              'removed': bool(item.attributes & 4)}
    return result


@contextmanager
def query_token(stage):
    current = W.HANDLE(); duplicate = W.HANDLE()
    stage.check(stage.api('advapi32.dll', 'OpenProcessToken', W.BOOL, [W.HANDLE, W.DWORD, ctypes.POINTER(W.HANDLE)])(
        stage.api('kernel32.dll', 'GetCurrentProcess', W.HANDLE, [])(), 0xa, ctypes.byref(current)))
    with stage.Handle(current.value) as handle:
        stage.check(stage.api('advapi32.dll', 'DuplicateToken', W.BOOL, [W.HANDLE, W.DWORD, ctypes.POINTER(W.HANDLE)])(
            handle, 2, ctypes.byref(duplicate)))
    with stage.Handle(duplicate.value) as token:
        yield token  # Never impersonated; no privilege is enabled or removed.


def access_rights(stage, handle, token):
    descriptor = stage.P()
    code = stage.api('advapi32.dll', 'GetSecurityInfo', W.DWORD,
                     [W.HANDLE, W.DWORD, W.DWORD, stage.P, stage.P, stage.P, stage.P, ctypes.POINTER(stage.P)])(
        handle, 1, 7, None, None, None, None, ctypes.byref(descriptor))
    if code:
        raise ctypes.WinError(code)
    try:
        mapping = Mapping(0x120089, 0x120116, 0x1200a0, 0x1f01ff)
        function = stage.api('advapi32.dll', 'AccessCheck', W.BOOL,
                             [stage.P, W.HANDLE, W.DWORD, ctypes.POINTER(Mapping), stage.P,
                              ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD), ctypes.POINTER(W.BOOL)])
        result = {}
        for name, mask in RIGHTS.items():
            privileges = ctypes.create_string_buffer(4096); length = W.DWORD(len(privileges)); granted = W.DWORD(); allowed = W.BOOL()
            stage.check(function(descriptor, token, mask, ctypes.byref(mapping), privileges, ctypes.byref(length),
                                 ctypes.byref(granted), ctypes.byref(allowed)))
            result[name] = {'requestedMask': mask, 'allowedByObjectSecurityDescriptor': bool(allowed.value), 'grantedMask': granted.value,
                            'privilegeCountUsed': struct.unpack('<I', privileges.raw[:4])[0]}
        return result
    finally:
        stage.free(descriptor)


def inspect():
    stage = stage_module(); program = stage.known_folder('905e63b6-c1bf-494e-b29c-65b732d3d21a')
    trusted = {stage.SYSTEM, stage.ADMINS, stage.account_sid('NT SERVICE\\TrustedInstaller')}
    result = []
    with stage.pinned_parents(program/'SL3 Rebuild') as handles, query_token(stage) as token:
        for handle in handles:
            entry = {'file': stage.information(handle, True), 'security': stage.security_info(handle),
                     'currentTokenObjectAccess': access_rights(stage, handle, token)}
            try:
                proof = stage.safe_parent(handle, trusted)
                entry['currentAncestorPredicate'] = {'accepted': True, 'volumeAnchor': proof['volumeAnchor'], 'untrustedMutationMask': proof['untrustedMutationMask']}
            except ValueError as error:
                entry['currentAncestorPredicate'] = {'accepted': False, 'reason': str(error)}
            result.append(entry)
    return {'schema': 'sl3.ancestor-rights-inspection.v1', 'ancestors': result, 'tokenElevated': stage.elevated(),
            'tokenPrivileges': token_privileges(stage),
            'tokenImpersonated': False, 'privilegesChanged': False, 'hostAclWritten': False,
            'productionPredicateWrittenByDiagnostic': False, 'productionStageExecuted': False, 'deviceAccess': False}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv == ['--plan']:
        print(json.dumps({'schema': 'sl3.ancestor-rights-plan.v1', 'planOnly': True, 'hostAclWritten': False,
                          'productionPredicateWrittenByDiagnostic': False, 'deviceAccess': False})); return
    if argv != ['--inspect']:
        raise ValueError('Only --plan or read-only --inspect is supported')
    print(json.dumps(inspect()))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
