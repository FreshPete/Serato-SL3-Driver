"""Prepare source-bound installer/broker configuration and launcher project offline."""
import argparse
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]


def render(record, manifest, expected, api):
    template = (ROOT/'src/installer/SessionLauncher.cs').read_text(encoding='utf-8')
    pins = {str(ROOT/name):value for name,value in record['sources'].items()}
    pins[str(manifest)] = expected
    pins[record['python']['path']] = record['python']['sha256']
    pins[record['application']['path']] = record['application']['sha256']
    replacements = {'__PYTHON__':json.dumps(record['python']['path']), '__CAPSULE__':json.dumps(str(manifest)),
                    '__CAPSULE_HASH__':json.dumps(expected), '__INSTALLER__':json.dumps(str(ROOT/'scripts/serato-session-installer.py')),
                    '__BROKER__':json.dumps(str(ROOT/'scripts/serato-session-broker.py')),
                    '__PINS__':',\n'.join('    { '+json.dumps(path)+', '+json.dumps(value)+' }' for path,value in sorted(pins.items()))}
    for key,value in replacements.items():
        api['require'](template.count(key) == 1,'Launcher template marker differs: '+key)
        template = template.replace(key,value)
    return template


def prepare(application,bundle,expected,output=None,capture=False):
    api = runpy.run_path(str(ROOT/'scripts/serato-session-capsule.py'))
    application,bundle = Path(application).absolute(),Path(bundle).absolute()
    api['require'](application.name == 'Serato DJ Pro.exe' and api['sha'](application) == api['APP_SHA'],
                   'Reviewed Serato application required')
    api['module']('prepare-asio-deployment.py','verify')(bundle,expected)
    plan = json.loads((bundle/'deployment-plan.json').read_bytes())
    api['module']('prepare-asio-deployment.py','require_session_locator')(plan)
    api['require'](plan['timingMode'] == 'unmeasured-diagnostic-44100-128','Reviewed diagnostic package required')
    python = Path(sys.executable).absolute()
    record = {'schema':'sl3.session-capsule.v1','projectRoot':str(ROOT),
              'python':{'path':str(python),'sha256':api['sha'](python)},
              'application':{'path':str(application),'sha256':api['APP_SHA']},
              'bundle':{'path':str(bundle),'sha256':expected},
              'permitPath':str(application.parent/'bundles'/api['PERMIT_NAME']),
              'sources':api['source_hashes'](),'brokerLimitMs':600000,'captureOutput':bool(capture)}
    if output is not None:
        output = Path(output).absolute()
        api['require'](output.parent.resolve() == (ROOT/'analysis').resolve() and
                       output.name.startswith('sl3-session-capsule-') and not output.exists() and not output.is_symlink(),
                       'Fresh analysis/sl3-session-capsule-* directory required')
        record['sessionDirectory'] = str(output)
        raw = api['encoded'](record)
        import hashlib
        identity = hashlib.sha256(raw).hexdigest()
        manifest = output/'session-capsule.json'
        source = render(record,manifest,identity,api)
        project = ('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
                   '<TargetFramework>net10.0</TargetFramework><AssemblyName>SL3_Rebuild_Development_x64</AssemblyName>'
                   '<RuntimeIdentifier>win-x64</RuntimeIdentifier><PublishSingleFile>true</PublishSingleFile>'
                   '<SelfContained>false</SelfContained><EnableCompressionInSingleFile>false</EnableCompressionInSingleFile>'
                   '<Deterministic>true</Deterministic></PropertyGroup></Project>\n')
        output.mkdir()
        for name,data in (('session-capsule.json',raw),('Program.cs',source.encode('utf-8')),('Installer.csproj',project.encode('utf-8'))):
            with (output/name).open('xb') as stream:stream.write(data)
        api['verify'](manifest,identity)
        return {'prepared':True,'capsule':str(manifest),'capsuleSha256':identity,'launcherProject':str(output/'Installer.csproj'),
                'applicationLaunched':False,'registryWritten':False,'deviceAccess':False,'liveValidated':False}
    return {'planOnly':True,'sourcesVerified':len(record['sources']),'bundleVerified':True,'filesWritten':False,
            'applicationLaunched':False,'registryWritten':False,'deviceAccess':False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--expected-bundle-sha256',required=True)
    parser.add_argument('--prepare',type=Path)
    parser.add_argument('--capture-output',action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare(args.app,args.bundle,args.expected_bundle_sha256,args.prepare,args.capture_output),indent=2))
