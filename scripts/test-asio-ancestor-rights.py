"""Controlled ACL/junction experiments confined to fresh workspace fixtures."""
import ctypes
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/inspect-asio-ancestor-rights.py'


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    spec = importlib.util.spec_from_file_location('sl3_ancestor_inspector_test', TOOL)
    inspect = importlib.util.module_from_spec(spec); spec.loader.exec_module(inspect)
    stage = inspect.stage_module(); require(not stage.elevated(), 'Non-elevated fixture suite required')
    sid = stage.user_sid(); full = stage.Policy(sid, (stage.SYSTEM, stage.ADMINS, sid))
    child_policy = stage.Policy(sid, (stage.SYSTEM, stage.ADMINS))
    folder = ROOT/'artifacts/build/ancestor-policy-tests'/uuid.uuid4().hex; folder.mkdir(parents=True)
    cases = []; details = {}; host_before = inspect.inspect()

    def case(name, value):
        details[name] = value; cases.append({'name': name, 'passed': True})

    for name, args in [('default', []), ('plan', ['--plan']), ('readonly-inspect', ['--inspect'])]:
        result = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, encoding='utf-8', timeout=20)
        require(result.returncode == 0, f'{name}: {result.stderr}')
        (folder/f'{name}-stdout.json').write_text(result.stdout, encoding='utf-8')
        value = json.loads(result.stdout); require(value['hostAclWritten'] is False and not value['productionPredicateWrittenByDiagnostic'], 'Public CLI never changes host policy')
        case(name, value)

    def guard(path):
        require(path.is_absolute() and path.resolve().is_relative_to(folder.resolve()) and path != folder, 'Mutation confined to this fresh fixture tree')

    def set_dacl(handle, sddl):
        with stage.descriptor(sddl) as descriptor:
            present, defaulted, dacl = W.BOOL(), W.BOOL(), stage.P()
            stage.check(stage.api('advapi32.dll', 'GetSecurityDescriptorDacl', W.BOOL,
                                 [stage.P, ctypes.POINTER(W.BOOL), ctypes.POINTER(stage.P), ctypes.POINTER(W.BOOL)])(
                descriptor.descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)))
            code = stage.api('advapi32.dll', 'SetSecurityInfo', W.DWORD,
                             [W.HANDLE, W.DWORD, W.DWORD, stage.P, stage.P, stage.P, stage.P])(
                handle, 1, 0x80000004, None, None, dacl, None)
            if code:
                raise ctypes.WinError(code)

    def directory(path):
        guard(path)
        with stage.descriptor(full.sddl(True)) as descriptor:
            stage.check(stage.api('kernel32.dll', 'CreateDirectoryW', W.BOOL, [W.LPCWSTR, ctypes.POINTER(stage.Attributes)])(
                str(path), ctypes.byref(descriptor)))

    def probe(path, mask):
        guard(path)
        try:
            with stage.open_file(path, access=mask, share=7) as handle:
                stage.information(handle, False)
            return {'opened': True, 'requestedMask': mask, 'dataWritten': False, 'deleteDispositionSet': False}
        except OSError as error:
            return {'opened': False, 'requestedMask': mask, 'winerror': error.winerror}

    parent = folder/'parent'; directory(parent); child = parent/'protected.txt'; child.write_bytes(b'unchanged protected-child data\n')
    guard(child)
    with stage.open_file(parent, True, access=0x60080, share=7) as parent_handle, stage.open_file(child, access=0x60080, share=7) as child_handle:
        try:
            # Mirror the observed effective Modify mask, but only on this fixture.
            modify = f'O:{sid}D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;;0x1301bf;;;AU)(A;;0x1200a9;;;BU)'
            set_dacl(parent_handle, modify); set_dacl(child_handle, child_policy.sddl(False))
            with inspect.query_token(stage) as token:
                parent_rights = inspect.access_rights(stage, parent_handle, token)
                child_rights = inspect.access_rights(stage, child_handle, token)
            require(parent_rights['writeDataOrAddFile']['allowedByObjectSecurityDescriptor'] and
                    not parent_rights['deleteChildren']['allowedByObjectSecurityDescriptor'], 'Modify grants parent add-file but not delete-child')
            require(not child_rights['writeDataOrAddFile']['allowedByObjectSecurityDescriptor'], 'Protected child object denies data write')
            case('object-access-checks', {'parent': parent_rights, 'child': child_rights, 'ownerIsCurrentUserFixtureOnly': True})
            write = probe(child, 2); delete = probe(child, 0x10000)
            require(not write['opened'] and write['winerror'] == 5 and not delete['opened'] and delete['winerror'] == 5,
                    'Actual file opens deny protected child write/delete despite parent Modify')
            case('protected-child-opens-denied', {'write': write, 'delete': delete})
            add_delete = modify.replace('0x1301bf', '0x1301ff')
            set_dacl(parent_handle, add_delete)
            with inspect.query_token(stage) as token:
                require(inspect.access_rights(stage, parent_handle, token)['deleteChildren']['allowedByObjectSecurityDescriptor'], 'Explicit delete-child control granted')
            delete = probe(child, 0x10000); write = probe(child, 2)
            require(delete['opened'] and not write['opened'], 'Parent delete-child permits deletion access, not child data write')
            case('delete-child-control', {'deleteHandleOnly': delete, 'write': write})
            require(child.read_bytes() == b'unchanged protected-child data\n', 'No probe modified or deleted child')
        finally:
            set_dacl(child_handle, full.sddl(False)); set_dacl(parent_handle, full.sddl(True))
        stage.inspect_policy(child_handle, full, False); stage.inspect_policy(parent_handle, full, True)
        case('fixture-acls-restored', {'verified': True})

    target = folder/'junction-target'; directory(target); sentinel = target/'sentinel.txt'; sentinel.write_text('target must remain unchanged\n')
    sentinel_sha = sha(sentinel)
    results = []
    for name, nonempty in [('junction-empty', False), ('junction-nonempty', True)]:
        source = folder/name; directory(source); guard(source); guard(target)
        if nonempty:
            (source/'original.txt').write_text('source data retained\n')
        substitute = ('\\??\\'+str(target)).encode('utf-16le'); printable = str(target).encode('utf-16le')
        data = substitute+b'\0\0'+printable+b'\0\0'
        buffer = struct.pack('<IHHHHHH', 0xa0000003, 8+len(data), 0, 0, len(substitute), len(substitute)+2, len(printable))+data
        function = stage.api('kernel32.dll', 'DeviceIoControl', W.BOOL,
                             [W.HANDLE, W.DWORD, stage.P, W.DWORD, stage.P, W.DWORD, ctypes.POINTER(W.DWORD), stage.P])
        returned = W.DWORD(); success = False
        with stage.open_file(source, True, access=0xc0000000, share=3) as handle:
            before = stage.information(handle, True); require(Path(before['path']) == source, 'Exact private junction source handle')
            try:
                success = bool(function(handle, 0x900a4, buffer, len(buffer), None, 0, ctypes.byref(returned), None))
                error = 0 if success else ctypes.get_last_error()
                results.append({'name': name, 'setSucceeded': success, 'winerror': error, 'sourceNonempty': nonempty})
            finally:
                if success:
                    deletion = struct.pack('<IHH', 0xa0000003, 0, 0)
                    stage.check(function(handle, 0x900ac, deletion, len(deletion), None, 0, ctypes.byref(returned), None))
                after = stage.information(handle, True)
                require(before['identity'] == after['identity'], 'Original fixture directory retained without reparse tag')
        require(sha(sentinel) == sentinel_sha, 'Junction target bytes unchanged')
        if nonempty:
            require((source/'original.txt').read_text() == 'source data retained\n', 'Original nonempty source data unchanged')
        case(name, results[-1] | {'tagAbsentAfterward': True, 'originalDirectoryRetained': True})
    case('junction-calibration-scope', {'emptySourceCalibrated': results[0]['setSucceeded'],
                                      'nonemptyMountPointRefused': not results[1]['setSucceeded'],
                                      'volumeRootOrOtherReparseTagsTested': False})
    trusted = {stage.SYSTEM, stage.ADMINS, stage.account_sid('NT SERVICE\\TrustedInstaller')}
    anchor = next(x for x in host_before['ancestors'] if x['currentAncestorPredicate'].get('volumeAnchor'))
    import copy
    for name, changed in [('delete-child', 0x40), ('write-dacl', 0x40000), ('write-owner', 0x80000), ('generic-all', 0x10000000)]:
        altered = copy.deepcopy(anchor['security'])
        ace = next(x for x in altered['aces'] if x['sid'] == 'S-1-5-11' and not x['flags'] & 8)
        ace['mask'] |= changed
        refused = False
        try:
            stage.validate_ancestor_acl(anchor['file'], altered, trusted, anchor['currentAncestorPredicate']['volumeAnchor'])
        except ValueError:
            refused = True
        require(refused, 'Volume anchor must retain dangerous-right refusals')
        case('anchor-refuses-'+name, {'refused': True, 'hostAclChanged': False, 'syntheticAclModelOnly': True})
    with stage.open_file(parent, True, access=0x60080, share=7) as handle:
        # Apply the same effective Modify mask only to this ordinary fixture.
        try:
            set_dacl(handle, modify)
            refused = False
            try:
                stage.safe_parent(handle, trusted | {sid})
            except ValueError:
                refused = True
            require(refused, 'A writable ordinary directory never gains the drive-anchor exception')
            case('ordinary-directory-still-refused', {'refused': True, 'volumeAnchor': False})
        finally:
            set_dacl(handle, full.sddl(True))
        stage.inspect_policy(handle, full, True)
    host_after = inspect.inspect()
    require(host_after == host_before, 'Read-only host descriptor/access snapshots unchanged')
    require(all(x['currentAncestorPredicate']['accepted'] for x in host_after['ancestors']), 'Corrected native ancestor check passes this host without ACL changes')
    case('host-snapshot-unchanged', {'verified': True, 'productionGateReadOnlyPasses': True})
    (folder/'case-details.json').write_text(json.dumps(details, indent=2)+'\n', encoding='utf-8')
    files = {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob('*') if p.is_file()}
    report = {'schema': 'sl3.ancestor-policy-review-tests.v1', 'cases': cases, 'files': files,
              'hostBefore': host_before, 'hostAfter': host_after, 'hostAclsChanged': False,
              'privateFixtureAclsRestored': True, 'privateJunctionTagsRemoved': True,
              'junctionCalibration': results, 'productionPredicateSourceCorrected': True,
              'productionStageExecuted': False, 'sl3UsbDeviceAccess': False}
    index = folder/'index.json'; index.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/ancestor-policy-tests-last.json').write_text(json.dumps({'directory': str(folder), 'indexSha256': sha(index)}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'junctionCalibration': results,
                      'hostAclsChanged': False, 'productionPredicateSourceCorrected': True, 'evidenceDirectory': str(folder)}))


if __name__ == '__main__':
    main()
