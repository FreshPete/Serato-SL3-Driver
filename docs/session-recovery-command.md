# Explicit session recovery command

Prepared kit and fresh-session records now include `recoveryArguments` alongside the read-only `recoveryCheckArguments`.

```text
SL3_Rebuild_Development_x64.exe --recover-session --session-plan ABSOLUTE_PLAN --expected-session-plan-sha256 REVIEWED_PLAN_SHA256 --powershell-directory ABSOLUTE_POWERSHELL_DIRECTORY
```

This is a packaging backend, not yet a graphical recovery button or a publicly released installer. [Verification evidence](evidence/session-recovery-command-20261106.json)

## Behaviour

The compiled launcher pins the selected plan, its 46-source release closure, application and both private runtimes before running the ordinary-user gate. Complete plans pin 34 sources. The gate uses the existing recovery inspector, including protected resource witnesses, scoped ownership, process lifetime checks and broker retirement evidence.

* A currently clean setup returns zero without elevation or changes. Its report says `noChangesNeeded=true` and `recoveryCompleted=false`; this does not certify historical shutdown.
* Active sessions, unknown or conflicting ownership, missing broker retirement and incomplete evidence return a refusal. There is no process termination or automatic broker stop.
* Only a recognised interrupted session with a matching protected ownership record and observed retired owners/broker can request elevation. Internal gate code 10 means a transaction is required, not that recovery succeeded.

The native caller launches the pinned PowerShell transaction with `-Mode Recover`, retaining the original input/runtime leases. That transaction independently rechecks quiescence, scope and file identities before mutation, and preserves unknown state. A cancelled approval or failing transaction remains a failure. After a successful elevated process exit, the launcher runs the ordinary-user recovery inspector again; command success requires an observed clean setup. A failed postcheck is preserved even if the child reported success.

The privileged transaction is not force-terminated on an observer timer. This avoids treating an unknown commit outcome as a completed rollback. Recovery remains explicit: normal status/check operations never initiate it.

## Verification and limits

Eighteen handoff-policy cases passed. Six actual owned-process cases each exercised both native Check and Recover: clean, live owner, stale process identity, malformed owner, noncanonical owner and retired owner. The fixture exited normally, input files stayed unchanged and all Recover calls took the no-op/refusal route.

The relocated kit passed nineteen native entry cases with an empty PATH, including recovery no-op and rejection of a changed recovery gate before Python execution. Eight fresh-preparation cases passed with checks for the emitted recovery arguments. Eight native argument round trips passed. A direct command on this host also reported clean state without elevation, repair or device access.

No UAC prompt, Serato startup, device open or protected repair transaction ran during this checkpoint. The positive dirty-state handoff has policy coverage only; the native elevation/repair/postcheck sequence still needs an attended integration test. The audio binaries are unchanged. Live startup with the new protected ownership protocol, clean post-playback shutdown, audible output, longer reliability and another Windows account/PC remain release gates.
