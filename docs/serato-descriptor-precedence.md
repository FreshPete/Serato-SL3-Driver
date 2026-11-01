# Current Serato descriptor registration and numeric precedence

Current Serato's `PrimaryDeviceManager` appends resource-loaded descriptors before its identity-only discontinued-device stubs. Its numeric lookup returns the first exact VID/PID/`bcd_device` match. If there is no exact match, it selects the highest strictly older revision, with later entries winning equal-revision ties. This resolves one selection boundary; it does not establish an external descriptor installation route or working SL3 integration.

Target: original and installed Windows x64 Serato DJ Pro 5.0.0.1278, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. Both hashes pass the new verifier. No application/vendor code was executed, no descriptor was injected and no application/archive/account/driver/USB identity was changed.

## Registration order

Constructor `1405033d0` installs RTTI-validated `PrimaryDeviceManager` vtable `142808488` and initializes its descriptor vector at `+0xd8`, end at `+0xe0`. On its enabled construction branch it calls registration `140503a40` at `140503568`.

That registration calls the resource descriptor factory at `140503d34`. Each non-null result is appended to the vector, advancing its end by 16 bytes at `140503da5`. The immediate predicate `140502ae0` is an eight-byte leaf which checks whether the shared pointer is null; it is not a duplicate-identity test. Later, the same registration constructs identity-only stubs through `1405d02e0` at `140504a63` and appends them to the same vector at `140504aaf`.

This is relative order between those two groups. It does not establish every resource file's listing order, success of every parse or all later runtime mutations. Resource discovery still has the earlier [first-reader/archive dispatch constraint](serato-resource-loading.md).

## Numeric lookup

Function `140505360` iterates the vector in order, reading fields at complete descriptor `+0xa8` (VID), `+0xaa` (PID) and `+0xac`. The parser explicitly associates `+0xac` with XML key `bcd_device`: the key reference is at `1405c83b8`, default store at `1405c83b1` and parsed store at `1405c83ec`.

For ordinary 16-bit identity/revision arguments:

| Condition | Observed result |
| --- | --- |
| Different VID or PID | Skip the entry. |
| Equal `bcd_device` | Return this entry immediately; first exact match wins. |
| Entry revision newer than requested | Skip it. |
| Entry revision older, no fallback yet | Retain it as fallback. |
| Another older entry has a higher revision | Replace fallback. |
| Another older entry has the same revision | Replace fallback; later tie wins. |
| No qualifying entry | Return null. |

The exact return branch is `1405053d6 → 140505449`. Fallback compares current and candidate revision at `140505411`; only a strictly greater current fallback skips replacement at `140505414`. The end returns the retained fallback at `140505446`.

The virtual fallback getter is also verified rather than inferred from a slot number. The descriptor's virtual-base table contributes `0x730` relative to its `+8` pointer, locating the interface at complete `+0x738`. Its vtable `14281cbe8`, slot `+0x28`, points to leaf `1405c6530`, which reads interface `-0x68c`: complete `+0xac`.

## Caller limits

Wrapper `1405050b0` first checks a nonempty interface name through slot `+0x30` and matcher `140b21c80`, then falls back to the numeric lookup. [Subsequent inspection](serato-name-matching.md) recovers its optional Windows-prefix normalization and regex-pattern call boundary. Complete engine semantics remain unverified, so the numeric rule must not be generalized over that earlier branch. Its wrapper obtains three identity values through `140b1a250`, `140b1a200` and `140b1a150`, passes them in EDX/R8D/R9D and preserves the returned descriptor across cleanup. Machine instructions at `140505229` and `140505261` establish that return even though focused decompilation inferred `void`.

A separate real call at `14218cc17` explicitly clears R9D first, requesting revision zero. Consequently, not every caller supplies a physical device's `bcdDevice`. This investigation does not establish which call/argument selected the connected SL3 at runtime, nor the complete construction of those device-info values.

## Integration consequence

For two zero-revision entries ordered resource descriptor then stub, a numeric request for revision zero selects the resource entry immediately. For a request above zero where both are only older fallbacks, the later stub wins the tie. These are conditional consequences of the recovered branches, not executed application tests.

The previously verified zeroed allocation and identity-only SL3 stub imply revision zero unless another component changes it. That still does not establish a successful original descriptor parse, a discoverable local provider or the actual runtime lookup. Supplying a file at an arbitrary loose path, appending an entry or selecting a different numeric identity cannot be treated as a complete adapter. Preserve the original hardware identity and legitimate product/account requirements.

Subsequent work traces the [separate aggregation collection](serato-aggregation-selection.md): the primary vector is transferred in order, but aggregation registration suppresses certain duplicate identities before its USB-side numeric lookup. That lookup explicitly receives an enumerated revision. This narrows the connection boundary without establishing a provider or live SL3 connection. The [original descriptor](serato-legacy-sl3-descriptor.md), [current handshake difference](serato-clock-handshake.md), [audio selector](serato-audio-routing.md) and [DVS contract](serato-dvs-contract.md) remain independent requirements. No current Serato audio/DVS result follows from lookup precedence.

## Reproduction

Run `.venv/Scripts/python.exe scripts/export-serato-descriptor-precedence.py` with the original binary and local focused reports available. The [generated evidence](evidence/serato500-descriptor-precedence.json) checks original/installed identity, RTTI, exact instructions, virtual-base arithmetic, leaf extent and focused unwind ranges. Incorrect exploratory ranges and the unrelated pad-mode observer are excluded from the evidence. This is static analysis only; no production source changed and no native tests needed repeating.
