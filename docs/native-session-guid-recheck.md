# Observe and recheck the native logging GUID

The [actual 1 November attempt](attended-logging-20261101.md) establishes that the committed PLA collector can retain its configured GUID while the native session returns another GUID. The default `configured` policy still rejects that difference. A separate, explicit `observed-rechecked` diagnostic policy now handles this observed host behavior without changing the read-only query helper or reinterpreting the original failed record.

The opt-in path requires the usual absent-session observation and successful committed-service readback before Start. If the first live query fails solely because its GUID differs, the parent preserves that query as rejected metadata. It additionally requires the exact private session name and `images.etl` path, QPC, the reviewed file/system-logger modes, image enable flag 4 and zero observed loss counters. Only a distinct RFC-4122 version-4 GUID is a candidate; other formats require further investigation rather than automatic acceptance.

The parent immediately launches a **new strict query** with that candidate GUID. That query must independently report the same active name/GUID and private output under the same constraints. Only this second query becomes an accepted observation. Later queries keep that exact native GUID; any change fails and cannot trigger discovery again. Absence during the recheck does not establish a start. A preexisting source, failed API call, missing committed-start evidence, wrong name/path/mode/provider, observed loss, reserved/zero GUID or additional validation error cannot start discovery. Cleanup still uses the separately admitted persisted collector's original configured identity.

The result retains both identities in separate fields, the failed discovery file/hash, strict recheck file/hash and acceptance flag. A successful configured-GUID observation needs no discovery. Neither policy establishes a native creator attestation, timer cause, hard file quota, complete image rundown, USB readiness or SL3 compatibility. The opt-in policy is an operational diagnostic for the observed private logging route, not a change to Windows code integrity or driver trust.

Prepare a new reviewed batch explicitly:

```powershell
.venv/Scripts/python.exe scripts/logging-batch.py --prepare analysis/logging-batch-guid-session --durations 5 10 --native-identity-policy observed-rechecked
pwsh -NoProfile -File scripts/start-logging-batch.ps1 -Plan analysis/logging-batch-guid-session/batch.json
# One administrator launch covers both jobs; the first failure skips the next.
pwsh -NoProfile -File scripts/start-logging-batch.ps1 -Plan analysis/logging-batch-guid-session/batch.json -Run
```

The individual source runner also accepts `--native-identity-policy observed-rechecked`. Plans bind that choice. Runtime changes invalidate old unused batch plans, so a fresh batch is required. There is no automatic retry or persistent elevated host.

Offline verification passes 39 source-controller/policy, 11 query-helper and 14 batch tests. The source suite includes the new successful simulated recheck plus rejection, missing commit, API, loss/provider/name/path/mode, zero/reserved GUID, preexisting source, disappeared recheck and later GUID-change cases. Three mocked launch checks and five actual ordinary-token child failure-record checks also pass (72 checks). A real opt-in five-/ten-second plan validates without starting a source. The original failed attended evidence regenerates identically against its frozen runtime. The new policy has no live result at this checkpoint.

The subsequent [actual five-/ten-second sequence](native-guid-live-20261101.md) now passes both jobs with strict native rechecks, disappearance before supervisor stop, cleanup and independent after-absence. It also supplies image-window metadata agreement. The implementation checkpoint's missing-live-result limit is superseded by that separate record; timer cause, hard quota, loaded-memory identity and USB readiness remain unproved.
