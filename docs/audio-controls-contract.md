# SL3 audio-control table and notification views

The original x64 Rane ASIO DLL now establishes a partial interpretation of the 22-byte audio-control reply. Original C++ read-only views expose those fields. The subsequent [held-device inspection API](held-controls.md) now connects them to an explicit bounded getter; no setter, gain processing or control-panel deployment is added. [Original-byte and build evidence](evidence/audio-controls-contract.json).

## Recovered fields

| Logical control group | Phono-switch byte | Sensitivity-code byte | Through-state byte |
| --- | ---: | ---: | ---: |
| 0 | 0 | 3 | 8 |
| 1 | 1 | 9 | 14 |
| 2 | 2 | 15 | 20 |

Offsets are relative to the defined 22-byte payload returned by command `0x32`. Other bytes remain opaque and are preserved. These groups are control-table order; their relationship to USB stereo pairs, physical jacks and Serato deck routing remains unverified.

The original UI's data table begins at preferred image VA `1801b5b00`, with the three consumed integer offsets every `0x30` bytes. Readback code at `180004830` uses the first integer for phono state, the second for sensitivity and the third for through state. Its through handlers call the actual `sl3_set_audio_controls` export pointer with the third index, one byte and values 1 or 0. The original indexed setter's framing was established in the [earlier control contract](clock-control-audio.md).

The sensitivity selector adds 16 entries for codes **0–15**. Both its list and readback display calculate **2.5 + 0.5 × code mV**, giving displayed values from 2.5 through 10.0 mV. The selection handler passes one byte using the second table index. These facts establish the original UI scale and offered values. They do not establish measured input gain, converter calibration, clipping threshold or electrical behavior on this unit. No multiplier is applied to PCM samples.

The verifier checks original instructions, actual named exports/pointer slots, the real `USER32!SendMessageA` import, SDK combo-message values and exact float/string constants. The pinned ASIO SHA-256 is `e3d88039547b70915b1a9bc9e3e3f7dba32aaa9bc3ce8fd51616565ea1734141`. No vendor executable or library was run.

## Notification identities

The kernel's original explicit leaf `115c0:11698` writes command `0x38`, tag `00 00 00 02`, into shared bytes `+389..38b`. ASIO consumer `18000e8f0` passes those three bytes through the callback stored by **sl3_set_phonoswitch_callback**. The UI registers its callback at `180004400`, whose own diagnostic identifies phono switches.

Command `0x39`, tag `00 00 00 03`, writes four bytes to `+390..393`. ASIO consumer `18000e9b0` forwards all four through the callback stored by **sl3_set_thrustate_callback**. The registered UI callback at `180004520` consumes its first three values as through states. **The fourth byte's meaning remains unestablished.** The new typed notification retains it as an opaque extra byte.

Both UI callbacks normalize each of their three flag values using nonzero comparisons. Raw bytes are preserved by our views, including values other than 0 and 1. No physical switch polarity or fourth channel is inferred. This links the notification identities to original vendor consumers, beyond the earlier Linux comparison hypothesis.

The subsequent [historical Serato control contract](serato-sl3-through-contract.md) establishes a different application-facing view: its API slots use groups 1, 2, 0 and publish `raw == 0`. An upstream runtime vector also remaps incoming indexes. Table-group order and raw flag polarity must therefore stay distinct from application indexes and Booleans; the actual vector and physical routing remain unverified.

## Implementation and validation

`src/core/audio_controls.hpp` consumes only a successful, error-free `Event` with matching command, outcome and exact payload width. A full snapshot retains all 22 bytes and bounds-checks logical group access. Its optional sensitivity display is available for the original UI's 0–15 range. Higher raw codes remain observable and are not clamped or assigned guessed units. Notifications remain partial events, and cannot manufacture a full control snapshot or overwrite unrelated controls.

The existing native control-frame test now exercises a position-distinct table, unknown bytes, nonbinary flags, minimum/middle/maximum UI values, all 240 out-of-UI sensitivity codes, invalid group indexes, incorrect command/outcome/error/width combinations and both notifications. It checks that the fourth through byte survives and overload notifications are rejected as switch state.

Current **39/39 Release, 39/39 Debug, 25/25 SDK-free and 71/71 Python** checks pass, including the subsequent controls diagnostic. The tested control executables, worker/probe/DLL, manifests and logs are preserved locally at `artifacts/build/checkpoints/audio-control-views-20261030`. The source/build verifier reproduces with:

```powershell
.venv/Scripts/python.exe scripts/export-audio-controls-contract.py
```

The initial view-only checkpoint kept the hardware-tested worker/probe unchanged. The subsequent [held-device implementation](held-controls.md) adds an idle-only native getter and host API using retained protocol version 2. Its software checks pass; no physical `0x32` query or setter ran. Its new worker identity requires fresh physical prerequisites. The [earlier hardware result](retained-physical-test.md) remains pinned to its own binaries and covers silent streaming.

The bounded getter, journal markers, ownership gates and host API are now connected. The [diagnostic record/trace entry](controls-probe.md) is now implemented; next validate the control read with the owner present. Physical controls/routing tests require a signal fixture and recovery checks. Writes and UI deployment remain gated by that work. The separate [successive-object reopen problem](usbdk-detachment.md), sustained timing and current Serato/DVS integration remain open.

Subsequent [offline setting selection](audio-control-selection.md) implements read/write/read-back framing for the proven sensitivity/through indexes and UI value ranges. It interprets no acknowledgement status, enables no phono/arbitrary-table write and has no runtime caller. Native control inspection remains getter-only; this software engine does not supersede the physical read/write/routing gates above.
