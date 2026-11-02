"""Reviewed-journal recovery of own partial registration with an intact stage."""
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import winreg

# Reuse the coordinator's module identities, including its typed exceptions.
import importlib.util
_spec = importlib.util.spec_from_file_location('sl3_recovery_uninstaller', Path(__file__).with_name('asio-uninstall.py'))
uninstall = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(uninstall)


class RecoveryFailure(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__(report['error'])


def subset(registry, root, plan):
    """Every remaining own key must have exact values and remaining children."""
    items = registry.entries(plan); state = registry.inspect(root, plan)
    for item in items:
        actual = state['states'][item['key']]
        if actual is None:
            continue
        prefix = item['key']+'\\'
        children = [other['key'][len(prefix):] for other in items
                    if other['key'].startswith(prefix) and '\\' not in other['key'][len(prefix):] and
                    state['states'][other['key']] is not None]
        if actual != registry.model(item, children):
            raise ValueError('Remaining registration contains foreign values/types/children; preserve it')
    return state


def recover_owned(base, destination, expected_stage, original_journal, expected_journal, policy, root, overlay):
    j = uninstall.sibling('asio-install-journal'); s = j.stage_module(); registry = uninstall.sibling('asio-registry')
    report = {'schema': 'sl3.uninstall-recovery.v1', 'successful': False, 'productionPolicy': policy == s.PRODUCTION,
              'sourceJournalSha256': expected_journal, 'stageRecordSha256': expected_stage, 'journal': None,
              'initiallyAbsentKeys': [], 'deletedRegistryKeys': [], 'fileCleanupAttempted': False, 'fileResult': None,
              'finalRegistryAbsentObserved': False, 'directoryAbsentObserved': False, 'failureJournalPersisted': False,
              'error': '', 'deviceAccess': False, 'packageBinaryExecuted': False, 'partialFileRecoverySupported': False}
    try:
        for path in (base, destination, original_journal):
            s.local(path)
        s.require(destination.parent == base and original_journal.parent == base, 'Stage and original journal must share the fixed base')
        module = s.reader(); module.sha_value(expected_journal); module.sha_value(expected_stage)
        with ExitStack() as retained:
            # Keep the old journal immutable through the new transaction. Live
            # original writers are incompatible with this read lease.
            original = retained.enter_context(s.open_file(original_journal))
            s.inspect_policy(original, policy, False)
            raw = s.read_handle(original, j.MAX_TOTAL)
            s.require(j.digest(raw) == expected_journal, 'Original journal differs from reviewed SHA')
            previous = j.inspect_journal(base, original_journal, policy)
            s.require(previous['wholeFileSha256'] == expected_journal, 'Original journal changed during inspection')
            header = previous['records'][0]['payload']
            s.require(header['action'] == 'uninstall', 'Recovery requires an original uninstall transaction')
            validated = [x['payload'] for x in previous['records'] if x['payload'].get('event') == 'uninstall_validated']
            s.require(len(validated) == 1, 'Exactly one original validated uninstall record required')
            record = validated[0]['stageRecord']
            s.require(j.digest(module.encoded(record)) == expected_stage and Path(record['directory']['path']) == destination,
                      'Original stage record/hash/directory differs')
            bindings = {'packageId': record['packageId'], 'stageRecordSha256': expected_stage,
                        'bundleManifestSha256': record['bundleManifestSha256']}
            s.require(header['bindings'] == bindings, 'Original transaction package/bundle/stage pins differ')
            # This first recovery mode deliberately requires the complete stage.
            # Missing files/receipt/directory are preserved for separate recovery.
            s.inspect_stage(destination, expected_stage, policy)
            with j.transaction(base, policy, 'uninstall', bindings) as journal:
                report['journal'] = str(journal.path)
                try:
                    with ExitStack() as held:
                        held.enter_context(s.open_file(destination, True, access=0x20080, share=3))
                        names = set(record['files']) | {'stage-record.json', 'stage-intent.json'}
                        handles = {name: held.enter_context(s.open_file(destination/name)) for name in names}
                        s.inspect_stage(destination, expected_stage, policy)
                        s.require(s.read_handle(handles['stage-record.json'], module.LIMIT) == module.encoded(record),
                                  'Retained stage receipt differs from original validated record')
                        plan = module.record(s.read_handle(handles['deployment-plan.json'], module.LIMIT))
                        items = registry.entries(plan)
                        original_states = {item['key']: registry.model(item, ['InprocServer32'] if n == 0 else [])
                                           for n, item in enumerate(items)}
                        s.require(validated[0]['registryBefore']['exactOwned'] is True and
                                  validated[0]['registryBefore']['states'] == original_states and
                                  validated[0]['overlayBefore']['present'] is False,
                                  'Original journal does not prove the full owned pre-removal registry snapshot')
                        s.require(not registry.inspect_overlay(overlay, plan)['present'], 'Current-user overlay remains; preserve all state')
                        state = subset(registry, root, plan)
                        report['initiallyAbsentKeys'] = [key for key, value in state['states'].items() if value is None]
                        journal.append({'event': 'recovery_validated', 'originalJournalName': original_journal.name,
                                        'originalJournalSha256': expected_journal, 'originalTornTailBytes': previous['tornTailBytes'],
                                        'stageRecord': record, 'registryBeforeRecovery': state})
                        for item in [items[1], items[0], items[2]]:
                            current = subset(registry, root, plan)
                            if current['states'][item['key']] is None:
                                continue
                            journal.append({'event': 'recovery_before_registry_delete', 'key': item['key']})
                            subset(registry, root, plan)
                            s.require(not registry.inspect_overlay(overlay, plan)['present'], 'Overlay appeared during recovery')
                            with winreg.OpenKey(root, item['key'], 0, registry.READ) as handle:
                                s.require(registry.snapshot_handle(handle) == registry.model(item), 'Key changed before recovery deletion')
                                winreg.DeleteKeyEx(root, item['key'], winreg.KEY_WOW64_64KEY, 0)
                            report['deletedRegistryKeys'].append(item['key'])
                            journal.append({'event': 'recovery_registry_deleted', 'key': item['key']})
                    s.require(registry.inspect(root, plan)['allAbsent'] and not registry.inspect_overlay(overlay, plan)['present'],
                              'Registration remains or reappeared after recovery')
                    journal.append({'event': 'recovery_registration_absence_rechecked'})
                    report['fileCleanupAttempted'] = True
                    try:
                        report['fileResult'] = s.remove_stage(destination, expected_stage, policy, journal)
                    except s.CleanupFailure as error:
                        report['fileResult'] = error.report
                        raise
                    report['finalRegistryAbsentObserved'] = registry.inspect(root, plan)['allAbsent']
                    report['directoryAbsentObserved'] = s.absent(destination)
                    s.require(report['finalRegistryAbsentObserved'] and report['directoryAbsentObserved'] and
                              not registry.inspect_overlay(overlay, plan)['present'], 'Final recovery observations differ')
                    journal.append({'event': 'recovery_completed', 'registryAbsentObserved': True, 'directoryAbsentObserved': True})
                    report['successful'] = True
                except Exception as error:
                    report['error'] = str(error)
                    try:
                        journal.append({'event': 'recovery_failed', 'report': report})
                        report['failureJournalPersisted'] = True
                    except Exception as journal_error:
                        report['failureJournalError'] = str(journal_error)
                    raise
        return report
    except Exception as error:
        if not report['error']:
            report['error'] = str(error)
        raise RecoveryFailure(report) from error


def recover_production(base, destination, expected_stage, original_journal, expected_journal):
    s = uninstall.sibling('asio-install-journal').stage_module()
    s.require(s.elevated(), 'Explicit administrator token required; no automatic UAC')
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, '', 0, winreg.KEY_READ | winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as root:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as overlay:
            return recover_owned(base, destination, expected_stage, original_journal, expected_journal, s.PRODUCTION, root, overlay)


if __name__ == '__main__':
    if sys.argv[1:] not in ([], ['--plan']):
        print('Only --plan is exposed; recovery requires a trusted installer and reviewed journal', file=sys.stderr); sys.exit(2)
    print(json.dumps({'schema': 'sl3.uninstall-recovery-plan.v1', 'planOnly': True, 'registryWritten': False,
                      'filesWritten': False, 'deviceAccess': False, 'machineMutationCliExposed': False}))
