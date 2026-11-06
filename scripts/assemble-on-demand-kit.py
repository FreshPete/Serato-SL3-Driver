"""Assemble portable one-time setup engineering inputs; no application-derived archive is shipped."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import runpy
import shutil

ROOT=Path(__file__).resolve().parents[1]
def module(name):return runpy.run_path(str(ROOT/'scripts'/name))


def assemble(experiment,expected,python_runtime,python_expected,output=None):
    api=module('serato-on-demand-test.py');require,sha=api['require'],api['sha']
    with ExitStack() as held:
        record=api['verify'](Path(experiment).absolute(),expected,held)
        builder=module('prepare-asio-deployment.py');bundle=Path(record['bundle']['directory'])
        manifest,payload=builder['capture_bundle'](bundle,record['bundle']['sha256']);builder['verify_payloads'](manifest,payload)
        require(manifest['schema']=='sl3.deployment-bundle.v2','On-demand native package required')
        python_runtime=Path(python_runtime).absolute();runtime=module('prepare-embedded-python.py')['verify'](python_runtime,python_expected)
        require(runtime.get('dependencyProfile')=='compatibility-setup' and runtime.get('instrumentationIncluded') is False and set(runtime['dependencies'])=={'pefile'},'Setup-only reviewed Python runtime required')
        sources=set(api['source_names']())|{'scripts/assemble-on-demand-kit.py','scripts/prepare-on-demand-kit.py','scripts/prepare-on-demand-python.py','LICENSE'}
        files={name:(ROOT/name,sha(ROOT/name)) for name in sorted(sources)}
        for role,directory,expected_runtime in [('python',python_runtime,python_expected),
                ('powershell',Path(record['powershell']['directory']),record['powershell']['manifestSha256'])]:
            runtime=module('prepare-embedded-python.py' if role=='python' else 'prepare-portable-powershell.py')['verify'](directory,expected_runtime)
            for name,row in runtime['files'].items():files['runtime/'+role+'/'+name]=(directory/name,row['sha256'])
            files['runtime/'+role+'/runtime-manifest.json']=(directory/'runtime-manifest.json',expected_runtime)
        for name,row in manifest['files'].items():files['native-package/'+name]=(bundle/name,row['sha256'])
        files['native-package/bundle-manifest.json']=(bundle/'bundle-manifest.json',record['bundle']['sha256'])
        report={'schema':'sl3.on-demand-kit-assembly.v1','planOnly':output is None,'filesSelected':len(files),
            'derivedSeratoArchiveIncluded':False,'installed':False,'applicationLaunched':False,'nativeDeviceAccess':False}
        if output is None:return report
        output=Path(output).absolute();require(output.parent.resolve()==(ROOT/'artifacts/build').resolve() and output.name.startswith('sl3-on-demand-kit-') and not output.exists() and ';' not in str(output),'Fresh bounded engineering kit output required')
        output.mkdir();inventory={}
        for name,(path,expected_file) in sorted(files.items()):
            destination=output/name;destination.parent.mkdir(parents=True,exist_ok=True)
            with path.open('rb') as incoming,destination.open('xb') as outgoing:shutil.copyfileobj(incoming,outgoing,1024*1024)
            require(sha(destination)==expected_file,'Kit source changed while copying: '+name)
            inventory[name]={'bytes':destination.stat().st_size,'sha256':expected_file}
        encode=lambda value:json.dumps(value,sort_keys=True,indent=2)+'\n'
        (output/'kit-inventory.json').write_text(encode({'schema':'sl3.on-demand-kit-inventory.v1','files':inventory}),encoding='utf-8')
        saved={'schema':'sl3.on-demand-engineering-kit.v1','inventorySha256':sha(output/'kit-inventory.json'),
            'sourcePins':record['sources'],'pythonManifestSha256':python_expected,
            'pythonExecutableSha256':sha(python_runtime/'python.exe'),'powershellManifestSha256':record['powershell']['manifestSha256'],
            'nativeBundleSha256':record['bundle']['sha256'],'seratoApplicationIncluded':False,'derivedSeratoArchiveIncluded':False,
            'installed':False,'liveValidated':False}
        path=output/'kit-manifest.json';path.write_text(encode(saved),encoding='utf-8')
        return {**report,'prepared':True,'directory':str(output),'kitManifestSha256':sha(path)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',type=Path,required=True);p.add_argument('--expected-experiment-sha256',required=True);p.add_argument('--python-runtime',type=Path,required=True);p.add_argument('--expected-python-manifest-sha256',required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    print(json.dumps(assemble(a.experiment,a.expected_experiment_sha256,a.python_runtime,a.expected_python_manifest_sha256,a.output),indent=2))
