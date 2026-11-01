# Original SL3 initial control remapping

The original 2.5.5 descriptor parser constructs the SL3's initial inverse control map as **[0, 1, 2]**. Its ordinary channel-layout event cannot replace that map while the parsed `allow_channel_setup` flag is false; the original SL3 XML omits that element, so the inspected parser leaves it false. This resolves the initial mapping left open by the [through-control investigation](serato-sl3-through-contract.md). It remains a static successful-parse consequence, not a captured application session or physical socket mapping.

[Original-byte verifier](../scripts/export-serato-sl3-remap.py), [evidence](evidence/serato255-sl3-initial-remap.json). The original application SHA-256 remains `ba8641d0329fe0c955147d2b45f247eeea82ac0f812fe30a339834dbe0c0a503`. The verifier rechecks the preceding SL3 control contract and decrypts the pinned original descriptor locally using the existing inspected resource reader. It stores only interoperability fields and hashes, with no full XML, resource key or vendor executable in Git.

## Initial parser path

The parser `0x140356CD0:0x14035BC28` reads the actual `num_decks` tag, obtains its `value` and converts it through the imported `atoi`. The original SL3 resource declares 3. The count is saved at `[rbp-0x30]` and later loaded into R13D at `0x14035B480`.

The parser constructs a stack descriptor at `[rbp+0x700]`. Its map is at stack +0xA78, corresponding to complete-object +0x378; its inverse vector is at stack +0xA98, corresponding to complete-object +0x398. Mixing stack offsets with object offsets would misidentify the fields.

At `0x14035B8AD`, a comparison with 4 selects a special path only for four-deck declarations with four collected entries. With the SL3's count of 3, execution takes the other path. Starting from zero, the loop writes map entries `i -> i` for each index below the declared count. It sizes the inverse vector using that count, then writes each node's key at the position specified by its value. On successful parsing/allocation, the result is therefore [0, 1, 2].

Combined with the independently verified RaneSL3API methods, the **initial** incoming indexes 0, 1 and 2 reach API slots 0, 1 and 2, then table groups 1, 2 and 0. Setter Boolean inversion and zero-test read/notification behavior still apply. This does not establish user-visible deck numbering, analogue sockets or a current 5.0.0 integration.

## Layout-change path

The parser defaults the `allow_channel_setup` byte to zero at `0x14035AEF2`. A missing element branches past the optional value read. That byte is copied into stack descriptor +0xAF8, i.e. complete-object +0x3F8. The original SL3 resource has no such element.

The inspected event handler loads the same global descriptor used by the control helper, then tests descriptor +0x3F8 at `0x1400F7134`. Zero branches past the call to layout builder `0x140356850`. This establishes the guard in this handler; it does not exhaust every possible writer or later runtime mutation.

For other enabled descriptors, the builder contains these actual four configurations. Entries are forward-map key/value pairs; the consumed inverse vector is a different coordinate:

| Builder kind | Forward entries | Stored inverse vector |
| --- | --- | --- |
| 0 | 0→0, 1→1, 2→2, 3→3 | [0, 1, 2, 3] |
| 1 | 0→2, 1→0, 2→1, 3→3 | [1, 2, 0, 3] |
| 2 | 0→0, 2→1, 3→2, 5→3 | [0, 2, 3, 5] |
| 3 | 0→2, 2→0, 3→1, 5→3 | [2, 3, 0, 5] |

Those constants are not layouts to apply to the SL3. In particular, copying one of the four-element templates would replace the proven three-element initial contract with a different one.

## Verification and next use

The exporter checks actual source strings/imports, count flow, stack/object coordinates, the initial-map loop and inverse stores, the optional-field default/copy, the handler guard, and every alternate branch's SIMD constant source and table bytes. It also requires matching original-image hashes and complete focused reports. Actual regeneration is byte-identical. No native runtime source changed, so the archived native suites were not repeated.

```powershell
.venv/Scripts/python.exe scripts/export-serato-sl3-remap.py
```

The next application experiment should compare its actual descriptor/vector with this initial contract before translating requests into table groups. The rebuilt getter/setter diagnostic continues to use explicit table-group targets and preserve errors, rather than accepting an application index as a group number. Normal-token device access, physical routing and reliable reacquisition remain unattended-test limits. Current Serato's real-SL3 descriptor/DriverAPI/handshake admission is still unresolved; no identity, account, resource, firmware or security change was made here.
