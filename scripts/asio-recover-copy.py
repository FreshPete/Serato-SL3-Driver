"""Abort journal-witnessed partial staging; no registry writes or package execution."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import sys
import winreg

_spec = importlib.util.spec_from_file_location('sl3_copy_recovery_installer', Path(__file__).with_name('asio-install.py'))
install = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(install)


class CopyRecoveryFailure(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__(report['error'])


def witnessed_files(module, manifest, payload, policy, destination, steps, digest):
    """Reconstruct the exact known staging prefix and its canonical bytes."""
    def require(value, message):
        module.require(value, message)
    require(steps and steps[0].get('event') == 'stage_root_created', 'Original stage-root identity witness required')
    root = steps[0]['directory']
    require(steps[0] == {'event': 'stage_root_created', 'directory': root, 'packageId': manifest['packageId'],
                        'bundleManifestSha256': digest, 'policy': policy.record()} and Path(root['path']) == destination,
            'Stage-root witness path/package/policy differs')
    require(type(root['identity']) is dict and set(root['identity']) == {'volume', 'high', 'low'} and
            all(type(x) is int and 0 <= x <= 0xffffffff for x in root['identity'].values()), 'Valid root identity required')
    record = {'schema': 'sl3.file-stage.v1', 'packageId': manifest['packageId'], 'bundleManifestSha256': digest,
              'directory': root, 'policy': policy.record(), 'productionPolicy': policy == install.sibling('asio-install-journal').stage_module().PRODUCTION,
              'files': {}, 'registered': False, 'binaryPayloadExecuted': False, 'deviceAccess': False}
    intent = module.encoded({'schema': 'sl3.file-stage-intent.v1', 'packageId': manifest['packageId'],
                            'bundleManifestSha256': digest, 'directory': root, 'policy': policy.record(), 'complete': False,
                            'plannedFiles': {name: {'sha256': module.digest(data), 'bytes': len(data)} for name, data in payload.items()}})
    expected = {}; identities = {}; completed = set(); position = 1
    order = ['stage-intent.json', *payload, 'stage-record.json']
    for name in order:
        if position == len(steps):
            break
        if name in payload:
            require(steps[position] == {'event': 'before_file', 'name': name}, 'Original before-file order differs')
            position += 1
            if position == len(steps):
                break
        data = intent if name == 'stage-intent.json' else module.encoded(record) if name == 'stage-record.json' else payload[name]
        event = steps[position]; details = event.get('details', {}); identity = details.get('identity')
        require(type(identity) is dict and set(identity) == {'volume', 'high', 'low'} and
                all(type(x) is int and 0 <= x <= 0xffffffff for x in identity.values()), 'Valid created file identity required')
        require(event == {'event': 'stage_file_created', 'name': name,
                          'details': {'sha256': module.digest(data), 'bytes': len(data), 'identity': identity}},
                'Original created file bytes/order differs')
        identities[name] = identity; expected[name] = data; position += 1
        if position == len(steps):
            break
        require(steps[position] == {'event': 'stage_file_completed', 'name': name, 'details': details},
                'Original completed file order/identity differs')
        completed.add(name); position += 1
        if name == 'stage-intent.json':
            record['intent'] = details
        elif name in payload:
            record['files'][name] = details
    require(position == len(steps), 'Unexpected staging/registration events after known prefix')
    return root, expected, identities, completed


def recover_owned(bundle, expected_bundle, base, destination, original_journal, expected_journal, policy, root, overlay):
    j = install.sibling('asio-install-journal'); s = j.stage_module(); registry = install.sibling('asio-registry')
    report = {'schema': 'sl3.copy-recovery.v1', 'successful': False, 'productionPolicy': policy == s.PRODUCTION,
              'sourceJournalSha256': expected_journal, 'journal': None, 'initiallyAbsentFiles': [],
              'partialPrefixFilesObserved': [], 'deleteMarkedFiles': [], 'absentObservedFiles': [],
              'directoryAlreadyAbsentObserved': False, 'directoryDeletionMarked': False, 'directoryAbsentObserved': False,
              'finalRegistryAbsentObserved': False, 'failureJournalPersisted': False, 'error': '',
              'registryWritten': False, 'packageBinaryExecuted': False, 'deviceAccess': False,
              'unwitnessedCreationGapRecovered': False, 'initialBaseCreationGapRecovered': False}
    try:
        for path in (bundle, base, destination, original_journal):
            s.local(path)
        s.require(destination.parent == base and original_journal.parent == base, 'Stage/journal must share the fixed base')
        with ExitStack() as source:
            module, manifest, payload = s.snapshot_bundle(bundle, expected_bundle, source); module.sha_value(expected_journal)
            old = source.enter_context(s.open_file(original_journal)); s.inspect_policy(old, policy, False)
            s.require(j.digest(s.read_handle(old, j.MAX_TOTAL)) == expected_journal, 'Original journal differs from reviewed SHA')
            previous = j.inspect_journal(base, original_journal, policy)
            s.require(previous['wholeFileSha256'] == expected_journal, 'Reviewed original journal changed')
            records = previous['records']; header = records[0]['payload']
            bindings = {'packageId': manifest['packageId'], 'bundleManifestSha256': expected_bundle}
            s.require(header['action'] == 'install' and header['bindings'] == bindings and
                      not any(x['payload'].get('event') in ('stage_completed', 'install_completed') for x in records),
                      'Original pre-completion install required; complete stages use install recovery')
            admission = [(n, x['payload']) for n, x in enumerate(records) if x['payload'].get('event') == 'install_validated']
            before = [(n, x['payload']) for n, x in enumerate(records) if x['payload'].get('event') == 'before_stage']
            s.require(len(admission) == len(before) == 1 and admission[0][0] < before[0][0], 'One ordered admission/before-stage pair required')
            plan = module.record(payload['deployment-plan.json']); items = registry.entries(plan); admitted = admission[0][1]
            s.require(admitted['plan'] == plan and admitted['registryBefore']['newRegistrationAllowed'] is True and
                      admitted['registryBefore']['states'] == {item['key']: None for item in items} and
                      all(admitted['registryBefore']['containersPresent'].values()) and not admitted['overlayBefore']['present'],
                      'Original absent registration/overlay and verified plan required')
            s.require(before[0][1] == {'event': 'before_stage', 'directory': str(destination), 'bundleManifest': manifest},
                      'Original before-stage package/destination differs')
            steps = [x['payload']['data'] for x in records[before[0][0]+1:] if x['payload'].get('event') == 'step']
            original_root, expected, identities, completed = witnessed_files(module, manifest, payload, policy, destination, steps, expected_bundle)
            if policy == s.PRODUCTION:
                s.require(s.production_destination(plan) == (base, destination), 'Production destination differs')
            with j.transaction(base, policy, 'uninstall', bindings) as journal:
                report['journal'] = str(journal.path)
                try:
                    def absent_registration():
                        s.require(registry.inspect(root, plan)['allAbsent'] and not registry.inspect_overlay(overlay, plan)['present'],
                                  'Registration or overlay remains/reappeared; preserve stage')
                    absent_registration()
                    with ExitStack() as files:
                        files.enter_context(s.pinned_parents(destination)); missing = s.absent(destination)
                        report['directoryAlreadyAbsentObserved'] = missing
                        if missing:
                            s.require(all(s.absent(destination/name) for name in expected), 'File absence not observed')
                            report['initiallyAbsentFiles'] = sorted(expected)
                        else:
                            directory_owner = s.open_file(destination, True, access=0x30081, share=3)
                            directory = files.enter_context(directory_owner); info = s.inspect_policy(directory, policy, True)['file']
                            s.require(Path(info['path']) == destination and info['identity'] == original_root['identity'], 'Remaining root identity/path differs')
                            s.require({p.name for p in destination.iterdir()} <= set(expected), 'Unknown or unwitnessed stage data; preserve it')
                            handles = {}
                            for name, data in expected.items():
                                if s.absent(destination/name):
                                    report['initiallyAbsentFiles'].append(name); continue
                                owner = s.open_file(destination/name, access=0x80010000, share=0); handle = files.enter_context(owner)
                                info = s.inspect_policy(handle, policy, False)['file']
                                actual = b'' if info['size'] == 0 else s.read_handle(handle, module.LIMIT)
                                s.require(info['identity'] == identities[name] and
                                          (actual == data if name in completed else len(actual) <= len(data) and data.startswith(actual)),
                                          'Remaining file identity/bytes differ: '+name)
                                if len(actual) < len(data):
                                    report['partialPrefixFilesObserved'].append(name)
                                handles[name] = owner, handle
                            remaining = set(handles)
                            s.require({p.name for p in destination.iterdir()} == remaining, 'Stage changed while taking deletion leases')
                        journal.append({'event': 'copy_recovery_validated', 'originalJournalName': original_journal.name,
                                        'originalJournalSha256': expected_journal, 'originalTornTailBytes': previous['tornTailBytes'],
                                        'root': original_root, 'witnessedFiles': sorted(expected), 'completedFiles': sorted(completed),
                                        'initiallyAbsentFiles': report['initiallyAbsentFiles'], 'partialPrefixFilesObserved': report['partialPrefixFilesObserved'],
                                        'directoryAlreadyAbsentObserved': missing})
                        if not missing:
                            order = sorted(set(handles)-{'stage-intent.json', 'stage-record.json'})+['stage-intent.json', 'stage-record.json']
                            for name in order:
                                if name not in handles:
                                    continue
                                journal.append({'event': 'copy_recovery_before_delete', 'name': name}); absent_registration()
                                s.require({p.name for p in destination.iterdir()} == remaining, 'Stage changed before deletion')
                                owner, handle = handles[name]; s.inspect_policy(handle, policy, False)
                                s.mark_delete(handle); report['deleteMarkedFiles'].append(name); owner.close()
                                s.require(s.absent(destination/name), 'Marked file absence not observed')
                                report['absentObservedFiles'].append(name); remaining.remove(name)
                                journal.append({'event': 'copy_recovery_deleted', 'name': name})
                            journal.append({'event': 'copy_recovery_before_directory_delete'}); absent_registration()
                            s.require(not list(destination.iterdir()), 'Directory gained unknown data'); s.inspect_policy(directory, policy, True)
                            s.mark_delete(directory); report['directoryDeletionMarked'] = True; directory_owner.close()
                        report['directoryAbsentObserved'] = s.absent(destination)
                        s.require(report['directoryAbsentObserved'], 'Directory absence not observed')
                    absent_registration(); report['finalRegistryAbsentObserved'] = True
                    journal.append({'event': 'copy_recovery_completed', 'directoryAbsentObserved': True, 'registryAbsentObserved': True})
                    report['successful'] = True
                except Exception as error:
                    report['error'] = str(error)
                    try:
                        journal.append({'event': 'copy_recovery_failed', 'report': report}); report['failureJournalPersisted'] = True
                    except Exception as journal_error:
                        report['failureJournalError'] = str(journal_error)
                    raise
        return report
    except Exception as error:
        if not report['error']:
            report['error'] = str(error)
        raise CopyRecoveryFailure(report) from error


def recover_production(bundle, expected_bundle, base, destination, original_journal, expected_journal):
    s = install.sibling('asio-install-journal').stage_module()
    s.require(s.elevated(), 'Explicit administrator token required; no automatic UAC')
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, '', 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as root:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as overlay:
            return recover_owned(bundle, expected_bundle, base, destination, original_journal, expected_journal, s.PRODUCTION, root, overlay)


if __name__ == '__main__':
    if sys.argv[1:] not in ([], ['--plan']):
        print('Only --plan is exposed; copy recovery requires a trusted caller and reviewed bundle/journal', file=sys.stderr); sys.exit(2)
    print(json.dumps({'schema': 'sl3.copy-recovery-plan.v1', 'planOnly': True, 'registryWritten': False,
                      'filesWritten': False, 'packageBinaryExecuted': False, 'deviceAccess': False, 'machineMutationCliExposed': False}))
