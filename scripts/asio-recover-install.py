"""Abort an interrupted install after a journalled complete stage; inert CLI."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import sys
import winreg

_spec = importlib.util.spec_from_file_location('sl3_install_recovery_installer', Path(__file__).with_name('asio-install.py'))
install = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(install)


class InstallRecoveryFailure(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__(report['error'])


def witnessed_keys(records, completed_index, registry, plan):
    """Check the original registration callback prefix, not just key spellings."""
    expected = []
    for item in registry.entries(plan):
        expected.extend([{'event': 'before_create', 'key': item['key'], 'value': None},
                         {'event': 'created', 'key': item['key'], 'value': None}])
        expected.extend({'event': 'written', 'key': item['key'], 'value': name} for name in item['strings'])
    events = [x['payload']['data'] for x in records[completed_index+1:] if x['payload'].get('event') == 'step']
    if events != expected[:len(events)]:
        raise ValueError('Original registration events are not an exact known prefix')
    return {event['key'] for event in events if event['event'] == 'created'}


def remaining_state(registry, root, plan, created):
    """Only witnessed keys with exact own value subsets and known children."""
    state = registry.inspect(root, plan); items = registry.entries(plan)
    for item in items:
        actual = state['states'][item['key']]
        if actual is None:
            continue
        if item['key'] not in created:
            raise ValueError('Remaining key has no original created witness; preserve it')
        model = registry.model(item)
        prefix = item['key']+'\\'
        children = sorted(other['key'][len(prefix):] for other in items
                          if other['key'].startswith(prefix) and '\\' not in other['key'][len(prefix):]
                          and state['states'][other['key']] is not None)
        if actual['subkeys'] != children or any(name not in model['values'] or value != model['values'][name]
                                               for name, value in actual['values'].items()):
            raise ValueError('Remaining key contains foreign values/types/children; preserve it')
    return state


def recover_owned(base, destination, expected_stage, original_journal, expected_journal, policy, root, overlay):
    j = install.sibling('asio-install-journal'); s = j.stage_module(); registry = install.sibling('asio-registry')
    report = {'schema': 'sl3.install-recovery.v1', 'successful': False, 'recoveryAction': 'abort',
              'productionPolicy': policy == s.PRODUCTION, 'sourceJournalSha256': expected_journal,
              'stageRecordSha256': expected_stage, 'journal': None, 'initiallyAbsentKeys': [],
              'deletedRegistryKeys': [], 'fileCleanupAttempted': False, 'fileResult': None,
              'finalRegistryAbsentObserved': False, 'directoryAbsentObserved': False,
              'failureJournalPersisted': False, 'error': '', 'partialCopyRecoverySupported': False,
              'partialFileRecoverySupported': False, 'packageBinaryExecuted': False, 'deviceAccess': False,
              'nativeSessionStarted': False, 'sessionPointerWritten': False,
              'fileRecoverySnapshotPersisted': False}
    try:
        for path in (base, destination, original_journal):
            s.local(path)
        s.require(destination.parent == base and original_journal.parent == base,
                  'Stage and original journal must share the fixed base')
        module = s.reader(); module.sha_value(expected_stage); module.sha_value(expected_journal)
        with ExitStack() as source:
            old = source.enter_context(s.open_file(original_journal)); s.inspect_policy(old, policy, False)
            s.require(j.digest(s.read_handle(old, j.MAX_TOTAL)) == expected_journal, 'Original journal differs from reviewed SHA')
            previous = j.inspect_journal(base, original_journal, policy)
            s.require(previous['wholeFileSha256'] == expected_journal, 'Original journal changed during inspection')
            records = previous['records']; header = records[0]['payload']
            s.require(header['action'] == 'install' and
                      not any(x['payload'].get('event') == 'install_completed' for x in records),
                      'Interrupted original install required; completed installs use normal removal')
            validated = [x['payload'] for x in records if x['payload'].get('event') == 'install_validated']
            stages = [(n, x['payload']) for n, x in enumerate(records) if x['payload'].get('event') == 'stage_completed']
            s.require(len(validated) == len(stages) == 1, 'One validated install and journalled complete stage required')
            stage_index, completed = stages[0]; record = completed['stageRecord']; receipt = module.encoded(record)
            s.require(completed['stageRecordSha256'] == expected_stage and j.digest(receipt) == expected_stage and
                      Path(record['directory']['path']) == destination, 'Original stage/hash/directory differs')
            bindings = {'packageId': record['packageId'], 'bundleManifestSha256': record['bundleManifestSha256']}
            s.require(header['bindings'] == bindings, 'Original package/bundle pins differ')
            plan = validated[0]['plan']; items = registry.entries(plan)
            s.require(plan['packageId'] == record['packageId'] and
                      validated[0]['registryBefore']['newRegistrationAllowed'] is True and
                      validated[0]['registryBefore']['states'] == {item['key']: None for item in items} and
                      all(validated[0]['registryBefore']['containersPresent'].values()) and
                      validated[0]['overlayBefore']['present'] is False,
                      'Original absent registration/container/overlay snapshot required')
            created = witnessed_keys(records, stage_index, registry, plan)
            s.inspect_stage(destination, expected_stage, policy)
            if policy == s.PRODUCTION:
                s.require(s.production_destination(plan) == (base, destination), 'Production destination differs')
            with j.transaction(base, policy, 'uninstall', dict(bindings, stageRecordSha256=expected_stage)) as journal:
                report['journal'] = str(journal.path)
                try:
                    def current():
                        s.require(not registry.inspect_overlay(overlay, plan)['present'], 'Current-user overlay remains; preserve state')
                        return remaining_state(registry, root, plan, created)
                    with ExitStack() as held:
                        held.enter_context(s.open_file(destination, True, access=0x20080, share=3))
                        names = set(record['files']) | {'stage-record.json', 'stage-intent.json'}
                        handles = {name: held.enter_context(s.open_file(destination/name)) for name in names}
                        s.inspect_stage(destination, expected_stage, policy)
                        s.require(s.read_handle(handles['stage-record.json'], module.LIMIT) == receipt and
                                  module.record(s.read_handle(handles['deployment-plan.json'], module.LIMIT)) == plan,
                                  'Retained receipt/plan differs from original install')
                        state = current()
                        report['initiallyAbsentKeys'] = [key for key, value in state['states'].items() if value is None]
                        journal.append({'event': 'install_recovery_validated', 'originalJournalName': original_journal.name,
                                        'originalJournalSha256': expected_journal, 'originalTornTailBytes': previous['tornTailBytes'],
                                        'stageRecord': record, 'registryBeforeRecovery': state, 'originalCreatedKeys': sorted(created)})
                        for item in [items[1], items[0], items[2]]:
                            state = current(); path = item['key']
                            if state['states'][path] is None:
                                continue
                            journal.append({'event': 'install_recovery_before_registry_delete', 'key': path})
                            fresh = current()
                            s.require(fresh == state, 'Registry changed across recovery journal append')
                            with winreg.OpenKey(root, path, 0, registry.READ) as handle:
                                s.require(registry.snapshot_handle(handle) == state['states'][path] and
                                          not state['states'][path]['subkeys'], 'Key changed before recovery deletion')
                                winreg.DeleteKeyEx(root, path, winreg.KEY_WOW64_64KEY, 0)
                            report['deletedRegistryKeys'].append(path)
                            journal.append({'event': 'install_recovery_registry_deleted', 'key': path})
                    s.require(current()['allAbsent'], 'Registration remains after recovery')
                    journal.append({'event': 'install_recovery_registration_absence_rechecked'})
                    # The separate reviewed-bundle file recovery API can consume
                    # this new uninstall journal if cleanup is interrupted. Its
                    # all-absent snapshot does not rewrite original install history.
                    absent_state = current(); absent_overlay = registry.inspect_overlay(overlay, plan)
                    s.require(absent_state['allAbsent'] and not absent_overlay['present'], 'Registry absence changed before file snapshot')
                    journal.append({'event': 'uninstall_validated', 'stageRecord': record,
                                    'registryBefore': absent_state, 'overlayBefore': absent_overlay})
                    report['fileRecoverySnapshotPersisted'] = True
                    report['fileCleanupAttempted'] = True
                    def cleanup_event(event):
                        journal(event)
                        s.require(current()['allAbsent'], 'Registration reappeared during file cleanup; preserve remaining files')
                    try:
                        report['fileResult'] = s.remove_stage(destination, expected_stage, policy, cleanup_event)
                    except s.CleanupFailure as error:
                        report['fileResult'] = error.report
                        raise
                    report['finalRegistryAbsentObserved'] = current()['allAbsent']
                    report['directoryAbsentObserved'] = s.absent(destination)
                    s.require(report['finalRegistryAbsentObserved'] and report['directoryAbsentObserved'], 'Final recovery observations differ')
                    journal.append({'event': 'install_recovery_completed', 'registryAbsentObserved': True, 'directoryAbsentObserved': True})
                    report['successful'] = True
                except Exception as error:
                    report['error'] = str(error)
                    try:
                        journal.append({'event': 'install_recovery_failed', 'report': report}); report['failureJournalPersisted'] = True
                    except Exception as journal_error:
                        report['failureJournalError'] = str(journal_error)
                    raise
        return report
    except Exception as error:
        if not report['error']:
            report['error'] = str(error)
        raise InstallRecoveryFailure(report) from error


def recover_production(base, destination, expected_stage, original_journal, expected_journal):
    s = install.sibling('asio-install-journal').stage_module()
    s.require(s.elevated(), 'Explicit administrator token required; no automatic UAC')
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, '', 0, winreg.KEY_READ | winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as root:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as overlay:
            return recover_owned(base, destination, expected_stage, original_journal, expected_journal, s.PRODUCTION, root, overlay)


if __name__ == '__main__':
    if sys.argv[1:] not in ([], ['--plan']):
        print('Only --plan is exposed; recovery requires a trusted installer and reviewed original journal', file=sys.stderr); sys.exit(2)
    print(json.dumps({'schema': 'sl3.install-recovery-plan.v1', 'planOnly': True, 'registryWritten': False,
                      'filesWritten': False, 'deviceAccess': False, 'machineMutationCliExposed': False}))
