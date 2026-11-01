# Offline SL3 setting selection

Original implementation models sensitivity and through-state selection as an **inspect/write/read-back transaction**, with a transport-independent I/O policy and [protocol-v3 worker/host command](control-selection-ipc.md). The [native adapter](native-control-adapter.md) connects through an [explicit single-target diagnostic](native-control-selection-diagnostic.md), requiring a fresh baseline and journal. The [host probe and offline evidence validator](selection-host-probe.md) now preserve request, result and cleanup separately. Normal ASIO configuration stays read-only; no panel or physical setting write is present. [Original-byte/build evidence](evidence/audio-control-selection.json).

## Supported contract

| Setting | Logical group 0 / 1 / 2 table indexes | Accepted byte values |
| --- | --- | --- |
| Sensitivity | 3 / 9 / 15 | Original UI codes 0–15 |
| Through state | 8 / 14 / 20 | 0 or 1 |

These are logical control-table groups, not established physical jack/deck order. The [original UI consumers](audio-controls-contract.md) establish these indexes and offered values. Phono switches and other table bytes have no write API here. A sensitivity code is not measured gain or calibration; no PCM scaling is introduced.

Original ASIO setter `1800075f0` stores an index byte, a count byte and the requested value bytes in its control payload, then invokes control field 3/set. Its generic helper result is inverted into the returned status; the setter does not interpret the two receipt bytes as control values. The kernel field-3/set branch at `1219f` sends command `0x33` with the payload, then requests two acknowledgement bytes. The send helper constructs a zero-initialized 64-byte frame with the ordinary `1C C5 00 01` tag and 59-byte payload region. Exact instruction boundaries, register assignments, command/tag constants and copy extents are checked against the pinned original ASIO/kernel binaries.

The new single-byte frame has command/tag at bytes 0–4, index at 5, count 1 at 6 and value at 7; remaining bytes are zero. The acknowledgement values remain opaque. A matching command/tag receipt is not proof that the setting took effect.

## State and evidence

`src/core/audio_control_selection.hpp` implements `AudioControlSelection`. An invalid group, setting kind or value enters failed state without producing a request. Valid construction starts with the existing `0x32` 22-byte getter. If the targeted raw byte already equals the requested byte, that inspection completes the transaction without a setter.

Otherwise the engine offers one indexed `0x33` request, retains its opaque two-byte acknowledgement and offers another `0x32` getter. Completion requires the targeted read-back byte to equal the requested byte exactly. It retains initial, latest observed and verified snapshots separately. Other fields are preserved as observed, including changes from independent switches; this is not an atomic whole-device snapshot or a request to overwrite the entire table. There is no transaction nonce in the recovered ABI.

Each request can be taken once. Taking the setter immediately marks that this transaction may have changed the device, even if the future caller cannot prove submission/completion. Failed or aborted operations retain that uncertainty and any observation/receipt. A read-back mismatch retains its observed table but supplies no verified table. Terminal states cannot retry, accept a later frame as success or emit a compensating write.

The existing command/tag matcher permits up to three recognized notifications before each reply. Thus the engine admits at most three requests and twelve received frames. Notifications remain separate partial events, not replacement table snapshots. Malformed sizes/tags, unexpected replies or a notification flood fail the transaction. The engine itself performs no waits: a future native I/O owner must enforce one wall-clock deadline, cancellation/drain budgets, exclusive idle-device ownership and recovery. Request-count bounds are not a wall-clock bound.

## Injected-I/O deadline and cancellation policy

`src/core/audio_control_selection_io.hpp` now executes the selection engine against the existing `AudioControlsIo` interface. The caller supplies an exclusively owned idle device and must retire every transfer before returning, including failed transfers. The new code is called only by tests; the Windows getter-only adapter is unchanged.

One 4,500 ms policy budget spans inspection, optional setter/receipt and verification. Each output timeout is at most 100 ms and each input timeout at most 300 ms, further reduced by remaining budget. Clock regression, expiry or cancellation before/after every transfer stops the transaction. A complete, correctly framed read-back arriving at or beyond the deadline cannot establish verified state. The interface's synchronous call can take longer while retiring I/O; the policy does not guarantee return from a stuck native/kernel call.

The policy permits at most three writes, twelve reads and one setter attempt. It checks cancellation/time before taking a setter request. Once the setter is taken, failed/short submission, cancellation, deadline or later verification failure preserves possible-write uncertainty. Initial/observed/verified tables and an accepted opaque receipt remain distinct. No retry, rollback or guessed success is introduced.

