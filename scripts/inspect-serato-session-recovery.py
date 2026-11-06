"""Read-only recovery check for one reviewed session; never stop, repair or elevate."""
import argparse
import base64
import json
from pathlib import Path
import re
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def module(name): return runpy.run_path(str(ROOT / 'scripts' / name))


def classify(current, resources, owners, running, issues, has_run, broker_retired):
    live = running or any(owner.get('state') == 'alive' for owner in owners.values())
    uncertain = bool(issues) or any(owner.get('state') == 'unknown' for owner in owners.values())
    if live:
        phase, message = 'active_session', 'Close the active session before checking recovery again.'
    elif (uncertain or current.get('observed') is not True or resources.get('observed') is not True or
          resources.get('archiveState') not in ('original','install-staged','installed','rollback-staged','restored') or
          type(resources.get('bundlePresent')) is not bool or type(resources.get('pendingPresent')) is not bool):
        phase, message = 'review_required', 'Recovery evidence is incomplete or conflicting; no changes were made.'
    elif (current.get('currentSetupClean') is True and resources.get('archiveState') == 'original' and
          resources.get('bundlePresent') is False and resources.get('pendingPresent') is False):
        phase, message = 'clean', 'Original files and temporary registration are already clean.'
    elif not has_run or owners['runner']['state'] not in ('exited','replaced') or owners['stage']['state'] not in ('exited','replaced'):
        phase, message = 'review_required', 'Interrupted state lacks verified retired session owners.'
    elif not broker_retired:
        phase, message = 'broker_retirement_required', 'Broker retirement must be verified before protected recovery.'
    else:
        phase, message = 'recovery_required', 'Interrupted state remains; use the explicit recovery path after reviewing this report.'
    return {'phase':phase,'message':message,'originalSetupClean':phase == 'clean',
            'activeSessionObserved':live,'recoveryAuthorized':False}


def resources(plan, powershell):
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    script = '\n'.join(["$ErrorActionPreference='Stop'",
        '. ' + quote(ROOT / 'scripts/serato-installer-resource-transaction.ps1'),
        '$tx=New-Sl3ArchiveTransaction ' + quote(Path(plan['application']['path']).with_name('userio_resources.bin')) +
            ' ' + quote(plan['originalArchiveSha256']) + ' ' + quote(plan['archiveSource']['sha256']),
        "$quiet={if(Get-Process 'Serato DJ Pro' -ErrorAction SilentlyContinue){throw 'Close Serato before recovery inspection'}}",
        'Get-Sl3InstallerResourceRecoveryPlan $tx ' + quote(plan['installerResource']['sha256']) +
            ' $quiet ${function:Assert-Sl3ArchiveProtectedPath} | ConvertTo-Json -Depth 4'])
    command = [str(powershell / 'pwsh.exe'), '-NoLogo','-NoProfile','-NonInteractive','-EncodedCommand',
               base64.b64encode(script.encode('utf-16-le')).decode('ascii')]
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        stdout, stderr = child.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        child.kill(); child.communicate(timeout=5)
        raise ValueError('Read-only resource check timed out; only its owned child was stopped')
    if child.returncode or len(stdout) > 32768:
        raise ValueError('Protected resource preflight did not finish successfully')
    result = json.loads(stdout)
    if (result.get('schema') != 'sl3.installer-resource-recovery-plan.v1' or result.get('filesWritten') is not False or
        result.get('deviceAccess') is not False or result.get('archiveState') not in
            ('original','install-staged','installed','rollback-staged','restored') or
        type(result.get('bundlePresent')) is not bool or type(result.get('pendingPresent')) is not bool):
        raise ValueError('Resource check scope differs')
    return {**result, 'observed':True}


def inspect(plan_path, expected, powershell, powershell_sha):
    plan_path, powershell = Path(plan_path).absolute(), Path(powershell).absolute()
    api = module('prepare-serato-session-plan.py')
    plan = api['verify'](plan_path, expected)
    api['require'](type(powershell_sha) is str and re.fullmatch('[0-9a-f]{64}',powershell_sha) is not None,
                   'Expected PowerShell runtime identity required')
    directory = Path(plan['capsule']['path']).parent; output = Path(plan['hostOutput'])
    for path,prefix in ((directory,'sl3-session-capsule-'),(output,'sl3-startup-session-')):
        api['require'](path.parent.resolve() == (ROOT/'analysis').resolve() and path.name.startswith(prefix) and
            not path.is_symlink() and not path.is_junction(), 'Selected recovery paths must remain in the project')
    status = module('inspect-serato-session-status.py'); issues = []
    run = status['record'](directory/'session-run.lock',issues,'runner')
    intent = status['record'](output/'intent.json',issues,'intent')
    def owner(value, image, name, required=False):
        if value is None and not required: return {'state':'not_recorded'}
        if (not isinstance(value,dict) or type(value.get('pid')) is not int or not 0 < value['pid'] <= 0xffffffff or
            not isinstance(value.get('created'),str) or re.fullmatch('[1-9][0-9]{0,19}',value['created']) is None or
            not 0 < int(value['created']) <= 2**64-1):
            issues.append({'record':name,'message':'Valid owner identity is missing'})
            return {'state':'unknown'}
        return status['owner_state'](value,image)
    owners = {'runner':owner((run or {}).get('runner'),powershell/'pwsh.exe','runner',run is not None),
              'stage':owner((run or {}).get('stage'),powershell/'pwsh.exe','stage'),
              'supervisor':owner((intent or {}).get('supervisorOwner'),plan['python']['path'],'supervisor',intent is not None)}
    running = module('inspect-sl3-session-readiness.py')['running_serato']()['running']
    current, resource, retirement = {'observed':False},{'observed':False},False
    if not running and not any(value['state'] == 'alive' for value in owners.values()) and not issues:
        try:
            module('prepare-portable-powershell.py')['verify'](powershell,powershell_sha)
            current = status['current_state'](plan)
            resource = resources(plan,powershell)
            if run is not None:
                try:
                    capsule = module('serato-session-capsule.py')
                    deployment = json.loads((Path(plan['nativeBundle']['path'])/'deployment-plan.json').read_bytes())
                    capsule['require_retired'](directory,deployment); retirement = True
                except (OSError,ValueError,KeyError,TypeError,AttributeError): pass
        except (OSError,ValueError,KeyError) as error:
            issues.append({'record':'preflight','message':str(error)[:512]})
    summary = classify(current,resource,owners,running,issues,run is not None,retirement)
    ordinary = not module('asio-install-journal.py')['stage_module']().elevated()
    return {'schema':'sl3.session-recovery-check.v1','planSha256':expected,**summary,'owners':owners,
        'currentSetup':current,'resourcePlan':resource,'brokerRetirementReported':retirement,'issues':issues,
        'pointInTimeObservation':True,'ordinaryToken':ordinary,'previousSessionShutdownVerified':False,'repairAttempted':False,
        'filesWritten':False,'registryWritten':False,'elevationRequested':False,'deviceOpened':False,
        'deviceReadinessVerified':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-plan',type=Path,required=True)
    parser.add_argument('--expected-session-plan-sha256',required=True)
    parser.add_argument('--powershell-directory',type=Path,required=True)
    parser.add_argument('--expected-powershell-manifest-sha256',required=True)
    args=parser.parse_args()
    result=inspect(args.session_plan,args.expected_session_plan_sha256,args.powershell_directory,
                   args.expected_powershell_manifest_sha256)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['phase'] == 'clean' else 3)
