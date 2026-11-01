# Validation-only image-source preflight

The prepared image-source template now passes **PLA commit-time validation under an actually queried limited token**, without saving a collector or starting a trace. The named collector is not found before or after validation, and its prospective output directory remains absent. This advances the [configuration preparation](hub-image-source-preparation.md); live mode forwarding, image events, stopping and USB-window qualification remain unverified.

[Preflight](../scripts/validate-hub-image-source.ps1), [actual CLI tests](../scripts/test-hub-image-source-validation.py), [evidence](evidence/hub-image-source-validation-20261031.json).

The [offline exporter](../scripts/export-hub-image-source-validation.py) rechecks retained API/test/AST records, exact source/preparation bindings and the installed SDK's mode/status definitions before regenerating the compact evidence report. This performs no additional PLA operation.

## Exact non-persisting operation

The sole commit call uses literal **0x1000**, Microsoft's [plaValidateOnly mode](https://learn.microsoft.com/en-us/windows/win32/api/pla/ne-pla-commitmode). It combines no create, modify, running-instance update or flush flags. The script never calls Start, Stop, Delete or SetCredentials. A PowerShell syntax-tree check verifies the one literal commit mode and absence of those operational calls.

The preflight uses the local `[Service]SL3Image-…` name derived from the prepared record, checks that exact name through Query, validates the XML, calls Commit in validation-only mode and queries the name again. Both queries return `PLA_E_DCS_NOT_FOUND`, `0x80300002`. It changes no collector whose ownership is unknown and performs no cleanup of other sources.

The actual positive producer's directly queried token is non-elevated, elevation type 3. This proves permission for this validation-only operation on this host; it says nothing about permission to save/start a collector, redirect the SL3 or stream audio. The API documentation's [commit behavior and administrator requirement](https://learn.microsoft.com/en-us/windows/win32/api/pla/nf-pla-idatacollectorset-commit) remain separate from that observed limited operation. No separate trace-service process or live session was instrumented.

## Handling validation warnings

The call returns two `PLA_S_PROPERTY_IGNORED` entries (`0x00300100`): `TaskArguments` and `SubdirectoryFormatPattern`. In the actual input both are empty and inactive: no task is configured and the subdirectory format is zero. These are recorded rather than discarded.

The preflight permits only those exact codes/keys in those inactive-empty contexts, without duplicates. Every other warning or error fails validation. A successful call alone cannot establish a valid result; unknown warnings, failed token query, an unexpected existing collector or created directory also prevent success. The result's `valid` field applies to this preflight stage only. It always retains false values for trace start, runtime flag forwarding, independent-stop verification and readiness admission.

Before making the call, the script checks record/source identity, types, bounded JSON/XML, DTD/entity absence, unique private session identity, duration, local output root and filename policy, the single expected provider/keyword/filter configuration, QPC/system-logger mode, inactive scheduling/task settings and no prior persistence/start role.

## Actual checks

Sixteen CLI cases pass: the valid template; stale source; unsafe name; wrong/presented-as-string roles; oversized record; DTD; wrong provider/mode; circular output; escaped filename; extra keyword filter; nonempty task; nonempty inactive task arguments; nonempty inactive pattern; and existing-output protection. The task-argument case reaches real commit-time warning handling and is rejected. This host rejects the nonempty inactive pattern earlier during SetXml, which is recorded as an early refusal rather than misreported as a commit-stage test.

```powershell
pwsh -NoProfile -File scripts/validate-hub-image-source.ps1 `
  -PreparationRecord analysis/prepared-hub-image-source-20261031-02.json `
  -Output analysis/new-image-source-validation.json
.venv/Scripts/python.exe scripts/test-hub-image-source-validation.py `
  analysis/prepared-hub-image-source-20261031-02.json `
  analysis/new-image-source-validation-tests.json
```

Both output paths must be new. The preparation record must match the current preparer. The test runner uses only local validation-only calls and scratch records; it does not start traces or access USB. Native runtime/capture inputs are unchanged, so their archived suites were not repeated.

A live collector still needs owned create-new/start/status/stop/delete behavior, effective name/GUID/mode checks, complete ETL/loss inspection and an observed independent stop after launcher exit. This preflight is not that collector. Normal-token control access, reliable reopening, analogue/timing work and actual current Serato/DVS remain separate requirements.
