# Offline genuine-SL3 descriptor candidate

The project can now generate a concrete Windows x64 SL3 XML candidate and validate it against the current application's original device schema. The candidate preserves the genuine SL3 identity and historical audio/DVS declarations, names the rebuilt ASIO driver and explicitly labels its replacement for the retired DRIVER_API handshake path as an **unverified hypothesis**. The XML is not registered, packaged into the application, deployed or accepted by a running Serato session.

The actual candidate is saved privately under `analysis/sl3-descriptor-candidate-20261102/`, alongside its source-bound manifest. Its SHA-256 is `2a2b0828e75e622d0e485b6a051370a53c341d22ce02381798f1a2597a91649e`. The separate repeat preparation produces identical XML and manifest bytes. It is not an installable compatibility release.

## Inputs and construction

`scripts/prepare-serato-sl3-candidate.py` binds the sanitized historical descriptor evidence by its exact hash and checks the original 2.5.5/2.5.6 executable hashes. Both historical records must produce the same candidate. The selected historical XML digest is `314e81ffb5d052e53280903d543107c8223e99ff1f4e200311a2b3d90e49154c`. The generator reconstructs an allowlisted declaration from metadata; it does not redistribute the complete original XML or consume another product's description/key.

It checks the installed/extracted current executable and archive identities, the current schema member CRC/hash, the Release ASIO DLL and all 146 recorded native build source pins. Its intended name is bound to both the original ASIO `getDriverName` source and the deployment planner's registry name, `SL3 Rebuild Development`. Actual installed driver enumeration/name uniqueness and protected deployment remain unverified.

The retained declarations include:

- Name `Rane SL3`, VID 0x1CC5 and PID 0x0001; no foreign identity or hardware descriptor change.
- `midi_direction=none`, `requires_usb=true`, three declared decks and the original `DVS_DEVICE_YES` capability.
- Historical 48 kHz nominal selection and 48-frame application alignment. The [checked host-bank adaptation](serato-bank-adaptation.md) remains relevant; the descriptor is not changed to force the application's frame count onto the ASIO driver's preferred bank.
- Original stereo order: Deck3, Deck1, Deck2 for both input and output. The logical projection is pairs 0, 1, 2 respectively; it is not physically validated jack mapping.
- Historical software mixer/calibration/record-source metadata within the current schema. Retained Mac API/name strings are historical data, not a Mac adapter or compatibility claim.

The intentional changes and omissions are visible in `candidate.json`:

| Candidate choice | Status |
| --- | --- |
| `HANDSHAKE_TYPE_DRIVER_API` becomes `HANDSHAKE_TYPE_NONE` | Explicit connection/control hypothesis based on the current [conditional USB-only route](serato-usb-arrival.md), not an implemented substitute for the historical Rane control API. |
| Windows ASIO name and x64 driver-detection key use the rebuilt driver's name | Proposed future selection; no registry entry is installed or fabricated. |
| `has_hid=false` and `use_legacy_portaudio=true` are explicit | Current defaults are made visible; the known bare-USB branch and retained legacy ASIO path still need real validation. |
| `has_faders`, `platter_resolution`, `provides_software_through` are omitted | The current schema sequence does not accept these historical names. No replacement meaning is invented; missing control/through behavior remains work. |
| Non-x64 driver-detection fields | Only schema-required empty `osx`/`win_x86` placeholders remain; no non-Windows-x64 driver is proposed. The historical `osx_x64` tag is not emitted. |
| Creation date and element order | A fixed candidate revision date and the current schema's base/extension sequence make deterministic, schema-conforming output. |

The only secret field emitted is the original verified **empty** `secret_key`. No HID/MIDI section, nonempty key, response, challenge, foreign profile or account/entitlement alteration is generated. Historical DVS capability is a declaration, not proof of current licensed operation or calibration.

## Schema validation and its limit

The selected original asset is `midi/MIDI.xsd`, SHA-256 `9e15093df616f9b9eac7f2f0fc1dbebfc55ce353415e22569fcfa00b98c1cc56`. The original schema has an external DTD declaration. `scripts/validate-descriptor-schema.ps1` permits DTD-ignore mode only for that exact schema hash; all external resolution is disabled, and schema imports/includes are refused. Unknown schema DTDs and candidate XML DTDs are prohibited. Validation uses the existing Windows `.NET XmlSchemaSet`; no new dependency, vendor executable, application DLL or driver is loaded for the check.

