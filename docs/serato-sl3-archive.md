# Offline additive SL3 archive experiment

An original implementation can now prepare a private `userio_resources.bin` candidate containing the [genuine-SL3 XML hypothesis](serato-sl3-candidate.md). It retains all 229 original members and adds `audio/audio_rane_sl3_rebuild.xml` as member 230. Installed Serato files remain unchanged. This is an offline experiment, not an installable or working Serato release.

## Preservation and construction

The exact current archive is pinned to SHA-256 `872fc4fdad2eab2ddd34387d2d3c04dd9731c84798d9fdc7bd05ca54e1567db8`. The generator first revalidates the descriptor bundle against its source bindings and the actual current XSD. Its added inner ZIP uses a fixed timestamp, name and stored-data method. No original inner ZIP is recompressed, decoded and rewritten, or otherwise replaced.

The new resource encoder is checked against the existing independent decoder. For the actual original index and all 229 original encrypted members, decoding followed by encoding reproduces the exact original ciphertext. All original inner ZIP CRCs also pass. The builder changes only the outer index, shifts existing absolute offsets by the index-size difference, copies the entire original payload suffix unchanged, then appends the encoded new member. It checks the resulting index and every original member and compares the new member's contents with the exact candidate XML. Gaps, trailing data, order and original member names remain unchanged.

The prepared archive is 2,294,524 bytes; its index grows by 56 bytes. Its SHA-256 is `e05486b1c4c17f298834ddad2afb04da95e88c196a464bc3f1e4b88bf39c2cb1`. That byte identity binds this specific source revision, original archive and descriptor hypothesis. The manifest records source hashes, descriptor-manifest hash, CRC/hash preservation, schema results and all unverified runtime flags. No derived resource-codec value, original XML, vendor schema or authentication material is emitted in the public evidence. Generated archives contain vendor resources and remain private; they are not committed or redistributed.

## Use

The original licensed local application/extracted files and prepared descriptor bundle are required. From the project root:

```powershell
# Inspect the proposed result without writing an archive bundle.
.venv/Scripts/python.exe scripts/prepare-serato-sl3-archive.py `
  --candidate analysis/sl3-descriptor-candidate-20261102-owned-trace

# Create a fresh offline project-local bundle. Existing directories are refused.
.venv/Scripts/python.exe scripts/prepare-serato-sl3-archive.py `
  --candidate analysis/sl3-descriptor-candidate-20261102-owned-trace `
  --prepare analysis/sl3-archive-candidate-NAME

# Rebuild independently and compare exact archive and manifest bytes/claims.
.venv/Scripts/python.exe scripts/prepare-serato-sl3-archive.py `
  --candidate analysis/sl3-descriptor-candidate-20261102-owned-trace `
  --validate analysis/sl3-archive-candidate-NAME
```

The bundle contains only `userio_resources.bin` and `archive-candidate.json`. There is no install, execute, register or rollback action. Outputs are restricted to a direct `analysis/sl3-archive-candidate-*` directory; existing/reparse output and mismatched inputs are refused. Source bindings and the descriptor bundle are rechecked before writing. Verification does not modify the saved bundle. The installed original archive remains the recovery source; no installed replacement has occurred.

## Verification and limits

Seven new tests cover the inverse codec across word counts/padding and boundary keys, malformed sizes/keys, original encrypted-member/gap/suffix preservation, deterministic addition, existing-member refusal, corruption, fixed ZIP metadata and path/no-overwrite guards. Six actual CLI scenarios cover verification, repeat preparation, no-overwrite refusal, default inspection, archive-byte tampering and a false deployment claim. Repeat archive and manifest bytes are identical; the original bundle is preserved. [Sanitized evidence](evidence/serato-sl3-archive-20261102.json) binds these results.

Container checks establish internal byte/CRC consistency. They do not establish Serato's runtime trust or integrity checks, signature acceptance, successful parsing or admission. No executable signature or account/product check is patched. There is no claim that the codec or CRC is an authentication mechanism or that bypassing it provides legitimate admission.

The [default archive provider](serato-resource-loading.md) and [duplicate-descriptor precedence](serato-descriptor-precedence.md) were traced statically. Adding this file is a concrete input for a future experiment, not proof that the resource will be parsed, retained over the discontinued identity stub, selected for the connected SL3 or connected successfully. The NONE handshake/control hypothesis and omitted historical controls remain unresolved. Runtime package acceptance, explicit installation/rollback review, actual driver selection/deployment, measured timing, physical audio and legitimate current two-deck DVS remain required. Mac is deferred.

No UAC, application execution, driver/device acquisition, audio, registry/trust/security change, firmware or entitlement modification ran for this preparation.

The later [candidate selection check](serato-sl3-selection.md) connects the recorded zero USB revision to parser defaults and duplicate rules, including the separate empty `midi_name` field. Its predictions remain conditional; archive loading and actual chosen-descriptor observation are unverified.

The later [attended archive-test package](serato-archive-deployment.md) now prepares a source-bound review bundle and tested temporary-file transaction engine. Its default read-only Plan passes on the original installation. Protected install/rollback and application acceptance have not run or been approved.

The current source-bound archive bundle after the [native tracing build](asio-owned-trace.md) is `analysis/sl3-archive-candidate-20261102-owned-trace/`. Archive bytes are unchanged; its new manifest binds the current DLL/build. Older manifests remain preserved and are refused against current sources.
