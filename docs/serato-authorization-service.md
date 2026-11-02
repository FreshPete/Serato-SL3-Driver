# USB-only readiness helper: authorization-service receiver

The current USB helper's service calls do **not** target the generic `DriverAPI`. The accessor used by `CUSBAudioManager` obtains an object whose checked factory constructs either `serato::authorization::RLMAuthorization` or `serato::authorization::JWTAuthorization`. Equal vtable slot offsets on those unrelated objects do not imply equal methods or results. [Verified original-byte evidence](evidence/serato500-authorization-service.json).

This resolves the receiver behind the previously unassigned service calls. It does not query or modify account/license state, establish the complete authorization semantics, or prove an admitted SL3 session. The [NONE descriptor](serato-sl3-candidate.md) remains an unverified connection/control hypothesis; its [offline archive](serato-sl3-archive.md) is undeployed.

## Accessor and object construction

The exact current Windows executable remains SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`, matching the installed copy. Preferred VAs are shown below.

The USB helper calls `141960f80` at `14070ffcb` and again at `14070ffe7`, uses the returned object as RCX and dispatches its `+0xa0` and conditional `+0x90` methods. This is the helper previously traced to message 0x693 and the stored-byte OR result.

Accessor `141960f80` passes state `14402c860` to initializer `1419605a0`, then loads its returned service pointer from global `14402c858`. The initializer uses actual `KERNEL32.dll!InitOnceBeginInitialize` and `InitOnceComplete` imports. On its selected initialization branch it calls factory `141960a60`, moves the returned owned pointer and stores it in that same global.

The factory compares DWORD `14402c850` with zero:

| Checked factory branch | Allocation / constructor | RTTI-bound complete vtable |
| --- | --- | --- |
| Selector zero | 0xe8 bytes / `141984590` | `142fd12b8`, `RLMAuthorization` |
| Selector nonzero | 0x38 bytes / `14197fce0` | `142fd09c8`, `JWTAuthorization` |

Both constructors call base initialization `1419606b0` and install the respective table at complete-object offset zero. The exporter verifies each MSVC complete-object locator, decorated type name and constructor vtable store. This is a static branch identity; the live selector and actual backend were not read. Initializer allocation/error handling is not evidence of a successful live service object or exhaustive absence of later global writes.

## Distinct method bindings

| Receiver | Slot +0x90 | Slot +0xa0 |
| --- | --- | --- |
| RLMAuthorization | `14198f450` | `14198a130` |
| JWTAuthorization | `141983630` | `141982ba0` |
| Generic DriverAPI | `1404a4550` (previously verified constant false) | `1404a4540` (previously verified constant true) |

The third row is the separately RTTI-bound table `142e86360`. Its `+0x90` constant-false method cannot be substituted as the result of this helper's authorization-service call. Conversely, identifying the service does not prove either authorization method returns true, implements the historical Rane controls or makes the SL3 eligible.

As the [USB-arrival evidence](serato-usb-arrival.md) already establishes, the conditional service result is packaged into message 0x693. The helper subsequently reads stored bytes complete `+0x71` and `+0x70`, returning their OR. Message 0x693 updates the first of these and 0x692 the second under the checked handler. Message delivery timing, all producers of 0x692, actual permitted service results and later state changes remain unfinished. Neither an authorization type name nor the helper's Boolean proves audio readiness or DVS.

## Implementation consequence

Keep the genuine SL3 candidate identity and the original application authorization behavior. Do not implement a historical seven-export Rane shim merely to satisfy these unrelated service slots, and do not replace a service result/state byte with a fabricated value. The seven-export caller remains unestablished in the current target. A real current integration still needs its descriptor to load and parse, the permitted service/state path to work, actual ASIO selection/control readiness and physical audio/DVS validation.

No account was inspected, entitlement changed, response/token/key emitted, service result emulated or license purchased. There is no conclusion that purchasing or possessing any particular license would admit an SL3. Normal account/product behavior remains a required part of a future application test.

## Verification

```powershell
.venv/Scripts/python.exe scripts/export-serato-authorization-service.py
# Optional fresh report path; existing output is refused before analysis.
.venv/Scripts/python.exe scripts/export-serato-authorization-service.py --output analysis/service-binding-NAME.json
```

The exporter checks 33 new instruction facts, repeats 208 prior arrival checks, binds three RTTI tables and compares distinct service slots. Five fresh focused functions complete within their exact PE unwind extents: `141960f80:141960fa1`, `1419605a0:14196063c`, `141960a60:141960ad7`, `141984590:141984777` and `14197fce0:14197fd09`. The isolated unchanged import disables whole-program analysis and library loading; its log confirms zero additional files and discarded read-only import. The project is empty afterward. Whole-program, authorization-semantic and indirect-call completeness are not claimed.

A second export is identical after console newline normalization, and existing-output refusal preserves the original evidence. Raw focused output remains private; public evidence contains selected interoperability metadata and hashes, without full vendor pseudocode or authentication material. No new native tests are claimed for this static-only change. Native audio sources, driver/binding/trust/security, firmware, installed app/archive and physical device are unchanged; current SL3/audio/DVS remain unverified and Mac is deferred.
