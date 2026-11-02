"""Serialized own-registration/file removal; trusted caller API, inert CLI."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import sys
import winreg


def sibling(name):
    key = 'sl3_uninstall_'+name.replace('-', '_')
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, Path(__file__).with_name(name+'.py'))
        module = importlib.util.module_from_spec(spec); sys.modules[key] = module; spec.loader.exec_module(module)
    return sys.modules[key]


class UninstallFailure(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__(report['error'])


def uninstall_owned(base, destination, expected, policy, registry_root, overlay_root):
    """Caller supplies real machine roots or explicit isolated test roots."""
    journal_module = sibling('asio-install-journal'); s = journal_module.stage_module(); registry = sibling('asio-registry')
    report = {'schema': 'sl3.uninstall.v1', 'successful': False, 'productionPolicy': policy == s.PRODUCTION,
              'directory': str(destination), 'stageRecordSha256': expected, 'journal': None,
              'registryRemovalAttempted': False, 'registryResult': None, 'fileCleanupAttempted': False,
              'fileResult': None, 'finalRegistryAbsentObserved': False, 'directoryAbsentObserved': False,
              'failureJournalPersisted': False, 'error': '', 'deviceAccess': False, 'binaryPayloadExecuted': False}
    try:
        s.require(destination.parent == base, 'Stage must be a direct child of the installer base')
        s.inspect_stage(destination, expected, policy)
        # Read hash-bound identity before opening the journal. No registry write
        # is authorized by this read; full retained-handle validation follows.
        with s.open_file(destination/'stage-record.json') as handle:
            raw = s.read_handle(handle, s.reader().LIMIT)
            s.require(journal_module.digest(raw) == expected, 'Stage receipt changed before transaction')
            record = s.reader().record(raw)
        bindings = {'packageId': record['packageId'], 'stageRecordSha256': expected,
                    'bundleManifestSha256': record['bundleManifestSha256']}
        with journal_module.transaction(base, policy, 'uninstall', bindings) as journal:
            report['journal'] = str(journal.path)
            try:
                # Retain every stage object without write/delete sharing until
                # registration removal finishes. Cleanup then takes its own
                # exclusive deletion handles and repeats the full validation.
                with ExitStack() as held:
                    held.enter_context(s.open_file(destination, True, access=0x20080, share=3))
                    handles = {name: held.enter_context(s.open_file(destination/name))
                               for name in set(record['files']) | {'stage-record.json', 'stage-intent.json'}}
                    s.inspect_stage(destination, expected, policy)
                    plan = s.reader().record(s.read_handle(handles['deployment-plan.json'], s.reader().LIMIT))
                    state = registry.inspect(registry_root, plan); overlay = registry.inspect_overlay(overlay_root, plan)
                    s.require(not overlay['present'], 'Current-user COM overlay remains; preserve registration and files')
                    s.require(state['allAbsent'] or state['exactOwned'], 'Foreign or partial registration; preserve remaining state')
                    journal.append({'event': 'uninstall_validated', 'stageRecord': record,
                                    'registryBefore': state, 'overlayBefore': overlay})
                    if state['exactOwned']:
                        report['registryRemovalAttempted'] = True
                        try:
                            report['registryResult'] = registry.unregister_owned(registry_root, plan, journal)
                        except registry.RegistryFailure as error:
                            report['registryResult'] = error.report
                            raise
                s.require(registry.inspect(registry_root, plan)['allAbsent'] and
                          not registry.inspect_overlay(overlay_root, plan)['present'], 'Registration reappeared before file cleanup')
                journal.append({'event': 'registration_absence_rechecked'})
                report['fileCleanupAttempted'] = True
                try:
                    report['fileResult'] = s.remove_stage(destination, expected, policy, journal)
                except s.CleanupFailure as error:
                    report['fileResult'] = error.report
                    raise
                report['finalRegistryAbsentObserved'] = registry.inspect(registry_root, plan)['allAbsent']
                report['directoryAbsentObserved'] = s.absent(destination)
                s.require(report['finalRegistryAbsentObserved'] and report['directoryAbsentObserved'] and
                          not registry.inspect_overlay(overlay_root, plan)['present'], 'Final removal observations do not agree')
                journal.append({'event': 'uninstall_completed', 'registryAbsentObserved': True, 'directoryAbsentObserved': True})
                report['successful'] = True
            except Exception as error:
                report['error'] = str(error)
                try:
                    journal.append({'event': 'uninstall_failed', 'report': report})
                    report['failureJournalPersisted'] = True
                except Exception as journal_error:
                    report['failureJournalError'] = str(journal_error)
                raise
        return report
    except Exception as error:
        if not report['error']:
            report['error'] = str(error)
        raise UninstallFailure(report) from error


def uninstall_production(base, destination, expected):
    j = sibling('asio-install-journal'); s = j.stage_module()
    s.require(s.elevated(), 'Explicit administrator token required; no automatic UAC')
    # transaction additionally validates native x64, fixed base and ancestors.
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, '', 0, winreg.KEY_READ | winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as root:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as overlay:
            return uninstall_owned(base, destination, expected, s.PRODUCTION, root, overlay)


if __name__ == '__main__':
    if sys.argv[1:] not in ([], ['--plan']):
        print('Only --plan is exposed; machine removal requires a trusted installer', file=sys.stderr); sys.exit(2)
    print(json.dumps({'schema': 'sl3.uninstall-plan.v1', 'planOnly': True, 'filesWritten': False,
                      'registryWritten': False, 'deviceAccess': False, 'machineMutationCliExposed': False}))
