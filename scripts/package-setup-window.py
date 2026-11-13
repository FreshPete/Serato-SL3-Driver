"""Package a verified portable setup window and its kit for private testing."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def package(build_path, expected, output):
    build_path,output = Path(build_path).absolute(),Path(output).absolute()
    require(sha(build_path)==expected,'Reviewed window build record required')
    build = json.loads(build_path.read_bytes())
    require(build['schema']=='sl3.setup-window-build.v1' and build['configuration']=='Release' and
            build['contractChecksPassed'] is True,'Verified Release setup window required')
    source_path = build_path.parent/'window-source.json'
    require(sha(source_path)==build['sourceManifestSha256'],'Reviewed window source manifest required')
    source = json.loads(source_path.read_bytes())
    layout = source.get('portableLayout')
    require(source['schema']=='sl3.setup-window-source.v1' and source['experimentSha256'] is None and
            isinstance(layout,dict),'Portable window build required')
    require(all(sha(ROOT/name)==digest for name,digest in source['sourcePins'].items()) and
            all(sha(source_path.parent/name)==digest for name,digest in source['generatedPins'].items()),'Window source changed')
    kit,entry = Path(layout['kit']),Path(layout['entry'])
    manifest_name = layout.get('manifestName', 'kit-manifest.json')
    require(manifest_name in ('kit-manifest.json','watcher-payload.json'),'Unknown portable setup inventory')
    kit_manifest = kit/manifest_name
    require(sha(kit_manifest)==source['kitManifestSha256'],'Reviewed setup kit required')
    manifest = json.loads(kit_manifest.read_bytes())
    files = {'kit/'+manifest_name:(kit_manifest,source['kitManifestSha256'])}
    if manifest_name == 'watcher-payload.json':
        runpy.run_path(str(ROOT/'scripts/setup-serato-native-watcher.py'))['read_payload'](kit,source['kitManifestSha256'])
        entries = manifest['files']
    else:
        inventory = kit/'kit-inventory.json'
        require(sha(inventory)==manifest['inventorySha256'],'Reviewed kit inventory required')
        entries = json.loads(inventory.read_bytes())['files']
        helper = 'scripts/prepare-on-demand-kit.py'
        require(sha(kit/helper)==entries[helper]['sha256'],'Reviewed kit verifier required')
        runpy.run_path(str(kit/helper))['verify'](kit_manifest,source['kitManifestSha256'])
        files['kit/kit-inventory.json'] = (inventory,manifest['inventorySha256'])
    files.update({'kit/'+name:(kit/name,row['sha256']) for name,row in entries.items()})
    window = build_path.parent/'build/Release/SL3_Compatibility_Setup.exe'
    files.update({'SL3_Compatibility_Setup.exe':(window,build['executableSha256']),
                  'SL3_Setup_Engineering.exe':(entry,source['nativeEntrySha256'])})
    watcher = layout.get('watcherAssets')
    if watcher is not None:
        require(set(watcher)=={'setup-notice-startup.ps1','watch-notice-startup.ps1','sl3-notice-startup-early.dll'},
                'Reviewed watcher inventory required')
        files.update({'watcher/'+name:(Path(asset['path']),asset['sha256']) for name,asset in watcher.items()})
    require(output.parent.resolve()==(ROOT/'artifacts/build').resolve() and output.suffix=='.zip' and not output.exists(),
            'Fresh ZIP below artifacts/build required')
    with tempfile.TemporaryDirectory(prefix='setup-zip-',dir=output.parent) as scratch:
        pending = Path(scratch)/output.name
        with zipfile.ZipFile(pending,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as archive:
            for name,(path,digest) in sorted(files.items()):
                raw = path.read_bytes()
                require(hashlib.sha256(raw).hexdigest()==digest,'Portable setup input changed: '+name)
                archive.writestr(name,raw)
        with zipfile.ZipFile(pending) as archive:
            require(len(archive.namelist())==len(files) and set(archive.namelist())==set(files),'Portable ZIP inventory differs')
            for name,(_,digest) in files.items():
                with archive.open(name) as stream:
                    require(hashlib.file_digest(stream,'sha256').hexdigest()==digest,'Portable ZIP bytes differ: '+name)
        pending.rename(output)
    return {'schema':'sl3.portable-setup-zip.v1','files':len(files),'archiveSha256':sha(output),
            'kitManifestSha256':source['kitManifestSha256'],'windowSha256':build['executableSha256'],
            'generatedSetupStateIncluded':False,'liveValidated':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window-build',type=Path,required=True)
    parser.add_argument('--expected-window-build-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(package(args.window_build,args.expected_window_build_sha256,args.output),indent=2))
