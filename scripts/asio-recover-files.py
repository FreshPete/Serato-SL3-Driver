"""Reviewed original bundle/journal recovery of a partially removed stage."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import sys
import winreg

_spec = importlib.util.spec_from_file_location('sl3_file_recovery_uninstaller', Path(__file__).with_name('asio-uninstall.py'))
uninstall = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(uninstall)


class FileRecoveryFailure(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__(report['error'])


def recover_owned(bundle, expected_bundle, base, destination, expected_stage, original_journal, expected_journal, policy, root, overlay):
    j = uninstall.sibling('asio-install-journal'); s = j.stage_module(); registry = uninstall.sibling('asio-registry')
    report = {'schema': 'sl3.file-recovery.v1', 'successful': False, 'productionPolicy': policy == s.PRODUCTION,
              'journal': None, 'sourceJournalSha256': expected_journal, 'stageRecordSha256': expected_stage,
              'initiallyAbsentFiles': [], 'deleteMarkedFiles': [], 'absentObservedFiles': [],
              'directoryAlreadyAbsentObserved': False, 'directoryDeletionMarked': False, 'directoryAbsentObserved': False,
              'finalRegistryAbsentObserved': False, 'failureJournalPersisted': False, 'error': '',
              'receiptOriginalIdentityAvailable': False, 'registryWritten': False, 'packageBinaryExecuted': False, 'deviceAccess': False}
    try:
        for path in (bundle, base, destination, original_journal):
            s.local(path)
        s.require(destination.parent == base and original_journal.parent == base, 'Stage/journal must be direct children of the installer base')
        with ExitStack() as held_source:
            module, manifest, payload = s.snapshot_bundle(bundle, expected_bundle, held_source)
            module.sha_value(expected_stage); module.sha_value(expected_journal)
            original = held_source.enter_context(s.open_file(original_journal)); s.inspect_policy(original, policy, False)
            s.require(j.digest(s.read_handle(original, j.MAX_TOTAL)) == expected_journal, 'Original journal differs from reviewed SHA')
            previous = j.inspect_journal(base, original_journal, policy)
            s.require(previous['wholeFileSha256'] == expected_journal, 'Reviewed journal changed')
            header = previous['records'][0]['payload']
            validated = [x['payload'] for x in previous['records'] if x['payload'].get('event') == 'uninstall_validated']
            s.require(header['action'] == 'uninstall' and len(validated) == 1, 'Original validated uninstall journal required')
            record = validated[0]['stageRecord']; receipt = module.encoded(record)
            bindings = {'packageId': manifest['packageId'], 'bundleManifestSha256': expected_bundle, 'stageRecordSha256': expected_stage}
            s.require(j.digest(receipt) == expected_stage and header['bindings'] == bindings and
                      record['schema'] == 'sl3.file-stage.v1' and record['packageId'] == manifest['packageId'] and
                      record['bundleManifestSha256'] == expected_bundle and record['policy'] == policy.record() and
                      record['productionPolicy'] == (policy == s.PRODUCTION) and Path(record['directory']['path']) == destination and
                      all(record[k] is False for k in ('registered', 'binaryPayloadExecuted', 'deviceAccess')),
                      'Original stage/policy/package pins differ')
            s.require(set(record['files']) == set(payload), 'Original stage inventory differs from verified bundle')
            for name, data in payload.items():
                item = record['files'][name]
                s.require(item['bytes'] == len(data) and item['sha256'] == j.digest(data), 'Original stage payload differs from verified bundle')
            intent = module.encoded({'schema': 'sl3.file-stage-intent.v1', 'packageId': manifest['packageId'],
                'bundleManifestSha256': expected_bundle, 'directory': record['directory'], 'policy': policy.record(),
                'complete': False, 'plannedFiles': {name: {'sha256': j.digest(data), 'bytes': len(data)} for name, data in payload.items()}})
            s.require(record['intent']['sha256'] == j.digest(intent) and record['intent']['bytes'] == len(intent), 'Original intent cannot be reconstructed')
            expected_bytes = dict(payload, **{'stage-intent.json': intent, 'stage-record.json': receipt})
            identities = {name: item['identity'] for name, item in record['files'].items()}
            identities['stage-intent.json'] = record['intent']['identity']
            plan = module.record(payload['deployment-plan.json']); items = registry.entries(plan)
            full = {item['key']: registry.model(item, ['InprocServer32'] if n == 0 else []) for n, item in enumerate(items)}
            before = validated[0]['registryBefore']
            s.require((before['exactOwned'] is True and before['states'] == full) or
                      (before['allAbsent'] is True and before['states'] == {key: None for key in full}), 'Original registry snapshot differs')
            s.require(validated[0]['overlayBefore']['present'] is False, 'Original overlay snapshot not absent')
            if policy == s.PRODUCTION:
                s.require(s.production_destination(plan) == (base, destination), 'Production destination differs from original plan')
            with j.transaction(base, policy, 'uninstall', bindings) as journal:
                report['journal'] = str(journal.path)
                try:
                    def registry_absent():
                        s.require(registry.inspect(root, plan)['allAbsent'] and not registry.inspect_overlay(overlay, plan)['present'],
                                  'Registration or overlay remains/reappeared; preserve files')
                    registry_absent()
                    with ExitStack() as files:
                        files.enter_context(s.pinned_parents(destination))
                        missing_directory = s.absent(destination)
                        if missing_directory:
                            report['directoryAlreadyAbsentObserved'] = True
                            s.require(all(s.absent(destination/name) for name in expected_bytes), 'Expected file absence not observed')
                            report['initiallyAbsentFiles'] = sorted(expected_bytes)
                        else:
                            directory_owner = s.open_file(destination, True, access=0x30081, share=3)
                            directory = files.enter_context(directory_owner)
                            info = s.inspect_policy(directory, policy, True)['file']
                            s.require(info['identity'] == record['directory']['identity'] and Path(info['path']) == destination,
                                      'Remaining directory identity/path differs')
                            s.require({p.name for p in destination.iterdir()} <= set(expected_bytes), 'Unknown data in remaining stage; preserve it')
                            handles = {}
                            for name, data in expected_bytes.items():
                                if s.absent(destination/name):
                                    report['initiallyAbsentFiles'].append(name); continue
                                owner = s.open_file(destination/name, access=0x80010000, share=0)
                                handle = files.enter_context(owner); info = s.inspect_policy(handle, policy, False)['file']
                                s.require((name not in identities or info['identity'] == identities[name]) and
                                          s.read_handle(handle, module.LIMIT) == data, 'Remaining file identity/bytes differ: '+name)
                                handles[name] = (owner, handle)
                            remaining = set(handles)
                            s.require({p.name for p in destination.iterdir()} == remaining, 'Stage changed while taking deletion leases')
                        journal.append({'event': 'file_recovery_validated', 'originalJournalName': original_journal.name,
                            'originalJournalSha256': expected_journal, 'originalTornTailBytes': previous['tornTailBytes'],
                            'stageRecord': record, 'alreadyAbsentFiles': report['initiallyAbsentFiles'],
                            'directoryAlreadyAbsentObserved': missing_directory, 'receiptOriginalIdentityAvailable': False})
                        if not missing_directory:
                            priority = ['sl3_asio.dll', 'sl3_broker_controller.exe', 'sl3_usbdk.exe', 'UsbDkHelper.dll']
                            order = priority+sorted(set(payload)-set(priority))+['stage-intent.json', 'stage-record.json']
                            for name in order:
                                if name not in handles:
                                    continue
                                journal.append({'event': 'file_recovery_before_delete', 'name': name})
                                registry_absent()
                                s.require({p.name for p in destination.iterdir()} == remaining, 'Unknown/missing data appeared during file recovery')
                                owner, handle = handles[name]; s.inspect_policy(handle, policy, False)
                                s.mark_delete(handle); report['deleteMarkedFiles'].append(name); owner.close()
                                s.require(s.absent(destination/name), 'Marked file absence not observed')
                                report['absentObservedFiles'].append(name); remaining.remove(name)
                                journal.append({'event': 'file_recovery_deleted', 'name': name})
                            journal.append({'event': 'file_recovery_before_directory_delete'})
                            registry_absent(); s.require(not list(destination.iterdir()), 'Directory gained unknown data')
                            s.inspect_policy(directory, policy, True)
                            s.mark_delete(directory); report['directoryDeletionMarked'] = True; directory_owner.close()
                        report['directoryAbsentObserved'] = s.absent(destination)
                        s.require(report['directoryAbsentObserved'], 'Directory absence not observed')
                    registry_absent(); report['finalRegistryAbsentObserved'] = True
                    journal.append({'event': 'file_recovery_completed', 'directoryAbsentObserved': True,
                                    'registryAbsentObserved': True, 'filesDeletedThisAttempt': report['absentObservedFiles']})
                    report['successful'] = True
                except Exception as error:
                    report['error'] = str(error)
                    try:
                        journal.append({'event': 'file_recovery_failed', 'report': report}); report['failureJournalPersisted'] = True
                    except Exception as journal_error:
                        report['failureJournalError'] = str(journal_error)
                    raise
        return report
    except Exception as error:
        if not report['error']:
            report['error'] = str(error)
        raise FileRecoveryFailure(report) from error


def recover_production(bundle, expected_bundle, base, destination, expected_stage, original_journal, expected_journal):
    s = uninstall.sibling('asio-install-journal').stage_module()
    s.require(s.elevated(), 'Explicit administrator token required; no automatic UAC')
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, '', 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as root:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as overlay:
            return recover_owned(bundle, expected_bundle, base, destination, expected_stage, original_journal, expected_journal, s.PRODUCTION, root, overlay)


if __name__ == '__main__':
    if sys.argv[1:] not in ([], ['--plan']):
        print('Only --plan is exposed; file recovery requires reviewed original bundle/journal', file=sys.stderr); sys.exit(2)
    print(json.dumps({'schema': 'sl3.file-recovery-plan.v1', 'planOnly': True, 'filesWritten': False,
                      'registryWritten': False, 'packageBinaryExecuted': False, 'deviceAccess': False, 'machineMutationCliExposed': False}))
