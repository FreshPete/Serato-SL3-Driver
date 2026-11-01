"""Prepare/check a fixed single-use scope/USB trace plan. Never launches a child."""
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
    require(0<path.stat().st_size<=131072,'Invalid scope plan record size')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def runtime():
    build_path=ROOT/'artifacts/build/native/native-build-Release.json';build=read(build_path)
    require(sha(ROOT/'scripts/build-native.ps1')==build['buildScriptSha256'].lower(),'Build runner changed')
    for name,digest in build['inputs'].items():require(sha(ROOT/name)==digest.lower(),'Native build input changed: '+name)
    pins=build['scopeProbe']['scriptInputs'];require(len(pins)==19,'Scope runtime dependencies missing')
    for name,digest in pins.items():require(sha(ROOT/'scripts'/name)==digest.lower(),'Scope dependency changed: '+name)
    for name,digest in build['scopeProbe']['traceLauncherInputs'].items():
        require(sha(ROOT/'scripts'/name)==digest.lower(),'Scope launcher dependency changed: '+name)
    images={}
    for name,digest in (('sl3_scope_probe.exe',build['scopeProbe']['executableSha256']),('sl3_usbdk.exe',build['usbdk']['executableSha256'])):
        path=ROOT/'artifacts/build/native/Release'/name;require(sha(path)==digest.lower(),'Tested native image changed: '+name);images[name]=sha(path)
    pwsh=shutil.which('pwsh');require(pwsh is not None,'PowerShell 7 required')
    return {'buildManifestSha256':sha(build_path),'powershell':str(Path(pwsh).resolve()),'powershellSha256':sha(Path(pwsh)),
            'nativeImages':images,'scriptInputs':pins,'plannerSha256':sha(Path(__file__)),
            'launcherSha256':sha(ROOT/'scripts/start-scope-trace.ps1')}


def plan_value(directory):
    directory=directory.resolve()
    require(directory.parent==(ROOT/'analysis').resolve() and re.fullmatch(r'scope-trace-[A-Za-z0-9-]{1,64}',directory.name),
            'Expected a direct analysis/scope-trace-* directory')
    context=ROOT/'tests/results/local'/(directory.name+'-scope')
    require(context.parent.is_dir() and not context.exists(),'Scope context must be fresh')
    r=runtime()
    return {'schema':'sl3.scope-trace.plan.v1','scenario':'Scope','contextDirectory':str(context.resolve()),'runtime':r,
            'traceSeconds':60,'probeDeadlineSeconds':30,'postRetirementTraceSecondsRequired':12,
            'redirectsRequested':1,'facadeObjects':3,'clockReads':3,'audioStarts':0,'rateSetters':0,
            'automaticRetry':False,'readinessAdmission':False,'imageWindowQualified':False,
            'normalRole':{'script':str(ROOT/'scripts/test-controls-user-probe.ps1'),
                          'arguments':['-Run','-Scenario','Scope','-TraceSeconds','60','-ContextDirectory',str(context.resolve())]},
            'collectorRole':{'script':str(ROOT/'scripts/capture-controls-user-context.ps1'),
                             'arguments':['-Run','-WithStateObserver','-TraceSeconds','60','-ContextDirectory',str(context.resolve())]}}


def validate(path,claimed=False):
    require(path.name=='scope-trace.json','Unexpected scope plan filename')
    for p in (path,path.parent):require(not p.is_symlink() and not p.is_junction(),'Scope plan reparse point refused')
    expected=plan_value(path.parent);require(read(path)==expected,'Scope plan or tested runtime changed')
    if not claimed:require(not (path.parent/'attempted.json').exists(),'Scope plan already attempted; never rearm it')
    return expected


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',type=Path);mode.add_argument('--plan',type=Path);mode.add_argument('--collector-check',type=Path)
    parser.add_argument('--expected-sha256');parser.add_argument('--launch-id');args=parser.parse_args()
    if args.prepare:
        require(not args.expected_sha256 and not args.launch_id and not args.prepare.exists(),'Choose a fresh scope plan directory')
        value=plan_value(args.prepare);args.prepare.mkdir();path=args.prepare/'scope-trace.json'
        with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    else:
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