The framework validates the actual saved candidate with the original schema. Initial attempts were rejected for missing creation date, legacy element order/tags and schema spelling/platform differences. The generator was corrected rather than weakening validation; the rejected-attempt logs are preserved privately. No failed attempt created the candidate directory.

**Schema acceptance is not application acceptance.** It checks XML structure/types against an asset, not Serato's runtime parser, provider/registration behavior, support/connection decisions, DriverAPI/control semantics, account/product state, physical audio or DVS. The manifest keeps all those runtime/deployment claims false even after successful schema validation.

## Commands and preservation

From the repository root:

```powershell
# Inspect the construction and source bindings; no persistent candidate output.
.venv/Scripts/python.exe scripts/prepare-serato-sl3-candidate.py

# Prepare a new project-local offline bundle; existing output is refused.
.venv/Scripts/python.exe scripts/prepare-serato-sl3-candidate.py `
  --prepare analysis/sl3-descriptor-candidate-NAME

# Reconstruct, revalidate against the schema and compare the exact saved bundle.
.venv/Scripts/python.exe scripts/prepare-serato-sl3-candidate.py `
  --validate analysis/sl3-descriptor-candidate-NAME
```

The bundle has exactly the generated XML and `candidate.json`. Verification rejects altered XML, source/runtime drift, unexpected files, reparse inputs and changed manifest claims. Actual schema validation uses a bounded owned temporary folder, suppresses process windows, times out and cleans up its own files. Preparation rechecks source hashes before writing create-new output; validation preserves existing files. There is no execute/deploy/register/archive-write option.

## Verification and next implementation boundary

Eight new tests cover genuine identity, historical endpoint/alignment preservation, explicit hypothesis flags, incompatible source mutations, deterministic ordering, strict JSON and existing-output/path refusal. Actual .NET checks accept valid synthetic XML, reject wrong values and XML DTDs, and refuse unknown schema DTDs/external includes. Six additional actual CLI scenarios cover positive verification, repeat preparation, default inspection, no-overwrite refusal and XML-identity/manifest-claim tampering. The original bundle is unchanged. [Evidence](evidence/serato-sl3-candidate-20261102.json) binds sources, schema results, candidate/manifest hashes and logs.

At this descriptor checkpoint no current resource writer/provider had been implemented or deployed. The later [offline additive archive builder](serato-sl3-archive.md) now prepares a private archive experiment; no provider or modified archive is deployed. The archive builder verifies exact original-member preservation; a runtime package experiment still needs application integrity/signature assessment, installation/rollback and registered-instance/duplicate-precedence handling. This XML file is not an established loose-file override. The NONE hypothesis, omitted controls/through behavior and service/state eligibility must be resolved before a current-Serato compatibility claim. The rebuilt ASIO path also still needs measured native timing, physical mapping/levels, reliable reopening and protected deployment.

Installed executable/archive, registry, driver binding/trust, normal security, firmware and account state were not modified. No UAC prompt, SL3 acquisition, audio, Serato or Phase execution ran. Genuine current SL3 admission and actual two-deck DVS remain required; the Windows goal stays active and Mac is deferred.

The later [candidate selection check](serato-sl3-selection.md) connects the recorded zero USB revision to parser defaults and duplicate rules, including the separate empty `midi_name` field. Its predictions remain conditional; archive loading and actual chosen-descriptor observation are unverified.

The later [authorization-service receiver proof](serato-authorization-service.md) identifies the helper's +0xa0/+0x90 receiver as RLMAuthorization or JWTAuthorization, distinct from DriverAPI. It does not query account state, establish a permitted service result or validate current SL3/audio/DVS.

The later [attended archive-test package](serato-archive-deployment.md) now prepares a source-bound review bundle and tested temporary-file transaction engine. Its default read-only Plan passes on the original installation. Protected install/rollback and application acceptance have not run or been approved.

After the [ASIO call-tracing build](asio-call-tracing.md), the current source-bound bundle is `analysis/sl3-descriptor-candidate-20261102-owned-trace/`. The original XML bytes/hash are unchanged; earlier manifests are historical and refused against current source/build pins.
