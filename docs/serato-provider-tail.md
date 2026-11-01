# Remaining default resource readers

The checked Serato 5.0.0.1278 resource construction does not reveal an additional loose device-profile loader. Its extra `EffectResources` reader returns an empty directory listing. The other two default archive readers register stems and beat-grid-analysis namespaces. A separately found archive-registration call registers `userio_images`. These are static findings about the selected construction and direct call sites, not proof that every possible runtime extension is absent. [Verified evidence](evidence/serato500-provider-tail.json).

The original and installed executable both retain SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. The application was neither executed nor modified for this work. No archive was repacked, profile installed or account inspected.

## Constructed archive arguments

The verifier reconstructs these actual RDX/R8 arguments from the original straight-line x64 copy instructions. It models literal loads, register moves, stack/allocated storage and the single allocation call without executing native code. Both strings must have fully known bytes, lengths, capacities and terminators. This is stronger evidence than finding their names somewhere in the executable.

| Registration call | Prefix argument | Archive argument |
| --- | --- | --- |
| `14139bb6b` | `userio` | `userio_resources.bin` |
| `14139bcb5` | `components` | `dj_resources_components.bin` |
| `14139bddb` | `manifest` | `dj_resources_effect_manifest.bin` |
| `14139bf14` | `effects` | `dj_resources_effects.bin` |
| `14139c05a` | `fade_effects` | `dj_resources_fade_effects.bin` |
| `14139c38b` | `stems` | `bundle2.bin` |
| `14139c563` | `analysis_beatgrid` | `bundle1.bin` |
| `1415febe7` | `userio_images` | `userio_image_resources.bin` |

The first seven sites are in base resource setup `14139b980:14139c643`. Five calls use wrapper `1417763c0`; the other two call map-registration helper `1417765e0` directly. The image-registration site is in a different function and is not assigned a runtime position in the default reader vector here. Archive arguments are names supplied at these call boundaries; the table does not independently establish every final filesystem path.

Within base setup, three calls to `14139b810` construct archive-reader owners. That wrapper calls the already identified ArchiveResourceReader constructor at `141772cd0`. Base setup has four append calls, ordered `14139c0c9`, `14139c237`, `14139c3f9`, `14139c5c5`: the first archive reader, the effect reader, the stems archive reader and the analysis archive reader. The enclosing QRC setup calls this base setup at `140b0aa7a`, then appends QRC later at `140b0b18a`.

## Effect reader listing

Constructor `1413e37e0` installs vtable `142f345d0`. Its checked MSVC complete-object locator identifies `serato::audio::EffectResources`, and the hierarchy places the `serato::resources::ResourceReader` base at offset zero. Slot `+0x28`, the common reader listing slot, points directly to `1404a4b40`.

That complete leaf zeroes the output vector's three pointers and returns its output address. It has no conditional branch, filesystem access, enumeration call or returned entry. Regardless of which identifiers its predicate accepts, this listing implementation supplies no discovered device-description paths. This does not make assertions about all effect byte/text reads or saved-preset behaviour.

## Consequence and limits

Combined with the [first-reader dispatch and non-merged listings](serato-resource-loading.md), the [decoded main userio archive](serato-resource-container.md) and the [checked Qt indexes](serato-qrc-indexes.md), these additional readers supply no evidenced loose SL3 profile registration route through this construction. `userio_images` is a different registered namespace from `userio`, `userio_partner` and `userio_hidden_from_partners`.

This remains a bounded conclusion. Selected direct calls do not exhaust indirect registrations, later vector/map mutations, all plugin code or every payload. No runtime provider selection or application admission was observed. A discoverable profile would still need the [actual audio/DVS/component contract](current-serato-integration-decision.md) and a genuine current handshake; the missing historical DRIVER_API entry is not replaced with NONE or another device's identity.

The constrained copier's eight focused tests pass. They reject unknown string metadata, unproved terminators, unsupported branches/calls, writes into the original image or unallocated model memory, and incomplete literal reads; they check volatile-register clobbering and x64 zero-extension. All eight real construction blocks then reconstruct the expected arguments. Four fresh focused Ghidra decompilations completed within exact original unwind bounds; assembly and RTTI are checked independently. These are analysis/software results, not current Serato or hardware validation.

Regenerate with `./.venv/Scripts/python.exe scripts/export-serato-provider-tail.py`. Raw reports, navigation results, tests and exact verifier sources are retained under `artifacts/build/checkpoints/serato-provider-tail-20261101`. Native sources and the 48-test Windows worker were unchanged; no new device/UAC/driver/trust/security/firmware operation ran.
