"""Protected installer-base preparation. No registration, payload or device I/O."""
from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes as W
import importlib.util
import json
import re
import uuid
from pathlib import Path
import sys


def journal_module():
    key = 'sl3_base_preparation_journal'
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, Path(__file__).with_name('asio-install-journal.py'))
        module = importlib.util.module_from_spec(spec); sys.modules[key] = module; spec.loader.exec_module(module)
    return sys.modules[key]


class BasePreparationFailure(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__(report['error'])


def production_base():
    return journal_module().stage_module().known_folder('905e63b6-c1bf-494e-b29c-65b732d3d21a')/'SL3 Rebuild'


def parent_checks(base, policy, stack):
    s = journal_module().stage_module(); s.local(base)
    handles = stack.enter_context(s.pinned_parents(base))
    if policy != s.PRODUCTION:
        return []  # Explicit test/caller policy is never production protection.
    s.require(ctypes.sizeof(s.P) == 8 and base == production_base(), 'Native x64 fixed production base required')
    trusted = {s.SYSTEM, s.ADMINS, s.account_sid('NT SERVICE\\TrustedInstaller')}
    return [s.safe_parent(handle, trusted) for handle in handles]


def check_production_base():
    s = journal_module().stage_module(); base = production_base()
    with ExitStack() as stack:
        ancestors = parent_checks(base, s.PRODUCTION, stack)
        missing = s.absent(base); observed = None
        if not missing:
            handle = stack.enter_context(s.open_file(base, True, access=0x20080, share=3))
            observed = s.inspect_policy(handle, s.PRODUCTION, True)
        return {'schema': 'sl3.base-preflight.v1', 'path': str(base), 'ancestorChecks': ancestors,
                'baseAbsentObserved': missing, 'existingBasePolicy': observed, 'filesWritten': False,
                'registryWritten': False, 'deviceAccess': False, 'tokenElevated': s.elevated()}


def bootstrap_writer(base, policy, stack, action='prepare_base', source_sha=None):
    """Protected sibling log; its parent already has a retained namespace lease."""
    j = journal_module(); s = j.stage_module()
    s.require(action in ('prepare_base', 'recover_empty_base'), 'Known bootstrap action required')
    parent = stack.enter_context(s.open_file(base.parent, True, access=0x20080, share=3))
    parent_info = s.information(parent, True)
    s.require(Path(parent_info['path']) == base.parent, 'Bootstrap parent path differs')
    suffix = '.bootstrap-' if action == 'prepare_base' else '.bootstrap-recovery-'
    path = base.with_name(base.name+suffix+uuid.uuid4().hex+'.jsonl')
    with s.descriptor(policy.sddl(False)) as attributes:
        handle = stack.enter_context(s.open_file(path, access=0xc0000000, share=0, create=1, security=attributes))
    info = s.inspect_policy(handle, policy, False)['file']
    writer = j.Journal(handle, path, policy)
    stack.callback(setattr, writer, 'active', False)
    header = {'event': 'transaction_header', 'action': action, 'directory': str(base),
              'parentIdentity': parent_info['identity'], 'journalIdentity': info['identity'], 'journalName': path.name,
              'policy': policy.record(), 'productionPolicy': policy == s.PRODUCTION}
    if source_sha is not None:
        header['sourceJournalSha256'] = source_sha
    writer.append(header)
    return writer


def creation_witness(base, path, expected, policy, stack):
    j = journal_module(); s = j.stage_module(); s.local(path)
    s.require(type(expected) is str and re.fullmatch('[0-9a-f]{64}', expected), 'Reviewed lowercase bootstrap hash required')
    s.require(path.parent == base.parent and re.fullmatch(re.escape(base.name)+r'\.bootstrap-[0-9a-f]{32}\.jsonl', path.name),
              'Typed direct sibling creation journal required')
    handle = stack.enter_context(s.open_file(path)); info = s.inspect_policy(handle, policy, False)['file']
    raw = s.read_handle(handle, j.MAX_TOTAL)
    s.require(j.digest(raw) == expected, 'Reviewed bootstrap journal changed')
    parsed = j.parse(raw)
    s.require(parsed['tornTailBytes'] == 0 and len(parsed['records']) == 2, 'Complete header and creation witness required; preserve creation gaps')
    header, witness = [row['payload'] for row in parsed['records']]
    parent = stack.enter_context(s.open_file(base.parent, True, access=0x20080, share=3))
    parent_info = s.information(parent, True)
    s.require(header == {'event': 'transaction_header', 'action': 'prepare_base', 'directory': str(base),
              'parentIdentity': parent_info['identity'], 'journalIdentity': info['identity'], 'journalName': path.name,
              'policy': policy.record(), 'productionPolicy': policy == s.PRODUCTION}, 'Bootstrap header/namespace/identity differs')
    s.require(set(witness) == {'event', 'directory'} and witness['event'] == 'base_created' and
              witness['directory']['path'] == str(base), 'Creation witness target differs')
    return witness['directory']


def recover_empty_base(base, original_journal, expected_journal, policy):
    """Explicit trusted-caller cleanup of a witnessed empty base. CLI stays inert."""
    j = journal_module(); s = j.stage_module(); s.local(base)
    report = {'schema': 'sl3.empty-base-recovery.v1', 'successful': False, 'productionPolicy': policy == s.PRODUCTION,
              'sourceJournalSha256': expected_journal, 'journal': None, 'baseAlreadyAbsentObserved': False,
              'baseDeletionMarked': False, 'baseAbsentObserved': False, 'error': '',
              'creationToWitnessGapRecovered': False, 'registryWritten': False, 'packageBinaryExecuted': False, 'deviceAccess': False}
    try:
        with ExitStack() as stack:
            if policy == s.PRODUCTION:
                s.require(s.elevated(), 'Explicit administrator token required; no automatic UAC')
            parent_checks(base, policy, stack)
            witness = creation_witness(base, original_journal, expected_journal, policy, stack)
            missing = s.absent(base); report['baseAlreadyAbsentObserved'] = missing
            owner = None
            if not missing:
                owner = s.open_file(base, True, access=0x30081, share=3)
                handle = stack.enter_context(owner); observed = s.inspect_policy(handle, policy, True)['file']
                s.require(observed['identity'] == witness['identity'] and Path(observed['path']) == base, 'Base identity/path differs; preserve replacement')
                s.require(not list(base.iterdir()), 'Base contains data; preserve all installation/foreign contents')
            journal = bootstrap_writer(base, policy, stack, 'recover_empty_base', expected_journal)
            report['journal'] = str(journal.path)
            journal.append({'event': 'empty_base_validated', 'directoryIdentity': witness['identity'], 'alreadyAbsent': missing})
            if not missing:
                s.require(not list(base.iterdir()), 'Base gained data; preserve it')
                s.inspect_policy(handle, policy, True)
                journal.append({'event': 'before_base_delete', 'directoryIdentity': witness['identity']})
                s.mark_delete(handle); report['baseDeletionMarked'] = True; owner.close()
            report['baseAbsentObserved'] = s.absent(base)
            s.require(report['baseAbsentObserved'], 'Base absence not observed')
            journal.append({'event': 'empty_base_recovery_completed', 'baseAbsentObserved': True})
            report['successful'] = True
        return report
    except Exception as error:
        report['error'] = str(error)
        raise BasePreparationFailure(report) from error


@contextmanager
def prepared_base(base, policy):
    """Create only the final directory or verify it; retain parents/root for caller."""
    s = journal_module().stage_module()
    report = {'schema': 'sl3.base-preparation.v1', 'path': str(base), 'productionPolicy': policy == s.PRODUCTION,
              'creationAttempted': False, 'created': False, 'existingCandidateObserved': False, 'existingDirectoryReused': False,
              'policyVerified': False, 'observed': None, 'ancestorChecks': [], 'error': '',
              'existingPermissionsChanged': False, 'existingContentsClaimedOwned': False,
              'registryWritten': False, 'payloadCopied': False, 'deviceAccess': False,
              'bootstrapJournal': None, 'bootstrapJournalSha256': None, 'creationWitnessPersisted': False}
    with ExitStack() as stack:
        try:
            if policy == s.PRODUCTION:
                s.require(s.elevated(), 'Explicit administrator token required; no automatic UAC')
            report['ancestorChecks'] = parent_checks(base, policy, stack)
            writer = None
            if s.absent(base):
                writer = bootstrap_writer(base, policy, stack)
                report['bootstrapJournal'] = str(writer.path)
                report['creationAttempted'] = True
                with s.descriptor(policy.sddl(True)) as attributes:
                    s.check(s.api('kernel32.dll', 'CreateDirectoryW', W.BOOL, [W.LPCWSTR, ctypes.POINTER(s.Attributes)])(
                        str(base), ctypes.byref(attributes)))
                report['created'] = True
            else:
                report['existingCandidateObserved'] = True
            handle = stack.enter_context(s.open_file(base, True, access=0x20080, share=3))
            observed = s.inspect_policy(handle, policy, True)
            s.require(Path(observed['file']['path']) == base, 'Prepared base final path differs')
            report['observed'] = observed; report['policyVerified'] = True
            report['existingDirectoryReused'] = not report['created']
            if writer is not None:
                writer.append({'event': 'base_created', 'directory': observed['file']})
                report['creationWitnessPersisted'] = True
                report['bootstrapJournalSha256'] = journal_module().digest(writer.raw)
        except Exception as error:
            report['error'] = str(error)
            raise BasePreparationFailure(report) from error
        # Consumer errors retain their own type/receipt. Never remove a created
        # base, change descriptors or claim the consumer's operation completed.
        yield report


if __name__ == '__main__':
    if sys.argv[1:] in ([], ['--plan']):
        print(json.dumps({'schema': 'sl3.base-preparation-plan.v1', 'planOnly': True,
                          'filesWritten': False, 'registryWritten': False, 'deviceAccess': False}))
    elif sys.argv[1:] == ['--check-production']:
        try:
            print(json.dumps(check_production_base()))
        except Exception as error:
            print(str(error), file=sys.stderr); sys.exit(1)
    else:
        print('Only --plan and read-only --check-production are exposed', file=sys.stderr); sys.exit(2)
