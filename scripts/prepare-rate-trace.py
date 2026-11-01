"""Prepare/check a fixed single-use rate/USB trace plan. Never launches a child."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT=Path(__file__).resolve().parents[1]


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    require(0<path.stat().st_size<=131072,'Invalid rate plan record size')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def runtime():
    build_path=ROOT/'artifacts/build/native/native-build-Release.json';build=read(build_path)
    require(sha(ROOT/'scripts/build-native.ps1')==build['buildScriptSha256'].lower(),'Build runner changed')
    for name,digest in build['inputs'].items():require(sha(ROOT/name)==digest.lower(),'Native build input changed: '+name)
    feature=build['hostProbe']['rateSelection'];require(feature['testsPassed'] is True and feature['physicalRateChangeTested'] is False and feature['traceRunnerPrepared'] is True and feature['traceLauncherPrepared'] is True,'Rate trace source not prepared')
    pins=feature['traceScriptInputs'];require(len(pins)==23,'Rate runtime dependencies missing')
    for name,digest in pins.items():require(sha(ROOT/'scripts'/name)==digest.lower(),'Rate dependency changed: '+name)
    launchers=feature['traceLauncherInputs']
    require(set(launchers)=={'prepare-rate-trace.py','start-rate-trace.ps1'},'Rate launcher dependencies missing')
    for name,digest in launchers.items():
        require(sha(ROOT/'scripts'/name)==digest.lower(),'Rate launcher dependency changed: '+name)
    images={}
    for name,digest in (('sl3_host_probe.exe',build['hostProbe']['executableSha256']),('sl3_usbdk.exe',build['usbdk']['executableSha256'])):
        path=ROOT/'artifacts/build/native/Release'/name;require(sha(path)==digest.lower(),'Tested native image changed: '+name);images[name]=sha(path)
    pwsh=shutil.which('pwsh');require(pwsh is not None,'PowerShell 7 required')
    return {'buildManifestSha256':sha(build_path),'powershell':str(Path(pwsh).resolve()),'powershellSha256':sha(Path(pwsh)),
            'nativeImages':images,'scriptInputs':pins,'plannerSha256':sha(Path(__file__)),
            'launcherSha256':sha(ROOT/'scripts/start-rate-trace.ps1')}


def plan_value(directory,target,initial):
    require(type(target) is int and target in (44100,48000) and type(initial) is int and initial in (44100,48000),
        'Canonical intended and reviewed initial rates required')
    directory=directory.resolve()
    require(directory.parent==(ROOT/'analysis').resolve() and re.fullmatch(r'rate-trace-[A-Za-z0-9-]{1,64}',directory.name),
            'Expected a direct analysis/rate-trace-* directory')
    context=ROOT/'tests/results/local'/(directory.name+'-rate')
    require(context.parent.is_dir() and not context.exists(),'Rate context must be fresh')
    r=runtime()
    return {'schema':'sl3.rate-trace.plan.v1','scenario':'Rate','targetHz':target,'expectedInitialHz':initial,
            'contextDirectory':str(context.resolve()),'runtime':r,'traceSeconds':60,'probeDeadlineSeconds':30,
            'postRetirementTraceSecondsRequired':12,'redirectsRequested':1,'maximumRateSetters':1,'audioStarts':0,
            'automaticRetry':False,'automaticRollback':False,'readinessAdmission':False,'imageWindowQualified':False,
            'normalRole':{'script':str(ROOT/'scripts/test-rate-user-probe.ps1'),
                          'arguments':['-Run','-TargetHz',str(target),'-ExpectedInitialHz',str(initial),'-ContextDirectory',str(context.resolve())]},
            'collectorRole':{'script':str(ROOT/'scripts/capture-controls-user-context.ps1'),
                             'arguments':['-Run','-WithStateObserver','-TraceSeconds','60','-ContextDirectory',str(context.resolve())]}}



def validate(path,claimed=False):
    require(path.name=='rate-trace.json','Unexpected rate plan filename')
    for p in (path,path.parent):require(not p.is_symlink() and not p.is_junction(),'Rate plan reparse point refused')
    saved=read(path);expected=plan_value(path.parent,saved['targetHz'],saved['expectedInitialHz']);require(saved==expected,'Rate plan or tested runtime changed')
    if not claimed:require(not (path.parent/'attempted.json').exists(),'Rate plan already attempted; never rearm it')
    return expected


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',type=Path);mode.add_argument('--plan',type=Path);mode.add_argument('--collector-check',type=Path)
    parser.add_argument('--target',choices=('44100','48000'));parser.add_argument('--expected-initial',choices=('44100','48000'))
    parser.add_argument('--expected-sha256');parser.add_argument('--launch-id');args=parser.parse_args()
    if args.prepare:
        require(not args.expected_sha256 and not args.launch_id and not args.prepare.exists(),'Choose a fresh rate plan directory')
        require(args.target and args.expected_initial,'Explicit target and reviewed initial rate required')
        value=plan_value(args.prepare,int(args.target),int(args.expected_initial));args.prepare.mkdir();path=args.prepare/'rate-trace.json'
        with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    else:
        require(not args.target and not args.expected_initial,'Saved rate targets cannot be overridden')
        path=(args.plan or args.collector_check).absolute();value=validate(path,bool(args.collector_check))
        if args.collector_check:
            require(re.fullmatch('[0-9a-f]{64}',args.expected_sha256 or '') and sha(path)==args.expected_sha256 and
                    re.fullmatch('[0-9a-f]{32}',args.launch_id or ''),'Collector plan binding differs')
            attempted=read(path.parent/'attempted.json');normal=read(path.parent/'normal-started.json')
            require(attempted['launchId']==normal['launchId']==args.launch_id and attempted['planSha256']==normal['planSha256']==sha(path),
                    'Collector has no matching single-use launch')
            require(not (path.parent/'collector-started.json').exists(),'Collector already attempted')
        else:require(not args.expected_sha256 and not args.launch_id,'Internal arguments require collector role')
    print(json.dumps(value,indent=2))


if __name__=='__main__':main()
