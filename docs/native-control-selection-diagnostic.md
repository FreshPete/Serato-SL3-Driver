# Explicit native control-selection diagnostic

The native held device now connects the tested setting engine to the real bounded interrupt adapter, behind an **explicit single-target diagnostic grant**. Normal ASIO configuration remains read-only. No positive native setting test ran; the current read-only physical baseline and a supervised setting-test launcher/recovery validator are still required.

The grant is `WorkerSpec::diagnostic_control_target`, accepted only with native kind, retained lifetime and an absolute diagnostic directory. The host forwards it as `--control-test-target` to the isolated worker and supplies a fresh startup journal. The worker independently requires device-worker mode, helper/channel arguments, a journal and a canonical target. Its existing helper/driver hashes and exact SL3 descriptor checks still precede redirection. The production configuration parser does not set this field.

| Target syntax | Bounds |
| --- | --- |
| `sensitivity:GROUP:VALUE` | Group 0–2, original UI code 0–15 |
| `through:GROUP:VALUE` | Group 0–2, value 0 or 1 |

Parsing is case-sensitive and canonical: no leading zeros, whitespace, sign, extra field or alternate setting kind. These are logical original-table groups, not verified physical jack/deck labels.

## Admission and operation

`ControlSelectionDiagnostic<Device, Transfer, Clock>` is the same wrapper instantiated by the native device and the fake-transfer tests. Its default has no target grant. Supplying a target alone offers no capability: an explicit held control inspection must first produce the [fresh same-owner observation](control-baseline.md). The worker refreshes its capability flag after that read and rechecks the device's current capability before dispatching a selection. Expiry or consumption therefore prevents another native operation even when the host's last decoded snapshot is older.

The target must exactly match the grant. One attempt consumes the diagnostic lifetime, including a no-op or a failed/refused operation. Another read can obtain evidence but cannot rearm selection. A missing/expired observation or mismatching target produces a typed failure with no setter and known no-write state when handled directly by the wrapper. Worker admission can reject earlier, before invoking it. The host preserves its existing pre-operation rejection and unknown-reply distinctions and seals/closes on failure.

On admission, the wrapper consumes the observation, invokes the existing 4,500 ms inspect/set/read-back engine through `NativeControlsIo`, retains native error and complete/partial result, and invalidates the remaining baseline. Exact frame order, full initial-table match, freshness checks, 100/300 ms transfer wait caps, one setter, and native drain/fail-stop storage lifetime remain in effect. The 7.5-second worker watchdog/eight-second host reply budget and independent final release are unchanged. Protocol remains v3; build hashes still bind every executable.

Both public host start paths reject a diagnostic grant before launching audio, and the native device's `begin()` independently rejects any audio start in this mode. No alternate activation or isochronous stream is needed for selection. Sensitivity and through changes can still affect hardware gain/routing; no analogue behaviour is inferred from byte read-back.

## Evidence and next test boundary

The mandatory journal records fixed kind/group/value markers before helper loading. The adapter retains its before-transfer markers, including `audio_control_selection_set.enter` before preparation/submission. The wrapper records selection entry, possible-write/no-write classification, verified/failed classification and return. An entry marker alone does not prove packet submission. Raw initial/observed/verified tables, opaque receipt and detailed failure remain in the typed operation reply, independent of final owner release.

The [host-probe setting CLI and offline record/journal validator](selection-host-probe.md) are now implemented. The supervised USB trace/security/recovery wrapper remains unfinished. The existing `--controls` probe/normal-token trace workflow stays read-only and is the next physical baseline; its validator intentionally rejects setting-mode records. A future traced launcher must bind the reviewed baseline/current binaries and target, preserve uncertainty, and validate complete trace/security/recovery. A getter or this worker flag does not establish physical setting validation.

Fake-transfer tests exercise this exact wrapper's default refusal, target/baseline admission, verified result, wrong target, expiry and one-attempt/no-rearm behaviour. Existing all-target/frame/partial/error/deadline tests remain. Actual simulated worker processes test capability appearing after controls and disappearing before a repeated operation. Actual native safe negatives test standard and granted/journal modes with an absent helper, plus invalid target/mode/journal arguments before helper access. Host tests reject invalid diagnostic specs and refuse audio without a worker. No native positive acquisition/setting is implied by these tests.

[Build-bound adapter/diagnostic evidence](evidence/native-control-adapter.json), [IPC evidence](evidence/control-selection-ipc.json), and [original setting bytes](evidence/audio-control-selection.json). The underlying production `Transfer` retirement implementation is unchanged. No firmware, driver/trust/security, binding, registration, application/account or physical setting operation ran.

At the diagnostic-API checkpoint, suites passed **39/39 Release, 39/39 Debug, 25/25 SDK-free and 125/125 Python**, with seven exporters. The worker rejected older physical prerequisites. That checkpoint remains at `artifacts/build/checkpoints/selection-diagnostic-20261031`; the subsequent [host-probe checkpoint](selection-host-probe.md) adds its own test/validator and new evidence.
