"""Actual child failure-record checks; refuses elevation and never requests UAC."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists() and args.output.parent.is_dir()
    spec = importlib.util.spec_from_file_location('batch', ROOT/'scripts/logging-batch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    token = module.source_runner().own_token()
    assert token['queried'] is True and token['elevated'] is False, 'Run this test only under the ordinary token'
    plan = module.validate(args.plan)
    launcher = ROOT/'scripts/start-logging-batch.ps1'
    directory = args.plan.resolve().parent
    outcomes, artifacts = [], []

    def call(path, identity, digest):
        return subprocess.run([plan['runtime']['powershell'], '-NoProfile', '-File', str(launcher),
                               '-Plan', str(path.resolve()), '-Execute', '-ExpectedSha256', digest,
                               '-LaunchId', identity], capture_output=True, text=True, timeout=20)

    for name, digest, text in [('ordinary-token-refused', sha(args.plan), 'already elevated'),
                               ('changed-plan-refused', '0'*64, 'Plan changed before child execution')]:
        identity = uuid.uuid4().hex
        result = call(args.plan, identity, digest)
        log = directory/f'child-{identity}.log'
        exit_file = directory/f'child-{identity}-exit.json'
        value = json.loads(exit_file.read_text(encoding='utf-8-sig'))
        assert result.returncode == value['exitCode'] == 1 and text in log.read_text(encoding='utf-8')
        assert value['launchId'] == identity and value['executionMarkerPresent'] is False
        assert value['batchResultPresent'] is False and value['readinessAdmission'] is False
        outcomes.append({'name': name, 'passed': True})
        artifacts.extend([log, exit_file])
    original_hashes = {p: sha(p) for p in (log, exit_file)}
    result = call(args.plan, identity, digest)
    assert result.returncode != 0 and all(sha(p) == digest for p, digest in original_hashes.items())
    outcomes.append({'name': 'completed-attempt-not-overwritten', 'passed': True})
    with tempfile.TemporaryDirectory(prefix='sl3-batch-foreign-') as folder:
        foreign = Path(folder)/'batch.json'
        foreign.write_bytes(args.plan.read_bytes())
        result = call(foreign, uuid.uuid4().hex, sha(foreign))
        assert result.returncode != 0 and 'Unexpected child output location' in result.stderr
        assert len(list(Path(folder).iterdir())) == 1
    outcomes.append({'name': 'foreign-output-location-refused', 'passed': True})
    before = set(directory.iterdir())
    result = call(args.plan, 'invalid-id', sha(args.plan))
    assert result.returncode != 0 and 'Invalid internal execution role' in result.stderr
    assert set(directory.iterdir()) == before
    outcomes.append({'name': 'invalid-launch-identity-refused', 'passed': True})
    assert not (directory/'execution-started.json').exists()
    for job in plan['jobs']:
        assert not Path(job['contextDirectory']).exists() and not Path(job['captureRoot']).exists()
    report = {'scope': 'Actual ordinary-token PowerShell child failures; no elevation, source lifecycle or device access',
              'casesPassed': len(outcomes), 'cases': outcomes, 'ownToken': token,
              'planSha256': sha(args.plan), 'launcherSha256': sha(launcher), 'testSourceSha256': sha(Path(__file__)),
              'executionMarkerCreated': False, 'sourceContextsCreated': False,
              'artifacts': {str(p.relative_to(ROOT)): sha(p) for p in artifacts}}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print('Five actual child failure-record checks passed; no UAC or trace started')


if __name__ == '__main__':
    main()
