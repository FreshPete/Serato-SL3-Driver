# Typed finite-input diagnostic worker

The real `sl3_usbdk.exe` can now serve typed commands over the supervised message channel. Its handshake and missing-driver failure path have been exercised through real IPC. **The worker's physical descriptor/capture paths remain untested, and this is not a continuous ASIO audio session.**

The default executable still runs plan-only. Explicit `--worker --channel <owned-local-channel> --helper <pinned-helper-path>` requires a channel already created by the parent. It does not install a driver, register ASIO, import trust or change security settings. Existing standalone list/capture/silent-duplex modes remain separate; combining worker and capture modes is rejected before device access.

## Commands and readiness

Every version-1 request has an empty body. Payload-bearing requests and unknown commands fail. A successful hello must precede device operations; duplicate hello is rejected. Quit is allowed before hello so the parent can retire an unused worker.

| Opcode | Command | Successful reply |
| --- | --- | --- |
| 0x100 | Hello | Compiled protocol/finite-input capabilities and format |
| 0x101 | Descriptor probe | Exact SL3 VID/PID, pinned UsbDk high-speed enum 3, 235-byte configuration match; no redirection/audio |
| 0x102 | Finite input capture | Current reported rate, actual packet frame counts and tightly packed PCM, after successful API cleanup |
| 0x1FF | Quit | Empty acknowledgement, then worker exit |

The hello's two feature bits mean descriptor probing and finite input capture are implemented. It advertises six logical channels, three-byte containers, 18-byte frames, 126-byte maximum packets and 256 planned intervals/32,000 microseconds. **None of that claims a present/open device, physical audio, sample-clock measurement, continuous timing, latency or output support.** The strict decoder rejects unknown feature/format fields. There is no stream-start, rate-setter, output or firmware command in this worker protocol.

Statuses distinguish OK, bad request, bad state and operation failure. Operation errors carry at most 512 bytes of diagnostic text; clients must check status before decoding a successful payload. An operation failure is not a readiness result. The dispatcher does not replay a failed operation automatically.

## Real capture path, not yet physically run

The worker reuses the pinned service/helper checks, exact descriptor fixture, 0x30 rate getter, audio alternate selection and native four-request capture backend. It prepares four × 64 intervals IN on endpoint 0x82. Full-width packet statuses/lengths must succeed, be nonzero, fit 126 bytes and contain whole 18-byte frames. Registered-buffer padding is excluded; no guessed lengths or recovery samples are substituted.

USB storage stays private to the worker. The reply copies completed data into the IPC payload only after transfer cleanup and successful alternate/redirection API cleanup. Unknown pending I/O or failed cleanup uses the diagnostic's process-failure path; the parent receives worker exit rather than fabricated successful data. The worker process is the termination boundary, not Serato.

Each packet length is represented as a frame count from 1 to 7. The capture wire payload is a 32-byte little-endian header, 256 one-byte counts, then raw interleaved PCM. At the endpoint maximum, this totals **32 + 256 + 256 × 126 = 32,544 bytes**, fitting the 32,768-byte mailbox. Decoding validates version, rate, interval count, flags, reserved fields, frame-count sum and exact PCM length before accepting the batch. The only success flag records API cleanup; it does not establish physical alternate readback, analogue audio or a measured clock.

Packet/frame consistency is distinct from clock plausibility and continuity. Synthetic codec tests can exercise maximum lengths without establishing any physical packet schedule. Repeated finite requests close/reopen redirection and cannot be treated as a gap-free stream.

Mailbox waits now permit up to ten seconds, accommodating the finite capture core's five-second operation plus two-second drain and startup/control overhead. Device operations also retain the isolated diagnostic's 20-second watchdog. These are failure-containment limits, not real-time guarantees. Parent timeout/termination still requires recovery inspection. The worker serves at most 64 requests and retires after a five-second idle receive timeout. Its last published reply remains available through exit.

## Tests actually run

All **15 native tests pass in Release and Debug**. The SDK-free build passes thirteen with an absent SDK path. Tests exercise both-rate synthetic codec round trips, maximum payload size, invalid/truncated header/rate/count/flag/packet fields, the actual executable's handshake, capture-before-handshake rejection, malformed/unknown/duplicate requests, graceful quit and preservation of the 64th reply as the worker exits. Normal tests supply a deliberately nonexistent helper path and never request a valid device operation.

An additional explicit test confirms UsbDk service absence before sending a probe to the real worker. It receives operation failure with Win32 1060 before helper load. Read-only preflight agrees that the service is absent. No worker/fixture process remains alive. [Build/source and negative-path evidence](evidence/typed-worker-build.json).

The non-hardware checks can be reproduced with:

```powershell
$workerExe=(Resolve-Path ./artifacts/build/native/Release/sl3_usbdk.exe).Path
./artifacts/build/native/Release/sl3_worker_protocol_tests.exe $workerExe
# Optional negative path, only when UsbDk is absent; the test checks that first:
./artifacts/build/native/Release/sl3_worker_protocol_tests.exe $workerExe --probe-absent
```

## Remaining integration

Owner-present driver loading, tracing and input-capture gates still precede physical worker use. The existing standalone traced capture should establish packet/clock behaviour first; an IPC-specific trace/result wrapper is still needed. The IPC capture path has compiled and its codec has been tested, but **no hardware capture request was sent through it**.

Implement a continuous session/data path with output scheduling and callback/buffer retirement, then connect the [ASIO DLL](asio-com-server.md). Keep process creation/handshake separate from actual stream availability. Physical channel mapping, clock/latency, normal-security driver admission, Serato/DVS and the later macOS route remain unverified requirements. [Worker supervision](worker-process.md), [mailbox ownership](worker-mailbox.md), [Serato routing](serato-audio-routing.md).
