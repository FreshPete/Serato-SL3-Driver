"""Assemble/verify the complete temporary session plan without launching it."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import struct

import pefile

ROOT=Path(__file__).resolve().parents[1]
EXTRA_SOURCES=(
    'scripts/prepare-serato-session-plan.py','scripts/serato-session.ps1',
    'scripts/run-serato-startup-session.py','scripts/prepare-serato-startup-shim.py','scripts/serato-sl3-startup-shim.js',
    'scripts/retire-serato-session-cache.py','scripts/serato-installer-resource-transaction.ps1',
    'scripts/serato-archive-file-transaction.ps1','scripts/inspect-serato-resource-archive.py',
    'scripts/prepare-serato-sl3-installer-bundle.py',
    'scripts/serato-session-stop.py',
)


def require(value,message):
    if not value:raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def module(name):return runpy.run_path(str(ROOT/'scripts'/name))


def runtime_files(directory):
    package=directory/'frida'
    require(package.is_dir() and (package/'__init__.py').is_file(),'Existing reviewed Frida package directory required')
    files={str(path.absolute()):sha(path) for path in sorted(package.rglob('*'))
           if path.is_file() and path.suffix in ('.py','.pyd') and '__pycache__' not in path.parts}
    require(0<len(files)<=64 and any(path.endswith('.pyd') for path in files),'Expected Windows Frida runtime files')
    return files


def embedded_runtime_files(python):
    directory=Path(python).parent
    manifest=directory/'runtime-manifest.json'
    if not manifest.exists():return {}
    expected=sha(manifest)
    verified=module('prepare-embedded-python.py')['verify'](directory,expected)
    return {str(manifest):expected,**{str(directory/Path(name)):details['sha256'] for name,details in verified['files'].items()}}


def bind_installer(application,launcher,resource):
    require(launcher.name=='SL3_Rebuild_Development_x64.exe' and 64<=launcher.stat().st_size<=1024*1024,
            'Reviewed bounded launcher executable required')
    require(resource.name=='8c7758f23375cee18a9cf3be4a3acc15.bin' and 8<=resource.stat().st_size<=16*1024*1024,
            'Expected bounded installer resource')
    pe=pefile.PE(str(application),fast_load=True)
    try:seed=pe.get_data(0x2f2de98,16)
    finally:pe.close()
    require(len(seed)==16,'Pinned resource seed location differs')
    key=struct.unpack('<4I',bytes((((value^0xcf)>>(index&7))|((value^0xcf)<<((8-(index&7))&7)))&255
                                for index,value in enumerate(seed)))
    plain=module('inspect-serato-resource-archive.py')['decode_block'](resource.read_bytes(),key)
    expected=module('prepare-serato-sl3-installer-bundle.py')['resource_bundle'](launcher.name,launcher.read_bytes())
    require(plain==expected,'Installer resource does not contain the exact selected launcher')


def construct(capsule,capsule_sha,prepared,prepared_sha,archive,resource,launcher,frida):
    capsule,prepared,archive,resource,launcher,frida=(Path(path).absolute() for path in
        (capsule,prepared,archive,resource,launcher,frida))
    api=module('serato-session-capsule.py')
    record,plan,directory=api['verify'](capsule,capsule_sha)
    require(archive.stat().st_size<=16*1024*1024 and sha(archive)==module('run-serato-startup-session.py')['PHASE_RESOURCES'],
            'Reviewed Phase resource archive required')
    application=Path(record['application']['path'])
    bind_installer(application,launcher,resource)
    host=module('run-serato-startup-session.py')
    host['preflight'](prepared,prepared_sha,application,Path(record['bundle']['path']),record['bundle']['sha256'],sha(resource))
    embedded_files=embedded_runtime_files(record['python']['path'])
    sources={**record['sources'],**{name:sha(ROOT/name) for name in EXTRA_SOURCES}}
    if embedded_files:sources['scripts/prepare-embedded-python.py']=sha(ROOT/'scripts/prepare-embedded-python.py')
    tag=directory.name.removeprefix('sl3-session-capsule-')
    require(re.fullmatch('[A-Za-z0-9-]{1,80}',tag),'Bounded session directory tag required')
    return {'schema':'sl3.serato-session-plan.v1','projectRoot':str(ROOT),
        'capsule':{'path':str(capsule),'sha256':capsule_sha},
        'preparedShim':{'path':str(prepared),'sha256':prepared_sha},
        'python':record['python'],'application':record['application'],'nativeBundle':record['bundle'],
        'archiveSource':{'path':str(archive),'sha256':host['PHASE_RESOURCES']},'originalArchiveSha256':host['ORIGINAL_RESOURCES'],
        'installerResource':{'path':str(resource),'sha256':sha(resource)},
        'launcher':{'path':str(launcher),'sha256':sha(launcher)},'permitPath':record['permitPath'],
        'fridaDirectory':str(frida),'runtimeFiles':{**runtime_files(frida),**embedded_files},'sources':sources,
        'hostOutput':str(ROOT/'analysis'/('sl3-startup-session-'+tag)),
        'nativeInstallation':plan['installationDirectory'],'pointerPath':plan['pointerPath'],
        'registryEntries':plan['registryEntries'],'stageLimitSeconds':900,'permitLimitSeconds':300,
        'installerPayloadBound':True,'liveValidated':False}


def verify(path,expected):
    path=Path(path).absolute()
    require(path.stat().st_size<=65536 and sha(path)==expected,'Session plan identity differs')
    saved=json.loads(path.read_bytes())
    require(saved['schema']=='sl3.serato-session-plan.v1','Unsupported session plan')
    capsule=Path(saved['capsule']['path'])
    require(path.parent==capsule.parent and re.fullmatch(r'session-plan[-A-Za-z0-9]*\.json',path.name),
            'Session plan must remain in its bound capsule directory')
    actual=construct(capsule,saved['capsule']['sha256'],saved['preparedShim']['path'],saved['preparedShim']['sha256'],
                     saved['archiveSource']['path'],saved['installerResource']['path'],saved['launcher']['path'],saved['fridaDirectory'])
    require(saved==actual,'Session inputs or sources changed')
    return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',type=Path)
    parser.add_argument('--expected-plan-sha256')
    parser.add_argument('--capsule',type=Path)
    parser.add_argument('--expected-capsule-sha256')
    parser.add_argument('--prepared',type=Path)
    parser.add_argument('--expected-preparation-sha256')
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--installer-resource',type=Path)
    parser.add_argument('--launcher',type=Path)
    parser.add_argument('--frida-directory',type=Path)
    parser.add_argument('--prepare',type=Path)
    args=parser.parse_args()
    if args.verify:
        require(args.expected_plan_sha256 is not None,'Expected session plan SHA-256 required')
        result=verify(args.verify,args.expected_plan_sha256)
        print(json.dumps({'planVerified':True,'sourcesVerified':len(result['sources']),
                          'installerPayloadBound':True,'processStarted':False,'registryWritten':False,'deviceAccess':False}))
    else:
        require(all(value is not None for value in (args.capsule,args.expected_capsule_sha256,args.prepared,
                args.expected_preparation_sha256,args.archive,args.installer_resource,args.launcher,args.frida_directory)),
                'Complete source-bound session inputs required')
        result=construct(args.capsule,args.expected_capsule_sha256,args.prepared,args.expected_preparation_sha256,
                         args.archive,args.installer_resource,args.launcher,args.frida_directory)
        if args.prepare:
            output=args.prepare.absolute()
            require(output.parent==args.capsule.absolute().parent and re.fullmatch(r'session-plan[-A-Za-z0-9]*\.json',output.name),
                    'New session-plan*.json in the capsule directory required')
            raw=(json.dumps(result,sort_keys=True,indent=2)+'\n').encode('utf-8')
            with output.open('xb') as stream:stream.write(raw)
            print(json.dumps({'prepared':True,'path':str(output),'sha256':hashlib.sha256(raw).hexdigest(),
                              'installerPayloadBound':True,'installed':False,'liveValidated':False}))
        else:
            print(json.dumps({'planOnly':True,'sourcesVerified':len(result['sources']),'filesWritten':False,
                              'installerPayloadBound':True,'processStarted':False,'deviceAccess':False}))
