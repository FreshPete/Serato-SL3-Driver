# Current Serato descriptor resource loading

The current Windows application has a filesystem fallback in one resource
reader, but this does **not** establish a loose XML device-registration route.
Its ordinary `userio` resources are assigned to an earlier archive reader.
Resource dispatch stops at the first matching reader, including when that
reader returns no data. Directory listings are not merged across readers.

This extends the [supported-device contract](serato-supported-contract.md),
[audio selector](serato-audio-routing.md) and [DVS requirements](serato-dvs-contract.md).
It narrows an implementation candidate; it does not restore current Serato
support or demonstrate that every possible integration boundary is closed.

The [archive container has subsequently been decoded read-only](serato-resource-container.md): all 229 member ZIP CRCs pass, 228 XML members parse, and no SL3 identity appears in the inspected scalar descriptor fields. This establishes the actual archive contents within that scope, without changing installed files or demonstrating a writable runtime integration route.

Subsequent [Qt resource index inspection](serato-qrc-indexes.md) covers the nine registered external Qt bundles and eleven explicit embedded registration sites: 8,176 file entries, none in the three device-description folders and none with an SL3 filename. This is a separate index-only scope; it does not search arbitrary payload identities or exhaust all possible indirect providers.

The [remaining default reader inventory](serato-provider-tail.md) now verifies the other base-setup append sites: EffectResources has an empty listing, while the additional archive mappings concern stems and beat-grid analysis. An extra direct registration outside that setup maps `userio_images`. Eight actual argument pairs are reconstructed from original copy instructions. This narrows those additional candidates without claiming complete runtime-provider coverage.

Target: original Windows x64 Serato DJ Pro 5.0.0.1278, SHA256
`66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`.
The installed executable still matches. Addresses below are preferred image
VAs. All findings are static; application files, archives, configuration,
account state and drivers were not changed or executed for this investigation.

## Observed registration and parsing chain

Registration `0x140503A40` calls folder helper `0x1405037D0` for these folders:

| Group | Folders |
| --- | --- |
| Main | `userio/midi`, `userio/audio`, `userio/hid` |
| Partner | `userio_partner/midi`, `userio_partner/audio`, `userio_partner/hid` |
| Hidden from partners | `userio_hidden_from_partners/midi`, `userio_hidden_from_partners/audio`, `userio_hidden_from_partners/hid` |

The helper prefixes `resource:` (literal `0x142808588`), constructs a resource
identifier and calls manager enumeration `0x141771E50`. Registration iterates
the resulting paths and calls descriptor factory `0x1405CE9D0` at
`0x140503D34`. The factory calls type/product-ID pre-parser `0x1405C7330`
at `0x1405CEA6C`; that parser gets text through manager `0x141772090`
at `0x1405C73A4`, then parses XML. It recognizes `native_pro_device`,
`native_intro_device`, `osa_device` and product-ID lists. The chosen descriptor
class subsequently performs its full parse.

Thus descriptor XML is an application resource at this boundary. It is not
opened directly by the registration loop as an arbitrary Windows file.

## Observed reader dispatch and order

Both managers iterate the provider vector from its beginning, using 16-byte
shared-pointer entries. They call vtable +8 to ask whether a reader handles the
identifier. On the first true result:

| Manager | Action | Checked call |
| --- | --- | --- |
| Text `0x141772090` | Reader vtable +0x20, then checks/logs empty output | `0x141772117` |
| Listing `0x141771E50` | Reader vtable +0x28, then returns | `0x141771ECE` |

There is no retry of a later reader after that selected action. The listing
manager returns an empty vector if no reader matches.

RTTI and exact vtable contents independently identify two implementations:

| Reader | Primary vtable | Handles | Text | Listing |
| --- | --- | --- | --- | --- |
| `serato::resources::ArchiveResourceReader` | `0x142FABB98` | `0x141776AA0` | `0x141775360` | `0x1417738D0` |
| `serato::ui::qt::QRCResources` | `0x142E74538` | `0x140B0E5A0` | `0x140B0D760` | `0x140B0D280` |

QRC setup `0x140B0AA40` first constructs the base manager through
`0x14139B980` at `0x140B0AA7A`. That base setup registers prefix `userio`
against `userio_resources.bin` through `0x1417763C0` at `0x14139BB6B`
and appends its archive reader at `0x14139C0C9`. QRC is appended later at
`0x140B0B18A`. Append helper `0x141771C70` adds to the end of the vector.

Archive matching compares the scheme with the actual `resource` bytes, takes
the path prefix before `/` through `0x141773720`, and checks its prefix map.
Registration helper `0x1417765E0` populates that map at reader +0x28; archive
existence is not the predicate used by the manager to select QRC instead.
The archive reader's byte path resolves the mapped archive/member before
reading. Its listing walks the archive member index. It does not merge an
arbitrary loose directory with that index.

