# Explicit stop requests for a selected session

The native launcher now exposes a stop command for a verified live session. Session and kit preparation records include its argument vector alongside Plan and Start. The stop route was exercised through the compiled native entry with a real ordinary-token PowerShell runner and a Frida-owned headless Python child. The fixture exited normally with an empty job and no forced termination. No Serato, audio driver or SL3 was started. [Control-channel and regression evidence](evidence/session-stop-channel-20261106.json)

This supplies a way to end the next attended test before its viewing limit. It does **not** resolve or validate Serato's post-playback shutdown behavior.

## Request and ownership contract

`scripts/serato-session-stop.py` defaults to a read-only stop Plan. It verifies the complete selected session plan, its capsule, preparation and native package. A request requires the selected supervisor output and matching intent, no completed supervisor/final result, and both live owners: the ordinary PowerShell wrapper recorded in `session-run.lock` and the Python supervisor recorded in its intent.

Owner checks retain query/synchronize-only process handles, match creation FILETIMEs, and compare the running image's file identity with the selected interpreter/runtime image. No process is terminated or selected for control by executable name. Parent-directory leases and read-only intent handles prevent path replacement during publication. An exited owner, stale creation time, different image, mismatched intent or completed result is refused. Existing results and unknown state are preserved.

Explicit request writes a unique pending record, flushes it, then renames it within the selected supervisor directory to `stop.txt`. On Windows that rename is atomic and refuses an existing target. Failed publication preserves the pending record for diagnosis. A matching existing request is idempotent; another session's record is refused. The record binds the capsule hash, exact supervisor-intent hash and supervisor identity.

The native developer entry uses the existing full-session argument shape:

```text
SL3_Rebuild_Development_x64.exe --stop-session --session-plan ABSOLUTE_SESSION_PLAN --expected-session-plan-sha256 REVIEWED_SESSION_PLAN_SHA256 --powershell-directory ABSOLUTE_POWERSHELL_DIRECTORY
```

It runs the fixed Python stop dispatcher without elevation after the normal release source/runtime checks. The updated launcher pins 41 source/license/evidence files; complete plans pin 27 sources with the embedded runtime. No stop command runs the installer, opens USB, changes registration or directly removes any staged file.

## Supervisor behavior

The supervisor intent now records its capsule hash and live process identity. Its stop callback validates the typed record, so a partially written/plain legacy marker is not accepted as a matching request. Atomic publication avoids observing an incomplete JSON request.

Requests are polled while waiting for startup events as well as during manual interaction. A request during startup produces `manual_stop_during_startup`, runs owned-process cleanup and does not claim a completed audio session. It does not prove no asynchronous device work had occurred before observation. A request after the startup tracer is fully detached produces `manual_stop`; cleanup follows the existing path. The existing application-close wait and forced-termination fallback remain in place, with forced exit still reported as unsuccessful. Diagnostic lifetime and hard bounds are unchanged.

The request report deliberately says `shutdownConfirmed=false`. Only subsequent supervisor, broker and final rollback results can establish what happened. A Stop request can therefore succeed while Serato later hangs, shows a dialog or requires the existing fallback. The graphical close handler and real device retirement still need an attended run; no graceful Serato shutdown is inferred from this work.

## Verification

Eight stop-channel cases passed: read-only live-owner verification, stale owner creation refusal, different runner file identity refusal, foreign intent refusal, completed-result preservation, atomic request observed by the owned-child supervisor, idempotent repeat and foreign-capsule record refusal. The final run issued the request through the actual compiled native Stop entry. The Frida runtime was real, but startup events were synthetic and the child was this project's Python interpreter. A fixture-specific cooperative marker retired the headless child; the test did not exercise a Serato window's `WM_CLOSE` handler. The fixture PowerShell runner exited normally afterward.

Fourteen supervisor cases passed, including early cancellation and normal/forced owned-process distinction. Four complete-plan and six result cases passed. Thirteen native kit, eleven capsule entry and eight Windows argument cases also passed: 64 targeted checks. The native audio binaries were unchanged and the private runtime inventory passed. Fixture records remain private and explicitly marked; they are not a real installed session. The assembled kit remains uninstalled with no session state.

Earlier plain stop markers and source-bound plans are historical. Fresh complete plans and a newly packed native installer resource were prepared for this source change. The next attended test must verify actual kit startup, the Stop command before the viewing limit, application exit/dialog handling, broker I/O retirement, rollback and immediate reopen. Physical output, timing, longer reliability, another account/PC and the simple launch/recovery interface remain unfinished.
