# Native bounded capture diagnostic

The preparation below describes the initial WinUSB diagnostic. Later UsbDk captures at both rates are independently preserved in the physical checkpoint. [New offline content analysis](capture-pcm-analysis.md) of those actual files now identifies large stored-prefix values and supplies statistics/byte-exact WAV export, without claiming analogue quality or current-worker validation.

The original C++ capture diagnostic now builds as Windows x64 in Release and Debug, with MSVC warnings treated as errors. Native packet/lifecycle tests, plan-only smoke runs and the missing-WinUSB device gate pass. **No audio has been captured on the SL3 yet.** The device is left on its original driver/code-39 baseline; no elevation prompt, binding or trust change was initiated for this offline work.

## What is implemented

`sl3_capture.exe` is a user-mode executable, not a kernel driver or installed service. It defaults to plan-only operation. Explicit capture requires a fresh output directory and an already-bound project WinUSB interface. It opens the device exclusively, validates VID/PID, the entire 235-byte configuration fixture, high-speed operation, interface identities, initial alternate-zero settings and exact pipe layout.

After a single 0x30 rate getter, it selects the previously verified audio alternates and prepares **four independent registered buffers**, each for 64 high-speed intervals (8 ms). Each buffer is 8,064 bytes with 126-byte slot capacity; total planned capture is **32 ms / 256 intervals / 32,256 registered bytes**. Every registration uses offset zero in its own buffer, avoiding ambiguity about result offsets relative to shared buffer segments. Only isochronous IN 0x82 is submitted. Subsequent requests require continuity rather than silently skipping frames.

The packet decoder uses returned offsets/lengths/status, ignores unused padding, rejects overlapping/out-of-range slices, nonzero USB status, nonmultiples of 18 and lengths above 126, and sign-extends six little-endian 24-bit samples. Zero-length packets are recorded and prevent a successful-audio claim. No physical jack mapping or converter precision is inferred.

## Completion ownership and deadlines

Each request owns stable registered storage, a packet-descriptor array and a manual-reset event/OVERLAPPED object. The platform-independent transaction engine first prepares all resources, then submits all requests. Any error triggers cancellation of every pending request, followed by completion draining under a shared deadline. Release occurs only after a terminal completion is known. A cancellation request alone never authorizes releasing its memory.

The normal request deadline is 3 seconds, with 2 seconds for cancellation/draining. A process-wide watchdog bounds even blocked synchronous APIs or teardown at 20 seconds. If a request or registration cannot be retired safely, the isolated process terminates without unwinding/freeing that native storage; Windows performs process I/O teardown. This is a failure outcome requiring evidence review, not successful cleanup. The traced parent records the exit and still performs targeted driver/trust recovery.

The Windows adapter uses the original CreateFile handle for `CancelIoEx`, and the **primary WinUsb_Initialize handle** for `WinUsb_GetOverlappedResult`, including operations on associated interface 2. [Microsoft completion-handle requirements](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_getoverlappedresult), [cancellation ownership rules](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelioex).

Hardware behaviours of cancellation, separate buffer registrations and continuity scheduling still require real-device validation. The tests establish the core ownership rules and compile-time adapter correctness; they do not establish that Windows/SL3 will deliver usable audio.

## Output and first-error policy

The fresh result directory receives `capture.json`, per-request registered-buffer snapshots and tightly packed `capture.pcm` containing only successful packet slices. JSON distinguishes planned intervals from submitted/completed requests and separates transfer success, packet-decoding success and alternate restoration. Request UTC bounds and per-packet statuses/offsets/lengths are retained for ETW comparison. Raw PCM stays local under ignored results; it has six logical channels with no assigned physical speaker layout.

The diagnostic stops on the first transfer/validation error. It does not select a new rate, enable status command 0x36, change routes, clear/reset a pipe, reset/cycle a port, send audio OUT, touch firmware or change any Windows security setting. On normal completion/error, both attempted audio alternates are restored in reverse order. The existing parent runner restores original Rane binding and removes temporary package/trust/GUID entries.

## Build and verification

```powershell
./scripts/build-native.ps1
./scripts/build-native.ps1 -Configuration Debug
./artifacts/build/native/Release/sl3_capture.exe --plan
```

The verified host toolchain is Visual Studio 2019 Build Tools / MSVC 19.29 with Windows SDK 10.0.19041.0, targeting user-mode Windows x64. This is not a WDK/kernel build or signing result. Build logs and binaries are ignored under `artifacts/build/native`; [sanitized build records](evidence/native-capture-build.json) include source/executable hashes.

The native test executable covers packet padding/signed boundaries, invalid packet lengths/status/bounds/overlap, successful request completion, partial preparation/submission failure, failed completion, failed cancellation followed by draining, stuck requests retaining ownership and failed unregister retaining ownership. Each build configuration now passes seven CTest entries: this core executable, playback layouts, the fixed-block audio bridge, and plan-only/conflicting-mode checks for both WinUSB and UsbDk diagnostics. The latest combined build record is in [audio-bridge-build.json](evidence/audio-bridge-build.json). The existing 12 Python tests also pass.

Successful captures additionally validate an offline playback layout using their actual packet lengths and decoded frames. No output is submitted. The report distinguishes this repacking check from the necessary WinUSB maximum-packet shape check; [transport findings and remaining tests](playback-transport.md).

The negative device gate was exercised while independently confirming `strmdrv` / code 39. The diagnostic reported no matching project WinUSB interface, **zero submitted/completed requests**, no frames and no attempted alternate changes. This validates rejection before capture; it is not a failed audio-stream test.

## Prepared hardware run — not executed while owner is away

The existing elevated PowerShell 7 runner now accepts a capture mode:

```powershell
./scripts/test-winusb-traced.ps1 -Run -DevelopmentTrustApproved -CaptureAudio `
    -ResultDirectory tests/results/local/native-capture-traced-01
```

It starts ETW before binding, verifies the native executable and source hashes against the successful Release build record, runs the read-only initial probe, launches the bounded native capture only if WinUSB started and enough trace time remains, and performs targeted cleanup afterward. Exactly one experiment mode is allowed. Rebuild if a source hash changes. This command deliberately performs the already-approved temporary development trust/binding setup; no automation/elevation prompt has been left running for it.

An actual successful read requires packet/trace review and independent final-state verification. The full rebuild goal remains open: playback packetization, sustained streaming, physical channel mapping, ASIO, current Serato/DVS integration and macOS testing remain outstanding.
