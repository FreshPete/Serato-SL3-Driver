"""Prepare a private no-shim normal-start setup/restore experiment; no installed writes or application launch."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
API = runpy.run_path(str(ROOT/'scripts/serato-on-demand-test.py'))
require, sha = API['require'], API['sha']


def prepare(application,bundle,bundle_sha,powershell,powershell_sha,python_sha,output):
    application,bundle,powershell,output = (Path(p).absolute() for p in (application,bundle,powershell,output))
    require(output.parent == ROOT/'analysis' and output.name.startswith('sl3-on-demand-test-') and not output.exists(),
            'Fresh direct analysis/sl3-on-demand-test-* output required')
    s = API['module']('asio-install-journal.py')['stage_module']()
    require(application == s.known_folder('905e63b6-c1bf-494e-b29c-65b732d3d21a')/'Serato/Serato DJ Pro/Serato DJ Pro.exe',
            'Reviewed original installation path required')
    API['module']('prepare-embedded-python.py')['verify'](Path(sys.executable).parent,python_sha)
    pins = {name:sha(ROOT/name) for name in API['source_names']()}
    native = API['Native'](bundle,bundle_sha)
    require(native.observe()['state'] == 'absent', 'New experiment requires absent native registration/stage')
    recipe = API['module']('prepare-serato-installed-phase-archive.py')
    candidate_output = ROOT/'analysis'/('sl3-archive-candidate-'+output.name.removeprefix('sl3-on-demand-test-'))
    require(not candidate_output.exists(), 'Fresh private archive preparation output required')
    report = recipe['prepare'](application,powershell,powershell_sha,candidate_output)
    command = "$s=Get-AuthenticodeSignature -LiteralPath '"+str(application).replace("'","''")+"'; [ordered]@{status=$s.Status.ToString();thumbprint=$(if($s.SignerCertificate){$s.SignerCertificate.Thumbprint}else{$null})}|ConvertTo-Json -Compress"
    signature_result = subprocess.run([str(powershell/'pwsh.exe'),'-NoProfile','-NonInteractive','-Command',command],
        capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    require(signature_result.returncode == 0, 'Original executable signature query failed')
    signature = json.loads(signature_result.stdout)
    require(signature['status'] == 'Valid' and isinstance(signature['thumbprint'],str) and len(signature['thumbprint']) == 40,
            'Original executable signature must verify')
    encode = lambda value:(json.dumps(value,indent=2)+'\n').encode('utf-8')
    core = (ROOT/'scripts/serato-archive-file-transaction.ps1').read_bytes()
    inner = {'schema':'sl3.on-demand-archive-plan.v1','target':str(application.with_name('userio_resources.bin')),
        'originalArchiveSha256':API['ORIGINAL_SHA'],'candidateArchiveSha256':API['CANDIDATE_SHA'],
        'originalApplicationSha256':API['APP_SHA'],'originalExecutableSignature':signature,'installed':False}
    raw_inner = encode(inner)
    template = (ROOT/'scripts/serato-archive-deployment-template.ps1').read_text(encoding='utf-8-sig')
    values = {'TARGET':inner['target'].replace("'","''"),'ORIGINAL_SHA':API['ORIGINAL_SHA'],
        'CANDIDATE_SHA':API['CANDIDATE_SHA'],'EXE_SHA':API['APP_SHA'],'SIGNER':signature['thumbprint'],
        'CORE_SHA':API['hashlib'].sha256(core).hexdigest(),'PLAN_SHA':API['hashlib'].sha256(raw_inner).hexdigest()}
    for name,value in values.items():
        token='@@'+name+'@@'; require(template.count(token) == 1,'Archive wrapper token changed'); template=template.replace(token,value)
    require('@@' not in template,'Unresolved archive token')
    files = {'archive/candidate-userio_resources.bin':(candidate_output/'userio_resources.bin').read_bytes(),
        'archive/serato-archive-file-transaction.ps1':core,'archive/deployment-plan.json':raw_inner,
        'archive/archive-test.ps1':template.encode('utf-8')}
    require(all(sha(ROOT/name)==value for name,value in pins.items()),'Experiment sources changed during preparation')
    require(sha(application)==API['APP_SHA'] and sha(application.with_name('userio_resources.bin'))==API['ORIGINAL_SHA'],
            'Original inputs changed')
    record = {'schema':'sl3.on-demand-normal-start-test.v1','projectRoot':str(ROOT),'application':str(application),
        'applicationSha256':API['APP_SHA'],'originalArchiveSha256':API['ORIGINAL_SHA'],'candidateArchiveSha256':API['CANDIDATE_SHA'],
        'bundle':{'directory':str(bundle),'sha256':bundle_sha},'powershell':{'directory':str(powershell),'manifestSha256':powershell_sha},
        'python':{'path':str(Path(sys.executable).absolute()),'sha256':sha(Path(sys.executable)),'manifestSha256':python_sha},'sources':pins,
        'assets':{name:API['hashlib'].sha256(raw).hexdigest() for name,raw in files.items()},'maximumOwnerLifetimeMs':600000,
        'applicationLaunched':False,'startupShimUsed':False,'installed':False,'nativeDeviceAccess':False,'combinedAtomicTransaction':False}
    (output/'archive').mkdir(parents=True)
    for name,raw in files.items():
        with (output/name).open('xb') as stream:stream.write(raw)
    path=output/'experiment.json'
    with path.open('xb') as stream:stream.write(encode(record))
    return {'prepared':True,'experiment':str(path),'experimentSha256':sha(path),'archivePreparation':report,
        'installed':False,'applicationLaunched':False,'deviceAccess':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('application','bundle','expected-bundle-sha256','powershell','expected-powershell-manifest-sha256','expected-python-manifest-sha256','output'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.application,args.bundle,args.expected_bundle_sha256,args.powershell,
        args.expected_powershell_manifest_sha256,args.expected_python_manifest_sha256,args.output),indent=2))
