"""Exercise opt-in metadata logging on the exact packaged DLL without configuration."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exercise(bundle, expected, diagnostic_manifest, diagnostic_sha, output):
    bundle = Path(bundle).absolute()
    deployment = runpy.run_path(str(ROOT / 'scripts/prepare-asio-deployment.py'))
    deployment['verify'](bundle, expected)
    diagnostic_manifest = Path(diagnostic_manifest).absolute()
    require(sha(diagnostic_manifest) == diagnostic_sha, 'Diagnostic manifest differs')
    diagnostic = json.loads(diagnostic_manifest.read_bytes())
    require(diagnostic['schema'] == 'sl3.asio-private-trace-build.v1' and
            diagnostic['configuration'] == 'Release', 'Reviewed Release diagnostic required')
    for name, identity in diagnostic['inputs'].items():
        source = ROOT / name
        require(not Path(name).is_absolute() and source.resolve().is_relative_to(ROOT) and
                sha(source) == identity, 'Diagnostic source differs: ' + name)
    tool = diagnostic_manifest.parent / 'Release/sl3_asio_private_trace.exe'
    require(sha(tool) == diagnostic['executableSha256'], 'Diagnostic executable differs')
    selected = json.loads((bundle / 'bundle-manifest.json').read_bytes())['files']['sl3_asio.dll']['sha256']
    require(sha(bundle / 'sl3_asio.dll') == selected, 'Packaged ASIO DLL differs')
    output = Path(output).absolute()
    require(output.parent.resolve() == (ROOT / 'analysis').resolve() and
            output.name.startswith('asio-owned-session-') and not output.exists(), 'Fresh local analysis output required')
    output.mkdir()
    isolated = output / 'isolated'; isolated.mkdir()
    with (isolated / 'sl3_asio.dll').open('xb') as stream:
        stream.write((bundle / 'sl3_asio.dll').read_bytes())
    validator = runpy.run_path(str(ROOT / 'scripts/validate-asio-private-trace.py'))
    cases = []
    for mode in ('--self-disabled', '--self-refused', '--self-capture'):
        directory = output / mode.removeprefix('--self-')
        child = subprocess.Popen([str(tool), mode, str(directory), str(isolated / 'sl3_asio.dll')],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        expired = False
        try:
            stdout, stderr = child.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            expired = True
            child.kill(); stdout, stderr = child.communicate(timeout=5)
        (output / (directory.name + '-stdout.txt')).write_bytes(stdout)
        (output / (directory.name + '-stderr.txt')).write_bytes(stderr)
        outcome = {'mode': mode, 'exitCode': child.returncode, 'timedOut': expired, 'childExited': child.poll() is not None}
        (output / (directory.name + '-process.json')).write_text(json.dumps(outcome, indent=2)+'\n', encoding='utf-8')
        require(not expired and child.returncode == 0, 'Owned trace fixture failed: ' + mode)
        if mode == '--self-capture':
            marker = json.loads((directory / 'session.json').read_bytes())
            validator['validate_owned_marker'](marker, child.pid)
            rows = [json.loads(line) for line in (directory / 'events.jsonl').read_bytes().splitlines()]
            summary = json.loads((directory / 'capture.json').read_bytes())
            verified = validator['validate_rows'](rows, summary, child.pid)
            outcome.update(decodedEvents=summary['decodedEvents'], completedCallPairs=verified['completePairs'],
                           loggerStopped=marker['complete'], dllUnloaded=summary['dllUnloaded'])
        else:
            fallback = json.loads((directory / 'fallback.json').read_bytes())
            require(fallback == {'schema':'sl3.asio-owned-fallback.v1','ordinaryResultsPreserved':True,
                'dllUnloaded':True,'traceDirectoryCreated':False,'deviceAccess':False,'seratoExecuted':False},
                'Exact unavailable fallback outcome required')
            outcome.update(dllUnloaded=True, traceDirectoryCreated=False)
        outcome['passed'] = True; cases.append(outcome)
    require(sha(isolated / 'sl3_asio.dll') == selected and sha(tool) == diagnostic['executableSha256'], 'Fixture input changed')
    files = {p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
    report = {'schema':'sl3.packaged-asio-owned-trace-tests.v1','nativeBundleSha256':expected,
        'asioDllSha256':selected,'diagnosticManifestSha256':diagnostic_sha,'diagnosticExecutableSha256':sha(tool),
        'cases':cases,'files':files,'configurationPresent':False,'applicationStarted':False,'deviceAccess':False,
        'registryWritten':False,'elevationRequested':False,'seratoShutdownValidated':False}
    (output / 'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--expected-bundle-sha256', required=True)
    parser.add_argument('--diagnostic-manifest', type=Path, required=True)
    parser.add_argument('--expected-diagnostic-manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(exercise(args.bundle,args.expected_bundle_sha256,args.diagnostic_manifest,
                             args.expected_diagnostic_manifest_sha256,args.output), indent=2))
