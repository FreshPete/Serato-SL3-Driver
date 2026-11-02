"""Real non-elevated cleanup tests, confined to new workspace-owned stages."""
import ctypes
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/asio-file-stage.py'


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    spec = importlib.util.spec_from_file_location('sl3_cleanup_under_test', TOOL)
    stage = importlib.util.module_from_spec(spec); sys.modules[spec.name] = stage; spec.loader.exec_module(stage)
    require(not stage.elevated(), 'Unattended test must be non-elevated')
    pointer = json.loads((ROOT/'artifacts/build/deployment-tests-last.json').read_text())
    index = Path(pointer['directory'])/'index.json'
    require(sha(index) == pointer['indexSha256'], 'Reviewed package index hash')
    package = json.loads(index.read_text()); bundle = ROOT/package['positiveBundle']; expected = package['bundleManifestSha256']
    stage.reader().verify(bundle, expected)
    folder = ROOT/'artifacts/build/file-cleanup-tests'/uuid.uuid4().hex; folder.mkdir(parents=True)
    sid = stage.user_sid(); policy = stage.Policy(sid, (stage.SYSTEM, stage.ADMINS, sid))
    plan = json.loads((bundle/'deployment-plan.json').read_text())
    locations = [Path(plan['installationDirectory']), Path(plan['pointerPath']).parent]
    before = [p.exists() for p in locations]; source_before = {p.name: sha(p) for p in bundle.iterdir()}
    cases = []; details = {}

    def case(name, operation):
        value = operation(); cases.append({'name': name, 'passed': True}); details[name] = value
        return value

    def fixture(name):
        destination = folder/name
        require(destination.is_relative_to(folder) and not destination.exists(), 'Fresh private stage only')
        receipt = stage.stage_new(bundle, expected, destination, policy)
        return destination, receipt['stageRecordSha256']

    def snapshot(destination):
        return {p.name: sha(p) for p in destination.iterdir() if p.is_file()}

    def refused(destination, digest, journal=None, used_policy=policy, zero=True):
        before_files = snapshot(destination)
        try:
            stage.remove_stage(destination, digest, used_policy, journal)
        except stage.CleanupFailure as error:
            value = error.report
            require(not value['successful'] and not value['directoryAbsentObserved'], 'Failure cannot certify cleanup')
            if zero:
                require(not value['deleteMarkedFiles'] and not value['absentObservedFiles'], 'Refuse before any deletion')
                require(snapshot(destination) == before_files, 'Refused stage bytes preserved')
            return value
        raise AssertionError('Expected cleanup refusal')

    def command(name, args, exit_code):
        result = subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        (folder/(name+'-stdout.txt')).write_text(result.stdout, encoding='utf-8')
        (folder/(name+'-stderr.txt')).write_text(result.stderr, encoding='utf-8')
        require(result.returncode == exit_code, name+': '+result.stderr)
        return {'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}

    for name, args in [('default', []), ('plan', ['--plan'])]:
        result = case(name, lambda name=name, args=args: command(name, args, 0))
        require(json.loads(result['stdout'])['planOnly'], 'Default/plan inert')
    case('no-public-removal-command', lambda: command('no-removal-command', ['--remove-production', '--bundle', bundle,
        '--expected-bundle-sha256', expected], 2))
    case('no-public-test-policy-override', lambda: command('no-policy-override', ['--stage-production', '--bundle', bundle,
        '--expected-bundle-sha256', expected, '--test-policy', sid], 2))
    def normal_token():
        try:
            stage.remove_production_stage(folder, '0'*64, lambda event: None)
        except ValueError as error:
            require('explicitly elevated' in str(error), 'Elevation gate precedes all cleanup work')
            return {'refused': True, 'error': str(error)}
        raise AssertionError('Production cleanup must refuse the ordinary token')
    case('normal-token-production-refusal', normal_token)

    positive, digest = fixture('positive'); events = []
    result = case('complete-owned-cleanup', lambda: stage.remove_stage(positive, digest, policy, events.append))
    require(result['successful'] and result['directoryDeletionMarked'] and result['directoryAbsentObserved'] and
            stage.absent(positive) and len(result['deleteMarkedFiles']) == 14 and
            result['deleteMarkedFiles'] == result['absentObservedFiles'], 'All fourteen files and own directory observed absent')
    require(events[0]['event'] == 'validated' and events[0]['stageRecordSha256'] == digest and
            len(events[0]['stageRecord']['files']) == 12, 'Caller receives recovery metadata before mutation')
    require(result['deleteMarkedFiles'][-2:] == ['stage-intent.json', 'stage-record.json'] and
            result['deleteMarkedFiles'][0] == 'sl3_asio.dll', 'Binaries first, intent/receipt last')
    (folder/'positive-journal.json').write_text(json.dumps(events, indent=2)+'\n', encoding='utf-8')

    destination, digest = fixture('bad-hash')
    case('wrong-receipt-hash', lambda: refused(destination, '0'*64))
    case('production-rejects-user-owned-stage', lambda: refused(destination, digest, used_policy=stage.PRODUCTION))

    destination, digest = fixture('changed-file'); (destination/'README.txt').write_bytes(b'changed fixture')
    case('changed-payload', lambda: refused(destination, digest))
    destination, digest = fixture('extra-file'); (destination/'foreign.txt').write_bytes(b'preserve foreign data')
    case('extra-file', lambda: refused(destination, digest))
    destination, digest = fixture('missing-file'); (destination/'README.txt').unlink()
    case('missing-file', lambda: refused(destination, digest))
    destination, digest = fixture('hardlink'); alias = folder/'linked-readme.txt'
    try:
        os.link(destination/'README.txt', alias)
        case('hardlink', lambda: refused(destination, digest))
    finally:
        alias.unlink()

    destination, digest = fixture('same-byte-replacement'); text = destination/'README.txt'; data = text.read_bytes()
    replacement, replacement_hash = fixture('replacement-donor')
    saved = folder/'original-readme.txt'; text.replace(saved); (replacement/'README.txt').replace(text)
    require(text.read_bytes() == data, 'Replacement bytes identical')
    case('same-byte-new-file-identity', lambda: refused(destination, digest))
    saved.replace(text)  # Restore original owned fixture; no recursive deletion.

    destination, digest = fixture('replacement-after-preflight'); donor, donor_hash = fixture('late-replacement-donor')
    original_inspect = stage.inspect_stage; saved = folder/'preflight-readme.txt'
    def replace_after_inspection(*args, **kwargs):
        value = original_inspect(*args, **kwargs)
        (destination/'README.txt').replace(saved)
        (donor/'README.txt').replace(destination/'README.txt')
        return value
    try:
        stage.inspect_stage = replace_after_inspection
        case('identity-rechecked-through-delete-handle', lambda: refused(destination, digest))
    finally:
        stage.inspect_stage = original_inspect
        if saved.exists():
            saved.replace(destination/'README.txt')

    destination, digest = fixture('held-delete-handles'); writer_denied = []
    def probe_writer(event):
        if event['event'] == 'validated':
            try:
                with stage.open_file(destination/'README.txt', access=0x40000000, share=7):
                    pass
            except OSError as error:
                require(error.winerror == 32, 'Native held-handle sharing refusal')
                writer_denied.append(True)
            require(writer_denied, 'All reviewed file handles deny a concurrent writer before deletion')
    case('delete-handles-deny-concurrent-writer', lambda: stage.remove_stage(destination, digest, policy, probe_writer))
    require(writer_denied, 'Actual write-open probe ran')

    destination, digest = fixture('wrong-directory'); donor, donor_hash = fixture('receipt-donor')
    (destination/'stage-record.json').write_bytes((donor/'stage-record.json').read_bytes())
    case('receipt-for-different-root', lambda: refused(destination, donor_hash))

    destination, digest = fixture('active-reader')
    with stage.open_file(destination/'README.txt'):
        value = case('active-reader-refuses-before-deletion', lambda: refused(destination, digest))
        require('[WinError 32]' in value['error'], 'Sharing violation observed')
    case('reader-release-allows-cleanup', lambda: stage.remove_stage(destination, digest, policy))

    destination, digest = fixture('weak-acl'); target = destination/'README.txt'
    def set_dacl(sddl):
        with stage.open_file(target, access=0x60000, share=7) as handle:
            with stage.descriptor(sddl) as attributes:
                present, defaulted, dacl = W.BOOL(), W.BOOL(), stage.P()
                stage.check(stage.api('advapi32.dll', 'GetSecurityDescriptorDacl', W.BOOL,
                    [stage.P, ctypes.POINTER(W.BOOL), ctypes.POINTER(stage.P), ctypes.POINTER(W.BOOL)])(
                        attributes.descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)))
                result = stage.api('advapi32.dll', 'SetSecurityInfo', W.DWORD,
                    [W.HANDLE, W.DWORD, W.DWORD, stage.P, stage.P, stage.P, stage.P])(handle, 1, 0x80000004, None, None, dacl, None)
                if result:
                    raise ctypes.WinError(result)
    try:
        set_dacl(policy.sddl(False)+'(A;;FA;;;WD)')
        case('unexpected-write-ace', lambda: refused(destination, digest))
    finally:
        set_dacl(policy.sddl(False))
    case('fixture-acl-restored', lambda: stage.inspect_stage(destination, digest, policy))

    destination, digest = fixture('journal-before-mutation')
    def fail_before(event):
        if event['event'] == 'validated':
            raise OSError('Simulated external recovery journal failure')
    case('journal-failure-before-mutation', lambda: refused(destination, digest, fail_before))

    destination, digest = fixture('journal-after-first-file'); external = []
    def fail_after(event):
        external.append(event)
        if event['event'] == 'deleted':
            raise OSError('Simulated journal failure after observed first deletion')
    result = case('journal-failure-truthful-partial', lambda: refused(destination, digest, fail_after, zero=False))
    require(result['deleteMarkedFiles'] == ['sl3_asio.dll'] and result['absentObservedFiles'] == ['sl3_asio.dll'] and
            result['stageRecordStillPresent'] and result['intentStillPresent'], 'Partial receipt retains exact observed deletion and recovery records')
    require(not (destination/'sl3_asio.dll').exists() and len(snapshot(destination)) == 13, 'No retry or remaining file deletion')

    destination, digest = fixture('late-foreign-file'); unknown = destination/'foreign.txt'
    def late_file(event):
        if event['event'] == 'before_delete' and event['name'] == 'stage-intent.json':
            unknown.write_bytes(b'foreign data must survive')
    result = case('late-foreign-file-preserved', lambda: refused(destination, digest, late_file, zero=False))
    require(len(result['absentObservedFiles']) == 12 and result['stageRecordStillPresent'] and result['intentStillPresent'] and
            unknown.read_bytes() == b'foreign data must survive', 'Late unknown data and recovery metadata retained')

    destination, digest = fixture('late-directory-data'); late = destination/'foreign.txt'
    def before_directory(event):
        if event['event'] == 'before_directory_delete':
            late.write_bytes(b'directory is no longer empty')
    result = case('nonempty-final-directory-preserved', lambda: refused(destination, digest, before_directory, zero=False))
    require(len(result['absentObservedFiles']) == 14 and not result['directoryDeletionMarked'] and late.exists() and
            not result['stageRecordStillPresent'], 'External recovery record required after receipt deletion')

    destination, digest = fixture('mapped-image')
    mapping = None; view = None
    try:
        with stage.open_file(destination/'sl3_asio.dll', share=7) as handle:
            mapping = stage.Handle(stage.api('kernel32.dll', 'CreateFileMappingW', W.HANDLE,
                [W.HANDLE, stage.P, W.DWORD, W.DWORD, W.DWORD, W.LPCWSTR])(handle, None, 0x1000002, 0, 0, None))
            view = stage.check(stage.api('kernel32.dll', 'MapViewOfFile', stage.P,
                [W.HANDLE, W.DWORD, W.DWORD, W.DWORD, ctypes.c_size_t])(mapping.value, 4, 0, 0, 0))
        # Only an image section/view remains; no file handle or LoadLibrary.
        result = case('image-section-blocks-deletion', lambda: refused(destination, digest))
        require('[WinError 5]' in result['error'], 'Native access-denied image deletion refusal')
    finally:
        if view:
            stage.check(stage.api('kernel32.dll', 'UnmapViewOfFile', W.BOOL, [stage.P])(view))
        if mapping:
            mapping.close()
    case('released-image-allows-cleanup', lambda: stage.remove_stage(destination, digest, policy))

    require([p.exists() for p in locations] == before, 'Planned Program Files and pointer locations unchanged')
    require({p.name: sha(p) for p in bundle.iterdir()} == source_before, 'Source bundle unchanged')
    (folder/'case-details.json').write_text(json.dumps(details, indent=2)+'\n', encoding='utf-8')
    files = {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob('*') if p.is_file()}
    value = {'schema': 'sl3.file-cleanup-tests.v1', 'cases': cases, 'files': files,
             'toolSha256': sha(TOOL), 'testScriptSha256': sha(Path(__file__)),
             'testPolicyOwnerCurrentUser': True, 'productionCleanupExecuted': False,
             'plannedLocationsUnchanged': True, 'sourceBundleUnchanged': True,
             'registryWritten': False, 'binaryPayloadExecuted': False, 'deviceAccess': False,
             'imageSectionMappedWithoutExecution': True, 'liveRegistrationGuardsPositivelyTested': False}
    index = folder/'index.json'; index.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/file-cleanup-tests-last.json').write_text(json.dumps(
        {'directory': str(folder), 'indexSha256': sha(index)}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'evidenceDirectory': str(folder), 'productionCleanupExecuted': False}))


if __name__ == '__main__':
    main()