These observations establish relative order in this construction path.
Runtime selection of this setup and any later provider changes have not been
instrumented. The `userio` mapping must not be generalized to all the other
folder prefixes without tracing their registration too.

## Observed QRC fallback and its limit

QRC constructor `0x140B0BA00` stores an optional root string at +0x20, with
length +0x30. Text reader `0x140B0D760` has two paths:

- Without a root, it reads a colon-prefixed Qt resource.
- With a root, it first reads the combined root/path through filesystem stream
  helper `0x140B0BF50`. If the resulting string is empty, it falls back to
  `QResource` helper `0x140B0BD40`.

The empty-result branch and fallback call are checked at `0x140B0DC53`
through `0x140B0DC6A`. The filesystem helper uses C++ file/stream buffers;
the other helper calls the actual Qt `QResource` imports, including validity
and uncompressed-data queries.

QRC listing `0x140B0D280` constructs its `QDirIterator` from a colon-prefixed
identifier path. It does not use the instance's optional filesystem root.
So even for an identifier handled by QRC, the text fallback is not proof that
a new loose file becomes discoverable through this listing.

The root comes from `0x141CB4C40`, which combines a module-derived directory
with a stored resource-folder component and returns empty if its filesystem
validation fails. The [default initialization is now recovered](#module-derived-root-default):
the component is `.`. No particular installed `Data` path is established as an
enabled override. The validation helper has not been proved to be a
directory-only predicate; the earlier description as a directory check was
too strong.

## Module-derived root default

Path-state accessor `14083dfe0` returns the state at `143fe8860`. Its guarded
initialization calls helper `1420fc4b0` with the state as output. That helper
calls `1420fc5b0`, whose verified `GetModuleHandleExW` import uses flag 4 and
an address in this executable (`1404a67c0`), then calls the actual
`GetModuleFileNameW` import with capacity 260 wide characters. This is a
module-path query, not a registry/environment override. The helper's
zero-return/error path and possible long-path behavior are not runtime tested.

The accessor initializes the next three string components at state `+0x20`,
`+0x40` and `+0x60` with bytes `2e 00` (`.` and its terminator). Root builder
`141cb4c40` passes the state to directory-part helper `141cb4400`, copies
component `+0x20`, joins the two strings through `141cb6c00`, and calls
filesystem-validation helper `141cb1230`. The directory-part path converts
the stored module path and uses separator-aware helper `14210a070`, whose
instructions test both slash and backslash. Some focused decompilations omit
the second argument; the actual RCX/RDX assignments are verified.

Under this default initialization and successful path queries, the root is
derived from the containing executable directory plus `.`. This resolves the
default; it does not prove exhaustive absence of later writes, runtime provider
changes or another integration mechanism. The identified accessor callers
were inspected without executing their registry, shell or application paths.
No configuration was read from or written to the application's registry by
this analysis.

The archive-reader precedence and QRC listing limitation above still apply.
A module-relative text fallback is not a discoverable loose descriptor
provider. No file was placed in the application directory and no archive was
changed to test that hypothesis.

The [root-default evidence](evidence/serato500-resource-root.json) pins original
and installed PE identity, actual OS imports, module-address/flag arguments,
default stores, builder calls and focused-report ranges. Reproduce with
`.venv/Scripts/python.exe scripts/export-serato-resource-root.py`. This runs
only the original analysis script; vendor code and OS module-query imports
are inspected as bytes, not invoked.

## Implementation consequence and next work

**Interpretation:** simply adding `Data/userio/audio/SL3.xml` is not an
evidence-backed integration test. The mapped archive can claim `userio`
before the QRC filesystem fallback, and neither manager merges providers.
Missing archive/member output does not by itself activate a later reader.
No such file was installed, no archive was repacked and no support or account
check was patched.

The [original SL3 descriptor is now recovered](serato-legacy-sl3-descriptor.md)
from both 2.5.5 and 2.5.6. The [numeric descriptor precedence](serato-descriptor-precedence.md) is also recovered: first exact revision wins, while equal older fallbacks favor later entries. The module-relative root default is now verified too. Trace the relevant connection caller and any supported provider configuration beyond this default next. A
usable integration must supply the recovered audio/DVS/control contract and
preserve legitimate product/account requirements. Physical driver admission,
PCM, latency, routing and two-deck DVS remain separate unverified gates.

## Reproduction

Run `.venv/Scripts/python.exe scripts/export-serato-resource-evidence.py` from
the repository after generating the focused reports listed in its output.
It checks original/installed PE identity, exact RTTI/vtable slots, relevant
instructions and call/branch targets, literal bytes and focused unwind ranges.
The [sanitized evidence](evidence/serato500-resource-dispatch.json) retains
bounded assembly and report/archive hashes. Focused reports, vendor binaries
and the vendor archive remain in ignored local analysis/artifact directories.
The report hashes record this analysis snapshot; they do not claim complete
control-flow recovery or runtime confirmation.
