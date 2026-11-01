# Bounded rate-selection transaction

An original, transport-independent C++ transaction engine now prepares the SL3's known rate-change sequence. An injected runner and an explicit native diagnostic mode now connect it to bounded interrupt transfers. The production ASIO facade remains observed-rate-only; IPC/startup do not select rates. No physical rate write or other new device command has been executed.

## Original evidence

The pinned original kernel function `0x11a90` permits only 44,100 and 48,000 Hz, swaps the requested 16-bit rate into wire byte order, sends command `0x31`, consumes two acknowledgement bytes, then sends getter `0x30` with zero payload and compares the resulting two bytes with the requested rate. It updates its confirmed-rate field only after both a successful acknowledgement and matching readback. The acknowledgement bytes are not themselves interpreted as an echoed rate.

The [evidence exporter](../scripts/export-rate-selection-evidence.py) checks the exact kernel hash and instructions, including both commands, byte rotation, two-byte receive widths, readback comparison and confirmed-field store. [Generated evidence](evidence/rate-selection-build.json) pins those instructions and current source/build/log/test-binary hashes. This extends the [earlier clock/control analysis](clock-control-audio.md); it executes no vendor binary.

## Implemented behavior

`RateSelection` in `src/core/rate_selection.*` is a noncopyable, fixed-storage state machine. Only 44,100 and 48,000 are valid targets. Its owner takes each outgoing request once; no transport call occurs inside the engine.

1. Inspect current rate using the existing bounded getter. If it already matches, finish without a setter.
2. Otherwise prepare exactly one `0x31` frame with big-endian target bytes and a zero unused payload. Accept only the matching command/tag and two defined, opaque acknowledgement bytes.
3. Prepare a fresh `0x30` getter. Finish successfully only if its readback matches the target.

Each exchange permits at most four received frames, including defined asynchronous notifications, giving a maximum of three requests and twelve received frames. Wrong commands/tags, unsupported getter rates, short/oversized frames and exhausted notification budgets fail permanently. A reply received before request ownership fails the transaction. Duplicate requests are not issued and terminal state cannot be revived by late replies or abort.

The returned `Event` describes an individual control frame. A well-formed reply can still fail target comparison; callers must require `phase() == RatePhase::complete` and inspect `verified_rate_hz()` for transaction success. Acknowledgement or reply framing alone is insufficient.

Taking the setter marks the device as **possibly changed**, before the caller can claim submission success. Cancellation, timeout, malformed acknowledgement or mismatched readback retains that flag and produces no verified rate. There is no automatic retry or rollback write. A successful readback also retains write history; it proves a device-reported selection, not measured oscillator frequency or working audio.

This adds a pre-inspection/no-op path to the original sequence. It also stops immediately after a failed acknowledgement instead of issuing another query as the original kernel does. These are explicit transaction policies, not claims of identical vendor recovery behavior.

## Validation and limits

All 28 native tests pass in Release and Debug; all 20 SDK-free tests pass with an explicitly nonexistent SDK path. Tests exercise both directions, no-op selection, exact wire bytes, opaque acknowledgement values, three notifications before every valid reply, duplicate-request prevention, invalid targets, cancellation at all six nonterminal boundaries, malformed exchanges at all three waiting stages, mismatched readback and immutable terminal state. The engine's runtime caller is the new diagnostic runner.

Runner tests inject transfer failure, short completion and cancellation at every one of the maximum fifteen operations. They also cover deadline exhaustion on the final reply, shrinking timeouts, expired budgets, backwards time, malformed acknowledgement, wrong supported readback and a notification flood. A well-framed late reply cannot become verified success. No fake test calls a USB helper.

Both real executables reject thirteen malformed/mixed/missing argument cases with exit 2. A separate test first confirms `OpenService` error 1060, then checks the valid diagnostic invocation with an intentionally nonexistent helper path. Both builds reject the absent service before helper loading, redirect or transfer. If the service exists or its absence cannot be proved, that test is skipped. This negative test is not driver admission or physical I/O evidence.

To reproduce evidence after builds:

```powershell
.venv/Scripts/python.exe scripts/test-rate-diagnostic-cli.py
.venv/Scripts/python.exe scripts/export-rate-selection-evidence.py
```

## Explicit native diagnostic boundary

