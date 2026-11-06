"""Export selected observations without copying paths, messages, events or audio."""
import argparse
import hashlib
import json
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
BOOL_FIELDS = {
    'readiness': ('readyForAttempt', 'deviceOpened', 'audioStarted'),
    'recovery': ('originalSetupClean', 'activeSessionObserved', 'brokerRetirementReported',
                 'previousSessionShutdownVerified', 'repairAttempted', 'deviceOpened'),
    'supervisor': ('asioStartObserved', 'stagedAsioVerified', 'tracerDetached',
                   'instrumentationManagerClosedBeforeViewing', 'supervisionCompleted'),
    'asio': ('sessionMetadataComplete', 'observedPairsComplete', 'moduleCallBudgetReached',
             'completionMarkerUsed', 'shutdownVerified', 'missingTerminalProvesBlockedCall',
             'sourceHostIdentityVerified', 'wholeHostSequenceVerified', 'seratoCaptureVerified'),
}
SCHEMAS = {'readiness': 'sl3.session-readiness.v1', 'recovery': 'sl3.session-recovery-check.v1',
           'supervisor': 'sl3.startup-supervisor-result.v1',
           'asio': ('sl3.asio-call-analysis.v1', 'sl3.asio-incomplete-call-analysis.v1')}
OPERATIONS = ('class_object', 'init', 'name', 'version', 'error_message', 'start', 'stop', 'channels',
              'latencies', 'buffer_size', 'can_rate', 'get_rate', 'set_rate', 'clocks', 'set_clock',
              'create_buffers', 'dispose_buffers', 'control_panel')
CHECKS = ('platform', 'application', 'filter', 'device', 'state', 'dependencies')
PROCESS_FIELDS = ('processStarted', 'processExited', 'observerForcedTermination', 'closeRequested',
                  'jobEmpty', 'instrumentationManagerClosed', 'ownershipUnproven')
END_REASONS = ('application_exited', 'manual_stop', 'viewing_limit', 'manual_stop_during_startup', 'failure')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'Duplicate JSON member')
        value[key] = item
    return value


def load(path):
    # Read one bounded snapshot; its digest binds exactly the bytes summarized.
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, 'Input exceeds report size bound')
    value = json.loads(raw, object_pairs_hook=unique_object,
                       parse_constant=lambda _: require(False, 'Non-finite JSON value'))
    require(type(value) is dict, 'Input must be a JSON object')
    return value, hashlib.sha256(raw).hexdigest()


def booleans(source, names):
    result = {}
    for name in names:
        if name in source:
            require(type(source[name]) is bool, 'Expected boolean observation: ' + name)
            result[name] = source[name]
    return result


def bounded_count(value, maximum=8192):
    require(type(value) is int and 0 <= value <= maximum, 'Invalid observation count')
    return value


def asio_summary(source):
    result = booleans(source, BOOL_FIELDS['asio'])
    for name in ('recordCount', 'pairedCalls', 'completedCalls', 'abandonedCalls'):
        if name in source:
            result[name] = bounded_count(source[name])
    for name in ('reportedEventsLost', 'reportedBuffersLost'):
        if name in source:
            result[name] = None if source[name] is None else bounded_count(source[name], 0xffffffff)
    for name in ('unterminatedBegins', 'orphanTerminals', 'callIdGaps'):
        if name in source:
            require(type(source[name]) is list, 'Expected observation list')
            result[name + 'Count'] = bounded_count(len(source[name]))
    if 'methods' in source:
        methods = source['methods']
        require(type(methods) is dict and all(name in OPERATIONS for name in methods), 'Unknown ASIO method')
        result['methods'] = {}
        for name, observation in methods.items():
            require(type(observation) is dict, 'Expected method observations')
            result['methods'][name] = {field: bounded_count(observation[field])
                                      for field in ('paired', 'abandoned', 'returnedErrors') if field in observation}
    # Only marker-free analysis supplies operation details for unmatched begins.
    # Keep operations/counts, never object/thread/call identities or raw rows.
    if 'unterminatedBeginDetails' in source:
        details = source['unterminatedBeginDetails']
        require(type(details) is list and len(details) <= 4096, 'Invalid unmatched begin details')
        operations = {}
        for row in details:
            require(type(row) is dict and row.get('operation') in OPERATIONS, 'Unknown unmatched operation')
            name = row['operation']
            operations[name] = operations.get(name, 0) + 1
        result['unterminatedOperations'] = operations
    return result


