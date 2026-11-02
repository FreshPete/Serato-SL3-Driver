"""Protected installer-base preparation. No registration, payload or device I/O."""
from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes as W
import importlib.util
import json
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


@contextmanager
def prepared_base(base, policy):
    """Create only the final directory or verify it; retain parents/root for caller."""
    s = journal_module().stage_module()
    report = {'schema': 'sl3.base-preparation.v1', 'path': str(base), 'productionPolicy': policy == s.PRODUCTION,
              'creationAttempted': False, 'created': False, 'existingCandidateObserved': False, 'existingDirectoryReused': False,
              'policyVerified': False, 'observed': None, 'ancestorChecks': [], 'error': '',
              'existingPermissionsChanged': False, 'existingContentsClaimedOwned': False,
              'registryWritten': False, 'payloadCopied': False, 'deviceAccess': False}
    with ExitStack() as stack:
        try:
            if policy == s.PRODUCTION:
                s.require(s.elevated(), 'Explicit administrator token required; no automatic UAC')
            report['ancestorChecks'] = parent_checks(base, policy, stack)
            if s.absent(base):
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
