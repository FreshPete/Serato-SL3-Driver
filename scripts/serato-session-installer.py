"""Parameterized attended installer dispatch. Default action is read-only Plan."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import runpy
import time


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('plan','install','revoke','rollback'),nargs='?',default='plan')
    parser.add_argument('--capsule',type=Path,required=True)
    parser.add_argument('--expected-capsule-sha256',required=True)
    args = parser.parse_args(argv)
    api = runpy.run_path(str(Path(__file__).with_name('serato-session-capsule.py')))
    record,plan,directory = api['verify'](args.capsule,args.expected_capsule_sha256)
    module = api['module']; bundle = Path(record['bundle']['path']); expected = record['bundle']['sha256']
    permit_path = Path(record['permitPath']); receipt = api['layout'](directory)['install-receipt.json']
    stage = module('asio-install-journal.py','stage_module')()
    stage.local(permit_path)
    if args.action == 'plan':
        with stage.pinned_parents(permit_path):
            api['require'](not permit_path.exists(),'A permit already exists; preserve the active session')
        print(json.dumps({'planOnly':True,'capsuleVerified':True,'bundleVerified':True,
                          'registrationWritten':False,'deviceAccess':False}))
        return 0
    api['require'](stage.elevated(),'Explicit administrator token required for installer operations')
    if args.action == 'rollback':
        api['require_retired'](directory,plan)
        report = json.loads(receipt.read_bytes())
        digest = report['stageResult']['stageRecordSha256']
        destination = Path(plan['installationDirectory'])
        result = module('asio-uninstall.py','uninstall_production')(destination.parent,destination,digest)
        print(json.dumps(result));return 0 if result['successful'] else 1
    permit = runpy.run_path(str(Path(__file__).with_name('serato-installer-permit.py')))
    trusted = {stage.SYSTEM,stage.ADMINS,stage.account_sid(r'NT SERVICE\TrustedInstaller')}
    with ExitStack() as stack:
        for handle in stack.enter_context(stage.pinned_parents(permit_path)):
            stage.safe_parent(handle,trusted)
        if args.action == 'revoke':
            deadline = time.monotonic()+20
            while True:
                try:
                    permit['revoke'](stage,permit_path,expected);return 0
                except OSError as error:
                    if error.winerror not in (32,33) or time.monotonic() >= deadline: raise
                    time.sleep(.2)
        stack.enter_context(permit['claim'](stage,permit_path,expected))
        api['require'](not Path(plan['pointerPath']).exists(),'An active broker pointer is present')
        install = module('asio-install.py','install_production')
        with receipt.open('x',encoding='utf-8') as stream:
            try:
                result = install(bundle,expected)
            except Exception as error:
                result = getattr(error,'report',{'successful':False,'error':str(error)})
            json.dump(result,stream);stream.flush();os.fsync(stream.fileno())
        return 0 if result['successful'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
