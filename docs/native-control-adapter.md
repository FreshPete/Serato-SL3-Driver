# Native interrupt-control adapter

The Windows worker uses the shared `NativeControlsIo<Device, Transfer, Clock>` template for explicit idle control-table inspection. Default construction remains getter-only. Its selected constructor is now connected through an [explicit single-target native diagnostic](native-control-selection-diagnostic.md), requiring a fresh observation and mandatory journal. Ordinary ASIO configuration does not grant selection. No setting was sent to the SL3.

The [same-owner baseline gate](control-baseline.md) requires a move-only observation issued by a successful getter, fresh at reservation and immediately before any setter. Target alone is insufficient. New observations, audio activation, close and owner destruction invalidate earlier observations. Normal ASIO configuration grants no setting capability; the diagnostic target is explicit and single-use.

The adapter in `src/windows/control_transfer_io.hpp` uses the existing native `Transfer` for 64-byte interrupt requests on OUT `0x01` and IN `0x81`. Its production cancellation/drain/storage-retention implementation is unchanged from the selection-IPC checkpoint. The template is also instantiated with fake device/transfer/clock types in the existing control test, so frame admission and timeout preparation execute the same adapter code without loading a helper or opening a device.

| Boundary | Enforcement |
| --- | --- |
| Getter-only default | One exact `0x32` getter followed by bounded replies/notifications; no setter or reuse. |
| Explicit selected target | Valid original sensitivity/through target; an independent selection engine supplies the exact next admissible output frame. Every byte, including unused padding, must match. |
| Ordering | No input before a request, setter before initial observation, second request while a reply is pending, or transfer after completion/failure. |
| Time | 1,500 ms getter lifetime or 4,500 ms selection lifetime; per-call output/input ceilings 100/300 ms; request preparation consumes both per-call and lifetime budgets. Clock regression/expiry seals the adapter. |
| Terminal I/O | The underlying native request must retire or fail-stop. A short transfer seals the adapter; late completion cannot establish a verified setting. |
| Error evidence | Capture a request's completion error before request destruction can change thread-local last-error state. The outer policy retains possible-write/initial/observed/verified/receipt evidence. |

This second protocol check is at the native admission boundary; it does not replace the outer transaction engine or its evidence. Successful raw reads remain available to the outer engine even when a reply is malformed or its read-back mismatches, preserving detailed protocol/observation failure rather than turning it into a guessed transfer success. There is no nonce in the recovered protocol, so matching frames do not establish freshness against independent actors.

Fake-transfer checks exercise all 54 targets with changed/no-op outcomes, mutations of every setter byte, ordering/reuse/default-setting refusal, invalid targets/timeouts, failure/short/late completion at all six transfer boundaries, preparation/lifetime clamping, clock regression, maximum interleaved notifications and mismatching read-back. The fake destructor deliberately changes `GetLastError`; the expected request completion error must survive. These tests do not prove native driver cancellation or physical setting behaviour.

Reproduce the build-bound evidence after both configurations and the SDK-free suite:

```powershell
python scripts/export-native-control-adapter.py
```

The [exported record](evidence/native-control-adapter.json) pins the tested source/binaries/logs and checks that the production `Transfer` implementation is unchanged against the exact archived build input. Prior hardware results remain tied to their old worker hashes. There is no current-worker physical setting claim.

At the adapter-only checkpoint verification passed **39/39 Release, 39/39 Debug, 25/25 SDK-free and 125/125 Python**. Seven build/feature exporters passed. The worker rejected older physical capture/duplex prerequisites with exit 1 and `Build/security mismatch`. The initial notification-test fixture used an invalid tag and was corrected. Local checkpoint: `artifacts/build/checkpoints/native-control-adapter-20261031`. The subsequent [baseline checkpoint](control-baseline.md) has its own rebuilt worker/evidence and preserves that earlier checkpoint separately.

Before a native setting experiment: obtain the prepared current-worker read-only clock/table baseline; add explicit acquired-device selection admission tied to that baseline; journal target/possible-write/result/retirement; run the bounded owner-attended trace/recovery sequence. Production capability stays false until that path is reviewable. No automatic rollback, rate/phono setter, control panel or CLI setting command is introduced. Safe reacquisition, analogue/timing validation, deployment and current Serato/DVS remain separate unfinished requirements.
