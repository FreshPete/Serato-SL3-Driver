# Current Serato stereo input-map consumers

The current audio consumer treats descriptor `hw_src` values as **stereo-pair indices**, expanding each value `h` into mono channels `2*h` and `2*h+1`. This resolves the input-index units left open in the earlier DVS contract. It does not identify physical sockets, complete the current SL3 descriptor or establish a working DVS connection.

The target is unchanged Windows x64 Serato DJ Pro 5.0.0.1278, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. Addresses below are preferred image VAs. The investigation reads the original PE and focused decompilations without executing vendor code. [Verified machine-code evidence](evidence/serato500-endpoint-consumers.json).

## Descriptor maps reach the native mixer

Descriptor helpers `0x1405C6D50` and `0x1405C6D80` copy the input map at complete-object +0x6B8 and output map at +0x6C8. Setup function `0x142148010` calls both and copies them into its receiver at +0xF0 and +0x100 respectively. Validated RTTI places this interface at complete-object +0x88 in `CNativeMixer`, vtable `0x1431C4AA8`; setup occupies slot +0x80. The resulting complete-object map offsets are therefore +0x178 and +0x188. These receiver and complete-object offsets must not be mixed.

The input parser starts a sequential source counter at zero, copies the current value into a per-entry local, and lets an explicit `hw_src` attribute replace that local. At `0x1405CB384` the local becomes the map node's value at +0x20; the separate sequential counter increments afterward. The original SL3 resource has no explicit source overrides, so its declared order supplies pair indices 0, 1 and 2.

Current input enum-map initializer `0x1405C3350`, reached from static initializer `0x14020C3E0`, stores `Deck1In=2`, `Deck2In=3`, `Deck3In=4` and `Deck4In=5`. These enum keys are distinct from the map's hardware pair values. Helper `0x1421744A0` queries the input map for keys starting at 2 and bounded by the descriptor's deck count, collecting the mapped hardware values into a sorted unique set. It is not a direct mono-channel list or proof that all collected decks are active DVS inputs.

## Final input-channel expansion

The same mixer interface's slot +0x10 points to `0x14214E370`. Its input loop looks up each configured endpoint's map value, then executes:

```text
0x14214E4BA  read map value h
0x14214E4BD  form 2*h
0x14214E4C6  obtain channel 2*h through 0x1421B9D30
0x14214E4CE  form 2*h+1
0x14214E4D7  obtain that second channel through the same helper
```

After resolving the corresponding input object, the loop forwards both pointers to `0x142185B10`, which stores them at object +0x30/+0x38 and clears +0x40. The channel helper checks the requested index, multiplies it by the per-channel stride and returns the buffer base plus four times that product. This is a planar audio-buffer consumer; it is not a change to the SL3's six packed 24-bit USB channels. The intervening host conversion and the exact decoder-object/deck association remain separate verification points.

## Consequence for the historical SL3 descriptor

The separately verified original resources in 2.5.5 and 2.5.6 declare input order `Deck3In, Deck1In, Deck2In`. Applying the current parser and consumer rules to that order yields:

| Historical endpoint | Enum key | Default hardware pair | Zero-based mono channels |
| --- | --- | --- | --- |
| Deck3In | 4 | 0 | 0, 1 |
| Deck1In | 2 | 1 | 2, 3 |
| Deck2In | 3 | 2 | 4, 5 |

This is a conditional logical mapping. The current discontinued identity stub does not contain that full descriptor, and no resource or application file has been changed to supply it. It would be incorrect to claim the connected device currently routes Serato Deck1/Deck2 this way.

The result narrows the physical validation: preserve all six native channels, inject one controlled signal into a known socket pair at a time, then compare the observed pair with the intended logical endpoint before wiring two timecode sources. Do not simply assign the first four USB channels to Deck1/Deck2 because there are two decks. Physical input selection, signal levels, left/right polarity, software through and Phase/DVS operation still require actual tests. The later [output graph trace](serato-output-routing.md) independently verifies `hw_dest` expansion into stereo destination ports; final backend conversion and physical playback remain unverified.

Reproduce the bounded export with `.venv/Scripts/python.exe scripts/export-serato-endpoint-consumer-evidence.py`. It checks the original PE hash, focused unwind ranges, enum literals/stores, parser source/index operations, map-copy calls, mixer RTTI/slots and final doubled-channel instructions. It binds the earlier historical descriptor evidence by hash and checks its declared order. No native audio source changed at this checkpoint, so no unrelated C++ rebuild is used as evidence for these static findings.
