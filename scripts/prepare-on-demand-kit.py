"""Verify an engineering kit and prepare one-time setup; never installs or launches Serato."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import stat
import subprocess
import uuid

ROOT=Path(__file__).resolve().parents[1]
def require(value,text):
    if not value:raise ValueError(text)
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def module(name):return runpy.run_path(str(ROOT/'scripts'/name))
def member(root,name):
    require(isinstance(name,str) and name and '\\' not in name and ':' not in name and not name.startswith('/') and
            all(x not in ('','.','..') for x in name.split('/')),'Relative kit member required')
    path=root.joinpath(*name.split('/'));require(path.resolve().is_relative_to(root.resolve()),'Kit member escaped root');return path
def regular(path,maximum=256*1024*1024):
    info=path.lstat();require(stat.S_ISREG(info.st_mode) and not getattr(info,'st_file_attributes',0)&0x400 and 0<=info.st_size<=maximum,'Bounded regular kit input required');return info


def verify(path,expected):
    path=Path(path).absolute();require(path.name=='kit-manifest.json' and re.fullmatch('[0-9a-f]{64}',expected),'Reviewed kit manifest identity required')
    root=path.parent;require(root==ROOT and ';' not in str(root) and not root.is_symlink() and not root.is_junction(),'Selected copied kit root required')
    regular(path,65536);require(sha(path)==expected,'Kit manifest differs');record=json.loads(path.read_bytes())
    require(record['schema']=='sl3.on-demand-engineering-kit.v1' and all(record[k] is False for k in
            ('seratoApplicationIncluded','derivedSeratoArchiveIncluded','installed','liveValidated')),'Uninstalled source-only compatibility kit required')
    inventory=root/'kit-inventory.json';regular(inventory,1024*1024);require(sha(inventory)==record['inventorySha256'],'Kit inventory differs')
    saved=json.loads(inventory.read_bytes());require(saved['schema']=='sl3.on-demand-kit-inventory.v1','Known inventory format required');files=saved['files']
    require(1<=len(files)<=2048 and len({n.casefold() for n in files})==len(files) and sum(x['bytes'] for x in files.values())<=768*1024*1024,'Bounded nonalias kit inventory required')
    for name,details in files.items():
        require(name.split('/')[0].casefold()!='analysis','Mutable state cannot be payload')
        item=member(root,name);require(regular(item).st_size==details['bytes'] and sha(item)==details['sha256'],'Kit file differs: '+name)
    actual=set()
    for child in root.iterdir():
        require(not child.is_symlink() and not child.is_junction(),'Kit redirect refused')
        if child.name=='analysis':require(child.is_dir(),'Analysis must be a directory');continue
        for item in ([child] if child.is_file() else child.rglob('*')):
            require(not item.is_symlink() and not item.is_junction(),'Kit redirect refused')
            if item.is_file():actual.add(item.relative_to(root).as_posix())
    require(actual==set(files)|{'kit-manifest.json','kit-inventory.json'},'Unexpected kit files')
    for name,key in [('runtime/python/runtime-manifest.json','pythonManifestSha256'),('runtime/powershell/runtime-manifest.json','powershellManifestSha256'),('native-package/bundle-manifest.json','nativeBundleSha256')]:
        require(files[name]['sha256']==record[key],'Component inventory binding differs')
    require(set(record['sourcePins'])==set(module('serato-on-demand-test.py')['source_names']()) and
            all(files[name]['sha256']==value for name,value in record['sourcePins'].items()),'Prepared source closure differs')
    runtime=module('prepare-embedded-python.py')['verify'](root/'runtime/python',record['pythonManifestSha256'])
    require(runtime.get('dependencyProfile')=='compatibility-setup' and runtime.get('instrumentationIncluded') is False and set(runtime['dependencies'])=={'pefile'},'Setup-only reviewed Python runtime required')
    module('prepare-portable-powershell.py')['verify'](root/'runtime/powershell',record['powershellManifestSha256'])
    builder=module('prepare-asio-deployment.py');manifest,payload=builder['capture_bundle'](root/'native-package',record['nativeBundleSha256'])
    require(manifest['schema']=='sl3.deployment-bundle.v2','Self-starting native package required');builder['inspect_portable_payloads'](manifest,payload)
    return record


def prepare(path,expected,application,write=False):
    record=verify(path,expected);stage=module('asio-install-journal.py')['stage_module']()
    require(not stage.elevated(),'Prepare engineering inputs as an ordinary user; no elevation is requested')
    application=Path(application).absolute();api=module('serato-on-demand-test.py')
    require(application==stage.known_folder('905e63b6-c1bf-494e-b29c-65b732d3d21a')/'Serato/Serato DJ Pro/Serato DJ Pro.exe' and
            sha(application)==api['APP_SHA'] and sha(application.with_name('userio_resources.bin'))==api['ORIGINAL_SHA'],'Reviewed original installed Serato build required')
    installation=stage.known_folder('905e63b6-c1bf-494e-b29c-65b732d3d21a')/'SL3 Rebuild/on-demand-diagnostic-v1'
    pointer=stage.known_folder('f1b32785-6fba-4fcf-9d55-7b8e7f157091')/'SL3Rebuild/on-demand-unused.txt'
    rebinder=module('rebind-asio-deployment.py')
    rebound=rebinder['rebind'](ROOT/'native-package',record['nativeBundleSha256'],installation=installation,pointer=pointer)
    result={'schema':'sl3.on-demand-kit-preparation.v1','planOnly':not write,'kitVerified':True,'bundleBinding':rebound,
            'installed':False,'elevationRequested':False,'seratoLaunched':False,'nativeDeviceAccess':False,'normalStartupValidated':False}
    if not write:return result
    analysis=ROOT/'analysis';require(not analysis.is_symlink() and not analysis.is_junction(),'Ordinary analysis state directory required');analysis.mkdir(exist_ok=True)
    identity=uuid.uuid4().hex
    rebound=rebinder['rebind'](ROOT/'native-package',record['nativeBundleSha256'],analysis/('sl3-deployment-rebound-'+identity),installation,pointer)
    python=ROOT/'runtime/python/python.exe';require(sha(python)==record['pythonExecutableSha256'],'Kit Python image differs')
    output=analysis/('sl3-on-demand-test-'+identity)
    command=[str(python),'-I','-B',str(ROOT/'scripts/prepare-serato-on-demand-test.py'),'--application',str(application),
        '--bundle',rebound['directory'],'--expected-bundle-sha256',rebound['bundleManifestSha256'],
        '--powershell',str(ROOT/'runtime/powershell'),'--expected-powershell-manifest-sha256',record['powershellManifestSha256'],
        '--expected-python-manifest-sha256',record['pythonManifestSha256'],'--output',str(output)]
    child=subprocess.run(command,capture_output=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
    require(child.returncode==0,'Local one-time preparation refused: '+child.stderr.decode('utf-8',errors='replace'))
    prepared=json.loads(child.stdout);verify(path,expected)
    common=['--experiment',prepared['experiment'],'--expected-experiment-sha256',prepared['experimentSha256']]
    entry=[str(python),'-I','-B',str(ROOT/'scripts/serato-on-demand-test.py')]
    return {**result,'bundleBinding':rebound,'preparedExperiment':prepared,'planArguments':entry+['plan']+common,
            'setupArguments':entry+['setup']+common,'restoreArguments':entry+['restore']+common,
            'setupAndRestoreRequireAlreadyElevatedProcess':True}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--expected-manifest-sha256',required=True)
    p.add_argument('--application',type=Path,required=True);p.add_argument('--prepare',action='store_true');a=p.parse_args()
    print(json.dumps(prepare(a.manifest,a.expected_manifest_sha256,a.application,a.prepare),indent=2))
