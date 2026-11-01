# Preserve rate readback through failed verification

The bounded rate-selection transaction now retains the **actual accepted verification getter** even when it differs from the requested target. Previously that path reported `readback_mismatch` with verified rate zero but discarded the returned supported rate. For example, a request for 48,000 followed by a valid getter of 44,100 now preserves `readback_rate_hz: 44100` while `verified_rate_hz` stays zero and the operation fails.

The transaction separately records whether a matching, complete setter acknowledgement was accepted. Those two opaque acknowledgement bytes are still not treated as an echoed rate or proof of selection. A no-op, where the initial getter already matches, has no setter acknowledgement and no second getter; its readback field remains zero rather than fabricating another observation. Zero means **no accepted verification getter**, not a measured zero-Hz clock.

The injected runner exports that readback and acknowledgement state plus a setter-attempt count. The native diagnostic writes schema `sl3.rate-diagnostic.v2`. It saves its setter-attempt count before a setter may be submitted and cross-checks final runner/adapter accounting. An attempt is conservative possible effect, not proof that USB submission or completion occurred. Terminal errors/aborts retain their observation history. Wrong framing, late replies, cancellation and expired deadlines do not become accepted readback evidence.

## Validation boundaries

`validate-usbdk-rate.py --native-record FILE` still requires a successful operation and confirmed native cleanup. Version-two records additionally require coherent observation types, request/read bounds, acknowledgement/readback ordering and changed/no-op outcomes. Historical version-one records remain readable under their original checks but cannot claim the new fields.

`--observation-record FILE` checks a completed version-two observation, including failure or incomplete cleanup, without qualifying the experiment. Its output deliberately uses `validObservation`, not the successful-test `valid` field. It separates `operationVerified`, `cleanupConfirmed` and `rateRestorationVerified: false`. An acknowledged mismatch can therefore be retained consistently without passing native or full trace validation. The operation's clock result and final redirect retirement remain separate facts.

No retry, restoration write, alternate activation, audio operation, deadline relaxation, new IPC command or ASIO rate setter is added. The production ASIO facade still accepts only its observed rate. The existing standalone diagnostic opens a fresh redirect; clock selection on the same retained ASIO connection remains to be implemented and physically validated before it can solve the requested session-lifetime requirement.

## Verification and next test plans

Native transaction tests cover accepted/no-op/mismatching getters, opaque acknowledgement separation, terminal-history immutability and the existing exhaustive transfer/short-reply/cancellation fault boundaries. Python checks keep failed observations separate from successful native results, reject missing/inconsistent fields and test the observation-only CLI with synthetic records. Positive native version-two output on the physical SL3 has not been collected. No actual rate command, USB acquisition, UAC prompt, installation, registration, firmware or security-policy change ran for this update.

The first Release build failed on a field mistakenly called as a method in a new test. That test typo was corrected; the failed compile log is preserved separately from successful verification. The earlier [physical 44.1→48 kHz trial](first-physical-usbdk-tests.md) belongs to its archived worker and version-one record. It is not a physical pass for this rebuilt worker or the new fields.

Because native worker inputs changed, the preceding prepared Scope/image plan at `analysis/logging-batch-scope-image-ready-20261101` was **disarmed without execution**. Explicit no-execution markers consume both its combined collector and logging batch, and validation refuses it. It must never be rearmed. Its original source/plan evidence remains in the previous checkpoint. A later attended test needs a fresh plan bound to the rebuilt worker and runtime.

Fresh test results and source/binary identities are in [verification evidence](evidence/rate-observations-20261101.json). Current-build physical streaming, reliable acquisition across host lifetimes, measured analogue routing/latency, deployed ASIO and current Serato/two-deck DVS remain unfinished. See [rate transaction](rate-selection.md), [combined Scope capture](scope-image-capture.md) and [current integration boundary](current-serato-integration-decision.md).
