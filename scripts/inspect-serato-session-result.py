"""Read saved temporary-session outcomes without starting or changing anything."""
import argparse
import hashlib
import json
from pathlib import Path


def read_record(path, expected_schema=None):
    data = path.read_bytes()
    if len(data) > 2_000_000:
        raise ValueError('Saved report exceeds inspection bound')
    record = json.loads(data)
    if not isinstance(record, dict) or (expected_schema and record.get('schema') != expected_schema):
        raise ValueError('Unsupported report: ' + path.name)
    return record, hashlib.sha256(data).hexdigest()


def inspect(plan_path, expected_sha):
    plan, actual_sha = read_record(plan_path, 'sl3.serato-session-plan.v1')
    if actual_sha != expected_sha:
        raise ValueError('Reviewed session plan differs')
    directory = Path(plan['capsule']['path']).parent
    host = Path(plan['hostOutput'])
    records = {}
    hashes = {}
    issues = []
    for name, path, schema in (
        ('host', host/'result.json', 'sl3.startup-supervisor-result.v1'),
        ('intent', host/'intent.json', 'sl3.startup-supervisor-intent.v1'),
        ('broker', directory/'broker-clean.json', None),
        ('worker', directory/'broker-session/result.json', 'sl3.broker-controller-result.v1'),
        ('stage', directory/'session-final.json', None),
    ):
        try:
            records[name], hashes[name] = read_record(path, schema)
        except (OSError, ValueError) as error:
            issues.append(name + ': ' + str(error))
    host_result = records.get('host', {})
    process = host_result.get('process', {})
    if not isinstance(process, dict):
        process = {}
    intent = records.get('intent', {})
    intent_bound = (intent.get('applicationSha256') == plan['application']['sha256'] and
                    intent.get('preparationSha256') == plan['preparedShim']['sha256'] and
                    intent.get('deploymentManifestSha256') == plan['nativeBundle']['sha256'])
    broker = records.get('broker', {})
    worker = records.get('worker', {})
    retirement = (bool(worker) and broker == {**worker, 'controllerExited': True} and
                  all(broker.get(key) is True for key in
                      ('controllerExited', 'processExited', 'jobEmpty', 'ioRetiredVerified', 'deviceReleasedVerified')))
    stage = records.get('stage', {})
    restoration = (stage.get('restored') is True and stage.get('registrationAbsent') is True and
                   stage.get('error') is None and stage.get('receiptState') == 'success')
    startup = (intent_bound and all(host_result.get(key) is True for key in
               ('asioStartObserved', 'stagedAsioVerified', 'tracerDetached')))
    host_clean = (host_result.get('supervisionCompleted') is True and host_result.get('error') is None and
                  not host_result.get('cleanupError') and not host_result.get('publicationError') and
                  process.get('processStarted') is True and process.get('processExited') is True and
                  process.get('jobEmpty') is True and process.get('observerForcedTermination') is False and
                  type(process.get('exitCode')) is int and process['exitCode'] == 0)
    manual_exit = (host_clean and host_result.get('endReason') == 'application_exited' and
                   process.get('closeRequested') is False)
    broker_success = (broker.get('successful') is True and broker.get('failed') is False and
                      broker.get('ownerFailureCode') == 'none')
    checks = {'intentMatchesReviewedPlan': intent_bound, 'startupAndDetachReported': startup,
              'hostShutdownReportedClean': host_clean, 'exitPrecededObserverClose': manual_exit,
              'workerAndControllerRetirementReported': retirement,
              'brokerSessionReportedSuccessful': broker_success, 'restorationReported': restoration}
    return {'schema': 'sl3.session-result-inspection.v1', 'planSha256': actual_sha,
            'reportSha256': hashes, 'checks': checks, 'missingOrInvalidReports': issues,
            'cleanSessionReported': not issues and all(checks.values()),
            'brokerFailure': {key: broker.get(key) for key in
                              ('reason', 'ownerFailureCode', 'ownerFailurePhase', 'connectionDiagnostic')},
            'savedReportsOnly': True, 'currentDeviceStateVerified': False,
            'physicalAudioVerified': False, 'permanentInstallationValidated': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-plan', type=Path, required=True)
    parser.add_argument('--expected-plan-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.session_plan, args.expected_plan_sha256), indent=2))
