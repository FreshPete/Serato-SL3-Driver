# Current MIDI processor gate: descriptor field sources

The previously unnamed vector that gates one current MIDI processor is now tied
to the XML property **`secret_serato_key`**, with one-byte elements. The response
predicate's second descriptor argument is **`midi_id`**, defaulted from the
16-bit product ID and optionally overridden by XML. This establishes field
provenance; it supplies no key values, successful handshake or SL3 admission.

Target: unchanged original/installed Windows Serato DJ Pro 5.0.0.1278, SHA-256
`66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`.
All addresses are preferred VAs. Vendor code and device operations were not run.

## Name, storage and creation gate

The class-bound `ControllerDescriptor` parser constructs two XML property names
through small field-name helpers. The new verifier checks the complete inspected
function extents/hashes and statically decodes **only those names**. It opens no
key-bearing XML archive and exports no property values or protocol messages.

| Property | Name construction | Parser use | Complete-object storage |
| --- | --- | --- | --- |
| `secret_key` | Copy `1405c01c0`, name helper `1405c71f0`, local string at RBP+0x400 | Lookup at `1405c8580`; byte append at `1405c85fb` | Begin/end/capacity at +0x160/+0x168/+0x170 |
| `secret_serato_key` | Copy `1405c0210`, name helper `1405c7280`, local string at RBP+0x3e0 | Lookup at `1405c8635`; byte append at `1405c86ab` | Begin/end/capacity at +0x178/+0x180/+0x188 |

The constructor at `1405bead0` installs the same RTTI-bound complete-object
vtable used by the parser, and initializes both pointer triples to zero. The
parser clears the second vector through `1405cd970` before reading its property;
that leaf sets the end pointer to the begin pointer. An absent property, or a
loop that appends no entries, leaves this vector empty on the checked parser
branch. A present property without a `value` attribute is not assigned a standalone
result: `strtok` can retain state between calls. This is not proof about every
later mutation or a live descriptor.

The second property's `value` is tokenized on comma/space delimiters. The checked
loop compares the first two token characters with `0x`, stops on a mismatch, calls
`strtol` with base 16 and appends the low byte. It does not establish strict token
or range validation. The full bounded append leaf has a byte-store/increment
fast path and a tail jump to growth code; the growth slow path is not exhaustively
recovered here. These facts identify byte storage, without publishing any values.

The [earlier consumer proof](serato-handshake-consumers.md) already connects the
primary descriptor to MIDI processor construction, manager ownership and its
response predicate. Its creation test compares +0x178 with +0x180: this is the
**`secret_serato_key` vector's nonemptiness**, not a generic MIDI port list.
Other pointer conditions still guard construction, and current kind 1/2 branches
are conditional protocol checks, not successful results. A changed kind or a
synthetic nonempty vector is not an implemented legitimate connection.

## `midi_id` argument

At `1405c84a1` the parser zero-extends complete-object word +0xaa (product ID)
and stores it at DWORD +0xd0. It then looks up `midi_id`; if present, the `value`
attribute is passed to the actual CRT import `strtoul(value, nullptr, 0)`, and EAX
overwrites +0xd0. An absent `midi_id` child retains the product-derived default in
this parser path. No strict conversion-error handling is established here.

Processor `140603de0` later reads this +0xd0 member into EDX before calling
`1406042f0`, alongside the kind in ECX. This names that previously unresolved
argument; it does not prove the actual value or protocol outcome for an SL3
session. The discontinued stub is constructed through a separate helper, so
this parser default is not assumed to have run for that stub.

## Historical comparison and consequence

The [prior verified historical SL3 projection](serato-legacy-sl3-descriptor.md)
records `secret_key` as empty in 2.5.5 and 2.5.6, and lists no
`secret_serato_key` value field. Both projected declarations use
`HANDSHAKE_TYPE_DRIVER_API`. Their executable hashes are rechecked here; the
comparison uses that earlier verified projection, not a newly executed legacy
connection or an exhaustive investigation of every possible secret source.

Together with the [current kind map](serato-clock-handshake.md), this rules out
treating the old descriptor as a ready-made contract for this current MIDI
processor. It neither restores the old driver-API path nor demonstrates a valid
current SL3 connection. No other product's material, identity, kind or reply is
adopted. A genuine supported descriptor/provider/control route remains required;
all other handshake engines and later field mutations are not exhausted.

## Verification and remaining work

Run `.venv/Scripts/python.exe scripts/export-serato-midi-field-sources.py`.
The [deterministic evidence](evidence/serato500-midi-field-sources.json) checks 85
instructions, five inspected functions, three complete bounded leaf bodies,
five actual CRT-import sites and constructor/parser RTTI. Five fresh focused
Ghidra functions provide a separate reduced-coverage view. The read-only import
ran without whole-program auto-analysis or extra library loading, exited zero
and discarded its temporary project. Complete analysis output remains private.

Regeneration is byte-identical. Native and the latest 334-check software
checkpoint inputs remain unchanged; those checks are not rerun or presented as
new physical evidence for this static-only change. The full Windows/current
Serato/two-deck DVS objective stays active: genuine current admission/control,
actual native/analogue audio/timing, protected deployment and remaining recovery
gaps are still unfinished. macOS is deferred.
