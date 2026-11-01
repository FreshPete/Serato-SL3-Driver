# First verified real continuous bridge

On 30 October 2026 the single-open probe ran the actual native worker, USB request engine, six-channel SDK buffer planes and audio-owner callbacks for **one second at 44.1 kHz**. It completed 341 real buffer callbacks and 123 successful USB OUT requests carrying the zero-output stream. The probe retired normally, disposed its buffers and required no forced termination. The complete USB trace has no lost events/buffers, selected device/security state recovered and Secure Boot remained enabled.

This is the first real continuous USB-to-callback bridge result in the rebuild. It is not a registered production ASIO device, analogue playback/loopback, measured latency, current Serato connection, DVS calibration or sustained stability result. [Reproducible metadata evidence](evidence/first-real-single-open-bridge-20261030.json).

## Device recovery and actual prerequisites

After the preceding rapid-reopen failures, the unit temporarily appeared as an unknown USB device with descriptor-request failure. The owner acknowledged a longer power-off and different direct USB port. Windows then recorded a normal SL3 arrival at 17:39:19 UTC on port 4, with the original Rane code-39 baseline and no descriptor failure. No security setting, trust entry, installed application, firmware or driver binding was changed by these tests.

The first sequenced capture passed: 1,411 six-channel frames at 44.1 kHz, four completed IN requests, selected-state recovery and a loss-free trace. The next silent-duplex attempt failed its **first input packet**, reporting `USBD_STATUS_BABBLE_DETECTED` (`0xC0000012`, sign-extended in the recorded 64-bit field). Its request-level status alone was success; checking per-packet status was essential. That request contained 63 other successful packets. The transaction then canceled the remaining pending IN requests and submitted **zero** audio OUT requests. Those cancellation results must not be presented as independent original hardware faults or as a passed duplex test. The sequence stopped and did not run its bridge stage.

An explicitly requested input-only follow-up collected all four requests and passed all 256 packets, again yielding 1,411 frames. Its trace has 16,359 events and no loss; recovery and Secure Boot checks passed. A fresh sequence revalidated that same-worker capture, then ran new silent duplex. This time all four requests per direction and all packet results passed. The API accepted 25,398 zero-PCM output bytes, and independent inspection confirmed all four saved output buffers contained only zeros. Its native output lengths/offsets matched the fresh corresponding input lengths. The bridge stage ran only after that gate passed.

This observed intermittent startup packet error remains unresolved. No validator, buffer capacity, packet-status rule or output gate was relaxed to obtain the later success. The SDK-backed status summary preserves original 64-bit values, recognizes valid sign extension and excludes unsubmitted/nonterminal packet storage from completion results. In the failed duplex record, 256 unsubmitted OUT packet rows were excluded rather than being mistaken for successful all-zero completions.

## Real bridge result

| Item | Observed result |
| --- | --- |
| Native worker SHA-256 | `f29720369d443f7ec9b6ee4bf9c20a766f174ea02879b0727e28576a2077ab66` |
| Probe SHA-256 | `abe85e2a0978c68cd643611e7dd1b6636896bf413a6c85526a0762f5b2f48498` |
| Device rate verified within the stream's one redirection | 44,100 Hz |
| Temporary inspections/reopens inside the probe | 0 |
| Requested/observed stream window | 1,000 / 1,000 ms |
| USB intervals / SDK bank frames | 64 / 128 |
| Completed native input blocks / frames | 124 / 43,744 |
| Audio-owner input frames / published output frames | 43,744 / 43,744 |
| Callbacks started / completed | 341 / 341 |
| USB OUT submissions / successful completions | 124 / 123 |
| Final pending / retained request masks | 0 / 0 |
| Stream / worker / host fault | None |
| Audio thread / native process / private job | Retired / exited / empty |
| Buffers disposed / forced termination | Yes / no |
| Bridge trace | 16,255 events, zero events/buffers lost |

The OUT submission/completion counters differ at stop. Final request masks and independent ownership domains retired, but that does not mean every submitted OUT request completed normally before stopping. The evidence retains both counters rather than replacing them with a single “all completed” count. No additional unrecorded per-request cancellation status is inferred for this continuous run.

The 341 complete 128-frame callbacks cover 43,648 logical frames. The larger captured/audio-owner frame count must not be presented as that many frames delivered through complete SDK callbacks; 96 additional frames do not form another complete callback bank at stop.

The probe's callback writes only zero samples; the bridge's preroll/output FIFO path and actual request engine are exercised. Successful USB completion is not evidence of analogue DAC output or physical channel mapping. The separate finite duplex test supplies saved-buffer proof of zero payload, while the continuous run supplies its source-bound callback/output policy and actual native completion counters.

## Timing and applicability limits

All 341 callback timing observations fit the fixed journal, with no dropped timing records. The callback spacing median was approximately 4.3 microseconds, its 95th percentile approximately 8.00 ms and its maximum approximately 8.05 ms. Multiple 128-frame banks are delivered in bursts after each larger USB block. This is software delivery behaviour, not a measured ADC/DAC latency or oscillator result. Logical frame progression and a loss-free ETW recording do not prove sample-perfect USB continuity.

The production facade uses eight intervals, not this probe's 64. Its exact-mode timing, retained device lifetime across IASIO initialization/dummy probes/stop-start, measured profile, registration and application tests remain required. The default production facade has not been switched to the diagnostic single-open entry. Four-hour streaming, ten reopen/reconnect cycles, power/reboot recovery, analogue signal/loopback and current Serato/DVS remain outstanding.

## Reproduction and retained failures

`scripts/test-single-open-sequence.ps1` defaults to a no-device plan. Explicit elevated execution runs capture, silent duplex and the single-open bridge in order, stopping on first failure with no automatic retry. Optional `-ValidatedCaptureRun` revalidates a supplied same-worker capture before the remaining stages. Each nested test retains its own fingerprints, trace and recovery gates. This reduces repeated administrator prompts without waiving prerequisites.

`scripts/export-single-open-physical-evidence.py` independently reads the retained records, checks current source/executable bindings, validates the capture and finite zero-output buffers/layout, verifies complete traces and snapshots, checks native callback/retirement counters, and preserves the earlier failed gate. Raw PCM and USB traces remain local under ignored `tests/results/local/`. The exported evidence contains metadata only.

The software checkpoint remains 33/33 Release, 33/33 Debug and 23/23 SDK-free. Python passes 56/56, including new status-summary checks; the final SDK-verification refactor also passed its five focused tests and the real-record exporter. These checks are distinct from the actual hardware result above.
