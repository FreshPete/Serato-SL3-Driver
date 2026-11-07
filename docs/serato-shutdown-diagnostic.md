# Serato shutdown after the two-deck test

## Timing of the looped playback retest

The close instruction was sent at 11:25:28.368 UTC. Windows recorded exit of the supervisor's exact Serato process 188.016 seconds later, and the supervisor identifies that exit as forced at its viewing limit. The owner's normal-close confirmation reached the chat 126.909 seconds after the process exit. These timestamps identify the instruction, process exit and receipt of the confirmation. The time of any manual window-close action remains unknown. [Bound timeline](evidence/looped-playback-shutdown-timeline-20261107.json)

The broker reported `client_control_abandoned` in its running phase. The controller and worker journals place redirect close and helper unload within the controller's shutdown tick. The final broker report verifies I/O retirement, device release, worker exit and an empty job. The saved trace had already detached after ASIO start and contains no ASIO stop or dispose calls for this run. The failure therefore identifies an abandoned running connection and the verified cleanup that followed. The cause of the delayed application exit remains open. [Looped playback and rollback](evidence/pointer-cleanup-live-retest-20261106.json)

The [offline exporter](../scripts/export-looped-playback-shutdown.py) binds the exact host and broker reports, both journals and a timing-only interaction receipt. It uses the Windows exit FILETIME for the application timestamp and keeps the separate host-monotonic and worker/controller tick clocks in their original domains. Two regenerations matched, and substituting the unwrapped broker result was refused. The interaction text and source records remain private.

For the next playback retest, arrange the manual-close point before the run and use the observer's actual process exit to verify it. A chat reply alone cannot establish when the window closed.

## Earlier shutdown observations

A second attended startup/manual-close cycle passed without a requested power-cycle between successful sessions. Both application exits were code 0 without observer close or forced termination, and both broker outcomes were successful with no ownership failure. This still does not reproduce the older shutdown failure after two-deck playback. [Second cycle evidence](evidence/serato-reopen-success-20261106.json)

**6 November 2026 update:** the assembled temporary wrapper has now passed an attended manual-close test after USB recovery. Serato exited with code 0 before any observer close request, and the new broker reported `ownerFailureCode=none` and a successful requested stop, with complete retirement and rollback. Playback stayed stopped. This establishes one clean startup/shutdown with the smaller fully detached tracer; it does not reproduce or definitively explain the older two-deck failure, or prove shutdown after sustained playback. [Successful session evidence](evidence/assembled-session-success-20261106.json)

The attended two-deck Phase test established owner-reported tracking and a five-second software output recording. At cleanup, the broker reported `successful=false`, `reason=owner_failure`, while its final device, stream and native error fields were zero. I/O retirement, device release, worker exit and empty job all verified. The original Serato resources were restored and the temporary driver removed. These are separate observations: safe release does not erase the failed ownership result. [Live result](evidence/phase-two-deck-session-20261105.json)

## What the old trace can establish

The saved process exit FILETIME is approximately 8,129.751 ms after the observer's `viewing_window_ended` event. The observer then posted window-close requests, waited eight seconds and, if still running, terminated its exact owned Serato process. This timing is consistent with the forced-close fallback being used. It is an inference: that observer version did not record the wait result, termination decision or application exit code. The data cannot distinguish a shutdown hang, an unanswered application dialog, or another reason for delayed exit.

The old broker's `owner_failure` is similarly too broad. The final typed worker snapshot describes device release, while the broker separately seals on an active client's disappearance or an unknown control outcome. Consequently, zero final device errors do not prove the ASIO client detached gracefully.

## Diagnostic change

`BrokerReport` now preserves the first typed ownership failure and the broker phase at that point. Later worker replies, clean release or repeated close cannot overwrite it. Causes distinguish worker-control failure, failed worker operation, admission/clock/start/stop failure, client exit during streaming, client/process observation failure, control abandonment and owner shutdown.

The controller adds `ownerFailureCode`, `ownerFailurePhase` and a connection diagnostic capped at 512 characters to its result. It uses the existing broker-pipe diagnostic channel. The success, containment, acquisition and cleanup rules are unchanged. No callback tracing or audio-path file logging is added.

The private manual-session observer is also prepared to record its close request, wait result, any successful forced-termination request, and the application's exit code. This runs after interaction without reattaching instrumentation. The revised observer passed a syntax check, but its new records have not been collected from a live session.

## Validation

The refreshed Release build passed all 71 native checks and all 26 deployment checks. A direct process-death test verifies that `client_exited_running` and the original running phase survive subsequent release and repeated close. Normal dormant closure retains `none`. The actual controller lifecycle checks verify no invented failure on ordinary stops and a typed cause on destructive client release.

The simulated blocked-client case recorded `client_control_abandoned`, phase `running`, and `Complete broker pipe operation: 109`, while still proving device and process retirement. This validates the new diagnostic path. Its worker also reported a synthetic stream fault, so it is not evidence of the cause of the real Serato session's shutdown failure.

A fresh private diagnostic bundle passed native-destination and direct-import checks. It is prepared and not installed. The previous working two-deck package and its raw evidence remain preserved. [Preparation evidence](evidence/shutdown-diagnostic-preparation-20261105.json)

## Next live check

Use the reviewed manual-only startup, detach the tracer, then stop playback and close Serato manually. Allow the owner to answer any application dialogs. The observer should detect process exit without needing its automatic close request. Inspect the new first-failure cause, connection diagnostic, application exit code and forced-termination flag alongside independent device-release evidence. Do not relabel an ownership failure as success merely because cleanup completes.

No further hardware run has been performed for this diagnostic change. Shutdown is not fixed yet. Physical audible output, independent turntable control, sustained operation and a permanent installation remain separate open requirements.
