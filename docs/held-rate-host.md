# Retained rate selection: host API and native diagnostic adapter

The host now exposes `HostSession::select_rate(target)` for an already acquired, idle retained device. The operation is separate from production `IASIO::setSampleRate`, which still accepts only its observed rate. No new hardware test has run.

## Host outcome and clock lifetime

`RateSelectionReport` separates an attempted command, an unknown outcome, possible device effects, explicit pre-operation refusal and an optional correlated rate observation. A valid success updates the host's last observed rate from the verified target. A valid failed operation preserves the accepted readback, if present, and seals/closes the owner. A missing, snapshot-only or malformed operation result keeps possible-write uncertainty and clears the previous host clock to zero; process death alone cannot prove stalled native I/O retired.

An optional-command refusal keeps the idle session usable only after decoding an unchanged ready snapshot with retired I/O, retained device, no stream fault and the prior rate. It reports `rejected_before_operation`, with no rate outcome or possible setter effect. Other errors cannot use this path. There is no automatic retry, cached-rate fallback, acquisition or restoration write.

Rate requests are refused locally before acquisition, in temporary-device mode, after final close, during callback reentry, while running, while audio ownership is unretired, or while buffers remain prepared. Stopping a stream does not invalidate its buffer contract: buffers must be disposed before selecting another rate. A later start continues to require a fresh matching device getter. Measured ASIO timing remains a separate rate/buffer-specific requirement.

## Explicit native diagnostic

`WorkerSpec::diagnostic_rate_target` forwards one canonical `--rate-test-target 44100|48000` to an isolated native device worker. Construction requires a native retained session and an absolute diagnostic directory. It cannot be combined with an audio-control target. The worker additionally requires its fresh local fixed-drive startup journal. Default production configuration has no rate grant.

The native adapter consumes a noncopyable process-local target grant before any operation, accepts only its specified rate and cannot repeat the attempt. Even a no-op consumes it. The diagnostic host refuses audio starts and other selection targets; the native device separately refuses audio activation for the entire granted lease, including after consumption. The grant supplies configuration only: ready/idle admission, exclusive device ownership, bounded I/O and retirement still come from the existing worker/device contracts.

The adapter uses the existing bounded rate runner and native interrupt-transfer adapter on its **existing held redirect**. Acquisition's initial getter and the rate transaction's own fresh initial getter are separate requests; the transaction remains bounded to three writes/twelve received frames, with at most one setter. No second redirect is opened, no alternate is activated and no audio is submitted by rate selection. The existing 3,000 ms transaction, cancellation/drain containment, 5,500 ms worker watchdog and 6,000 ms host reply bounds remain.

Before native rate I/O, the adapter creates a fresh directory named `<startup-journal>.rate` and persists progress/possible-setter state through the existing v2 writer. Its final `rate.json` describes the operation **before final redirect release**, so `redirect_closed` remains false. The observation-only validator can check that record; the standalone successful-native validator must reject its incomplete cleanup claim. Final owner snapshots and the startup/USB trace must independently establish later retirement. Zero native status means no independently captured Win32 status, not proof that a failed operation succeeded.

## Verification boundaries and next test

Software tests use actual isolated simulated workers to cover both rate directions, verified no-op, host clock update, independent getter, buffer/stream/reentry refusals, single acquisition/release, explicit unsupported-command refusal, mismatching readback, possible setter effects after transfer failure, missing/malformed outcomes, worker watchdog exit and later redirect-close failure. Native target parsing/grant checks cover invalid/duplicate/conflicting input and single-use target consumption. An actual native executable accepts the granted handshake and quit **without acquisition or helper loading**, and refuses rate selection before acquisition.

The native positive adapter remains physically unrun. No UAC, physical acquisition, rate write, firmware operation, trust/binding modification, registration or security-policy change was performed. The simulated stream exercised after reverse selection is at 48 kHz; it is not evidence for physical or continuous 44.1 kHz audio.

Next work is a bounded, traced diagnostic launcher and validator for this held-rate path, including separate operation/cleanup evidence and current executable/runtime pins. The old Scope/image plan remains permanently disarmed. Production ASIO rate selection, measured analogue routing/latency, reliable host-lifetime reacquisition, current Serato admission and two-deck DVS remain unfinished. See [verification evidence](evidence/held-rate-host-20261101.json), [rate wire/worker dispatch](held-rate-selection.md) and [current Serato boundary](current-serato-integration-decision.md).