`sl3_usbdk --select-rate 44100|48000 --helper FILE --output NEW_DIRECTORY` is a mutually exclusive diagnostic mode. It requires an explicit target, helper path and fresh result directory. Existing helper/service-image/unique-device/descriptor fixture gates run before redirect. It takes a fresh redirect and never activates audio alternates or submits isochronous data. No installer, security change, reset, automatic retry or rollback is added.

The runner imposes a three-second total control budget and clamps each write/read to the remaining budget and 100/300 ms respectively. The native adapter also deducts preparation/progress-writing time before submission. Individual request cancellation/draining retains storage for up to the existing two-second drain allowance; unproved retirement fail-stops the private diagnostic process with storage retained. The overall process has the existing twenty-second watchdog. These are separate budgets; the three-second control limit is not a promise that all cleanup completes within three seconds.

`rate.json` is flushed before each transfer and conservatively records possible rate change before a setter may leave the process. Final reporting separates verified rate, possible effects, transfer retirement and redirect closure. An unexpected outer failure preserves the last progress record instead of replacing uncertainty with zero. Closing the redirect does not restore the prior rate. The helper has no active-alt getter, so fresh default alternates are an API assumption already present in the transport, not measured readback.

The transaction class still cannot establish external ownership/retirement by itself. The native diagnostic's pending-I/O/cancel/drain behavior has not been tested against the actual helper/device. The first live transport experiment remains capture-first without rate writes. Keep Serato/audio clients closed for eventual exclusive diagnostic ownership.

A later explicit rate test needs a fresh baseline, traced setter/readback, uncertainty-preserving failure report and a separately justified restoration policy. It must not become automatic startup/recovery or a streaming rate change. Only after physical selection, transport timing and a matching timing profile are validated can the ASIO rate contract be extended. Current Serato descriptor/handshake integration and physical DVS remain independent work.

## Supervised trace workflow prepared

The plan-by-default wrapper now accepts `-Mode Rate -TargetRate 44100|48000`. This prints the exact native arguments without loading a helper, opening USB or creating a result directory. For example:

```powershell
pwsh -NoProfile -File scripts/test-usbdk-traced.ps1 -Mode Rate -TargetRate 48000 -ResultDirectory tests/results/local/rate-reviewed-plan
```

Live execution additionally requires `-Run`, an already elevated owner-present terminal, Secure Boot before/after, the unchanged already-running UsbDk service, source/binary preflight, one SL3 in the baseline and a `-ValidatedCaptureRun` from the same native build. It never requests elevation or installs drivers. The existing trace session must be live before native launch. The first test remains descriptor-only, then bounded input capture; this mode cannot substitute for those steps.

The wrapper records launch/exit times, target, native progress hash, last known possible effect and I/O retirement separately. Failed/timed-out children preserve their progress; missing or malformed records leave effects unknown. Native success must pass the strict native-record validator before the wrapper can clear its unknown-effect flag. Full evidence validation additionally requires consistent no-loss trace identity/window and ETL hash, native operation timestamps within that window, prior same-build capture validation and unchanged selected driver/security/application snapshot contracts.

Successful changed-rate results require three control writes and three to twelve reads; no-op results require one write and one to four reads. Acknowledgement-only, mismatched readback, nonterminal progress, failed cleanup, unexpected audio/alternate changes and contradictory effect flags are rejected. `rate-validation.json` is a consistency result, not an execution authorization or hardware attestation. Trace-header checks do not correlate USB payloads; inspect those events separately before claiming an observed wire sequence. Driver/security recovery does not restore the old sample rate. No automatic restoration write or retry is added.

All 36 Python tests pass, including seven new synthetic evidence tests and two plan-mode tests. Plans cover all existing modes and both rate targets, reject invalid/missing targets and create no output. Synthetic tests exercise changed/no-op records, failure/uncertainty/cleanup, count/type confusion, wrong identities/prerequisites, modified files/recovery contracts, trace loss/session/ETL mutation and time bounds. Existing native build hashes remain current; native tests were not repeated for this Python/PowerShell-only change. [Prepared workflow evidence](evidence/rate-trace-preparation.json) records those limits.

Validate a future completed run read-only with:

```powershell
.venv/Scripts/python.exe scripts/validate-usbdk-rate.py PATH_TO_RUN --expected-target 48000 --expected-native-sha256 SHA256_FROM_PREFLIGHT
```

Only plan modes and synthetic validation ran during preparation. Live trace orchestration, native pending transfers and physical rate selection remain untested.
