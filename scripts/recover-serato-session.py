"""Gate an explicitly requested recovery; only the pinned native caller elevates."""
import argparse
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]


def decision(report):
    # Exit 10 is an internal handoff, not a successful recovery. The elevated
    # transaction rechecks ownership, quiescence and resource identities.
    if (report.get('schema') != 'sl3.session-recovery-check.v1' or
        report.get('ordinaryToken') is not True or
        any(report.get(name) is not False for name in
            ('repairAttempted', 'filesWritten', 'registryWritten', 'elevationRequested', 'deviceOpened'))):
        return 3
    if (report.get('phase') == 'clean' and report.get('originalSetupClean') is True and
        report.get('activeSessionObserved') is False and report.get('issues') == []):
        return 0
    if (report.get('phase') == 'recovery_required' and report.get('activeSessionObserved') is False and
        report.get('issues') == [] and report.get('brokerRetirementReported') is True and
        report.get('resourcePlan', {}).get('protectedSessionOwnerPresent') is True):
        return 10
    return 3


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-plan', type=Path, required=True)
    parser.add_argument('--expected-session-plan-sha256', required=True)
    parser.add_argument('--powershell-directory', type=Path, required=True)
    parser.add_argument('--expected-powershell-manifest-sha256', required=True)
    args = parser.parse_args()
    inspector = runpy.run_path(str(ROOT/'scripts/inspect-serato-session-recovery.py'))
    report = inspector['inspect'](args.session_plan, args.expected_session_plan_sha256,
                                  args.powershell_directory, args.expected_powershell_manifest_sha256)
    code = decision(report)
    print(json.dumps({'schema':'sl3.session-recovery-gate.v1', 'check':report,
        'elevatedTransactionRequired':code == 10, 'recoveryCompleted':False,
        'noChangesNeeded':code == 0}, indent=2))
    raise SystemExit(code)
