# Current device-resource archive: decoded read-only

The exact current Windows archive has now been decoded independently without running Serato. All **229 members** passed ZIP CRC checks. Its **228 XML files** parsed successfully; the remaining XSD schema was hashed and CRC-checked without processing its declarations. No SL3-named member or scalar VID `1CC5`/PID `0001` match was found in its recognized descriptor nodes. The existing executable's identity-only SL3 stub remains a separate, already verified registration path.

This finding is limited to `userio_resources.bin` from Windows 5.0.0.1278. It does not prove absence from every provider, embedded resource or identity encoding. Both the installed executable and installed archive match the extracted originals:

| Input | SHA-256 |
| --- | --- |
| Executable | `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265` |
| Archive, 2,291,764 bytes | `872fc4fdad2eab2ddd34387d2d3c04dd9731c84798d9fdc7bd05ca54e1567db8` |

## Container contract

The initial little-endian 64-bit value is the encrypted index length, **12,876 bytes** for this archive. The decoded index begins with a 64-bit member count; each record has three 64-bit values: encrypted member size, absolute file offset and UTF-8 name length, followed by that many name bytes. The independent reader checks complete consumption, distinct normalized relative names, bounded extents outside the index and absence of overlaps.

The resource transform uses the XXTEA-style 32-bit word operation recovered at `141cc5ed0`, little-endian words and `6 + 52 / word_count` rounds. Resource setup `14139c650` derives a 16-byte value from bytes in the unchanged executable; `141772250` converts the resulting string to bytes. Those bytes stay transient in the independent reader and are never written to its report. The wrapper `1417723b0` calls `141cc6030` and then appends a terminator. Padding validation is recovered at `141cc6250`. This is the archive's data-decoding contract, not an authentication implementation or a claim about cryptographic security.

Each decoded outer member contains a separate single-member ZIP whose name must match the index. The inspector reads it in memory, verifies the CRC and bounds the uncompressed size. It never extracts filesystem paths. All 229 real member CRCs passed, providing checks on the independently implemented decoding across the actual resource data. The parser permits only a simple local DOCTYPE name in device XML; entity definitions, internal subsets and external declarations are rejected. The schema asset is deliberately not interpreted.

The report counts 65 `native_pro_device`, 76 `native_intro_device` and 56 `osa_device` nodes. These are parsed node counts, not connected devices, licensed products or unique hardware counts. Other resource elements are not reclassified as device definitions.

## Phase and SL3 implications

`hid/hid_mwm_phase.xml` is present. Its allowlisted interoperability fields identify an `osa_device` with no MIDI component, HID enabled, wireless operation and two wireless decks. Its handshake-type label selects the actual Serato DJ HID path. No handshake material is exported or emulated, and the presence of this definition does not prove a connected Phase session. Phase remains a control source; it does not supply the SL3's audio driver or restore its missing complete resource definition.

The resource archive is now a concrete, understood data boundary for a possible later compatibility experiment. **No writer, modified archive, loose descriptor, executable patch or live integration test has been produced.** An experiment still needs a complete current descriptor/control/handshake contract, legitimate product/account behavior and an independently working audio transport. Decoding and checksums do not establish that Serato would accept a modified archive or connect a restored SL3 definition. Installed application files remain unchanged.

## Reproduction and validation

Run `.venv/Scripts/python.exe scripts/inspect-serato-resource-archive.py` for a compact read-only report. Add `--output` with a fresh path to retain per-member offsets, sizes, CRCs and decoded hashes locally. It exports no XML, resource key material or authentication fields. Existing output files are not overwritten.

`scripts/export-serato-resource-container.py` repeats the inspection, checks the installed identities, binds the focused source reports to actual unwind ranges and writes [sanitized evidence](evidence/serato500-resource-container.json). The committed evidence contains aggregate metadata and a digest of the local member metadata, not the proprietary resource contents.

Six targeted parser tests passed using `.venv/Scripts/python.exe -m unittest discover -s tests -p test_resource_archive.py -v`. They check valid extents, truncation/count/suffix failures, path normalization and duplicate rejection, overlap/out-of-range records, invalid block storage and inner ZIP name/count/CRC failures. The actual 229-member inspection separately verifies the positive decoding path. No native audio source changed, so earlier simulated native tests were not repeated or represented as hardware validation.
