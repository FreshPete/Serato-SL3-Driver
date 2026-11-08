# Variable-packet / fixed-block audio bridge

The original C++ bridge now converts captured six-channel frames into fixed host double buffers and renders host output back into the observed variable USB packet layout. Release/Debug simulation tests pass, including a host that fills output **after its callback returns**. **This is a stream core, not an installed ASIO driver or demonstrated hardware stream.**

## Data and buffer ownership

`src/core/audio_bridge.cpp` preserves signed 24-bit little-endian containers and logical channel indexes 0–5. Constructor configuration chooses active input/output channels and a power-of-two host block of 64–1024 frames. Invalid/duplicate channels fail. Each selected channel gets two stable planar buffers; unselected planes return null. No physical jack/deck names are inferred.

Actual captured frames drive block completion. There is no timer, resampler or nominal-rate packet generator. The supplied rate is checked against 44100/48000 but does not create samples. Rendering requires the caller's successful observed packet lengths in groups of eight and preserves each boundary through cumulative offsets. Malformed lengths, insufficient destination capacity and insufficient queued audio are checked before any output consumption or write.

On a completed input block, the core first consumes the **other** output bank, then clears and offers the current bank to the host. The host has until the next switch to fill the offered bank; callback return is not treated as output-completion proof. This follows the double-buffer ownership described in the official ASIO SDK. A deferred-host test would fail if output were copied immediately after the callback.

One queued priming block and the initially empty other bank produce two blocks of startup silence for a host respecting bank ownership. At 64 frames, the normal simulation therefore renders 128 silent frames before the first produced output. Start clears both banks; restart preserves their addresses and resets counters/queues. Unwritten/unselected channels stay zero, rather than replaying stale bank contents. This intentional initialization differs from an underrun: queue underruns and overflows fault the stream instead of silently inventing replacement audio.

The output ring has fixed capacity of eight host blocks. Storage allocates during construction; start, processing, rendering and stop do not grow it. Tests count C++ `new`/`new[]` allocations around successful streaming/callback/restart paths and observe zero. This is not a measurement of real transport/host latency or of an arbitrary application's own allocation behaviour.

Output stays in packed 24-bit form from the ASIO banks through the interleaved ring. Rendering copies each packet directly, splitting the copy if it crosses the end of the ring. The bridge tests check exact samples and packet boundaries across that wrap at 32 and 64 frames. Output bank ownership and the two-block delay are the same as above.

In a local MSVC Release benchmark at 44.1 kHz with six input and six output channels, the median processing and rendering time per USB-shaped batch fell from 1.07 to 0.90 µs at 32 frames and from 1.04 to 0.84 µs at 64 frames. Each median used seven trials of 140,000 batches. This measures bridge CPU work with a synthetic callback. End-to-end latency and Serato playback stability require a live run. All 73 Windows software tests passed for the separate development build.

The local benchmark record is `artifacts/build/packed-output-bench-20261108/benchmark.json`, SHA-256 `37d61bfc337c3476d6ff4ad2a3a63e32bc38bd9182b8c8708683d2022ee5d2e4`. The native build record is `artifacts/build/native-packed-output-20261108/native-build-Release.json`, SHA-256 `a19ee39dca27e08cd16b4bdbdf1359ee6c42a521aecc948d5da8ee45920a7101`.

## Position, faults and threading

Input frame positions must be contiguous from session position zero. Host observation times must not regress. Each callback receives the input block's first logical frame position and the completing batch's supplied observation time. The latter is **not a measured first-sample timestamp**, USB frame number or proven hardware clock. A future ASIO time-info implementation must account for this distinction.

Invalid sample values, discontinuity, regressing observation time, output overflow/underrun or a throwing host callback put the core in a fault state. Further processing/rendering is rejected until the owner explicitly stops/restarts. Invalid caller buffer arguments leave queued output intact. Mutating reentrant calls from the callback are rejected; queries and offered plane access remain available.

The core is **single-owner**, with no worker thread, lock or USB I/O. Its session owner must serialize control operations with streaming, preserve host callback/buffer lifetimes, provide valid disjoint render storage and synchronize any deferred host writes within their ownership window. It must also handle real callback deadlines, transport backpressure, cancellation and ASIO resync notifications. The existing native capture decoder allocates result vectors; its successful diagnostic tests are not a claim that the entire future continuous transport is allocation-free.

Input-only/output-only channel selections are supported by the core. Capture still drives the clock, and it can render silent six-channel output when no host outputs are selected. Whether a physical session submits those output packets remains a transport/test decision; this component makes no USB call.

## Verification completed

Seven native CTest entries pass in both Release and Debug. The bridge test adds:

- Synthetic 44.1/48 kHz variable-packet streams across block sizes 64, 128, 256, 512 and 1024, without claiming these are the SL3's measured packet patterns.
- Independent signed-sample/channel/order checks, cumulative packet boundaries and exact two-block startup delay.
- Normal and deferred host writes, partial writes with stale-bank clearing, and input-only/output-only selections.
- Stable planes and reset counters on repeated start/stop, reentrant-stop rejection, and zero observed C++ allocations during the successful stream paths.
- Invalid configuration/rate/sample cases, discontinuity, time regression, output underflow/overflow, invalid packet/capacity and callback-exception recovery boundaries.

The build script now checks the registered test inventory before running it and saves test names plus its own/source/executable hashes. [Current build and scenario record](evidence/audio-bridge-build.json). No capture or audio OUT hardware test was added or run for this work.

## SDK reference and remaining integration

Official ASIO SDK **2.3.4, 15 October 2025** was downloaded from Steinberg's SDK endpoint and extracted under ignored local artifacts. Its interface confirms packed Int24LSB type 17 and the double-buffer processing window. The SDK remains a reference here: no SDK header/implementation is included in this stream-core build, and no SDK source is tracked, and no ASIO DLL or COM/ASIO registration was added. Package hash/source are in the [download ledger](evidence/downloads.jsonl). [Steinberg's developer portal](https://www.steinberg.net/developers/).

The SDK-facing buffer/lifecycle component is now implemented and tested separately; [component and remaining runtime](asio-buffer-component.md). A distinct driver identity and transport-availability gate are still required. Connect a continuous transport session only after real capture, variable-length silent output, scheduling and recovery are verified. Report software buffering separately from measured USB/device latency. Current Serato still needs its descriptor/backend/channel/control route completed; the core alone does not restore it. [Recovered Serato host requirements](serato-supported-contract.md).
