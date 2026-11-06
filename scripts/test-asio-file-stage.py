"""Actual Windows file/ACL tests in a fresh workspace tree, never Program Files."""
import ctypes
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/asio-file-stage.py'


def require(value, text):
    if not value:
        raise AssertionError(text)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    spec = importlib.util.spec_from_file_location('sl3_file_stage_under_test', TOOL)
    stage = importlib.util.module_from_spec(spec); sys.modules[spec.name] = stage; spec.loader.exec_module(stage)
    require(not stage.elevated(), 'This unattended suite must run non-elevated; no machine stage is permitted')
    pointer = json.loads((Path(sys.argv[1]).absolute() if len(sys.argv) == 2 else ROOT/'artifacts/build/deployment-tests-last.json').read_text()); source_index = Path(pointer['directory'])/'index.json'
    require(sha(source_index) == pointer['indexSha256'], 'Reviewed package test index')
    package = json.loads(source_index.read_text()); bundle = ROOT/package['positiveBundle']; expected = package['bundleManifestSha256']
    staged_files = len(json.loads((bundle/'bundle-manifest.json').read_text())['files']) + 3
    module = stage.reader(); module.verify(bundle, expected)
    identity = uuid.uuid4().hex; folder = ROOT/'artifacts/build/file-stage-tests'/identity; folder.mkdir(parents=True)
    sid = stage.user_sid(); policy = stage.Policy(sid, (stage.SYSTEM, stage.ADMINS, sid))
    cases = []; diagnostics = {}
    plan = json.loads((bundle/'deployment-plan.json').read_text())
    installation = Path(plan['installationDirectory']); profile_pointer = Path(plan['pointerPath'])
    before = (installation.exists(), profile_pointer.parent.exists())

    def case(name, action):
        result = action()
        cases.append({'name': name, 'passed': True})
        if result is not None:
            diagnostics[name] = result
        return result

    def rejected(action):
        try:
            action()
        except (ValueError, OSError) as error:
            return {'refused': True, 'error': str(error)}
        raise AssertionError('Expected file-stage refusal')

    def command(name, args, expected_exit=0):
        result = subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True, encoding='utf-8', timeout=30)
        (folder/f'{name}-stdout.txt').write_text(result.stdout, encoding='utf-8')
        (folder/f'{name}-stderr.txt').write_text(result.stderr, encoding='utf-8')
        require(result.returncode == expected_exit, f'{name}: {result.returncode}: {result.stdout} {result.stderr}')
        return result

    for name, args in [('default', []), ('plan', ['--plan'])]:
        def inert(args=args, name=name):
            result = json.loads(command(name, args).stdout)
            require(result['planOnly'] and not result['filesWritten'] and not result['registryWritten'], 'Inert plan')
            return result
        case(name, inert)
    case('elevation-gate', lambda: {'exit': command('elevation-gate', ['--stage-production', '--bundle', bundle, '--expected-bundle-sha256', expected], 1).returncode})

    def production_check():
        result = subprocess.run([sys.executable, str(TOOL), '--check-production', '--bundle', str(bundle), '--expected-bundle-sha256', expected],
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        (folder/'production-check-stdout.txt').write_text(result.stdout, encoding='utf-8'); (folder/'production-check-stderr.txt').write_text(result.stderr, encoding='utf-8')
        require(result.returncode in (0, 1), 'Read-only production check completes normally')
        if result.returncode == 0:
            value = json.loads(result.stdout); require(not value['filesWritten'] and not value['productionStageExecuted'], 'Preflight writes nothing')
        else:
            require('Untrusted write/replacement rights on installation ancestor' in result.stderr, 'Retain the observed conservative ancestor-policy refusal')
        return {'exit': result.returncode, 'parentPolicyPassed': result.returncode == 0, 'refusal': result.stderr.strip()}
    case('read-only-production-check', production_check)
    case('native-known-folders', lambda: {'programFiles': str(stage.known_folder('905e63b6-c1bf-494e-b29c-65b732d3d21a')),
                                         'planScope': list(map(str, stage.production_destination(plan)))})

    destination = folder/'positive'; source_before = {p.name: sha(p) for p in bundle.iterdir()}; attempted = []
    def journal(event):
        if not attempted:
            denied = False
            try:
                with (bundle/'sl3_asio.dll').open('r+b'):
                    pass  # Probe access only: never modify the reviewed source.
            except PermissionError:
                denied = True
            require(denied, 'Held source handle denies concurrent writable open')
            attempted.append(True)
    receipt = case('actual-user-policy-stage', lambda: stage.stage_new(bundle, expected, destination, policy, journal))
    require(attempted and not receipt['productionPolicy'] and not receipt['registered'], 'Test descriptor cannot certify production protection')
    record_hash = receipt['stageRecordSha256']
    value = case('actual-stage-inspection', lambda: stage.inspect_stage(destination, record_hash, policy))
    require(value['files'] == staged_files and not value['productionPolicy'] and not value['plannedDestinationMatches'], 'Actual user-owned stage remains distinct from planned Program Files installation')
    require(source_before == {p.name: sha(p) for p in bundle.iterdir()}, 'Source package unchanged')
    for name in module.required_files(json.loads((bundle/'bundle-manifest.json').read_text())) | {'bundle-manifest.json'}:
        require((bundle/name).read_bytes() == (destination/name).read_bytes(), 'Exact captured-to-staged bytes')
    case('production-rejects-test-descriptor', lambda: rejected(lambda: stage.inspect_stage(destination, record_hash)))
    original = {p.name: sha(p) for p in destination.iterdir()}
    case('existing-destination', lambda: rejected(lambda: stage.stage_new(bundle, expected, destination, policy)))
    require(original == {p.name: sha(p) for p in destination.iterdir()}, 'Existing target preserved')
    bad = folder/'bad-source-hash'
    case('source-manifest-hash', lambda: rejected(lambda: stage.stage_new(bundle, '0'*64, bad, policy))); require(not bad.exists(), 'No context on hash refusal')
    missing = folder/'missing-parent'/'stage'
    case('missing-parent', lambda: rejected(lambda: stage.stage_new(bundle, expected, missing, policy))); require(not missing.parent.exists(), 'No implicit parent creation')
    with (bundle/'sl3_usbdk.exe').open('r+b'):
        case('source-writer-sharing', lambda: rejected(lambda: stage.stage_new(bundle, expected, folder/'blocked-source', policy)))
    require(not (folder/'blocked-source').exists(), 'Existing source writer prevents any stage creation')

    partial = folder/'partial'; calls = []
    def interrupt(event):
        if event['event'] == 'before_file':
            calls.append(event)
        if len(calls) == 2:
            raise OSError('Injected caller-journal interruption before second file')
    case('interrupted-copy', lambda: rejected(lambda: stage.stage_new(bundle, expected, partial, policy, interrupt)))
    require((partial/'stage-intent.json').is_file() and not (partial/'stage-record.json').exists(), 'Partial stage retains intent and never publishes complete receipt')
    intent = json.loads((partial/'stage-intent.json').read_text()); require(intent['complete'] is False and intent['bundleManifestSha256'] == expected, 'Preserved recovery intent')
    require(len(list(partial.iterdir())) == 2, 'Only intent and first committed payload remain')

    text = destination/'README.txt'; old = text.read_bytes()
    try:
        text.write_bytes(old+b'changed')
        case('changed-payload', lambda: rejected(lambda: stage.inspect_stage(destination, record_hash, policy)))
    finally:
        text.write_bytes(old)
    case('restored-payload', lambda: stage.inspect_stage(destination, record_hash, policy))
    extra = destination/'unexpected.txt'
    try:
        extra.write_text('unknown data; must not be deleted by verification')
        case('extra-file', lambda: rejected(lambda: stage.inspect_stage(destination, record_hash, policy)))
        require(extra.read_text().startswith('unknown'), 'Unknown file preserved')
    finally:
        extra.unlink()
    alias = folder/'hardlink.txt'
    try:
        import os
        os.link(text, alias)
        case('hardlink', lambda: rejected(lambda: stage.inspect_stage(destination, record_hash, policy)))
    finally:
        alias.unlink()
    case('receipt-hash', lambda: rejected(lambda: stage.inspect_stage(destination, '0'*64, policy)))

    def make_text(path, data, sddl=None):
        with stage.descriptor(sddl or policy.sddl(False)) as attributes:
            with stage.open_file(path, access=0xc0040000, create=1, security=attributes) as handle:
                count = W.DWORD()
                stage.check(stage.api('kernel32.dll', 'WriteFile', W.BOOL, [W.HANDLE, stage.P, W.DWORD, ctypes.POINTER(W.DWORD), stage.P])(
                    handle, data, len(data), ctypes.byref(count), None))
                require(count.value == len(data), 'Complete synthetic text write')
                return stage.information(handle, False)

    saved = folder/'original-readme.txt'; replacement = folder/'replacement-readme.txt'
    make_text(replacement, old); text.replace(saved); replacement.replace(text)
    try:
        detail = case('same-byte-file-replacement', lambda: rejected(lambda: stage.inspect_stage(destination, record_hash, policy)))
        require('identity/bytes mismatch' in detail['error'], 'Exact file identity detects same-byte replacement')
    finally:
        saved.replace(text)

    weak = folder/'acl-test.txt'
    weak_sddl = policy.sddl(False)+'(A;;FA;;;WD)'
    with stage.descriptor(weak_sddl) as attributes:
        with stage.open_file(weak, access=0xc0040000, create=1, security=attributes) as handle:
            try:
                case('unexpected-write-ace', lambda: rejected(lambda: stage.inspect_policy(handle, policy, False)))
            finally:
                # Restore this exact synthetic test file even if the assertion fails.
                with stage.descriptor(policy.sddl(False)) as safe:
                    present, defaulted, dacl = W.BOOL(), W.BOOL(), stage.P()
                    stage.check(stage.api('advapi32.dll', 'GetSecurityDescriptorDacl', W.BOOL,
                                         [stage.P, ctypes.POINTER(W.BOOL), ctypes.POINTER(stage.P), ctypes.POINTER(W.BOOL)])(
                        safe.descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)))
                    code = stage.api('advapi32.dll', 'SetSecurityInfo', W.DWORD,
                                     [W.HANDLE, W.DWORD, W.DWORD, stage.P, stage.P, stage.P, stage.P])(
                        handle, 1, 0x80000004, None, None, dacl, None)
                    require(code == 0, 'Restore only the synthetic test-file DACL')
            case('test-acl-restored', lambda: stage.inspect_policy(handle, policy, False))

    copied = folder/'different-root'; copied_receipt = stage.stage_new(bundle, expected, copied, policy)
    copied_record = (copied/'stage-record.json').read_bytes()
    try:
        (copied/'stage-record.json').write_bytes((destination/'stage-record.json').read_bytes())
        case('receipt-in-different-directory', lambda: rejected(lambda: stage.inspect_stage(copied, record_hash, policy)))
    finally:
        (copied/'stage-record.json').write_bytes(copied_record)
    case('different-root-restored', lambda: stage.inspect_stage(copied, copied_receipt['stageRecordSha256'], policy))
    case('positive-stage-final', lambda: stage.inspect_stage(destination, record_hash, policy))
    require((installation.exists(), profile_pointer.parent.exists()) == before, 'Planned Program Files/pointer locations unchanged')
    require(source_before == {p.name: sha(p) for p in bundle.iterdir()}, 'Reviewed source remains unchanged after suite')
    (folder/'case-details.json').write_text(json.dumps(diagnostics, indent=2)+'\n', encoding='utf-8')
    files = {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob('*') if p.is_file()}
    result = {'schema': 'sl3.file-stage-tests.v1', 'cases': cases, 'files': files, 'testPolicyOwnerCurrentUser': True,
              'testDescriptorCertifiedAsProduction': False, 'productionStageExecuted': False, 'plannedLocationsUnchanged': True,
              'sourceBundleUnchanged': True, 'registryWritten': False, 'binaryPayloadExecuted': False, 'deviceAccess': False,
              'positiveStageRecordSha256': record_hash, 'productionPreflight': diagnostics['read-only-production-check']}
    index = folder/'index.json'; index.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/file-stage-tests-last.json').write_text(json.dumps({'directory': str(folder), 'indexSha256': sha(index)}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'productionStageExecuted': False, 'evidenceDirectory': str(folder)}))


if __name__ == '__main__':
    main()
