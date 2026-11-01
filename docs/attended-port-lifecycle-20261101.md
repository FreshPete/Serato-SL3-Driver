# UsbDk lifecycle in the saved 16:40Z experiment

Offline decoding now shows **successful UsbDk detachment followed by unsuccessful original-stack startup** in the preserved [failed experiment](attended-port-controls-20261101.md). This narrows the next implementation decision: a completed helper close is not a readiness barrier for another redirect. No new device operation, logging session or administrator prompt ran.

The captured lifecycle TMF decoded 18 UsbDk records but left three messages unformatted. The pinned MSI TMF supplies architecture-invariant definitions for those exact message IDs: device-name creation/deletion and process-owner matching. Their GUIDs occur in the pinned driver. Adding only those three formats decodes all **21 UsbDk records**, with **10,504 total events, zero reported event loss, zero format errors and zero unknown formats**. No driver, capture configuration or original run record changed.

| UTC, 1 November 2026 | Observed driver message |
| --- | --- |
| 16:41:33.9991277 | Worker 2324 queries device power state D3. |
| 16:41:33.9991559 | A system-thread power callback logs D0. |
| 16:41:34.1367993 | Redirector handle created for worker 2324. |
| 16:41:34.1464422 | Worker enters redirector close. |
| 16:41:34.1464940 | Worker waits for detachment of the exact SL3 identity. |
| 16:41:34.1476064 | Worker reports that SL3 detached. |
| 16:41:34.1476078 | Worker reports successful redirection removal. |

The detachment log interval is 1.1124 ms. It describes this wait's observed messages, not a transport latency or general deadline. The D3/D0 messages are 28.2 microseconds apart; their payload has no request identifier, so this analysis does not claim a proven pairing or successful completion status for a particular power request. The successful redirect handle and native control result independently show that this acquisition progressed past its startup waits.

The existing exact-port correlator also accepts this trace: the initial SL3, redirected child and post-release replacement occupy three distinct DSM contexts on port 4, with 11, 158 and 97 state rows. The replacement first enters `StoppedEnumerated` 87.9493 ms after probe completion. Its last successful entry precedes the timer by 10.0004557 seconds; the timeout/port-disable tail reaches `Stopped` 10.0918360 seconds after probe completion. The image logger failed before covering the whole USB window, so these symbolic state labels retain the cached-image/PDB qualification. This result does not replace the earlier fully image-qualified trace or claim a loaded-memory hash.

The port sampler's final query spans 16:41:34.147380–34.148496, overlapping the successful detachment/removal messages. Its missing raw response prevents identification of the rejected field. Timing suggests a handoff observation worth examining; it does not prove why the query was rejected or justify relaxing the decoder.

The evidence supports keeping two requirements separate: retiring the redirect ownership, and establishing whether the replacement original stack can accept another cycle. This run proves the former within its recorded scope and does not establish the latter. Do not replace that distinction with a fixed ten-second sleep or repeatedly reproduce the failed second open. The corrected observer can retain a future transient response; a reviewed persistent-ownership design could instead avoid unnecessary final-release cycles across ASIO object recreation.

Reproduce with `scripts/analyse-attended-port-lifecycle.py --output analysis/NEW-DIRECTORY`. The tool binds the original ETL/XML/run, checks source/driver/TMF and cached image/PDB identities, invokes the local SDK's Tracefmt on saved bytes only, and writes a separate result. [Compact evidence](evidence/attended-port-lifecycle-20261101.json). Four tests exercise exact stage/order/caller/target checks and refusal of missing, duplicate or architecture-dependent formats. Native binaries are unchanged.
