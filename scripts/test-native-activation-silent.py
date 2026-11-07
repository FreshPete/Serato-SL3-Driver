"""Opt-in production ASIO silent duplex and application-bound reopen probes."""
import argparse
import json
from pathlib import Path
import runpy

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--run-native-silent-duplex',action='store_true')
    modes.add_argument('--run-native-application-reopen',action='store_true')
    modes.add_argument('--prepare-application-reopen',action='store_true')
    names=('host-build','host-build-sha256','bundle','bundle-sha256','native-build')
    for name in names: parser.add_argument('--'+name)
    args=parser.parse_args()
    if not (args.run_native_silent_duplex or args.run_native_application_reopen or args.prepare_application_reopen):
        print(json.dumps({'schema':'sl3.native-silent-wrapper-plan.v1','initializationAttempted':False,'audioStarted':False}))
    else:
        if not all(getattr(args,n.replace('-','_')) for n in names): parser.error('All reviewed identities required')
        runner=runpy.run_path(str(Path(__file__).with_name('test-native-activation-control.py')))
        raise SystemExit(runner['run'](args,silent_duplex=True,
            application_reopen=args.run_native_application_reopen or args.prepare_application_reopen,
            prepare_only=args.prepare_application_reopen))
