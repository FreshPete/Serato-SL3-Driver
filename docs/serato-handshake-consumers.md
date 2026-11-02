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
| Kind argument | The processor reads its stored descriptor pointer, loads `+0x154` into ECX, another field `+0xd0` into EDX, and calls `1406042f0` at `140603ef9`. The second field's full meaning is not assigned. |

This establishes pointer/field provenance beyond merely finding the same numeric
offset in an unrelated object. Static data flow still does not observe actual
runtime instances, connected hardware or indirect-callee behaviour.

## Creation gate and response predicate

Before construction, callback `140525710` calls leaf `1405c7de0`. That exact
18-byte function returns whether descriptor pointers at `+0x178` and `+0x180`
differ. A false result skips the processor allocation/binding block. Additional
pointer conditions also guard it. The XML key, element type and runtime contents
of this vector are not established here; it is not assumed populated for an SL3.
Changing a kind integer alone does not create this processor.

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
