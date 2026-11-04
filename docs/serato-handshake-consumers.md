# Current handshake kind consumption: MIDI response path and HID comparison

Current Serato's parsed handshake kind now has a checked **component-specific**
consumer. A MIDI input-manager callback reaches a response predicate with branches
for current numeric kinds 1 and 2. A separately RTTI-bound HID callback compares
a descriptor-shaped field with 6. This is not a complete handshake dispatcher,
an admitted SL3 connection or evidence that another device's kind can replace
the historical driver-API path.

Target: unchanged original/installed Windows 5.0.0.1278, SHA-256
`66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`.
Addresses are preferred VAs. No vendor program, handshake, device, account or
registry operation ran, and no authentication material is published.

## Descriptor-to-MIDI provenance

The parser at `1405c7f90` receives the complete object through RCX, saves it in
RSI, and writes the mapped kind at complete-object `+0x154`. Its vtable slot is
bound to `ControllerDescriptor` with complete-object RTTI offset zero.
The earlier [primary lookup proof](serato-descriptor-precedence.md) establishes
wrapper `1405050b0`'s descriptor result; its checked return preservation remains
bound to the same original image.

The new chain is:

| Boundary | Checked evidence |
| --- | --- |
| Primary lookup | MIDI connection callback `140525710` calls `1405050b0` at `140525a3f`, saving the returned pointer in R15. |
| Continuing descriptor value | R15 has no intervening write on the path to processor construction. Its only restore in that interval is a straight early-return epilogue, which the verifier checks through `ret`. |
| Construction | The callback passes R15 in RDX to `140603d40`; the constructor stores RDX at new object `+0`, preserves its own pointer in RDI and returns it in RAX. Its three split unwind regions are checked separately. |
| Manager ownership | Setter `14060a8f0`, called at `140526aeb`, stores the processor at manager `+0x108`. |
| Input callback type | `CMIDIInputManager` vtable `142823cc0`, slot `+0x18`, targets `140609900`. |
| Callback to processor | That callback loads its `+0x108` member and calls processor `140603de0` at `140609d8a`. |
| Kind argument | The processor reads its stored descriptor pointer, loads `+0x154` into ECX, another field `+0xd0` into EDX, and calls `1406042f0` at `140603ef9`. [Later field-source tracing](serato-midi-field-sources.md) identifies the second field as `midi_id`. |

This establishes pointer/field provenance beyond merely finding the same numeric
offset in an unrelated object. Static data flow still does not observe actual
runtime instances, connected hardware or indirect-callee behaviour.

## Creation gate and response predicate

Before construction, callback `140525710` calls leaf `1405c7de0`. That exact
18-byte function returns whether descriptor pointers at `+0x178` and `+0x180`
differ. A false result skips the processor allocation/binding block. Additional
pointer conditions also guard it. [Later source tracing](serato-midi-field-sources.md)
identifies the XML property as `secret_serato_key` and its elements as bytes;
actual runtime contents remain unobserved, and it is not assumed populated for
an SL3. Changing a kind integer alone does not create this processor.

For an incoming 32-bit kind at predicate `1406042f0`, checked instructions subtract
one and branch on zero, then compare the remainder with one:

| Current kind | Static branch |
| --- | --- |
| 1, `SERATO_DJ` | `1406043b2`, conditional protocol checking |
| 2, `NUMARK` | `140604330`, a different response comparison |
| Other kind values | Cleanup and return false at `14060431b` |

These are branch destinations, **not successful protocol results**. No response
template, message constant, key, challenge or reply bytes are exported or copied
into the rebuilt driver. The report's kind projection is static, not an executed
application test. It supplies no justification for changing the real SL3 identity
or adopting a different product's handshake.

## Adding a MIDI port to the SL3

The original SL3 descriptor explicitly declares `midi_direction=none` and uses the legacy Rane driver API for control. The physical SL3's control interface is vendor-specific and has interrupt endpoints. An operating-system MIDI endpoint would therefore be a new translation layer with its own message contract. [Original descriptor](serato-legacy-sl3-descriptor.md) · [Physical USB configuration](findings.md).

