"""Derive a setup-only runtime from verified bytes and the reviewed pefile wheel RECORD."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parents[1]
def prepare(source,expected,output=None):
    api=runpy.run_path(str(ROOT/'scripts/prepare-embedded-python.py'));require=api['require'];source=Path(source).absolute()
    origin=api['verify'](source,expected)
    records=[n for n in origin['files'] if n.startswith('packages/pefile-') and n.endswith('.dist-info/RECORD')]
    require(len(records)==1,'One reviewed pefile wheel inventory required')
    name,record_sha,package=api['wheel_files'](source/records[0]);require(name=='pefile' and origin['dependencies']['pefile']['recordSha256']==record_sha,'Reviewed pefile dependency required')
    files={n:(source/n).read_bytes() for n in origin['files'] if '/' not in n};files.update(package)
    require(all(n in origin['files'] and hashlib.sha256(raw).hexdigest()==origin['files'][n]['sha256'] for n,raw in files.items()),'Derived bytes must match the verified origin')
    require(all(not n.startswith('packages/') or n in package for n in files),'Setup-only package closure required')
    manifest={'schema':'sl3.embedded-python.v1','sourceRuntimeManifestSha256':expected,'derivationToolSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'dependencies':{'pefile':{'recordSha256':record_sha}},'dependencyProfile':'compatibility-setup','instrumentationIncluded':False,
        'moduleSearch':origin['moduleSearch'],'files':{n:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for n,raw in sorted(files.items())},
        'systemPythonModified':False,'liveSeratoValidated':False}
    result={'schema':'sl3.setup-python-derivation.v1','planOnly':output is None,'filesVerified':len(files),'sourceFilesVerified':len(origin['files']),
        'expandedBytes':sum(map(len,files.values())),'dependencies':['pefile'],'instrumentationIncluded':False,'interpreterExecuted':False}
    if output is None:return result
    output=Path(output).absolute();require(output.parent.resolve()==(ROOT/'artifacts/build').resolve() and output.name.startswith('embedded-python-setup-') and not output.exists(),'Fresh setup-only runtime output required')
    output.mkdir()
    for n,raw in files.items():
        destination=output/n;destination.parent.mkdir(parents=True,exist_ok=True)
        with destination.open('xb') as stream:stream.write(raw)
    path=output/'runtime-manifest.json';path.write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8');expected_output=hashlib.sha256(path.read_bytes()).hexdigest();api['verify'](output,expected_output)
    return {**result,'prepared':True,'directory':str(output),'runtimeManifestSha256':expected_output}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--expected-source-manifest-sha256',required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    print(json.dumps(prepare(a.source,a.expected_source_manifest_sha256,a.output),indent=2))