def summarize(kind, source):
    require(kind in SCHEMAS, 'Unsupported report kind')
    schemas = SCHEMAS[kind] if type(SCHEMAS[kind]) is tuple else (SCHEMAS[kind],)
    require(source.get('schema') in schemas, 'Unsupported report schema')
    if kind == 'asio':
        return asio_summary(source)
    result = booleans(source, BOOL_FIELDS[kind])
    if kind == 'readiness':
        rows = source.get('checks')
        require(type(rows) is list and len(rows) == len(CHECKS), 'Expected six prerequisite observations')
        checks = {}
        for row in rows:
            require(type(row) is dict and row.get('id') in CHECKS, 'Unknown prerequisite observation')
            name = row['id']
            require(name not in checks and row.get('status') in ('pass', 'blocked', 'unknown'),
                    'Invalid or duplicate prerequisite observation')
            checks[name] = row['status']
        result['checks'] = checks
        require(type(source.get('readyForAttempt')) is bool and
                source['readyForAttempt'] == all(item == 'pass' for item in checks.values()),
                'Readiness claim contradicts prerequisite observations')
    elif kind == 'recovery':
        # Free-form messages, owners, paths and issue descriptions never leave the source.
        if 'issues' in source:
            require(type(source['issues']) is list, 'Expected recovery issue list')
            result['issueCount'] = len(source['issues'])
    else:
        if 'endReason' in source:
            require(source['endReason'] in END_REASONS, 'Unknown supervisor end reason')
            result['endReason'] = source['endReason']
        for name in ('error', 'cleanupError'):
            if name in source:
                require(source[name] is None or type(source[name]) is str, 'Invalid error observation')
                result[name + 'Present'] = bool(source[name])
        if 'process' in source:
            process = source['process']
            require(type(process) is dict, 'Expected process observations')
            result['process'] = booleans(process, PROCESS_FIELDS)
            if 'exitCode' in process:
                code = process['exitCode']
                require(code is None or (type(code) is int and 0 <= code <= 0xffffffff), 'Invalid process exit code')
                result['process']['exitCode'] = code
            for name in ('detachError', 'jobCleanupError'):
                if name in process:
                    require(type(process[name]) is str, 'Invalid process error observation')
                    result['process'][name + 'Present'] = bool(process[name])
            for name in ('closeWindowObservation', 'closeTimeoutWindowObservation'):
                if name in process:
                    windows = process[name]
                    require(type(windows) is dict, 'Expected window-close observations')
                    selected = booleans(windows, ('postCloseRequested', 'enumerationSucceeded'))
                    for field in ('ownedTopLevelWindows', 'visibleWindows', 'enabledVisibleWindows',
                                  'closeMessagesPosted', 'closePostFailures'):
                        if field in windows:
                            selected[field] = bounded_count(windows[field], 0xffffffff)
                    if 'callbackError' in windows:
                        require(windows['callbackError'] is None or type(windows['callbackError']) is str,
                                'Invalid window callback error observation')
                        selected['callbackErrorPresent'] = bool(windows['callbackError'])
                    result['process'][name] = selected
    return result


def export(inputs):
    require(inputs and all(kind in SCHEMAS for kind in inputs), 'Select at least one supported report')
    observations = {}
    for kind, path in inputs.items():
        value, digest = load(path)
        observations[kind] = {'sourceSha256': digest, 'reported': summarize(kind, value)}
    return {'schema': 'sl3.support-summary.v1', 'observations': observations,
            'interpretation': 'Selected saved observations only; inputs are not authenticated. '
                              'Reports may describe different sessions or times. Clean setup does not prove clean application exit. '
                              'No physical audio or DVS validation is inferred.',
            'sourcePathsIncluded': False, 'rawMessagesIncluded': False, 'audioIncluded': False,
            'applicationStarted': False, 'deviceAccess': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for kind in SCHEMAS:
        parser.add_argument('--' + kind, type=Path)
    parser.add_argument('--output', type=Path, help='Fresh output file; existing files are never overwritten')
    args = parser.parse_args()
    result = export({kind: getattr(args, kind) for kind in SCHEMAS if getattr(args, kind) is not None})
    rendered = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(rendered)
    else:
        print(rendered, end='')
