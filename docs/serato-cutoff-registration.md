# Historical cutoff: complete startup resource inventory

Both original Windows releases still register exactly one scalar SL3 identity in their startup resource arrays: resource 203 in 2.5.5 and resource 207 in 2.5.6. All **156 + 157 registered resource XMLs** were decoded and parsed, rather than selecting only the already-known SL3 file. No second scalar `vendor_id=0x1cc5`, `product_id=1` declaration appears in those arrays. This rules out a duplicate resource XML of that form as the explanation for the support cutoff, within this scope.

The SL3 XML remains byte-identical, SHA-256 `314e81ffb5d052e53280903d543107c8223e99ff1f4e200311a2b3d90e49154c`, with `native_pro_device`, name `Rane SL3` and supported-app declaration `Serato DJ`. Across the complete inventories, 136 XML hashes are shared, 20 appear only in 2.5.5 and 21 only in 2.5.6. Resource IDs are version-specific; changed IDs alone are not changed device definitions. These counts concern distinct XML hashes, not an inferred number of newly supported products.

Some complete resources have no null terminator inside their encrypted block allocation. The inventory accepts them only when the entire bounded decoded block parses as XML. For null-terminated resources it requires every remaining byte to be zero. The prior SL3-only terminator assumption cannot be applied to all resources. DTD/entity declarations, malformed XML, oversized blocks and out-of-range scalar identities are refused. Only identity/application projections and hashes are retained; no full XML, key, secret value or executable is exported into Git.

The original resource reader, array source, parser call, PE identity, cipher constants and published ECB vectors are rechecked through the earlier [historical descriptor verifier](serato-legacy-sl3-descriptor.md). Fresh focused startup decompilations completed for `1402afb50:1402b28b4` and `1402b0990:1402b3724`; their hashes and ranges are bound separately. Their completeness flag describes the requested decompilation, not all indirect calls, runtime predecessors or successful parser acceptance.

A separate inspected Rane-specific machine-code predicate is unchanged in meaning:

| Release | VID constant load | Unsigned product range |
| --- | --- | --- |
| 2.5.5 | `1400fa7a8` | Subtract `0x18`, compare the low 16 bits against 1, skip on unsigned above. |
| 2.5.6 | `1400fb258` | The same predicate. |

That range body selects product values `0x18` and `0x19`. Product 1 wraps to `0xffe9` after subtraction and skips the body; this branch therefore does not explain SL3 exclusion. The finding concerns this literal predicate only, without assuming the whole routine's role or excluding data-driven, packed-identity or indirect checks elsewhere.

The cutoff's actual runtime eligibility mechanism remains unresolved. The results narrow two specific alternatives—another scalar SL3 entry in the registered XMLs and this Rane product-range body. They do not establish that 2.5.6 runs the SL3, contradict vendor support status, select an application patch or restore 5.0.0's missing driver-API/descriptor contract. Current Serato admission, genuine backend ownership and real DVS remain separate unfinished requirements.

Reproduce with `scripts/export-serato-cutoff-registration.py --inventory-output analysis/NEW-INVENTORY.json`. [Compact evidence](evidence/serato-cutoff-registration-20261101.json). Three tests cover exact-block versus zero-padded XML, typed nested identities, secret omission and invalid-input refusal. The raw inventories, focused reports, input scripts and projected evidence are preserved under `artifacts/build/checkpoints/serato-cutoff-registration-20261101`. No vendor code was executed, no native runtime input changed and no hardware, registration, account, archive, application or security change ran.
