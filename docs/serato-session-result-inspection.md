# Reading the complete session outcome

`scripts/inspect-serato-session-result.py` reads the saved reports from the prepared session plan. It starts no process, imports no device or instrumentation runtime, writes no files and does not inspect or modify current Windows state.

```powershell
python scripts/inspect-serato-session-result.py `
  --session-plan 'ABSOLUTE_SESSION_PLAN_PATH' `
  --expected-plan-sha256 'REVIEWED_SESSION_PLAN_SHA256'
```

The output separately reports observed startup/detachment, application shutdown, exit before any observer close request, broker success, worker/controller retirement, and protected-stage restoration. It checks the startup intent against the reviewed plan and requires the broker cleanup report to equal the underlying worker report with its controller-exit fact added. Report hashes identify exactly which saved files were inspected.

`cleanSessionReported` is true only when every required report is present and all checks pass. This is deliberately the stricter result for the next manual-close diagnostic: an observer-requested graceful close can report clean host shutdown while still failing the separate manual-exit check. Failed ownership is retained even when all retirement and restoration checks pass. Missing, malformed or contradictory reports cannot become a successful session.

These are saved-report checks, not independent observations of current device state or physical audio. Historical reports from the private route do not have all the new wrapper's records and must not be relabelled as a passing new-wrapper run. The prepared wrapper has not yet run live. A complete report also does not validate a permanent installation or sustained operation.

Six tests exercise consistent manual exit, safely retired ownership failure, forced termination, contradictory worker evidence, missing reports, mismatched plan/intent, observer-initiated close, and a Boolean masquerading as an exit code. They use temporary synthetic report files only.
