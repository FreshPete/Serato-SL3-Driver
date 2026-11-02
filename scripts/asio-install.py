"""Runtime-gated new-stage/registration coordinator; inert public CLI."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import sys
import winreg


def sibling(name):
    key = 'sl3_install_'+name.replace('-', '_')
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, Path(__file__).with_name(name+'.py'))
        module = importlib.util.module_from_spec(spec); sys.modules[key] = module; spec.loader.exec_module(module)
    return sys.modules[key]


class InstallFailure(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__(report['error'])


def install_owned(bundle, expected, base, destination, policy, registry_root, overlay_root):
    """Trusted caller supplies existing protected base and explicit registry roots."""
    j = sibling('asio-install-journal'); s = j.stage_module(); r = sibling('asio-registry'); runtime = sibling('asio-runtime-check')
    report = {'schema': 'sl3.install.v1', 'successful': False, 'productionPolicy': policy == s.PRODUCTION,
              'journal': None, 'runtimeDirectImportsResolved': False, 'runtimeSnapshotSha256': None,
              'stageAttempted': False, 'stageResult': None, 'registrationAttempted': False, 'registrationResult': None,
              'stageVerifiedObserved': False, 'registrationOwnedObserved': False, 'failureJournalPersisted': False,
              'error': '', 'packageBinaryExecuted': False, 'deviceAccess': False, 'sessionPointerWritten': False,
              'nativeSessionStarted': False, 'installedAsioActivationTested': False}
    try:
        s.require(destination.parent == base, 'Stage must be a direct child of the installer base')
        s.require(not destination.exists(), 'New installation destination required; preserve existing state')
        # The public checker verifies captured package bytes before asking the
        # normal loader to resolve native-system direct dependencies only.
        admission = runtime.check(bundle, expected)
        s.require(admission['passed'] and admission['directImportsResolved'], 'Runtime direct-import admission failed')
        report['runtimeDirectImportsResolved'] = True
        report['runtimeSnapshotSha256'] = j.digest(j.encoded(admission))
        with ExitStack() as source:
            module, manifest, payload = s.snapshot_bundle(bundle, expected, source)
            s.require(manifest['packageId'] == admission['packageId'] and admission['bundleManifestSha256'] == expected,
                      'Runtime/package identity differs')
            plan = module.record(payload['deployment-plan.json'])
            if policy == s.PRODUCTION:
                s.require(s.production_destination(plan) == (base, destination), 'Production plan/base/destination mismatch')
            with j.transaction(base, policy, 'install', {'packageId': manifest['packageId'], 'bundleManifestSha256': expected}) as journal:
                report['journal'] = str(journal.path)
                try:
                    s.require(not destination.exists(), 'Destination appeared while acquiring installer lock')
                    state = r.inspect(registry_root, plan); overlay = r.inspect_overlay(overlay_root, plan)
                    s.require(state['newRegistrationAllowed'] and not overlay['present'], 'Registration/container/overlay conflict; preserve state')
                    journal.append({'event': 'install_validated', 'plan': plan, 'registryBefore': state,
                                    'overlayBefore': overlay, 'runtimeSnapshotSha256': report['runtimeSnapshotSha256'],
                                    'runtimeDependencies': [{k: x[k] for k in ('importName', 'resolvedHost', 'hostSha256', 'resolvedSymbolCount')}
                                                            for x in admission['dependencies']],
                                    'directImportsResolved': True, 'runtimeBehaviorVerified': False})
                    journal.append({'event': 'before_stage', 'directory': str(destination), 'bundleManifest': manifest})
                    report['stageAttempted'] = True
                    report['stageResult'] = s.stage_new(bundle, expected, destination, policy, journal)
                    receipt_sha = report['stageResult']['stageRecordSha256']
                    with ExitStack() as held:
                        held.enter_context(s.open_file(destination, True, access=0x20080, share=3))
                        names = set(manifest['files']) | {'bundle-manifest.json', 'stage-intent.json', 'stage-record.json'}
                        handles = {name: held.enter_context(s.open_file(destination/name)) for name in names}
                        s.inspect_stage(destination, receipt_sha, policy)
                        record = module.record(s.read_handle(handles['stage-record.json'], module.LIMIT))
                        journal.append({'event': 'stage_completed', 'stageRecordSha256': receipt_sha, 'stageRecord': record})
                        s.require(r.inspect(registry_root, plan)['newRegistrationAllowed'] and
                                  not r.inspect_overlay(overlay_root, plan)['present'], 'Registration changed before create; preserve stage')
                        report['registrationAttempted'] = True
                        try:
                            report['registrationResult'] = r.register_new(registry_root, plan, journal)
                        except r.RegistryFailure as error:
                            report['registrationResult'] = error.report
                            raise
                        report['stageVerifiedObserved'] = s.inspect_stage(destination, receipt_sha, policy)['verified']
                        report['registrationOwnedObserved'] = r.inspect(registry_root, plan)['exactOwned']
                        s.require(report['stageVerifiedObserved'] and report['registrationOwnedObserved'] and
                                  not r.inspect_overlay(overlay_root, plan)['present'], 'Final installation observations differ')
                        journal.append({'event': 'install_completed', 'stageRecordSha256': receipt_sha,
                                        'stageVerifiedObserved': True, 'registrationOwnedObserved': True,
                                        'nativeSessionStarted': False, 'installedAsioActivationTested': False})
                    report['successful'] = True
                except Exception as error:
                    report['error'] = str(error)
                    try:
                        journal.append({'event': 'install_failed', 'report': report})
                        report['failureJournalPersisted'] = True
                    except Exception as journal_error:
                        report['failureJournalError'] = str(journal_error)
                    raise
        return report
    except Exception as error:
        if not report['error']:
            report['error'] = str(error)
        raise InstallFailure(report) from error


def install_production(bundle, expected):
    j = sibling('asio-install-journal'); s = j.stage_module()
    s.require(s.elevated(), 'Explicit administrator token required; no automatic UAC')
    with ExitStack() as stack:
        module, manifest, payload = s.snapshot_bundle(bundle, expected, stack)
        base, destination = s.production_destination(module.record(payload['deployment-plan.json']))
        # Bootstrap of the fixed protected base is a separate, unfinished step.
        # Never silently create parents or relax an existing descriptor.
        s.require(base.exists(), 'Reviewed protected installer base must already exist')
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, '', 0, winreg.KEY_READ | winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as root:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, '', 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as overlay:
                return install_owned(bundle, expected, base, destination, s.PRODUCTION, root, overlay)


if __name__ == '__main__':
    if sys.argv[1:] not in ([], ['--plan']):
        print('Only --plan is exposed; installation requires a trusted installer', file=sys.stderr); sys.exit(2)
    print(json.dumps({'schema': 'sl3.install-plan.v1', 'planOnly': True, 'filesWritten': False,
                      'registryWritten': False, 'deviceAccess': False, 'machineMutationCliExposed': False}))
