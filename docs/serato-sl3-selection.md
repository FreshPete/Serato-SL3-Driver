# SL3 candidate selection at the recorded USB revision

The recorded SL3 USB revision is zero, and the current parser projects our candidate's omitted `bcd_device` to zero. Under the checked resource-before-stub numeric path, a successfully parsed candidate therefore takes the first exact match. This removes a reason to change the descriptor revision for the recorded device. It does not establish that Serato has loaded, registered or selected the candidate.

[Sanitized original-byte and saved-observation evidence](evidence/serato-sl3-selection-20261102.json) binds the exact current executable, candidate and four complete saved USB snapshots. No new hardware observation, vendor-library call, application session or installed change ran.

## What was checked

The exporter revalidates the [prepared descriptor](serato-sl3-candidate.md), its source pins and actual current XSD result. It rechecks 63 original selection instructions, 90 discovery instruction byte records, four complete identity getter leaves and 17 additional parser/getter instructions against the unchanged Windows 5.0.0.1278 executable. It also checks the shared identity vtable and virtual-base arithmetic.

The [30 October observation](usb-identity-baseline.md) contains four complete snapshots with VID 0x1CC5, PID 0x0001 and revision zero. The saved supervisor validator again accepts the original source/library/log bindings and exited child record; all three pinned saved files match the historical report. This is verification of old evidence, not a current device-state attestation. Bus 3/address 1 are historical observation values; zero is a USB descriptor revision word, not an identified firmware version.

## Parser fields and the name distinction

At `1405c8365`, EDI is zeroed. Store `1405c83b1` initializes complete descriptor `+0xac` to zero; the `bcd_device` lookup's absent-element branch at `1405c83ca` skips the parsed-value store. The current candidate omits that element, so its checked default is zero.

At `1405c83f3:1405c8401`, the parser initializes complete `+0xb0` from an empty literal. The lookup at `1405c8406` is specifically `midi_name`; its absent-element branch at `1405c8418` skips the replacement string. The candidate omits this element too.

Shared identity table `14281cbe8`, slot `+0x30`, points to `1405c6ec0`. It copies the string at receiver `-0x688`. With the verified interface at complete `+0x738`, that addresses complete `+0xb0`, precisely the parsed `midi_name`. It is **not** the Windows ASIO selection string `SL3 Rebuild Development`. Giving our driver its own name does not populate this shared identity-name field under the checked parser path.

## Conditional selection result

| Boundary | Consequence under the checked inputs |
| --- | --- |
| Primary vector, resource candidate before stub, requested revision zero | Candidate is the first exact identity/revision match and returns before the later stub. |
| Aggregator insertion, existing candidate and later stub have equal identity triples | Existing candidate's empty shared identity name takes the branch suppressing insertion of the later stub. |
| Aggregator numeric lookup with recorded revision zero | Registered candidate is an exact match under that separate collection's rule. |
| Primary lookup with a nonzero requested revision and both entries still at zero | Both are older fallbacks; the later stub wins their tie. The recorded-zero conclusion must not be generalized. |

These are deductions from original instructions and saved data. They require successful resource loading/full descriptor parsing, no later field/vector mutation, the documented resource-before-stub construction and the relevant numeric/aggregation lookup route. Matching stub identity/default revision remains a condition of the aggregation deduction. Other name matching, additional records, a different live revision or a different message payload can change the applicable case. In particular, the [USB-arrival payload proof](serato-usb-arrival.md) does not establish that every downstream third word is the physical USB revision.

No revision, VID/PID, device response, firmware or other product identity is fabricated or modified. The candidate/archive bytes are unchanged. No support/account check is changed. This result narrows duplicate precedence for a future test; it does not implement the NONE control hypothesis or prove service readiness, current admission, ASIO audio or DVS.

## Reproduction

```powershell
# Validate saved inputs and inspect the deterministic report; no new USB query.
.venv/Scripts/python.exe scripts/export-serato-sl3-selection.py

# Save at a fresh path; an existing output is refused before analysis.
.venv/Scripts/python.exe scripts/export-serato-sl3-selection.py --output analysis/sl3-selection-NAME.json
```

The actual exporter run completed, a second report was byte-identical after console newline normalization, and no-overwrite refusal preserved the original report. These are static/file verification results, not new native or physical tests. Runtime archive trust/parsing, actual selection, control/service semantics, measured ASIO timing/deployment and real current two-deck DVS remain unfinished. Mac stays deferred.
