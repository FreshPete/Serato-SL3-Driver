"""Prepare one release-bound launcher project; no installation or application launch."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = 'src/installer/PortableSessionLauncher.cs'
BUILDER = 'scripts/prepare-portable-session-launcher.py'


def prepare(output=None):
    api = runpy.run_path(str(ROOT/'scripts/serato-session-capsule.py'))
    pins = {**api['source_hashes'](), TEMPLATE:api['sha'](ROOT/TEMPLATE), BUILDER:api['sha'](ROOT/BUILDER)}
    python_sha = api['sha'](Path(sys.executable))
    record = {'schema':'sl3.portable-launcher-release.v1','sourcePins':pins,'pythonSha256':python_sha,
              'applicationSha256':api['APP_SHA'],'runtime':'net10.0 framework-dependent win-x64',
              'sessionBoundAtBuildTime':False,'liveValidated':False}
    template = (ROOT/TEMPLATE).read_text(encoding='utf-8')
    replacements = {'__PYTHON_SHA__':json.dumps(python_sha), '__APPLICATION_SHA__':json.dumps(api['APP_SHA']),
                    '__SOURCE_PINS__':',\n'.join('    { '+json.dumps(name)+', '+json.dumps(value)+' }' for name,value in sorted(pins.items()))}
    for marker,value in replacements.items():
        api['require'](template.count(marker)==1,'Portable launcher marker differs')
        template=template.replace(marker,value)
    if output is None:
        return {**record,'planOnly':True,'filesWritten':False,'sourceCount':len(pins)}
    output=Path(output).absolute()
    api['require'](output.parent.resolve()==(ROOT/'artifacts/build').resolve() and
                   output.name.startswith('portable-session-launcher-') and not output.exists(),
                   'Fresh artifacts/build/portable-session-launcher-* directory required')
    project=('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
             '<TargetFramework>net10.0</TargetFramework><AssemblyName>SL3_Rebuild_Development_x64</AssemblyName>'
             '<RuntimeIdentifier>win-x64</RuntimeIdentifier><PublishSingleFile>true</PublishSingleFile>'
             '<SelfContained>false</SelfContained><EnableCompressionInSingleFile>false</EnableCompressionInSingleFile>'
             '<Deterministic>true</Deterministic></PropertyGroup></Project>\n')
    output.mkdir()
    for name,data in (('Program.cs',template),('Launcher.csproj',project),('release.json',json.dumps(record,sort_keys=True,indent=2)+'\n')):
        with (output/name).open('x',encoding='utf-8',newline='\n') as stream:stream.write(data)
    return {'prepared':True,'directory':str(output),'releaseSha256':hashlib.sha256((output/'release.json').read_bytes()).hexdigest(),
            'sourceCount':len(pins),'sessionBoundAtBuildTime':False,'deviceAccess':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.prepare),indent=2))
