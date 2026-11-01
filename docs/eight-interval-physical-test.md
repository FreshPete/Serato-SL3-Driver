# Eight-interval physical bridge — 30 October 2026

31 October verification repair: the prerequisite checker explicitly selects the original script archive. Files omitted from that archive can be recovered only from the pinned original commit, with exact recorded byte hashes and checked LF/CRLF reconstruction. An existing corrupted archive file fails rather than falling back to another copy. Six regression tests cover corruption, missing inputs, Git hash mismatch, line endings and unsafe paths/revisions. The full exporter passes again and regenerates both historical records without semantic changes. This adds no hardware validation to newer builds.

The real single-open bridge passed a one-second test at **44.1 kHz, eight USB intervals per request and 128-frame SDK callback banks**. The owner requested another launch and accepted Windows elevation. The test used the unchanged reviewed worker and the explicitly eight-interval probe; unfinished retained-device changes were set aside before admission. The complete trace/security/recovery wrapper finished successfully.

Local record: `tests/results/local/single-open-eight-intervals-20261030-01`. [Reproducibly checked metadata](evidence/eight-interval-physical-20261030.json) is exported by `scripts/export-eight-interval-physical-evidence.py`, which also revalidates the earlier same-worker capture/zero-duplex prerequisites and preserves the earlier babble failure. Raw USB/audio records remain local. Binary/source verification uses the immutable eight-interval checkpoint and exact Git commit `525c472493a4ae4650d9cf5149eeea6a5c8dc949`, so subsequent implementation cannot inherit this hardware result.

| Observation | Result |
| --- | --- |
| Native worker / probe | `f29720369d443f7ec9b6ee4bf9c20a766f174ea02879b0727e28576a2077ab66` / `df6be7f2bc98977f24805d593afb752ef705dcc4527bfaa3db69c7a891bd7393` |
| Temporary inspections | Zero; the stream factory checked the actual clock on its one acquired handle |
| Completed SDK callbacks | 341; first logical position 0, last 43,520 |
| Input | 991 blocks, 43,700 six-channel frames |
| Output publication | 43,700 frames; zero-PCM callback policy |
| Native output | 989 submissions, 985 successful completions; 43,612 frames submitted |
| Stop | Pending/retained masks zero; I/O, device, audio thread and private process/job retired; buffers disposed; no forced termination |
| Trace | 22,022 events, zero lost events/buffers |
| Recovery/security | Selected before/after state contract matched; Secure Boot enabled before and after |

The counters at stop are deliberately distinct. There is no claim that all published frames were submitted to USB or that every submitted request completed successfully before cancellation. Likewise, 341 complete 128-frame callback banks account for 43,648 frames; the remaining input frames do not constitute another complete callback bank. The record preserves native error **1168** despite zero host/worker/stream faults; this is not rewritten to zero. The backend records unsuccessful cancellation requests, and retirement is established independently from terminal masks and ownership results, rather than inferred from that last error value.

Eight high-speed intervals represent a one-ms request shape. They do not establish measured audio latency. Callback timing observations are included in the evidence, but software publication spacing and one-second frame counts do not establish physical clock accuracy or sample continuity.

This clears the specific eight-interval hardware prerequisite. Sustained operation, the new retained-device lifecycle on real hardware, a measured timing profile, controlled analogue mapping, production ASIO application use and current Serato/two-deck DVS remain incomplete. The intermittent earlier startup babble is still unresolved. No rate setter, registration, installer, firmware operation or security-policy change ran in this test.
