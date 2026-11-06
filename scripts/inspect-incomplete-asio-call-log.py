"""Inspect recoverable ASIO records without a completion marker; never infer shutdown success."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('asio_call_analysis', ROOT / 'scripts/analyse-asio-call-log.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
v = a.v


def analyze(rows, pid):
    result = a.analyze_rows(rows, pid)
    pending = set(result['unterminatedBegins'])
    details = [{'call':row['payload']['call'], 'operation':a.NAMES[row['payload']['op']],
                'object':row['payload']['object'], 'thread':row['tid']}
               for row in rows if row['payload']['phase'] == 'begin' and row['payload']['call'] in pending]
    result.update(schema='sl3.asio-incomplete-call-analysis.v1',
        scope='Recoverable own-provider records only; session completion and host identity unverified',
        completionMarkerUsed=False, sessionMetadataComplete=False, sessionStopStatus=None,
        reportedEventsLost=None, reportedBuffersLost=None, shutdownVerified=False,
        matchingEventsObserved=bool(rows), unterminatedBeginDetails=details,
        missingTerminalProvesBlockedCall=False)
    return result


def inspect(etl, pid, folder, configuration='Release'):
    v.integer(pid, 1, 2**32-1)
    v.require(configuration in ('Release','Debug'), 'Reviewed decoder configuration required')
    etl, folder = Path(etl).absolute(), Path(folder).absolute()
    v.require(not folder.exists() and not folder.is_symlink() and not folder.is_junction() and folder.parent.is_dir(),
              'Fresh output directory required')
    manifest = ROOT / f'artifacts/build/asio-trace-decoder/decoder-build-{configuration}.json'
    build = v.parse(v.bounded(manifest, 1024*1024))
    v.require(build['schema'] == 'sl3.asio-etl-decoder-build.v1' and build['configuration'] == configuration,
              'Known decoder build required')
    def verify_build():
        for name, expected in build['inputs'].items():
            v.require(a.sha(ROOT / name) == expected, 'Decoder source drift')
        v.require(a.sha(exe) == build['executableSha256'] and a.sha(manifest) == manifest_sha, 'Decoder build drift')
    exe = manifest.parent / configuration / 'sl3_asio_decode_trace.exe'
    manifest_sha = a.sha(manifest); verify_build()
    sources = {name:a.sha(ROOT / name) for name in ('scripts/inspect-incomplete-asio-call-log.py',
              'scripts/analyse-asio-call-log.py', 'scripts/validate-asio-private-trace.py')}
    original_sha = a.sha(etl)
    folder.mkdir(); output = folder / 'events.jsonl'
    child = subprocess.Popen([str(exe), '--decode', str(etl), str(output), str(pid)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    expired = False
    try:
        stdout, stderr = child.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        expired = True
        child.kill(); stdout, stderr = child.communicate(timeout=5)
    (folder / 'decoder-stdout.json').write_bytes(stdout)
    (folder / 'decoder-stderr.txt').write_bytes(stderr)
    run = {'schema':'sl3.asio-incomplete-decoder-run.v1', 'inputSha256':original_sha, 'expectedPid':pid,
           'decoderSha256':a.sha(exe), 'buildManifestSha256':manifest_sha, 'sourceSha256':sources,
           'decoderExitCode':child.returncode, 'timedOut':expired, 'childExited':child.poll() is not None,
           'completionMarkerUsed':False, 'traceControllerStarted':False, 'deviceAccess':False, 'seratoExecuted':False}
    journal = folder / 'decoder-run.json'
    journal.write_text(json.dumps(run, indent=2)+'\n', encoding='utf-8')
    v.require(not expired and child.returncode == 0 and run['childExited'], 'Decoder did not finish successfully; partial outputs preserved')
    verify_build()
    v.require(a.sha(etl) == original_sha and all(a.sha(ROOT / name) == identity for name,identity in sources.items()),
              'Input evidence or analyzer changed')
    envelope = v.parse(stdout)
    v.require(envelope == {'schema':'sl3.asio-etl-decode.v1', 'pid':pid,
        'decodedEvents':envelope.get('decodedEvents'), 'readerReportedLosses':0,
        'traceControllerStarted':False, 'deviceAccess':False, 'seratoExecuted':False} and
        all(type(envelope[key]) is bool for key in ('traceControllerStarted','deviceAccess','seratoExecuted')),
        'Exact decoder scope required')
    v.integer(envelope['pid'],pid,pid); v.integer(envelope['decodedEvents'],0,8192)
    v.integer(envelope['readerReportedLosses'],0,0)
    raw = v.bounded(output, 8*1024*1024) if output.stat().st_size else b''
    rows = [v.parse(line) for line in raw.splitlines()]
    v.require(len(rows) == envelope['decodedEvents'], 'Decoded count differs')
    result = analyze(rows, pid)
    result.update(actualEtwCaptureDecoded=True, readerReportedLosses=0,
                  provenance={'etlSha256':original_sha, 'decodedJsonlSha256':hashlib.sha256(raw).hexdigest(),
                              'decoderRunSha256':a.sha(journal)})
    (folder / 'analysis.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--etl', type=Path, required=True)
    parser.add_argument('--expected-pid', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--configuration', choices=['Release','Debug'], default='Release')
    args = parser.parse_args()
    result = inspect(args.etl, args.expected_pid, args.output, args.configuration)
    print(json.dumps({key:value for key,value in result.items() if key not in ('pairs','methods')}, indent=2))
