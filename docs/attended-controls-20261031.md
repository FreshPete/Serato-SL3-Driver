# Attended current-worker control read — 31 October 2026

The current worker completed one SL3 acquire, clock read, full control-table read and release under directly queried normal tokens. The native component validator passes. The original end-to-end wrapper remains **failed** because its optional observer/XML comparison failed; it is preserved unchanged and is not an automated prerequisite for another hardware test.

Local context: `tests/results/local/user-controls-attended-20261031-120514`. The independent component assessment is `independent-assessment.json` there. Worker SHA-256 is `5fe2a44f1020032994c2b2e1a5ea868f87650caa9e23bc2077913760d0e88fe5`.

The [reproducible component/overwrite exporter](../scripts/export-attended-controls-20261031.py) now verifies the frozen runtime archive, native component, three tokens, snapshots, source hashes and exact retained/live state comparison. [Compact verified evidence](evidence/attended-controls-components-20261031.json). This supersedes the earlier component assessment's unexplained observer mismatch while preserving its failed-wrapper limit. The historical-only run verifier was separated from the operational helper so offline evidence improvements do not change that pinned runtime dependency.

| Observation | Result |
| --- | --- |
| Clock | 44,100 Hz throughout the recorded operation |
| Control table | All 22 bytes returned and decoded; raw bytes remain in the local assessment |
| Normal-token evidence | Parent PID 41000, probe PID 32092 and worker PID 34768 each queried directly: non-elevated, token type 3 |
| Ownership | One acquire/query/release; journal records getter return, close return and helper unload; native final retirement checks pass |
| Actions excluded by native record | Zero audio starts, rate changes, control setters and firmware requests |
| Trace | 25,305 events; zero reported lost events/buffers |
| Selected recovery | Independently compared before/after contracts match; Secure Boot true before and after |
| Live passive observer | Retired normally and reported 514 state rows; full source-XML matching remains failed/unverified |

Two preflight launches opened no device: the first rejected a changed offline verifier dependency; the second collector rejected Windows' `\??\C:\...` driver path before recording. The exact reviewed verifier bytes were restored for admission. A one-line local-drive path normalization was then reviewed; the installed driver hash matched the signed reviewed UsbDk image. Forty Release tests and three optional-capture tests passed. The capture-only runtime revision was recorded separately in the local build metadata; native inputs/binaries were unchanged, and no native rebuild is claimed.

The final validator initially rejected space-padded XML zero-loss counters. A reviewed whitespace-only parser correction exposed a further live-row/source-XML mismatch; that mismatch remains to investigate. The component assessment does not replace the failed wrapper or imply that its optional observer is accepted. No historical physical record was reassigned to this build.

Offline investigation now identifies the mismatch: the circular ETL reached exactly 64 MiB. Its header reports 919 buffers written at 131,072 bytes per buffer (120,455,168 bytes written through a 67,108,864-byte ring). It retained only 21 state rows; all 21 match live rows exactly, including timestamps. The other 493 live rows were overwritten in the file. Zero lost-event counters do not account for deliberate circular replacement. The failed full-window verdict is correct; the live reader is not disproved by this mismatch. The future collector now requests sequential `bin` format and explicitly fails at file capacity, and the shared trace checker rejects known circular headers at/over capacity. No new live test of that correction ran. [Microsoft's file-mode definitions](https://learn.microsoft.com/en-us/windows/client-management/mdm/diagnosticlog-ddf) distinguish sequential stop-at-limit from circular replacement.

The logging-only ETL initially hit the checker's unsupported version-3 image schema. Subsequent [installed-schema verification and offline parsing](attended-hub-image.md) recover 259 consistent kernel pairs, including a hub size/timestamp/checksum match for that image window. This is not loaded-memory identity, the earlier USB-window qualification or readiness proof. The original GUID-query failure remains unchanged; the header also shows no effective file-size maximum.

The subsequent [live-only release-state correlation](attended-release-state.md) finds a worker-associated candidate in `StoppedEnumerated` after the probe completed, with an observed ten-second startup-timeout tail. The target port association and full-file corroboration are missing, so it supplies no reopen gate or delay policy.

A separate logging-only source test ran from `tests/results/local/image-source-attended-20261031-120734`. It queued its private PLA collector, but its first successful API query rejected a returned session GUID differing from the requested GUID. The test correctly failed and retained an unknown start-observation outcome. Cleanup requested stop, deleted the owned collector and independently observed absence (Windows error 4201); no cleanup error was recorded. A 12,189,696-byte ETL was preserved, SHA-256 `154edb3aa1e868836ebd36eda0f416b8cab3d88e575afcf7d66671b8fe609ab3`. Its image-rundown content and effective source properties remain unverified; independent timed expiry is not established.

No test/worker process remained at the final process check. No device power cycle, firmware operation, security-policy change, ASIO registration, application patch or account change ran. This establishes useful current-worker normal-token control/ownership evidence within the component scope; audible audio, safe successive acquisition, sustained streaming, production ASIO and current Serato/two-deck DVS remain incomplete. Next inspect the saved live-row mismatch and image-source ETL offline before selecting another hardware operation.
