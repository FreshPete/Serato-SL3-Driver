# Shorter audio transfer batches

The shared audio channel and SDK queue adapter now accept **8–64 active packet intervals in multiples of eight**, instead of requiring 64. This removes the eight-millisecond batch shape as a prerequisite for the future continuous transport. **The real native USB worker still implements finite diagnostics only; this change does not enable streaming or ASIO initialization.**

## Batch shape and wire contract

The reviewed SL3 fixture is high speed with audio endpoint `bInterval=1`. At that interval, eight USB microframes make one millisecond and the Windows isochronous packet count must be a multiple of eight. These are scheduling units, not measured application or analogue latency. [Microsoft's isochronous transfer contract](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/transfer-data-to-isochronous-endpoints).

| Active packet intervals | Planned bus duration | Maximum actual PCM bytes |
| --- | --- | --- |
| 8 | 1 ms | 1,008 |
| 16 | 2 ms | 2,016 |
| 24 | 3 ms | 3,024 |
| 32 | 4 ms | 4,032 |
| 40 | 5 ms | 5,040 |
| 48 | 6 ms | 6,048 |
| 56 | 7 ms | 7,056 |
| 64 | 8 ms | 8,064 |

Transport **version 3** uses one formerly reserved 32-bit slot field at offset 24 for `packet_count`. The 8,192-byte slot and 196,800-byte mapping sizes remain unchanged. Versions 1/2 are rejected even when the mapping size happens to match; there is no implicit conversion or fallback. The separate finite-diagnostic command protocol remains version 1.

`packet_count` must be one of the eight values above. Every active packet contains 1–7 complete 18-byte audio frames; every inactive count must be zero. PCM is tightly packed from actual active lengths. Both producer input and copied wire metadata are validated before PCM copying or caller-output publication. Zero, nonmultiples of eight, oversized counts, nonzero inactive metadata and mismatched byte lengths fault the stream. Empty/error USB packets still require a separate recovery policy; this patch does not fabricate replacements.

The SDK adapter decodes only active frames, calls the buffer component using the actual frame total and renders exactly the active packet schedule. It copies the count and all packet metadata to output. Logical positions advance by actual frames, with no nominal-rate packet generator. Minimum bank size is 64 frames; an eight-interval block contains at most 56 frames, so one such block can complete at most one host bank. **Successive steps can still process a backlog in a burst. This is not a callback-pacing or deadline guarantee.**

## Verification

All **17 native tests pass in Release and Debug**; fourteen pass without the SDK at an intentionally absent SDK path. The queue test checks all eight count choices, zero inactive metadata, exact actual PCM copying, invalid API/wire counts, nonzero wire tails, unchanged caller output on rejection and explicit version-2 rejection. Its 2,000 real-process round trips now vary active packet counts as well as frames per packet.

The full queue/SDK test runs **7,200 real-process blocks per configuration**: both metadata rates, three host bank sizes, and mixed-count/fixed-eight/fixed-64 scenarios. It checks every actual host input sample and returned PCM byte, exact packet count/schedule, extrema, logical channel reversal, startup delay, frame conservation and callback totals. Fixed-eight runs additionally check that no individual step invokes more than one host callback. The 1,000-block local allocation measurement now covers mixed batch sizes and still observes zero C++ `new` allocations. Existing full-queue retention, pending discard, reentry and fault tests pass. The callback-failure fixture explicitly supplies enough input to reach a host-bank boundary; a valid short block may not trigger any callback.

Read-only preflight confirms the reviewed dependencies, unchanged no-helper/no-submission plan and absent UsbDk service; no test worker remains alive. Secure Boot cannot be freshly queried from this unelevated process, so the preflight records access denied rather than inventing a current result. No installation, trust/binding change, physical I/O or listening test occurred. [Source/build evidence and retained test-log hashes](evidence/audio-granularity-build.json).

## Next work

Implement a genuinely continuous worker loop with reusable overlapped requests, short input batches, bounded output preparation and explicit request ownership through completion/cancellation. It must validate each returned packet, preserve the input schedule, handle empty/full queues and missed deadlines explicitly, and retire all native leases before releasing storage. Keep sufficient native work queued while measuring continuity; a small transfer size alone does not guarantee that.

The session supervisor must coordinate start/stop/fault commands, monitor its retained worker process handle and retire callback/buffer callers before disposal. The COM DLL remains unavailable until that real session is connected. Physical capture, traced silent output, controlled analogue audio, clock/rate controls, current Serato/DVS and macOS retain their original validation requirements. [Full host adapter](queue-to-asio.md), [USB transport](native-usbdk.md), [bounded duplex](bounded-duplex.md).
