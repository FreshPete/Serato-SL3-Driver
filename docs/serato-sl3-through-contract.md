# Historical Serato SL3 through-control mapping

The original 2.5.5 application maps its three Rane SL3 API slots to control-table groups **1, 2, 0**, in that order. Its Boolean setting is inverted before the one-byte driver write; read-back and notifications independently use the same ordering and polarity. This supplies a concrete part of the historical application/control contract missing from the descriptor alone. It does not establish user-visible deck numbers, physical sockets or current Serato admission.

[Original-byte verifier](../scripts/export-serato-sl3-through-contract.py), [checked evidence](evidence/serato255-sl3-through-contract.json). Input hashes remain the original 2.5.5 executable `ba8641d0329fe0c955147d2b45f247eeea82ac0f812fe30a339834dbe0c0a503` and Rane x64 ASIO DLL `e3d88039547b70915b1a9bc9e3e3f7dba32aaa9bc3ce8fd51616565ea1734141`. Neither binary was executed or modified.

## Matching setter, getter and notification paths

Validated MSVC RTTI identifies `serato::device::driver::RaneSL3API`, complete-object vtable `0x1447B9B08`, locator `0x14482FBE0`. The initializer resolves the actual named exports into object members +0x90 (`sl3_get_audio_controls`), +0x98 (`sl3_set_audio_controls`) and +0xA0 (`sl3_set_thrustate_callback`). The opened handle is at +0x68.

| Historical API slot, after upstream remapping | Table byte | Original table group | Notification byte |
| --- | ---: | ---: | ---: |
| 0 | 14 (`0x0E`) | 1 | 1 |
| 1 | 20 (`0x14`) | 2 | 2 |
| 2 | 8 (`0x08`) | 0 | 0 |

The table-group column comes from the original Rane UI's actual data at `0x1801B5B00`, stride `0x30`, rather than assuming matching numeric indexes. The [22-byte control contract](audio-controls-contract.md) establishes the table's phono, sensitivity and through fields separately.

Vtable slot +0xB0 calls `0x140691CB0`. The method rejects an uninitialized API and indexes outside 0–2, maps the three valid slots to those byte offsets, XORs the input byte with 1, and calls the setter with length 1. For Boolean inputs, false writes raw 1 and true writes raw 0. This is a byte XOR, not a general logical inversion for arbitrary nonbinary inputs. The recovered Boolean must not be equated with the control panel's raw through flag without translating its polarity.

Vtable slot +0xB8 calls `0x140691C10`. Its three-iteration getter uses the same byte offsets and publishes `raw == 0`. Notification registration at slot +0xC0 (`0x140691AE0`) registers `0x140691D10` through the actual callback export pointer. That function reads incoming bytes 1, 2, 0, applying a zero comparison in each case. The last dispatch is a tail jump: Ghidra's pseudocode omits its Boolean argument, but machine code explicitly sets DL from `[rbx] == 0` before jumping. The fourth notification byte is not interpreted by these callbacks.

The old getter initializes its output byte to 1 before calling a void-style getter. If that byte remains unchanged, it publishes false. That is historical behavior, **not proof of successful control I/O**. The rebuilt transaction's explicit outcome/error/read-back evidence must remain authoritative; it should not reproduce this fallback as verified state.

## The upstream index is also remapped

Constructor `0x14041FF00` calls the original DriverAPI factory at `0x140420AE1` and stores the returned shared object's pointer at owner +0xF8 (`0x140420AF7`). The upstream helper `0x140422200:0x140422256` takes that same member, then reads a runtime vector from global object `0x144E39EF8`, begin +0x398 and end +0x3A0, using four-byte elements.

A valid incoming index is replaced with that vector's element before tail dispatch through DriverAPI slot +0xB0. An out-of-range or negative index forwards -1; the inspected SL3 implementation then performs no indexed write. A null global or null driver API returns without dispatch. The verifier checks the helper's entire instruction sequence because this leaf has no PE unwind entry.

Consequently, an incoming application index, an SL3 API slot and an SL3 table group are three distinct coordinates. The runtime remapping vector has not been captured. The descriptor's [Deck3/Deck1/Deck2 endpoint order](serato-legacy-sl3-descriptor.md) alone does not establish that vector or physical jack labels. No captured six-channel PCM order is changed on the strength of this analysis.

The subsequent [initial-map investigation](serato-sl3-initial-remap.md) now verifies that successful parsing of the original three-deck SL3 resource constructs [0, 1, 2]. Its absent/default-false channel-setup field also blocks the inspected ordinary layout-change handler. This narrows the initial state without claiming a runtime capture or excluding every later writer.

## Verification and implementation consequence

The exporter pins both original binaries, validates the RTTI locator and vtable methods, checks named export strings/pointer stores, branch and call instructions, notification callback targets, the original table bytes, the owner/factory connection and the complete upstream leaf. Focused Ghidra reports remain supplemental evidence; instruction checks preserve the argument that its last callback pseudocode missed. Re-running the exporter produces byte-identical output.

```powershell
.venv/Scripts/python.exe scripts/export-serato-sl3-through-contract.py
```

The next integration must supply the actual runtime remapping before converting an application request into a table-group target, translate Boolean polarity deliberately, and retain unknown/error state on failed reads. Existing diagnostic selection continues to use explicitly named table groups and raw UI values. No new setter caller, device operation, persistent transport, profile, DLL registration or application patch is introduced here. The production native build inputs are unchanged, so its archived suites were not repeated for this static verifier.

The historical driver-timer handshake and rate setup remain separate requirements. Current 5.0.0 also lacks a demonstrated real-SL3 descriptor/DriverAPI/handshake integration; these historical control facts do not fill that gap. Physical routing, normal-token transport access, reliable repeated acquisition and two-deck DVS remain unverified.
