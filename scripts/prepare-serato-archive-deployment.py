"""Prepare/verify a private attended archive-test bundle; never install or run Serato."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('archive_deployment', ROOT/'scripts/prepare-serato-sl3-archive.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
c = a.c
TARGET = Path('C:/Program Files/Serato/Serato DJ Pro/userio_resources.bin')
CORE = 'scripts/serato-archive-file-transaction.ps1'
TEMPLATE = 'scripts/serato-archive-deployment-template.ps1'


def encoded(value):
    return (json.dumps(value, indent=2)+'\n').encode()


def location(path):
    c.require(not path.is_symlink() and not path.is_junction(), 'Reparse bundle refused')
    path = path.absolute()
    c.require(path.parent.resolve() == (ROOT/'analysis').resolve() and
              re.fullmatch(r'sl3-archive-deployment-[A-Za-z0-9-]{1,64}', path.name), 'Direct analysis/sl3-archive-deployment-* bundle required')
    return path


def construct(candidate, archive_bundle):
    candidate = c.location(candidate)
    archive, manifest = a.prepare(candidate)
    original_bundle = a.location(archive_bundle)
    c.require(original_bundle.is_dir() and {p.name for p in original_bundle.iterdir()} == {a.ARCHIVE, 'archive-candidate.json'}, 'Exact reviewed archive bundle required')
    c.require(c.read(original_bundle/a.ARCHIVE) == archive and
              c.parsed(c.read(original_bundle/'archive-candidate.json')) == manifest, 'Reviewed archive bundle differs')
    c.require(c.digest(c.read(TARGET)) == manifest['originalArchiveSha256'], 'Installed archive is not the original')
    # Query original executable trust only; vendor executable is never loaded.
    command = "$s=Get-AuthenticodeSignature -LiteralPath 'C:\\Program Files\\Serato\\Serato DJ Pro\\Serato DJ Pro.exe'; [ordered]@{status=$s.Status.ToString();thumbprint=$(if($s.SignerCertificate){$s.SignerCertificate.Thumbprint}else{$null})}|ConvertTo-Json -Compress"
    result = subprocess.run(['pwsh', '-NoProfile', '-Command', command], capture_output=True, timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    signature = c.parsed(result.stdout)
    c.require(result.returncode == 0 and signature['status'] == 'Valid' and
              re.fullmatch('[0-9A-F]{40}', signature['thumbprint'] or ''), 'Original executable signature must verify')
    core = c.read(ROOT/CORE)
    template = c.read(ROOT/TEMPLATE).decode('utf-8-sig')
    sources = {p: c.digest(c.read(ROOT/p)) for p in [CORE, TEMPLATE, 'scripts/prepare-serato-archive-deployment.py']}
    plan = {'schema': 'sl3.attended-archive-deployment-plan.v1', 'status': 'prepared_not_executed',
            'descriptorBundle': candidate.relative_to(ROOT).as_posix(), 'archiveBundle': original_bundle.relative_to(ROOT).as_posix(),
            'target': str(TARGET), 'originalArchiveSha256': manifest['originalArchiveSha256'],
            'candidateArchiveSha256': manifest['archiveSha256'], 'originalApplicationSha256': manifest['sourceSha256']['artifacts/extracted/Serato DJ Pro 5.0.0/tree/PFiles64/Serato/Serato DJ Pro/Serato DJ Pro.exe'],
            'originalExecutableSignature': signature, 'sourceSha256': sources,
            'archiveManifestSha256': c.digest(c.read(original_bundle/'archive-candidate.json')),
            'sourceReadSetSha256': manifest['sourceSha256'],
            'replacement': 'Windows File.Replace; same-directory flushed staging and atomic original backup; metadata errors are not ignored',
            'rollback': 'Original backup staged, atomically restored and independently hashed; displaced candidate retained until explicit cleanup',
            'requiredCallerReview': ['Attended approval of this exact bundle and action', 'Serato closed, no concurrent installer/update or privileged writer',
                                   'Prepared ASIO profile/deployment and test scope remain separate prerequisites for audio',
                                   'Runtime archive integrity/parser acceptance and authorization behavior remain unverified'],
            'installExecuted': False, 'rollbackExecuted': False, 'protectedAclVerified': False,
            'runtimeArchiveAccepted': False, 'currentSeratoAdmissionVerified': False, 'twoDeckDvsVerified': False,
            'deviceAccess': False, 'applicationExecuted': False, 'securityPolicyModified': False,
            'authorizationModified': False, 'firmwareModified': False, 'deploymentApproved': False}
    plan_bytes = encoded(plan)
    values = {'TARGET': str(TARGET).replace("'", "''"), 'ORIGINAL_SHA': plan['originalArchiveSha256'],
              'CANDIDATE_SHA': plan['candidateArchiveSha256'], 'EXE_SHA': plan['originalApplicationSha256'],
              'SIGNER': signature['thumbprint'], 'CORE_SHA': c.digest(core), 'PLAN_SHA': c.digest(plan_bytes)}
    for name, value in values.items():
        token = '@@'+name+'@@'
        c.require(template.count(token) == 1, 'Template token differs: '+name)
        template = template.replace(token, value)
    c.require('@@' not in template, 'Unresolved wrapper token')
    files = {'candidate-userio_resources.bin': archive, 'serato-archive-file-transaction.ps1': core,
             'deployment-plan.json': plan_bytes, 'archive-test.ps1': template.encode()}
    files['provenance.json'] = encoded({'schema': 'sl3.archive-deployment-bundle.v1',
                                       'files': {name: c.digest(raw) for name, raw in files.items()},
                                       'vendorResourceArchiveForPrivateLocalTestOnly': True,
                                       'installExecuted': False, 'deploymentApproved': False})
    for path, sha in sources.items():
        c.require(c.digest(c.read(ROOT/path)) == sha, 'Deployment source changed during preparation')
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--descriptor', type=Path, default=Path('analysis/sl3-descriptor-candidate-20261102'))
    parser.add_argument('--archive', type=Path, default=Path('analysis/sl3-archive-candidate-20261102'))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare', type=Path)
    mode.add_argument('--validate', type=Path)
    args = parser.parse_args()
    path = location(args.prepare or args.validate) if args.prepare or args.validate else None
    if args.prepare:
        c.require(not path.exists() and path.parent.is_dir(), 'Fresh bundle required')
    files = construct(args.descriptor, args.archive)
    if args.prepare:
        path.mkdir()
        for name, raw in files.items():
            with (path/name).open('xb') as f:
                f.write(raw)
    elif args.validate:
        c.require(path.is_dir() and {p.name for p in path.iterdir()} == set(files), 'Exact deployment bundle files required')
        for name, raw in files.items():
            c.require(c.read(path/name) == raw, 'Deployment bundle differs: '+name)
    print(json.dumps({'status': 'prepared_not_executed', 'files': {p: c.digest(raw) for p, raw in files.items()},
                      'installExecuted': False, 'deploymentApproved': False, 'deviceAccess': False}, indent=2))


if __name__ == '__main__':
    main()
