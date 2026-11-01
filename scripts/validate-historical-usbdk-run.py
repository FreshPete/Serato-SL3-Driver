"""Historical run validation separate from the frozen operational dependency."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('original_physical_validation', ROOT/'scripts/export-usbdk-physical-checkpoint.py')
_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)
require, read, digest = _original.require, _original.read, _original.digest
capture_validator, state_contract = _original.capture_validator, _original.state_contract


def validate_runner_inputs(record, runner_directory, source_commit=None):
    # Historical callers must explicitly select their immutable script archive.
    # Never fall back to today's scripts when an archived file is absent/wrong.
    # Missing files may be recovered only from an explicitly pinned Git commit.
    directory = Path(runner_directory).resolve()
    inputs = record['runnerInputs']
    require(isinstance(inputs, dict) and bool(inputs), 'Missing runner inputs')
    for name, expected in inputs.items():
        require(isinstance(name, str) and name and '/' not in name and '\\' not in name
                and ':' not in name and name not in ('.', '..'), 'Unsafe runner source name')
        path = (directory/name).resolve()
        require(path.parent == directory, 'Unsafe runner source path: '+name)
        if not path.exists() and source_commit is not None:
            # Older capsules omitted some validators. Recover only from the
            # caller's pinned commit, requiring exact recorded LF/CRLF bytes.
            require(len(source_commit) == 40 and all(c in '0123456789abcdef' for c in source_commit),
                    'Historical source commit must be a full object ID')
            result = subprocess.run(['git', 'show', source_commit+':scripts/'+name], cwd=ROOT,
                                    capture_output=True, timeout=10)
            require(result.returncode == 0, 'Historical runner unavailable: '+name)
            lf = result.stdout.replace(b'\r\n', b'\n')
            require(any(hashlib.sha256(raw).hexdigest() == expected.lower()
                        for raw in (result.stdout, lf, lf.replace(b'\n', b'\r\n'))),
                    'Historical runner source changed: '+name)
            continue
        require(path.is_file(), 'Runner source unavailable: '+name)
        require(digest(path).lower() == expected.lower(), 'Runner source changed: '+name)


def validate_run(folder, mode, native_sha, *, runner_directory=None, source_commit=None):
    record = read(folder/'run.json')
    require(record['mode'] == mode and record['completed'] is True and record['error'] is None, 'Incomplete scenario: '+folder.name)
    require(record['nativeExitCode'] == 0 and record['traceExitCode'] == 0 and record['traceCleanupConfirmed'] is True
            and record['recoveryConfirmed'] is True and record['driverChanges'] is False, 'Scenario/cleanup failed')
    require(record['nativeSha256'].lower() == native_sha.lower() and record['secureBootBefore'] is True
            and record['secureBootAfter'] is True, 'Build/security mismatch')
    validate_runner_inputs(record, ROOT/'scripts' if runner_directory is None else runner_directory, source_commit)
    before = read(folder/'before-state.json')
    after = read(folder/'after-state.json')
    require(digest(folder/'before-state.json').lower() == record['beforeStateSha256'].lower()
            and digest(folder/'after-state.json').lower() == record['afterStateSha256'].lower(), 'Snapshot hashes differ')
    require(before['secureBoot'] is True and after['secureBoot'] is True
            and state_contract(before) == state_contract(after), 'Recovery state changed')
    stats = capture_validator.trace_statistics(folder/'events.xml')
    require(stats == record['traceStats'] and stats['eventsLost'] == 0 and stats['buffersLost'] == 0, 'Trace statistics differ or are lossy')
    trace = read(folder/'trace/capture.json')
    require(stats['session'] == trace['session'], 'Trace session differs')
    require(capture_validator.utc(trace['startedUtc']) <= capture_validator.utc(record['nativeStartedUtc'])
            <= capture_validator.utc(record['nativeCompletedUtc']) <= capture_validator.utc(trace['stoppedUtc']), 'Native operation outside trace')
    etls = list((folder/'trace').glob('*.etl'))
    require(len(etls) == 1 and digest(etls[0]).lower() == record['etlSha256'].lower(), 'ETL binding differs')
    return record, {'runRecordSha256': digest(folder/'run.json'), 'beforeStateSha256': digest(folder/'before-state.json'),
                    'afterStateSha256': digest(folder/'after-state.json'), 'traceStats': stats,
                    'etlSha256': digest(etls[0]), 'secureBootBeforeAndAfter': True, 'recoveryConfirmed': True}
