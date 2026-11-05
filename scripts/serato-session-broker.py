"""Source-bound ordinary-user broker dispatch; delegates owned cleanup."""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('plan','start','stop'),nargs='?',default='plan')
    parser.add_argument('--capsule',type=Path,required=True)
    parser.add_argument('--expected-capsule-sha256',required=True)
    args = parser.parse_args(argv)
    api = runpy.run_path(str(Path(__file__).with_name('serato-session-capsule.py')))
    record,plan,directory = api['verify'](args.capsule,args.expected_capsule_sha256)
    if args.action == 'plan':
        print(json.dumps({'planOnly':True,'capsuleVerified':True,'limitMs':record['brokerLimitMs'],
                          'captureOutput':record['captureOutput'],'processStarted':False,'deviceAccess':False}));return 0
    files = api['layout'](directory); bundle = Path(record['bundle']['path']); installation = Path(plan['installationDirectory'])
    if args.action == 'stop' and files['broker-clean.json'].exists():
        api['require_retired'](directory,plan)
        print(files['broker-clean.json'].read_text(encoding='utf-8'),end='');return 0
    payloads = json.loads((bundle/'bundle-manifest.json').read_bytes())['files']
    controller = installation/'sl3_broker_controller.exe'; pointer = Path(plan['pointerPath'])
    command = [sys.executable,'-I','-B',str(api['ROOT']/'scripts/asio-diagnostic-session.py'),args.action,
               '--controller',str(controller),'--controller-sha256',payloads[controller.name]['sha256'],
               '--session',str(files['broker-session']),'--pointer',str(pointer)]
    environment = os.environ.copy()
    if args.action == 'start':
        api['require'](not files['broker-session'].with_suffix('.closed').exists(),'Broker handoff is closed')
        receipt = json.loads(files['install-receipt.json'].read_bytes())
        api['require'](receipt.get('successful') is True,'Successful installation receipt required')
        if record['captureOutput']:
            api['require'](not files['output-capture'].exists(),'Fresh output capture directory required')
            environment['SL3_OUTPUT_CAPTURE_DIRECTORY'] = str(files['output-capture'])
        else:
            environment.pop('SL3_OUTPUT_CAPTURE_DIRECTORY',None)
        worker = installation/'sl3_usbdk.exe'; helper = installation/'UsbDkHelper.dll'
        for path in (controller,worker,helper):
            api['require'](api['sha'](path) == payloads[path.name]['sha256'],'Staged binary differs: '+path.name)
        timing = files['broker-timing.txt']; configuration = files['broker-input.conf']
        with timing.open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(f'SL3-ASIO-DIAGNOSTIC-TIMING-1\nworker_sha256={api["sha"](worker)}\n'
                         f'helper_sha256={api["sha"](helper)}\nrate_hz=44100\nbuffer_frames=128\n')
        with configuration.open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(f'SL3-ASIO-CONFIG-1\nworker={worker}\nworker_sha256={api["sha"](worker)}\n'
                         f'helper={helper}\ntiming_record={timing}\ntiming_record_sha256={api["sha"](timing)}\n')
        command += ['--input',str(configuration),'--limit-ms',str(record['brokerLimitMs'])]
    result = subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',env=environment)
    if result.returncode:
        with (directory/f'broker-{args.action}-failure.json').open('x',encoding='utf-8') as stream:
            json.dump({'exitCode':result.returncode,'stderr':result.stderr},stream)
        print(result.stderr,end='',file=sys.stderr);return result.returncode
    report = json.loads(result.stdout)
    if args.action == 'stop':
        api['require'](report.get('controllerExited') is True and not pointer.exists(),'Broker retirement is unverified')
        with files['broker-clean.json'].open('x',encoding='utf-8') as stream:json.dump(report,stream)
    print(result.stdout,end='');return 0


if __name__ == '__main__':
    raise SystemExit(main())
