# Historical cutoff: complete local caller comparison

The historical DriverAPI caller containing the previously checked Rane product-range predicate now has a complete instruction-index comparison between original Windows Serato DJ Pro 2.5.5.83 and 2.5.6.1001. Both pinned PE unwind ranges decode to **1,595 consecutive instructions**. Their **123 local direct branch/call edges** have identical instruction-index destinations. There are nine differences after explicitly setting aside relocated external-control targets, RIP references and image-address operands.

| Release | Compared preferred-VA range |
| --- | --- |
| 2.5.5 | `1400f9500:1400fb0d7` |
| 2.5.6 | `1400f9fb0:1400fbb87` |

Eight differences are numeric call-argument loads: paired uses of `0x47c → 0x483`, `0x584 → 0x58a`, and two paired uses of `0x47b → 0x482`. Their meanings are not inferred from the numbers. The ninth is `cmp byte ptr [rax + 0x2d1], 0` becoming `cmp byte ptr [rax + 0x2e9], 0`. It sits among floating-point comparisons and arithmetic; that context alone does not identify its object type or field meaning.

This establishes unchanged **local direct-edge structure** for this range, not equivalent execution. Each release has 402 explicitly inventoried references whose relocated targets are not equated. External callees, their state changes, referenced data, indirect control flow, mutable globals and runtime predecessors remain outside the comparison. A support exclusion in any of those places remains possible. This does not override vendor support status or prove that 2.5.6 admits an SL3.

## Displacement matching is not type matching

A fresh displacement scan found a 2.5.6 store using `+0x2e9` in function `1402d0850`. Checking the actual PE vtable and validated MSVC locator identifies its table as `CGUIAdvancedPopupMenu`, with receiver subobject offset `+0x138`, table `1449709b0`, slot `+0x18`. The selected handler case compares its second argument with `0x24e`, takes a value from a virtual call at `+0x10`, and stores AL at receiver-relative `+0x2e9`.

If dispatched through that table, the store is complete-object relative `+0x421`. There is no demonstrated type/provenance link from this receiver to the caller's read object. Treating the common displacement as proof of a descriptor eligibility flag would therefore be unsupported. No field, predicate, GUI setting or application was patched.

## Verification and consequence

The [exporter](../scripts/export-serato-cutoff-caller.py) pins both original executable hashes, verifies exact unwind boundaries and complete contiguous decoding, retains internal direct-edge indices and records every excluded relocation reference. It also checks the GUI candidate's locator signature/self/type/offset, vtable slot and selected original instructions. Three focused decompilation reports are pinned and complete for their requested ranges; they are navigation aids, not recovered buildable source or runtime traces.

Six new unit tests preserve changed branch destinations, integer operands and object displacements, expose external-call/RIP differences as explicitly uncompared, and reject partial decoding, branches into instruction interiors and different instruction counts. Together with the preceding three inventory tests, all nine checks pass. Actual exporter regeneration is byte-identical. The native runtime and its tested inputs are unchanged, so archived native or physical passes are not being reassigned or repeated.

The next application question is the data/callee provenance feeding this routine and the historical descriptor's application-support selection. The unchanged SL3 resource and retained API code still do not prove an eligible runtime session. Current 5.0.0 admission, genuine backend ownership, physical audio/timing and DVS remain unfinished. See [historical resource inventory](serato-cutoff-registration.md), [retained 2.5.6 API](serato256-sl3-api-path.md), [scope controller limitation](factory-scope-controller.md) and [current integration decision](current-serato-integration-decision.md).

Reproduce with `.venv/Scripts/python.exe scripts/export-serato-cutoff-caller.py`. [Compact original-byte evidence](evidence/serato-cutoff-caller-20261101.json). Focused reports and raw exploratory navigation remain in the private checkpoint. No vendor code, USB acquisition, audio, UAC prompt, registration, installation, account, identity, firmware or security-policy change ran.
