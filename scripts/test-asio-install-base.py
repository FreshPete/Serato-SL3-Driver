"""Actual Windows workspace creation/reuse/race tests; never Program Files writes."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import ctypes
from ctypes import wintypes as W
import json
from pathlib import Path
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT/'scripts/asio-install-base.py'


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    spec = importlib.util.spec_from_file_location('sl3_base_under_test', TOOL)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    j = m.journal_module(); s = j.stage_module()
    require(not s.elevated(), 'Unattended suite must run ordinary token')
    sid = s.user_sid(); policy = s.Policy(sid, (s.SYSTEM, s.ADMINS, sid))
    folder = ROOT/'artifacts/build/install-base-tests'/uuid.uuid4().hex; folder.mkdir(parents=True)
    cases = []; details = {}; production_before = m.check_production_base()
    def case(name, action):
        value = action(); cases.append({'name': name, 'passed': True}); details[name] = value; return value
    def prepare(path, used_policy=policy):
        with m.prepared_base(path, used_policy) as report:
            return report
    def failed(action):
        try:
            action()
        except m.BasePreparationFailure as error:
            require(not error.report['policyVerified'], 'Preparation failure cannot certify policy')
            return error.report
        raise AssertionError('Expected base refusal')
    def inspect(path):
        with s.open_file(path, True, access=0x20080, share=3) as handle:
            return {'file': s.information(handle, True), 'security': s.security_info(handle)}
    def command(name, args, expected_exit):
        result = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, encoding='utf-8', timeout=20)
        (folder/(name+'-stdout.txt')).write_text(result.stdout, encoding='utf-8')
        (folder/(name+'-stderr.txt')).write_text(result.stderr, encoding='utf-8')
        require(result.returncode == expected_exit, name+': '+result.stderr)
        return {'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    for name, args in [('default', []), ('plan', ['--plan'])]:
        value = case(name, lambda name=name, args=args: command(name, args, 0))
        require(json.loads(value['stdout'])['planOnly'], 'Inert default/plan')
    case('no-production-mutation-cli', lambda: command('no-mutation', ['--prepare-production'], 2))
    preflight = case('actual-readonly-production-preflight', lambda: command('production-check', ['--check-production'], 0))
    preflight = json.loads(preflight['stdout'])
    require(not preflight['filesWritten'] and not preflight['registryWritten'] and not preflight['tokenElevated'], 'Actual native preflight writes nothing')
    path = folder/'positive'
    value = case('new-explicit-policy-directory', lambda: prepare(path))
    require(value['created'] and value['creationAttempted'] and value['policyVerified'] and not value['productionPolicy'] and
            not list(path.iterdir()), 'Only one empty current-user test directory created')
    original = inspect(path)
    (path/'foreign.txt').write_bytes(b'preserve existing contents')
    value = case('verified-base-reused-with-foreign-data-preserved', lambda: prepare(path))
    require(value['existingDirectoryReused'] and not value['creationAttempted'] and not value['created'] and
            not value['existingContentsClaimedOwned'] and (path/'foreign.txt').read_bytes() == b'preserve existing contents' and
            inspect(path)['security'] == original['security'], 'Existing policy/data not repaired or claimed owned')
    def metadata_calibration():
        candidate = folder/'raw-metadata'; target = folder/'raw-metadata-renamed'; prepare(candidate)
        require(candidate.resolve().is_relative_to(folder.resolve()) and target.resolve().parent == folder.resolve(), 'Private calibration paths')
        raw = s.Handle(s.api('kernel32.dll', 'CreateFileW', W.HANDLE,
            [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.POINTER(s.Attributes), W.DWORD, W.DWORD, W.HANDLE])(
                str(candidate), 0x20080, 3, None, 3, 0x2200000, None))
        try:
            with raw as handle:
                original = s.information(handle, True)['identity']; candidate.rename(target)
                observed = s.information(handle, True)
                require(observed['identity'] == original and Path(observed['path']) == target, 'Metadata-only open permits real rename of same object')
                target.rename(candidate)
        finally:
            if target.exists() and not candidate.exists():
                target.rename(candidate)
        return {'metadataOnlyAccess': '0x20080', 'shareReadWriteNoDelete': True, 'renameSucceeded': True, 'originalPathRestored': True}
    case('raw-metadata-only-open-native-calibration', metadata_calibration)
    def cannot_rename():
        candidate = folder/'held-base'; target = folder/'unexpected-move'
        with m.prepared_base(candidate, policy) as report:
            require(candidate.resolve().is_relative_to(folder.resolve()) and target.resolve().parent == folder.resolve(), 'Private move-probe paths')
            try:
                candidate.rename(target)
            except OSError as error:
                require(error.winerror in (5, 32), 'Native retained-directory refusal')
                require(candidate.exists() and not target.exists(), 'Base remains at pinned path')
                return {'winerror': error.winerror, 'identity': report['observed']['file']['identity']}
            raise AssertionError('Retained base must not be renamed')
    case('retained-handle-refuses-base-rename', cannot_rename)
    def consumer_failure():
        candidate = folder/'consumer-error'
        try:
            with m.prepared_base(candidate, policy):
                raise RuntimeError('Simulated later installer failure')
        except RuntimeError as error:
            require(type(error) is RuntimeError and candidate.exists() and not list(candidate.iterdir()), 'Consumer error type/empty protected base retained')
        else:
            raise AssertionError('Expected consumer failure')
        value = prepare(candidate); require(not value['created'] and value['policyVerified'], 'Explicit retry reuses retained base')
        return value
    case('consumer-failure-retains-base-for-explicit-retry', consumer_failure)
    missing = folder/'absent-parent'/'base'
    value = case('missing-parent-not-created', lambda: failed(lambda: prepare(missing)))
    require(not value['creationAttempted'] and not missing.parent.exists(), 'No implicit parent creation')
    ordinary = folder/'foreign-directory'; ordinary.mkdir(); (ordinary/'sentinel.txt').write_bytes(b'foreign folder')
    before = inspect(ordinary)
    case('ordinary-foreign-descriptor-preserved', lambda: failed(lambda: prepare(ordinary)))
    require(inspect(ordinary)['security'] == before['security'] and (ordinary/'sentinel.txt').read_bytes() == b'foreign folder', 'No descriptor or data repair')
    file = folder/'file-instead-of-directory'; file.write_bytes(b'preserve file')
    case('file-in-base-slot-preserved', lambda: failed(lambda: prepare(file)))
    require(file.read_bytes() == b'preserve file', 'No replacement of non-directory')
    wrong_owner = s.Policy(s.SYSTEM, (s.SYSTEM, s.ADMINS, sid))
    case('different-expected-owner-refused', lambda: failed(lambda: prepare(path, wrong_owner)))
    missing_ace = s.Policy(sid, (s.SYSTEM, s.ADMINS))
    case('different-expected-ace-list-refused', lambda: failed(lambda: prepare(path, missing_ace)))
    require(inspect(path)['security'] == original['security'], 'Owner/ACL mismatch refusals leave original descriptor')
    case('production-refuses-normal-token', lambda: failed(lambda: prepare(m.production_base(), s.PRODUCTION)))

    race = folder/'first-create-race'; barrier = threading.Barrier(2); peer_finished = threading.Event(); real_absent = s.absent
    def synchronized_absent(path):
        result = real_absent(path)
        if path == race and result:
            barrier.wait(timeout=15)
        return result
    def contender():
        try:
            with m.prepared_base(race, policy) as receipt:
                require(peer_finished.wait(timeout=15), 'Competing CreateDirectory call completes')
                return {'outcome': 'created', 'receipt': receipt}
        except m.BasePreparationFailure as error:
            peer_finished.set()
            return {'outcome': 'refused', 'receipt': error.report}
    try:
        s.absent = synchronized_absent
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(contender), pool.submit(contender)]
            outcomes = [future.result(timeout=30) for future in futures]
    finally:
        s.absent = real_absent
    require(sorted(x['outcome'] for x in outcomes) == ['created', 'refused'], 'Exactly one create wins; loser does not open-and-repair')
    winner = next(x['receipt'] for x in outcomes if x['outcome'] == 'created')
    loser = next(x['receipt'] for x in outcomes if x['outcome'] == 'refused')
    require(winner['created'] and winner['policyVerified'] and loser['creationAttempted'] and not loser['created'] and
            '[WinError 183]' in loser['error'] and not list(race.iterdir()), 'Real CreateDirectory race disposition preserved')
    case('actual-two-contender-create-race', lambda: outcomes)
    value = case('race-winner-policy-and-identity-rechecked', lambda: prepare(race))
    require(value['observed']['file']['identity'] == winner['observed']['file']['identity'], 'No race replacement')
    require(m.check_production_base() == production_before, 'Host production base/ancestor state unchanged')
    (folder/'case-details.json').write_text(json.dumps(details, indent=2)+'\n', encoding='utf-8')
    sha = lambda p: j.digest(p.read_bytes())
    paths = [TOOL, Path(__file__), ROOT/'scripts/asio-file-stage.py', ROOT/'scripts/asio-install.py']
    value = {'schema': 'sl3.install-base-tests.v1', 'cases': cases,
        'files': {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob('*') if p.is_file()},
        'sourceSha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in paths},
        'productionPreflightPassed': True, 'productionBaseStateUnchanged': True, 'hostAncestorSnapshotsEqual': True,
        'nonElevated': True, 'testPolicyOwnerCurrentUser': True, 'productionPreparationExecuted': False,
        'hostAclsChanged': False, 'registryWritten': False, 'packageBinaryExecuted': False, 'deviceAccess': False}
    index = folder/'index.json'; index.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    (ROOT/'artifacts/build/install-base-tests-last.json').write_text(json.dumps({'directory': str(folder), 'indexSha256': sha(index)}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'productionPreparationExecuted': False, 'evidenceDirectory': str(folder)}))


if __name__ == '__main__':
    main()
