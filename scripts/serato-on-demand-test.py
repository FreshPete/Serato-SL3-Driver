"""Source-bound attended setup/restore for a no-shim normal-start test. Default Plan is read-only."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
APP_SHA = '66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265'
ORIGINAL_SHA = '872fc4fdad2eab2ddd34387d2d3c04dd9731c84798d9fdc7bd05ca54e1567db8'
CANDIDATE_SHA = 'd135e6f1c03601cc44b3e5f623eed36af81bbff585332a3fdc8d5d533b2cb66a'
ASSETS = {'archive/candidate-userio_resources.bin', 'archive/serato-archive-file-transaction.ps1',
          'archive/deployment-plan.json', 'archive/archive-test.ps1','archive/action-child.ps1'}


def require(value, text):
    if not value:
        raise ValueError(text)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name):
    return runpy.run_path(str(ROOT/'scripts'/name))


def source_names():
    return sorted(set(['scripts/serato-on-demand-test.py', 'scripts/prepare-serato-on-demand-test.py',
        'scripts/on-demand-action-lock.py',
        'scripts/on-demand-action-child.ps1',
        'scripts/prepare-asio-deployment.py', 'scripts/rebind-asio-deployment.py',
        'scripts/prepare-embedded-python.py',
        'scripts/serato-archive-file-transaction.ps1', 'scripts/serato-archive-deployment-template.ps1',
        *module('prepare-serato-installed-phase-archive.py')['SOURCES'],
        *(p.relative_to(ROOT).as_posix() for p in (ROOT/'scripts').glob('asio-*.py'))]))


def coordinate(action, archive, native):
    """Trusted adapters own protection/identity checks; no process/device launch here."""
    require(action in ('plan', 'setup', 'restore'), 'Known experiment action required')
    report = {'schema':'sl3.on-demand-test-action.v1', 'action':action, 'successful':False, 'before':None, 'after':None,
              'steps':[], 'error':None, 'applicationLaunched':False, 'nativeDeviceOpenedByTool':False,
              'normalSeratoStartupValidated':False, 'combinedAtomicTransaction':False}

    def observe():
        a = archive('Plan')
        require(a['schema'] == 'sl3.archive-deployment-action.v1' and a['action'] == 'Plan', 'Typed archive observation required')
        return {'archive':a['after']['state'], 'seratoRunning':a['seratoRunning'], 'native':native.observe()}

    try:
        report['before'] = observe()
        if action == 'plan':
            report['after'] = report['before']; report['successful'] = True; return report
        require(report['before']['seratoRunning'] is False, 'Close Serato manually before setup or restoration')
        if action == 'setup':
            require(report['before']['archive'] in ('original','install-staged','installed'), 'Recognized original/install state required')
            n = report['before']['native']
            if n['state'] == 'absent':
                require(report['before']['archive'] != 'installed', 'Installed profile without native ownership needs restoration')
                installed = native.install(); report['steps'].append({'nativeInstall':installed})
                require(installed['successful'] is True, 'Native installation did not succeed; preserve its typed result')
            else:
                require(n['state'] == 'installed', 'Foreign, incomplete or unregistered native state; preserve for reviewed recovery')
            if report['before']['archive'] != 'installed':
                report['steps'].append({'archiveInstall':archive('Install')})
            report['after'] = observe()
            require(report['after']['archive'] == 'installed' and report['after']['native']['state'] == 'installed', 'Setup observations differ')
        else:
            a = report['before']['archive']
            if a in ('installed','rollback-staged'):
                report['steps'].append({'archiveRollback':archive('Rollback')})
            elif a not in ('original','restored','install-staged'):
                raise ValueError('Conflicting archive witnesses; preserve before native removal')
            report['steps'].append({'archiveClean':archive('Clean')})
            n = native.observe()
            if n['state'] in ('installed','unregistered'):
                removed = native.remove(n['stageRecordSha256']); report['steps'].append({'nativeRemoval':removed})
                require(removed['successful'] is True, 'Native removal did not succeed; preserve its typed result')
            else:
                require(n['state'] == 'absent', 'Unknown/partial native state needs its reviewed installer recovery')
            report['after'] = observe()
            require(report['after']['archive'] == 'original' and report['after']['native']['state'] == 'absent', 'Restoration observations differ')
        report['successful'] = True
    except Exception as error:
        report['error'] = str(error)
        if isinstance(getattr(error,'report',None),dict):
            report['componentFailure'] = error.report
        # A failed setup preserves the actual partial state; no guessed undo.
        try:
            report['after'] = observe()
        except Exception as observation_error:
            report['observationError'] = str(observation_error)
    return report


def observe_owned_native(s, r, plan, destination, expected, policy, root, overlay_root):
    """Shared observation for production roots and explicit isolated installer fixtures."""
    registration = r.inspect(root,plan); overlay = r.inspect_overlay(overlay_root,plan)
    if overlay['present']:
        return {'state':'conflict','reason':'Current-user COM overlay is present'}
    if s.absent(destination):
        return {'state':'absent' if registration['newRegistrationAllowed'] else 'conflict'}
    try:
        receipt_sha = sha(destination/'stage-record.json')
        s.inspect_stage(destination,receipt_sha,policy)
        require(sha(destination/'bundle-manifest.json') == expected,'Existing protected stage belongs to another package')
        state = 'installed' if registration['exactOwned'] else 'unregistered' if registration['allAbsent'] else 'conflict'
        return {'state':state,'stageRecordSha256':receipt_sha}
    except Exception as error:
        return {'state':'conflict','reason':str(error)}


class Native:
    def __init__(self, bundle, expected, retained_broker=False):
        self.install_api = module('asio-install.py')
        self.i = self.install_api['sibling']('asio-install-journal')
        self.s = self.i.stage_module(); self.r = self.install_api['sibling']('asio-registry')
        self.bundle, self.expected = bundle, expected
        self.api = module('prepare-asio-deployment.py')
        self.manifest, payload = self.api['capture_bundle'](bundle, expected)
        self.api['verify_payloads'](self.manifest, payload)
        require(type(retained_broker) is bool, 'Typed retained broker mode required')
        self.plan = self.api['record'](payload['deployment-plan.json'])
        self.retained_broker = retained_broker
        if retained_broker:
            require(self.manifest['schema'] == 'sl3.deployment-bundle.v1' and
                    self.manifest['timingMode'] == 'unmeasured-diagnostic-44100-128' and
                    self.plan['automaticStart'] is False,
                    'Explicit retained broker test requires a bounded diagnostic locator bundle')
        else:
            require(self.manifest['schema'] == 'sl3.deployment-bundle.v2', 'On-demand native package required')
        self.base, self.destination = self.s.production_destination(self.plan)

    def require_idle_pointer(self):
        if self.retained_broker:
            pointer = Path(self.plan['pointerPath'])
            require(self.s.absent(pointer) and self.s.absent(pointer.with_name(pointer.name + '.pending')),
                    'Stop the retained broker and withdraw its pointer before changing setup')

    def observe(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,'',0,self.r.READ) as root, \
             winreg.OpenKey(winreg.HKEY_CURRENT_USER,'',0,self.r.READ) as overlay:
            return observe_owned_native(self.s,self.r,self.plan,self.destination,self.expected,self.s.PRODUCTION,root,overlay)

    def install(self):
        return self.install_api['install_production'](self.bundle, self.expected)

    def remove(self, receipt_sha):
        return module('asio-uninstall.py')['uninstall_production'](self.base, self.destination, receipt_sha)


def verify(path, expected, held):
    path = Path(path).absolute()
    require(path.name == 'experiment.json' and path.parent.parent == ROOT/'analysis' and
            path.parent.name.startswith('sl3-on-demand-test-'), 'Prepared local experiment path required')
    require(sha(path) == expected, 'Experiment manifest identity changed')
    record = json.loads(path.read_bytes())
    require(record['schema'] == 'sl3.on-demand-normal-start-test.v1' and record['applicationSha256'] == APP_SHA and
            record['originalArchiveSha256'] == ORIGINAL_SHA and record['candidateArchiveSha256'] == CANDIDATE_SHA,
            'Pinned normal-start experiment required')
    require(record['maximumOwnerLifetimeMs'] == 600000 and all(record[name] is False for name in
            ('applicationLaunched','startupShimUsed','installed','nativeDeviceAccess','combinedAtomicTransaction')),
            'Bounded unexecuted no-shim experiment required')
    require(record['projectRoot'] == str(ROOT) and set(record['sources']) == set(source_names()) and
            set(record['assets']) == ASSETS, 'Exact source/asset inventory required')
    s = module('asio-install-journal.py')['stage_module']()
    for name, expected_sha in [(str(path),expected),
            *((str(ROOT/name),value) for name,value in record['sources'].items()),
            *((str(path.parent/name),value) for name,value in record['assets'].items())]:
        handle = held.enter_context(s.open_file(Path(name)))
        require(hashlib.sha256(s.read_handle(handle, 16*1024*1024)).hexdigest() == expected_sha, 'Pinned source/asset differs')
    application = Path(record['application'])
    require(application == s.known_folder('905e63b6-c1bf-494e-b29c-65b732d3d21a')/'Serato/Serato DJ Pro/Serato DJ Pro.exe' and
            sha(application) == APP_SHA, 'Original application path and identity required')
    require(sha(Path(sys.executable)) == record['python']['sha256'], 'Prepared Python runtime required')
    module('prepare-embedded-python.py')['verify'](Path(sys.executable).parent,record['python']['manifestSha256'])
    module('prepare-portable-powershell.py')['verify'](Path(record['powershell']['directory']), record['powershell']['manifestSha256'])
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',choices=('plan','setup','restore'),default='plan')
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--expected-experiment-sha256',required=True)
    args = parser.parse_args()
    args.experiment = args.experiment.absolute()
    with ExitStack() as held:
        record = verify(args.experiment,args.expected_experiment_sha256,held)
        native = Native(Path(record['bundle']['directory']),record['bundle']['sha256'],record.get('retainedBroker', False))
        if args.action != 'plan':
            require(native.s.elevated(), 'Run this exact reviewed action as administrator; no automatic approval prompt is requested')
        lease=None
        def archive(action):
            command=[str(Path(record['powershell']['directory'])/'pwsh.exe'),'-NoProfile','-NonInteractive','-File']
            if lease is None:
                child=subprocess.run([*command,str(args.experiment.parent/'archive/archive-test.ps1'),'-Action',action],
                    capture_output=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                with lease.child() as (handle,options):
                    child=subprocess.run([*command,str(args.experiment.parent/'archive/action-child.ps1'),'-Action',action,'-ActionLockHandle',str(handle)],
                        capture_output=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW,**options)
            require(child.returncode == 0, 'Archive action refused: '+child.stderr.decode('utf-8',errors='replace'))
            return json.loads(child.stdout)
        if args.action == 'plan':
            result = coordinate(args.action,archive,native)
        else:
            locking=module('on-demand-action-lock.py')
            lock_path=Path(record['application']).with_name(locking['LOCK_NAME'])
            with locking['hold'](native.s,lock_path,native.s.PRODUCTION) as lease:
                native.require_idle_pointer()
                result=coordinate(args.action,archive,native)
            result['actionLock']=lease.report
        print(json.dumps(result,indent=2))
        return 0 if result['successful'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
