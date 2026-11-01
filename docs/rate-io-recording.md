# Preserve raw rate-control I/O separately from acceptance

**Later checkpoint:** [raw v2 parsing, replay and required host/trace gates](rate-io-replay.md) are now implemented. V2 adds the exact transaction timing origin missing from v1; the emission-only results below retain their checkpoint scope. No positive native recording has been collected.

The native bounded rate adapter now creates a fresh `rate-io.jsonl` next to `rate.json`. It records each rate transaction's request intent, retired adapter return and the bounded runner's separate decision. This covers the transaction's initial getter, optional setter/acknowledgement and verification getter. Acquisition's earlier standalone getter remains covered by the existing startup journal, not this new recording.

## What is retained

A write-through, create-new header identifies the requested target and worker PID. Before any submission, a `begin` record preserves the exact 64-byte OUT frame or an explicit null IN frame, sequence, requested timeout and adapter start tick. This is intent, not proof of USB submission. A stalled worker can leave only this prefix.

An `end` record retains the adapter's returned byte count and actual available IN prefix (at most the allocated 64 bytes), success/failure, API attempted/accepted/terminal facts, captured Win32 completion error, USBD status and submission/completion UTC strings. These API facts do not attest bus traffic. Failed and short reads are copied before native transfer storage is destroyed; their bytes cannot become accepted clock evidence merely because they were retained. An empty read is an empty string, while a not-yet-read input is null.

The core runner separately classifies each returned attempt as write-retired, notification, reply, exchange failure, cancellation, deadline or transfer failure. It checks cancellation/deadline before accepting a frame. A supported but late 48 kHz getter can therefore remain in the raw recording while accepted readback stays zero. A valid mismatching getter is a `reply` at the exchange level but still fails requested-rate verification in the summary.

The decision callback copies into a fixed fifteen-entry buffer and performs no file/device I/O. Decisions are appended only after the bounded transaction returns, before its final summary is persisted. Raw begin/end writes occur inside the native adapter's existing timeout accounting; they can exhaust a budget rather than extend a later USB wait. The enclosing watchdog still bounds recording and cleanup. There are at most fifteen attempts, thirty begin/end rows, fifteen decision rows and one header. Recording failure contains the isolated process; it cannot continue with unrecorded control writes.

No request, retry, rate target, notification allowance, transfer timeout, three-second control budget, setter count, audio operation, firmware operation or restoration behavior was added. The summary remains v2 with additive `rate_io_schema` and `rate_io_file` references.

## Validation boundaries

Native software tests cover every existing transfer/short/cancel boundary, notification/reply separation, opaque acknowledgement errors, exact setter bytes, mismatching readback, late returned data and time consumed before a subsequent exchange. Filesystem-only writer tests check append ordering, raw-versus-decision records, short byte counts, input absence, create-new/no-overwrite behavior and an explicitly incomplete prefix. No physical USB is accessed.

The first Release compile exposed a Windows `min` macro collision in the new self-contained header. Its call is now protected from macro expansion; the failed log is retained separately from successful builds.

**Remaining:** schema parsing, replay against the accepted summary and a required recording gate in the host/shared-trace validators still need implementation. Existing qualification does not claim to replay or qualify this file, and its pass scope has not expanded. USB/WPP payload/timing correlation remains separate. No positive native recording has been collected; source, binaries and software checks are identified in [checkpoint evidence](evidence/rate-io-recording-20261101.json).

Native inputs changed again. Old Scope/image and test-created rate plans remain disarmed; a future attended test needs a fresh current-build plan. Production ASIO rate selection, measured physical audio/latency and current Serato/DVS remain unfinished. No UAC, physical acquisition, binding/trust/registration, firmware or security-policy change ran for this checkpoint.
