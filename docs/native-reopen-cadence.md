# Reopen comparison has a timing confound

6 November 2026: the saved journals show different release-to-acquire gaps in the successful and failed native probes. The failed acquisition followed a stream, but these runs do **not** isolate streaming as the cause. No additional hardware operation was needed to establish this.

| Acquisition | Previous probe | Gap from previous `redirect_close.return` to this `redirect_start.enter` | Outcome |
| --- | --- | ---: | --- |
| First control-only probe | Not covered by this comparison | — | Success |
| Second control-only probe | Control-only | 16,922 ms | Success |
| Silent-duplex probe | Control-only | 253,453 ms | Success, including the three-second stream |
| Final control-only probe | Silent duplex | 9,406 ms | Failed before `redirect_start.return` |

These are differences between recorded `GetTickCount64` values, not packet timestamps or an independently measured USB readiness interval. `src/windows/startup_journal.hpp` records that clock and the worker PID. All four probes were launched and observed during the same uninterrupted agent execution. The individual raw records do not carry an independent boot identifier, so the generic comparator requires explicit same-boot context before calculating gaps.

The earlier [control-only reopen checkpoint](native-asio-control-reopen.md) establishes a second successful acquisition without a power cycle; it does not establish immediate reopening. The [silent-stream checkpoint](native-asio-silent-stream-reopen.md) establishes streaming success followed by a failed reopen. Neither report supplies an otherwise identical, same-cadence comparison between streamed and unstreamed runs.

The historical [Windows USB state analysis](reopen-state-context.md) found an unhandled cycle event during a stopped/enumerated state, followed by a roughly ten-second startup timeout. That is relevant context, not proof that the new run followed the same states. It does not justify a ten-, seventeen- or any other fixed-second sleep as a repair. The new failed call's internal wait remains unobserved.

A read-only query found the Kernel-PnP/Configuration channel enabled with 1,367 records, last write at 19:25:37 UTC, and no events matching the selected period beginning 22:45 UTC. This configuration log therefore provides no corroborating USB lifecycle sequence for these probes. Other logs/providers were not exhausted; absence in this channel is not absence of a Windows transition.

## Reproducible comparison

`scripts/summarize-native-reopen-cadence.py` accepts two to 32 completed result paths and an expected SHA-256 for each. It verifies the completed bytes and referenced worker journal bytes, requires one native build/bundle, one PID per journal, ordered bounded timestamps and unique start/return/close boundaries. A stalled start stays incomplete; it is not given an invented return or close. Without `--same-boot`, gaps stay null. That flag records a caller assertion, not a discovered boot identity.

Six focused interpretation tests cover completed/stalled stages, malformed/repeated/mixed-PID/backward journals, explicit boot context, out-of-order/overlapping runs, mixed build identities and changed result/journal bytes. The actual four-result comparison reproduced the gaps above from the exact local records. [Bound evidence and source identities](evidence/native-reopen-cadence-20261106.json).

This tool executes no vendor code, opens no USB device, changes no source-bound package and proposes no automatic retry. Existing native/installer candidates remain unchanged.

## Next physical observation

After owner-attended recovery, the useful next trace covers **one acquisition, one bounded silent stream and release**, followed by observation of the original Windows stack through the remainder of the trace. Do not immediately acquire again to reproduce a known failure. Capture USB/UsbDk lifecycle events and actual trace-loss/coverage evidence before selecting any readiness condition or binding change. The [existing detachment capture procedure](usbdk-detachment.md) remains the starting point; no new elevated trace was launched while the owner was away.

Normal Serato selection remains a separate installed-use question. This failure was reproduced in a direct ASIO host before clock inspection, without Serato or a DVS source being involved in the failed acquisition. Changing application licensing, device identity or DVS flags cannot be inferred as a remedy for this USB startup boundary.
