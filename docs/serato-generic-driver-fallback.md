# Legacy SL3 loader retention and current generic DriverAPI

A replacement DLL exposing the seven historical `sl3_*` exports is not an identified drop-in integration hook for the checked current Serato executable. Both historical targets retain those names and `RaneSL3API`; the installed 5.0.0 target does not contain their checked literal patterns. Its generic `DriverAPI` is a different, RTTI-bound base object with keyed integer state and constant Boolean methods. This narrows the implementation choice; it does not prove every possible provider is absent or establish an admitted SL3 session.

Targets are the pinned original Windows 2.5.5, 2.5.6 and 5.0.0 executables. The installed 5.0.0.1278 copy remains SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. [Reproducible evidence](evidence/serato500-generic-driver-fallback.json) verifies 45 new instructions, rechecks 322 earlier contract instructions, checks 24 virtual slots, four complete small functions and six fresh focused functions. Vendor code was read as data, never run or modified.

## Bounded named-loader comparison

| Terminated byte pattern | 2.5.5 | 2.5.6 | 5.0.0 |
| --- | --- | --- | --- |
| `RaneAsioSL3.dll` | One UTF-16LE hit | One UTF-16LE hit | No ASCII/UTF-16LE hits |
| Decorated `RaneSL3API` type name | One ASCII hit | One ASCII hit | No ASCII/UTF-16LE hits |
| Each of the seven historical export names | One ASCII hit each | One ASCII hit each | No ASCII/UTF-16LE hits |

The exports are `sl3_open`, `sl3_close`, `sl3_driver_timer`, `sl3_get_usb_port_status`, `sl3_get_audio_controls`, `sl3_set_audio_controls` and `sl3_set_thrustate_callback`. The filename scan folds ASCII case; other patterns are exact. The evidence records counts, original image identities and the earlier [2.5.6 named-loader binding](serato256-sl3-api-path.md). Retention in 2.5.6 still does not override its documented exclusion or prove a working runtime path.

This scan covers these whole executable files and these terminated byte patterns. Other DLLs, alternate names, generated/encrypted strings and indirect or external providers are outside that absence claim. No global claim that all corresponding functionality has been deleted is made.

## The current generic object

Current constructor `140bff9d0` installs table `142e86360`, RTTI-bound to `serato::device::driver::DriverAPI`, complete offset zero. Its direct call set contains only the two checked allocation/epilogue helper sites. The body initializes members and stores the incoming string object at `+0x60`. It does not directly call a library loader or export resolver.

There are five direct calls to this base constructor within the inspected factory. At the final checked call `140bfe0b5`, the factory passes a descriptor-supplied string from virtual slot `+0x48`, then reads the constructor result. This does not prove the real SL3 reaches that call. The prior factory evidence still has seven explicit Rane product matches, none PID 1; all other predicates, cached state and actual branch entry are not exhausted here.

Selected base slots are independently checked:

| Slot | Target and local behavior |
| --- | --- |
| `+0x08`, `+0xa0` | `1404a4540`: constant true |
| `+0x38`, `+0x90` | `1404a4550`: constant false |
| `+0x18` | `140bfffc0`: unsigned input index below four |
| `+0x20` | `140bfff40`: query keyed integer state under member `+0x50` |
| `+0x28` | `140c00360`: obtain a keyed value slot under `+0x50`, write the incoming integer, return true |
| `+0x50` | `140c00240`: pass the string at `+0x60` to the separately checked registry-string predicate `140bfffd0` |

The constant-false `+0x90` is distinct from the string/key readiness path. The getter/setter's local cache behavior is not proof of a USB request or hardware completion. Observers, subclasses, indirect consumers and every transitive callee are not universally exhausted. These methods are not assigned unproved licensing or audio-success semantics.

This explains why a generic DriverAPI object or a true return must not be treated as restored Rane control communication. It does not alter the actual discontinued support-map branch, the audio API/name selector or DVS/account requirements.

## Implementation consequence

Do not prioritize a historical seven-export shim as a direct current-Serato hook without a demonstrated caller. The original ASIO/control implementation can continue independently, while current integration still needs a concrete genuine SL3 description/provider, connection/control behavior, audio selection and real application/DVS validation. A vendor-supported extension has not been identified. An application/package compatibility experiment would need its own complete contract, integrity/signature assessment and reversible deployment before selection; no patch or override is selected by this comparison.

Generic ASIO availability, Phase accessory data, a changed support value or a successfully decoded resource is insufficient evidence for those requirements. No foreign identity, fabricated response, account state, resource or installed binary was substituted.

## Reproduction and scope

Run `.venv/Scripts/python.exe scripts/export-serato-generic-driver-fallback.py` with the pinned originals and ignored focused reports available. New focused ranges are `140bff9d0:140bffa8e`, `140bffb30:140bfff39`, `140bfff40:140bfffa9`, `140c00360:140c00384`, `140c00240:140c0025f` and `140bfffd0:140c00228`.

The fresh Ghidra input was an isolated byte-identical copy of the original executable, imported with whole-program analysis disabled, read-only mode, library loading disabled and an explicit empty library search directory. The log reports zero additional program files, a discarded import and success; the temporary project is absent. The isolated copy and full pseudocode remain private. These controls do not improve control-flow/type coverage or make inferred decompiler prototypes a verified ABI; selected machine instructions remain authoritative.

Export and byte-identical regeneration pass. Both native build/source and prepared trace pins remain unchanged; native tests were not rerun. No application, device, binding, registry, trust or security change ran. Protected deployment, native/analogue audio/timing, stable reopening and genuine current SL3/two-deck DVS remain unverified. The full Windows goal remains active and macOS deferred.
