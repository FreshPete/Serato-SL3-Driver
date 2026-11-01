# Idle setting selection across worker and host

The setting-selection message format connects the isolated worker and explicit host API. The [host-probe CLI and record validator](selection-host-probe.md) now exercise it with simulated positives and safe native negatives. Native SL3 selection remains behind an [explicit target grant](native-control-selection-diagnostic.md), fresh getter and journal. Normal ASIO configuration stays read-only; no panel, automatic ASIO setting operation, registration or physical setting write ran.

This completes the process-boundary step after the [selection evidence codec](control-selection-wire.md). It does not establish native USB selection, real control-state read-back, routing/gain behaviour or a current Serato/DVS session. [Build/test/source evidence](evidence/control-selection-ipc.json).

## Protocol and admission

Retained-device protocol **version 3** adds command **0x306** and a selection-supported bit in typed owner snapshots. Versions 1/2 are rejected. The separate temporary-stream protocol remains version 2; the inner selection format remains version 1.

The worker learns selection support only from an acquired `SessionDevice`. The interface defaults to false and its selection method defaults to refusal. `NativeHeldDevice` overrides neither; its exact native output-frame guard remains getter-only. A raw selection command is rejected before any device selection method when capability is absent.

Admission requires a valid exact target, handshake, ready already-held device, retired I/O and no audio stream. It never acquires, activates audio or changes rate implicitly. The host also requires retained lifetime, a usable/quiescent owner, no callback reentry, no active or blocked audio owner and advertised capability. Invalid local targets return without publishing a command or poisoning the healthy idle session.

## Results and ownership are separate

An operation reply contains the typed device snapshot followed by the fixed 132-byte selection record. The combined body is 260–772 bytes. Decode binds the exact requested target and validates the owner phase/capability/retirement, matching native error fields and selection success/failure consistency.

A successful selection keeps the device held. A failed but completed selection returns its initial/latest observations, receipt and possible-write state before final redirect release. The worker becomes failed and rejects another selection. The host then closes/seals the owner, retaining the accepted operation result even when that later close fails.

`HostSession::select_control` returns a `ControlSelectionReport`:

| Field | Meaning |
| --- | --- |
| `command_attempted` | The host attempted this explicit command; it is not a USB-submission counter. |
| `outcome_unknown` | Whether the setting effect remains unresolved. A typed rejection before device work resolves that question without a selection sample. |
| `device_may_have_changed` | Conservative operation uncertainty. It becomes true before publication and remains true for a lost/malformed outcome; an accepted result supplies the engine's more precise setter-attempt state. |
| `outcome` | Optional accepted selection evidence, retained independently of later cleanup. |

Use `report()`/`close()` separately for I/O, callback, device, process and job ownership. A verified table cannot turn a failed redirect release into success. Process exit alone does not prove native I/O/device release. A snapshot-only failure, even with a long diagnostic, does not become a fabricated setting result.

The reply's rate is cached owner metadata from the preceding clock observation, not an additional oscillator measurement or fresh clock query. Same-target freshness relies on enclosing mailbox sequencing and exclusive ownership; the USB protocol has no new transaction nonce.

## Deadlines and failure containment

Selection has an independent **8,000 ms host reply allowance**. The worker uses a **7,500 ms watchdog**, or a shorter configured startup policy. A compile-time check keeps the 4,500 ms engine budget plus one 2,000 ms cancellation-drain allowance below the watchdog and the watchdog below the host reply allowance. These are distinct from the getter's unchanged 5,000 ms host allowance.

Final owner closure has its own bounded cleanup policy and can add time after an operation failure. These limits are not proof of native kernel retirement. Device implementations must retire transfers before returning or throwing; unknown retirement must retain storage and contain the isolated worker. No retry or compensating write is performed. Native selection remains explicit-diagnostic-only and physically untested.

## Process tests

The actual worker and host tests cover successful selection, explicit repeated-target no-op, observation of the changed fixture byte, malformed targets/replies, capability refusal, before-acquire rejection, active-audio/callback/blocked-callback rejection and one acquire/final-release lifetime.

Fault tests preserve partial observations and possible-write state on transfer/read-back failure; seal the owner against retry; retain complete or partial evidence across failed final release; and preserve unknown-write uncertainty for thrown, malformed or stalled operations. An independent watchdog contains the stalled fixture. A 5.5-second fixture dispatch delay demonstrates use of the new reply allowance; it is not simulated native transfer/drain timing or hardware timing evidence. The native negative test rejects selection before acquisition with no helper/device access.

Fresh suites pass **39/39 Release, 39/39 Debug, 25/25 SDK-free and 125/125 Python**. Six build/original-byte exporters pass; the original ASIO lifetime and saved descriptor/identity evidence also revalidate. The new worker explicitly rejects the older physical capture/duplex prerequisites by hash. The public ASIO facade does not call selection. No positive native transport operation runs during these tests. Current suite/hash records are in the [evidence](evidence/control-selection-ipc.json).

## Remaining native gate

The [native diagnostic](native-control-selection-diagnostic.md) now supplies explicit target admission, fresh baseline, one attempt and journal wiring. Next obtain the prepared [normal-token read-only controls baseline](controls-user-probe.md) with the new worker, then complete/review the supervised setting launcher and trace/result/recovery validation before a physical setting test. The production cancellation/drain implementation is unchanged; fake tests do not revalidate it on hardware. Old version-2 controls results and older worker hashes do not establish the current baseline. Historical audio passes remain attached to their archived binaries.

Physical routing/levels, safe repeated acquisition, measured ASIO timing/deployment, current Serato admission and two-deck DVS remain incomplete. No firmware, authorization/account, signing-policy or security change is introduced.

```powershell
.venv/Scripts/python.exe scripts/export-control-selection-ipc.py
```

The exporter checks saved build/source/test records only; it performs no USB or application action.
