# Current descriptor components: audio hardware is not a MIDI-free template

Read-only comparison of current Serato's resource descriptors with its original getter/counting code now establishes another requirement for an SL3 integration: **omitting `midi_direction` does not mean no MIDI**. Exact `none` is different from an absent or unrecognized value. Modern soundcard-style products cannot be treated as MIDI-free descriptor templates merely from their physical role. [Checked original-byte and resource metadata](evidence/serato500-component-profiles.json).

Target remains the unchanged installed/extracted Windows 5.0.0.1278 executable, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`, and archive SHA-256 `872fc4fdad2eab2ddd34387d2d3c04dd9731c84798d9fdc7bd05ca54e1567db8`. No vendor code, hardware query or application session ran.

## Getter and component contribution

Parser instructions at `1405c90f6` locate `midi_direction`; when its element exists, the parser copies the value to complete-object `+0x3e0`. Descriptor-interface RTTI proves a receiver offset of +16. Getter `1405c6ef0` reads receiver `+0x3d0`, addressing that same string.

The getter uses the actual `VCRUNTIME140.dll!memcmp` import and exact string lengths:

| String | Getter result | MIDI contribution in the checked descriptor-count branch |
| --- | ---: | ---: |
| `in` | 1 | 1 |
| `out` | 2 | 1 |
| `none` | 0 | 0 |
| Empty or other value | 3 | 1 |

Comparison is case-sensitive; prefixes, surrounding spaces and a missing string are not converted into `none`. The fallback value includes the declared `duplex` case. These are numeric getter results and contribution rules, not assertions about physical connectors or observed MIDI traffic.

Worker instructions `1421db9e8`–`1421dbaa2` call the MIDI/HID/USB capability getters, turn a nonzero MIDI result into one contribution, and add the HID/USB getter values. This is a conditional descriptor branch in the existing aggregation worker; it is not a complete connection decision or a claim that every resource takes that branch at runtime. [Earlier aggregation/selection boundaries](serato-aggregation-selection.md).

## Current resource comparison

All 229 member ZIP CRCs were verified. The 197 recognized descriptor nodes comprise 65 native Pro, 76 native Intro and 56 accessories. Their MIDI declarations are absent in 179 nodes, exactly `none` in 15, `duplex` in one and `in` in two.

| Resource profile | Declared MIDI direction | HID / raw USB declarations | Handshake / DVS declarations |
| --- | --- | --- | --- |
| Serato virtual audio | `none` | HID absent; USB false | Handshake NONE; DVS absent |
| Denon DS1 | Absent | HID absent; USB true | SERATO_DJ; DVS YES |
| Reloop Flux | Absent | HID false; USB absent | SERATO_DJ; DVS YES |
| Reloop Flux Go | Absent | HID absent; USB absent | SERATO_DJ; DVS YES |
| Traktor Z2 | `none` | HID true; USB absent | Handshake absent; DVS REQUIRES_AUTH |
| Phase | `none` | HID true; USB absent | SERATO_DJ_HID; DVS absent; accessory kind |

Absent fields remain absent in the report. The table does not silently invent false Boolean values, no-handshake requirements or runtime support. Each selected row retains its XML digest and CRC. Only allowlisted interoperability fields are exported; authentication material and complete vendor XML are excluded.

Numeric row projections use the checked ControllerDescriptor getter. They do not prove the concrete runtime constructor/getter or connection branch selected for every resource node. No descriptor was instantiated to test that selection.

Among the fifteen explicit no-MIDI nodes, eleven are accessories, three are native Intro HID devices, and one is native Pro virtual audio. Fourteen explicitly declare HID true. No native Pro node in this explicit no-MIDI subset declares `DVS_DEVICE_YES`. The virtual-audio row declares no DVS capability; the recovered parser default and later runtime state must not be replaced by an assumption that its two-deck count enables DVS.

## SL3 consequence

The [historical SL3 descriptor](serato-legacy-sl3-descriptor.md) explicitly declares no MIDI, requires USB and uses the old DRIVER_API handshake. The current identity-only stub leaves MIDI direction empty; its static getter projection is therefore 3, contributing an expected MIDI component in the checked branch. An otherwise empty support-value edit does not supply the historical component contract.

The DS1/Flux profiles are not evidence that omitting MIDI avoids that expectation. Z2 demonstrates a different HID/authentication-dependent profile, not a route to skip authentication. Phase remains an accessory. Virtual audio does not establish primary SL3/DVS admission. No device identity, handshake result, authentication flag or account check was substituted.

An SL3 implementation still needs a real, discoverable component path matching its capabilities, an admitted current description, the actual audio/control contract and legitimate application requirements. Explicit no-MIDI data would remove one expectation under this branch, but cannot by itself provide the USB component, replace the removed historical handshake type or prove a working connection. No descriptor draft, resource writer or installed override is produced by this comparison.

## Reproduction

```powershell
.venv/Scripts/python.exe scripts/export-serato-component-profiles.py
```

The exporter verifies installed/extracted identities, original parser/getter/branch instructions, interface RTTI/slots, the comparison import, all member CRCs and the fixed profile inventory. Its metadata digest binds the complete allowlisted scan while only selected rows and no-MIDI names are retained in the report. No native build inputs changed; the preceding 39/39 Release, 39/39 Debug and 25/25 SDK-free results remain separate evidence, not new tests. Current Serato admission and real two-deck DVS remain unresolved.