The existing five-second read-only IPC command must not simply be reused for settings: the 4.5-second operation budget plus native cancellation/drain allowance needs a separately reviewed end-to-end host/worker deadline. Unknown I/O retirement still requires storage retention and isolated-worker containment. A future native adapter must also admit exactly the selected indexed frame, preserve explicit idle ownership and record uncertainty/read-back/recovery before a physical setting test.

Injected tests cover successful selection and no-op, failure and short I/O at every transfer, cancellation at every before/after boundary, expiry/regression at every completion, shrinking timeouts, late/mismatched read-back, wrong acknowledgement commands and the maximum fifteen-transfer notification sequence. They use synchronous fake I/O and exercise no driver/device.

## Tests and physical gate

The existing native control test now covers all 48 sensitivity and six through targets, exact wire frames, already-selected no-op cases, unknown/out-of-range targets, opaque receipt preservation, getter-only verification, independent table changes, request sequencing, abort at each nonterminal phase, malformed replies and notification limits at every stage. A twelve-frame interleaving case and read-back mismatch preserve their different success/uncertainty outcomes. No test loads the vendor driver or submits a USB operation.

Fresh full Release and Debug suites pass **39/39** each, and the refreshed SDK-free suite passes **25/25**. The preceding full Python **105/105** evidence remains for unchanged Python test/runtime logic; it was not rerun for this C++ addition. The metadata records current source/binary identities rather than inheriting an old physical result. The I/O-policy checkpoint preserves binaries/manifests/logs, its new header and expanded test source locally at `artifacts/build/checkpoints/control-selection-io-20261030`. The earlier state-engine checkpoint remains separate. Runtime DLL/worker/probe hashes match the identity-controls checkpoint; only the control test gains the new execution policy.

Reproduce after building both configurations and saving the SDK-free suite log:

```powershell
.venv/Scripts/python.exe scripts/export-audio-controls-contract.py
.venv/Scripts/python.exe scripts/export-audio-control-selection.py
```

The native held-controls adapter still rejects every output frame except the exact getter. No state-machine call is present in runtime `.cpp` sources. Existing [read-only controls/WPP testing](controls-probe.md) must establish the real table before selecting a future bounded native setting experiment. That experiment must record the requested field, possible-write state, exact read-back, recovery and physical routing/level behaviour. It must not add automatic rollback or assume a phono setter. Current Serato admission, safe reacquisition, analogue/timing and DVS remain separate requirements.

## Checked evidence format checkpoint

The new header-only selection wire codec has a 24-byte request and 132-byte reply with explicit little-endian fields, fixed optional observation slots and exact target correlation. It preserves all three table observations, opaque receipt, failure/counter/phase details, possible-write state and native error. Invalid lengths, enums, reserved bits/bytes, absent-field data, wrong targets and contradictory success/uncertainty reject. It does not attest ownership, freshness, runtime execution or cleanup. [Full format, validation and remaining worker/deadline connection](control-selection-wire.md).

The native control test checks all 54 targets in changed/no-op cases and compares every field through serialization for existing valid-target I/O fault/cancellation/deadline cases. This adds no CTest entry and does not call the USB helper. Build metadata marks the codec separately from the I/O policy; at that serialization-only checkpoint protocol v2, the production getter-only frame guard and runtime binaries were unchanged. The subsequent [worker/host IPC checkpoint](control-selection-ipc.md) changes protocol/runtime hashes; its native adapter still refuses selection.

At this wire-format checkpoint fresh Release/Debug each pass 39/39, SDK-free passes 25/25 and full Python passes 125/125. Five current exporters pass. The local `artifacts/build/checkpoints/selection-wire-20261031` checkpoint preserves exact sources, tests, manifests, binaries, logs and evidence. All six production worker/probe/ASIO binaries across Release/Debug match the prior user-controls checkpoint; the control-test executable changes. No device/UAC or setting operation ran.

## Worker/host selection IPC checkpoint

A distinct idle-only command is now implemented in retained-device protocol v3 with explicit acquired-device capability, typed owner/outcome consistency, separate operation/cleanup evidence, conservative unknown-write handling and sealed failure lifetime. The host gives selection its own eight-second reply allowance and the worker uses a 7.5-second watchdog. Real process tests use a simulated setting device, including partial/complete result survival through failed final close, callback/active-audio refusal and dispatch beyond the getter timeout. Native selection remains unsupported by default; the exact getter-only output guard is unchanged. [Implementation, tests and remaining native gate](control-selection-ipc.md).
