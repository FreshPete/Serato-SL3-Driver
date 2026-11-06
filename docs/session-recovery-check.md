# Native read-only recovery check

**Later update:** an [explicit recovery command](session-recovery-command.md) now connects this check to the existing protected transaction. Its no-op/refusal paths are verified; elevated repair remains untested. The Check command itself stays read-only.

**Later update:** [protected session ownership](protected-session-ownership.md) adds a matching protected record prerequisite for dirty-state recovery and observes its stage process. New bindings pin 45 release sources and 33 plan sources; the counts below describe this earlier checkpoint.

Prepared kit and fresh-session records now include `recoveryCheckArguments`. The native launcher exposes:

```text
SL3_Rebuild_Development_x64.exe --check-recovery --session-plan ABSOLUTE_PLAN --expected-session-plan-sha256 REVIEWED_PLAN_SHA256 --powershell-directory ABSOLUTE_POWERSHELL_DIRECTORY
```

This inspects current state; it never stops a process, repairs files, changes registration, opens the SL3 or requests elevation. It is a prerequisite for a future simpler recovery flow, not an automatic recovery command. [Verification evidence](evidence/session-recovery-check-20261106.json)

## Integrity and observation

Before helper execution, the native entry pins its 44-source release closure, both complete private runtimes and the selected application. The PowerShell manifest identity comes from the compiled release rather than session-provided command text. Complete embedded-Python plans now pin 32 sources, including the recovery inspector and its readiness/runtime-verifier dependencies. New source-bound plans and a new private kit were prepared; earlier plans remain preserved.

The inspector verifies the complete selected plan and its scoped capsule/output directories. It reads the wrapper/stage/supervisor records and checks PID, creation time and process-image file identity using the existing query/synchronize-only process handles. Invalid owner fields, incomplete records, query errors and unknown owners cannot yield a clean result. A reused PID does not authorise control of its new process.

An active recorded owner or running Serato produces a blocked result without starting the resource-inspection child. Otherwise the selected PowerShell runtime is verified, and a hidden child with the caller's token runs the real protected-path and hash-based resource preflight. This includes archive witnesses and both installer copies that the simpler current-status check does not cover. Current file/registration state and reported broker retirement remain separate observations.

## Results

| Phase | Meaning |
| --- | --- |
| `clean` | Current original resources, absence of temporary files/registration and available ownership evidence agree. |
| `active_session` | Serato or a recorded session owner remains active. Close the session first. |
| `review_required` | Ownership, observations or resource identities are incomplete/conflicting. |
| `broker_retirement_required` | Recorded owners retired, but broker retirement is not established. |
| `recovery_required` | Interrupted state remains after the observed prerequisites; explicit recovery still needs review and its own checks. |

Exit code 0 means currently clean. Other classified states return 3; integrity/inspection failures can fail the command separately. Every result says `recoveryAuthorized=false`. It is a point-in-time observation and never substitutes for quiescence, broker/native-install journal validation or file checks at actual mutation time. It does not fully validate a native installation or unknown cached-launcher contents. Historical clean shutdown and present device readiness remain unverified, even when original files are clean.

## Verification

Six classification cases passed. Six actual native-entry cases used an owned, hidden ordinary PowerShell process: prepared clean state, active-owner refusal, stale identity without targeting the new process, malformed/noncanonical owner refusal, and retired-owner clean state. Input file contents stayed unchanged across each inspection; the owned fixture exited normally. The actual protected resource preflight passed on this host. No Serato, audio worker or device ran.

The copied-kit suite also exercises this entry and rejects a changed recovery helper before Python execution. Complete-session planning and preparation remain read-only; live protected recovery and a graphical recovery action are still unvalidated or unfinished.

This checkpoint passed 50 targeted cases: six classification, six actual native owned-process, five complete-plan, seventeen copied-kit, eight fresh-preparation and eight Stop regressions. A final native check reported the host's original setup clean, using an ordinary token and the real protected resource preflight.
