# Read-only controls on the retained device

An explicit control-owner API now connects the [recovered audio-control view](audio-controls-contract.md) to the isolated native worker. It inspects an already acquired, idle SL3 through the existing redirect. It does not acquire another device, activate audio, change rate or write a control setting. Positive native control inspection remains untested on the physical SL3. [Build/source evidence](evidence/held-controls-build.json).

## Transaction and native ownership

`inspect_audio_controls` in `src/core/audio_controls_query.hpp` takes an injected I/O owner. It sends exactly one zero-payload `0x32` getter, then accepts at most four 64-byte frames. Up to three recognized notifications may precede the matching ordinary-tag reply. Wrong commands/tags, short completions, an exhausted frame budget, cancellation or deadline failure terminate the operation. There is no retry.

The total control budget is 1,500 ms. Each write/read timeout is capped at 100/300 ms and the remaining overall time. A reply completed at or after the deadline is rejected even if well framed. Time regression is also a failure. Only a completed, validated reply yields the typed table; failed results cannot default to an all-zero control snapshot.

The native adapter accepts only the exact getter frame for output and uses the reviewed interrupt endpoints `0x01`/`0x81`. It reuses `Transfer::bounded`: transfer storage survives pending I/O, cancellation and up to the existing 2,000 ms drain allowance. Unproved retirement fail-stops the private worker while retaining storage. The control deadline excludes that drain and final helper close. Neither a watchdog nor a user-mode deadline guarantees that Windows immediately retires a blocked kernel operation. [Separate detachment limits](usbdk-detachment.md).

When a startup journal is requested, fixed `audio_controls`, `audio_controls_write` and `audio_controls_read` enter/return markers record the operation. They follow the existing reader's syntax. A failed operation can leave an unmatched enter marker; it is not promoted into successful completion.

## Worker and host contract

The current retained-device handshake is **version 3**. Version-1/2 hello data is rejected; the original getter was introduced in version 2. Explicit IPC command `0x305` takes an empty body and is admitted only after acquisition, in ready state, with retired audio I/O and no stream. Successful replies contain the validated held-device snapshot, all 22 control bytes and a received-frame count from 1 through 4. Wrong owner state, stream fault, malformed sizes or invalid counts are rejected. Ordinary status replies remain distinct from successful control replies.

A normal control failure releases the device and seals further inspection/start attempts in failed state. A stalled implementation is covered by the worker's independent heartbeat watchdog. Failure to prove cleanup remains a containment result.

`HostSession::inspect_controls()` returns an optional `device_session::ControlSample`, including `.audio` and `.received_frames`. It requires the already held retained session, healthy control channel and retired callbacks. It rejects temporary mode, running audio, callback reentry, blocked callbacks, pre-acquisition and final-closed state without performing a query. It never implicitly calls acquisition.

Before publishing the request, the host invalidates its previous idle I/O-retirement flag. A normal worker failure can supply new cleanup evidence; a stalled/unobserved operation leaves I/O/device retirement unproved even after its process exits. The host waits up to 5,000 ms for the reply and then follows its existing final-release/containment path on failure. No stale sample is returned or cached after a failed call.

The reply's rate field describes the preceding clock observation. This command does not query or set rate. The native reply matcher uses the original command/tag ABI, which has no transaction nonce; a newly issued getter is not a stronger freshness/authentication guarantee than that ABI supplies. Interleaved notifications count toward the budget; this snapshot API does not dispatch their callbacks or include their payloads in its result. No new overload, status-enable, timer or firmware request is introduced.

## Verification and remaining deployment

Injected tests cover every transfer and short-completion failure, cancellation before/after transfers, shrinking timeouts, a late valid reply, clock regression, notification flood and malformed replies. Protocol tests cover complete raw-table round trips, legacy versions, truncation/extra bytes, invalid counts and invalid owner/fault state.

Actual private-process simulated tests inspect before and after audio on one acquired device, reject wrong states/bodies and exercise reported failure, malformed observations and a stalled implementation. Actual host tests preserve the sample/count through IPC, reject callback/active/blocked cases and prove that an old idle snapshot cannot certify a hung control operation. The real native negative test uses an asserted absent helper and verifies that a controls command before acquisition performs no helper/device open.

Current Release and Debug pass **39/39** checks each; the explicitly SDK-free build passes **25/25**, and Python consistency/plan tests pass **71/71**. The new [controls diagnostic and trace runner](controls-probe.md) adds one native executable test and seven Python evidence/plan tests. These are software checks, with simulated positive control I/O. No hardware query or administrator prompt ran during this work. The new worker/protocol has a different identity from the earlier physical checkpoint; that checkpoint remains bound to its tested binaries and does not certify this new control path.

Subsequent shared USB/WPP trace preparation keeps the native implementation unchanged and refreshes full Release/Debug suites at 39/39 each, with the full Python suite at 80/80. Its controls-evidence suite is now ten tests and its runner pins ten dependencies. The optional `-WithUsbDkLifecycle` records both providers in one ETL; no live query or WPP emission/decoding result is claimed. [Current supervised command and validation limits](controls-probe.md#optional-shared-usbdk-lifecycle-trace).

The initial held-API binaries/manifests/logs are preserved locally at `artifacts/build/checkpoints/held-controls-20261030`; the current diagnostic checkpoint is `artifacts/build/checkpoints/controls-probe-20261030`. Historical capture/duplex records validate under their own worker hash and fail the new worker identity gate. No device-test process remains running.

Reproduce the metadata after the recorded builds:

```powershell
.venv/Scripts/python.exe scripts/export-held-controls-build.py
```

The bounded no-audio diagnostic and trace/security/recovery entry are now prepared. Next run that [supervised controls test](controls-probe.md) with the owner present. The existing audio-stream modes do not automatically invoke control inspection, and no control-panel UI or ASIO registration was deployed. Physical switch/routing behavior and calibration, sustained audio/timing, successive COM-object startup and current Serato/DVS remain incomplete. macOS remains deferred by the owner.

The current retained protocol is **version 3**, with a separately admitted [setting-selection worker/host command](control-selection-ipc.md) and capability flag. The read-only getter contract above remains; old version-2 workers/results are incompatible. Normal ASIO configuration grants no selection; an [explicit native target diagnostic](native-control-selection-diagnostic.md) can offer it only after a fresh getter and consumes one attempt. New runtime hashes require fresh physical read-only baseline evidence; no native setting write ran.