The observed Serato 5.0 SL3 composite is USB-only. Its device-added callback publishes the USB arrival message only when neither HID nor MIDI is attached. If a new MIDI endpoint were matched and attached to that composite, the observed USB-only branch would no longer publish the arrival message. A positive result would require a separate, verified MIDI selection route. [USB arrival branch](serato-usb-arrival.md) · [Live selection trace](serato-archive-deployment.md#live-device-selection-trace).

Original-byte inspection of the two MIDI callback bodies found descriptor lookups and the existing conditional MIDI processor binding. In the checked callback at `14052d370`, the two direct message-constructor calls use IDs `0x2d0` and `0x645`, with subscribers identified as licence/device notifications and an information-panel controller. Those calls do not publish the primary selection message `0x2ca` or the USB manager initialization message `0x5d4`. The checked MIDI processor creation path also requires descriptor material absent from the historical SL3 profile. These bounds leave other indirect paths open, but provide no evidence that a bare MIDI endpoint would select the SL3.

An attended name-association test created a transient [Windows MIDI Services loopback pair](https://microsoft.github.io/MIDI/sdk-reference/Transports/Loopback/). The schema-validated private SL3 definition added the unique MIDI port name and changed MIDI direction from `none` to `in`, preserving the SL3 USB identity and other fields. The installed original archive was preserved for rollback. The virtual port advertised its actual zero VID/PID, and the test sent no MIDI commands.

Serato saw and added the named loopback as a separate MIDI device. It kept retrying aggregation for the physical SL3 through attempt 45 in the observed window, did not add the SL3, and stayed on offline audio. The device callback trace showed a MIDI-only composite and no USB arrival publication for the SL3. The test ended before the one-minute retry period completed, so it establishes no association during that window, not the terminal retry result or behavior of a genuine combined hardware endpoint. Afterward both loopbacks, the temporary driver registration and the temporary archive were removed, and restoration was verified.

A second run observed Serato for 80 seconds. It added both loopback ports separately and exhausted the SL3 retry window. After attempt 119, Serato logged `Device MIDI connection is not ready [1cc5_0001_0000#1]`. The only successful audio startup was `Offline Device`, and the trace recorded no named audio selection. The original archive was restored, and removal of the temporary ASIO registration and loopback ports was verified.

### What the MIDI matcher requires

In the original 5.0.0.1278 image, the composite worker calls `1421df830` at `1421dc11f` with the selected descriptor. The helper reads the descriptor's [shared `midi_name` getter](serato-sl3-selection.md) at `1421df89c`. A nonempty name goes to `1421df1e0`, which invokes the [Windows name matcher](serato-name-matching.md) at `1421df255` and tests direction at `1421df286`. An empty name takes the separate VID/PID path through `1421df650`, which also checks direction. The dispatcher makes no VID/PID fallback after a failed name lookup on this path.

The shared direction predicate `1421dfbe0` requires exactly one port side for direction 1 or 2 and both sides for direction 3. The test descriptor requested `in` (1), while Serato logged the named loopback as `duplex`. The combination cannot pass the direction predicate if the probe is still available to the SL3 worker. The log also shows that a separate worker acquired the probe during the SL3's first retry, so the trace does not establish that the SL3 worker reached the predicate for that endpoint. A controlled retest can keep the same name and physical identity, request duplex, and trace which worker takes the port. Successful pairing would still need a separate ASIO selection check.

The duplex retest changed only the descriptor's MIDI direction and kept the same named loopback and physical SL3 identity. Serato reported the probe as duplex and a separate worker acquired it on the SL3's first retry. The SL3 again reached attempt 119 and reported its MIDI connection was not ready. The trace observed no successful descriptor-based MIDI take, no named audio selection and no load of `sl3_asio.dll`. Offline audio was the only successful startup. This leaves endpoint availability or ownership open as a separate question from direction. The original archive was restored and removal of the temporary ASIO registration and MIDI ports was verified.

### Existing resource slot replacement

An attended Windows test put the exact earlier USB-only SL3 XML into the existing Denon DS1 archive slot. The candidate kept 229 indexed members, verified the other 228 members and retained the SL3's real `1cc5:0001` identity. This was an archive-slot replacement. Serato built its runtime descriptors from that archive through its normal loader.

Serato logged `Device Added: Rane SL3` and emitted the genuine USB arrival message `0x2d4`. It listed the rebuilt ASIO driver during enumeration. The 24-second trace showed no receipt by the traced USB audio handler, no named audio selection and no load of `sl3_asio.dll`. The only successful audio startup was `Offline Device`. Thus the existing resource slot reproduced the additive test's selection result. The original archive was restored and temporary ASIO registration removal verified.

A second attended test loaded the additive archive as a source for the same SL3 object, then replaced the DS1 entry in memory at the end of descriptor registration. It moved the SL3 object from index 195 to the DS1 slot at 49, removed its old entry, and reduced the vector from 235 to 234 entries. It preserved the physical SL3 USB identity and used no virtual MIDI endpoint. Serato added the SL3 and published `0x2d4`, but the 24-second trace showed only default audio selection and no rebuilt DLL load. The original resource archive and temporary ASIO registration were cleaned up and verified. This tests the Windows runtime descriptor slot independently of USB identity substitution and MIDI.

### Process-local USB alias

An independent Windows test changed only the PID returned to Serato's USB discovery call, from `0001` to a synthetic `fffe`. The otherwise identical USB-only SL3 spec used that PID so the lookup could succeed. The test used the additive archive and no virtual MIDI endpoint or runtime slot replacement. Windows continued to enumerate the physical `1cc5:0001` device.

Serato aggregated `1cc5:fffe`, added `Rane SL3` and emitted `0x2d4` carrying the alias. The 24-second trace showed no receipt by the traced USB audio handler, no named audio selection and no rebuilt ASIO DLL load. Serato listed the rebuilt ASIO driver during enumeration, while offline audio was the only successful startup. The original archive was restored and the temporary ASIO registration removed. This isolates one synthetic identity change and does not test the three changes in combination.

### Combined Windows test

The 80-second combined run verified the in-memory DS1 slot replacement, the process-local `1cc5:fffe` USB alias, and Windows' duplex MIDI loopback. Serato assigned the probe to a separate MIDI device. The aliased SL3 reached attempt 119 and reported that its MIDI connection was not ready. The trace showed no successful descriptor-based MIDI take, no named audio selection, and no load of `sl3_asio.dll`. Offline audio was the only successful startup. This tests the three Windows implementations together. The MIDI loopback is a standalone endpoint and did not supply the SL3 with an associated control interface. Cleanup restored the original archive and verified removal of the temporary ASIO registration and both MIDI endpoints.

### MIDI associated with the SL3

An 80-second follow-up kept the combined configuration and reserved the named probe in Serato's MIDI connection list. A process-local diagnostic returned an empty result only when the standalone aggregation caller tried to take that exact test endpoint by URI. This left the endpoint available to the SL3's existing descriptor-based matcher. The trace confirmed a name match and a successful MIDI take on the SL3 aggregation thread during its first attempt. The application logged `Device Added: Rane SL3`. This is an application-level association of a real virtual endpoint. It does not implement SL3 control messages or establish a persistent Windows MIDI binding.

Serato enumerated the rebuilt ASIO driver. Offline audio was the only successful startup, with no named audio selection, no rebuilt ASIO DLL load and no USB-only arrival publication in the trace. The original archive was restored and removal of the temporary ASIO registration and MIDI endpoints was verified.

## Separate HID branch

Vtable `142810290` is RTTI-bound to `HidManager`, subobject offset 16; slot `+8`
targets `140546110`. The callback preserves its third argument in R14. In the
checked conditional branch it reads that argument's pointee and compares field
`+0x154` with 6 before calling `140544620`. The current parser map labels 6
`SERATO_DJ_HID`.

All incoming HID descriptor provenance and callers are **not exhausted**, so this
separate comparison is not promoted into the fully traced MIDI pointer chain or
a universal HID connection rule. Runtime Phase/SL3 connection, actual selected
descriptor and protocol success remain unobserved.

The later [HID verifier investigation](serato-hid-verifier.md) now identifies the preceding control-section gate, conditionally resolves the concrete descriptor getter, binds the allocated verifier type and traces its separate primary numeric lookup. It still does not exhaust incoming descriptor provenance or establish protocol success.

## Reproduction and consequence

Run `.venv/Scripts/python.exe scripts/export-serato-handshake-consumers.py`.
The [LF-stable evidence](evidence/serato500-handshake-consumers.json) checks 56
exact instructions, three RTTI/vtable bindings, the current eight labels/stores,
the small vector predicate and four fresh focused Ghidra results. Export and
byte-identical regeneration pass. The original/installed hashes are rechecked.

The Ghidra import was read-only, with automatic whole-program analysis and library
loading disabled. It loaded no additional files, exited zero and discarded its
temporary project. Complete pseudocode and navigation records remain private;
bounded instruction facts and original verifier are published. No native source
or runtime input changed, so prior software tests were not rerun or represented
as new physical evidence.

The [earlier map result](serato-clock-handshake.md) remains exact: the historical
`DRIVER_API` text is absent from the recovered current map; old integer 5 is now
`AKAI`. This new work identifies selected consumers, not every current engine or
raw-USB path. It does not prove universal removal, supply a supported extension,
permit a fabricated reply or replace legitimate product/account requirements.
The unchanged genuine SL3 still has its independently verified discontinued
support branch; these consumers are not a newly observed SL3 session or gate.

A concrete genuine descriptor/provider/connection path, actual current control
interface, native/analogue audio, measured timing and real two-deck DVS remain
unfinished. The full Windows/current-Serato goal remains active; macOS is deferred.
