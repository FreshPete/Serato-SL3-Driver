# Native continuous-transfer adapter

`UsbDkStreamBackend` now implements the continuous engine's native request boundary using the reviewed UsbDk structures and Windows overlapped APIs. `MailboxStreamPeer` connects that engine to the actual checked input/output queues. **Tests simulate helper I/O and completion/cancellation results.** A later [continuous worker checkpoint](continuous-worker.md) adds the production dispatcher/watchdog. **Its native happy path and physical USB stream remain untested; no available ASIO device is claimed.**

| Layer | What this checkpoint exercises |
| --- | --- |
| Helper read/write functions | Injected simulation; no helper DLL load or USB submission |
| Events and clock | Actual Windows events; real default-QPC/event smoke check and deterministic test clock |
| Completion/cancellation results | Explicit injected Windows boundary, including errors and races |
| Request engine and shared queues | Actual production components |
| Host processing | Software PCM echo; SDK callback path remains separately tested |
| Production session and hardware | Not connected or exercised |

## Native storage and lifetime

Each of eight fixed slots owns its PCM, 64-bit length/result arrays, request, manual-reset event and `OVERLAPPED`. Input endpoint is `0x82`; output is `0x06`. All request addresses remain stable across reuse. Preparation validates the configured active count and creates no inheritable event handle. Failed event creation acquires no resource. Preparation and event creation precede measured processing.

Only an idle prepared slot can submit. The adapter clears the event, overlapped fields and old aggregate/packet results before handing a new request to the helper. IN uses fixed 126-byte strides for 8–64 intervals. OUT validates every active/inactive count, copies tightly packed PCM into its own slot, supplies exact variable packet lengths and sets `BufferLength` to the actual byte sum. The caller may immediately reuse its buffer; native memory stays leased independently.

Known helper rejection returns no accepted lease. Synchronous success still requires a terminal poll before reuse; asynchronous success requires a completion observation. An unrecognized helper return is conservatively retained as uncertain, because the adapter cannot prove that nothing was accepted. It is never converted into permission to free/retry memory. The helper's API exposes no explicit USB frame placement or continuation parameter, so the engine's logical continuation flag does not prove ASAP continuity.

Polling waits only with timeout zero. An unsignalled event reports pending. A signalled event is followed by `GetOverlappedResult` on the borrowed redirector **system** handle with waiting disabled. `ERROR_IO_INCOMPLETE`/pending preserve the lease; successful observation proves terminal completion. Observed `ERROR_OPERATION_ABORTED` is a terminal cancellation error. Other failed observations remain unproven, including invalid handles and failed waits. This intentionally conservative policy can require process containment for an error that the adapter cannot safely classify. [Windows completion contract](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-getoverlappedresult).

The adapter preserves full-width IN lengths/statuses in a terminal snapshot for the engine to validate and compact; it never points native I/O at that snapshot. Aggregate errors fail a completed request. OUT additionally requires every packet status to succeed; packet `ActualLength` is not interpreted as accepted output bytes. The tests deliberately fill successful OUT lengths with maximum 64-bit values and verify that only statuses control success.

Cancellation targets only the matching `OVERLAPPED` on the system handle. Even `ERROR_NOT_FOUND` does not retire its lease. Only a later terminal observation permits event/storage release. Microsoft requires retaining/reusing the overlapped structure only after the I/O has completed. [Cancellation and completion ownership](https://learn.microsoft.com/en-us/windows/win32/fileio/canceling-pending-i-o-operations).

This class is **isolated-worker only**. It borrows handles and helper function pointers; the owner must pin the reviewed helper, validate/redirect the exact SL3, read its rate and activate audio alternates first. The handles/module outlive this backend. It performs no loading, installation, redirection, reset, firmware or clock programming. The constructor validates its explicit table/handles and clock conversion, not physical identity/readiness.

Destroying the backend with an unobserved/uncertain request or failed resource release terminates **its own process with exit 70**. It never attempts ordinary unwinding or retries an uncertain event close. This guard must never run inside Serato or an ASIO host. The existing supervisor must retain the worker's process/job handle and report cleanup. Native API calls can still block despite nonblocking poll options; the future continuous worker needs an independent heartbeat watchdog.

## Verification actually performed

All **19 native tests pass in Release and Debug**; sixteen pass without the SDK at an intentionally absent path. New integration tests use the actual adapter, continuous engine and both checked shared queues for **8,000 input batches and 7,984 output submissions per configuration**, across both declared rates and 8/64-interval shapes. Every actual output byte, requested packet length, request-buffer size, reset overlapped/event/result field and stable request address is checked at the simulated helper boundary. The final unsubmitted/unfinished batches are deliberately cancelled or discarded during stop; submission counts are not physical playback/completion evidence.

After setup, successful adapter/engine/queue processing observes **zero C++ `new` allocations**. This is not a kernel-allocation, page-residency or real-time guarantee. Separate tests cover synchronous/asynchronous success, helper rejection, event create/reset/wait failures, signalled-but-incomplete results, unproven observation and later recovery, cancel-not-found with later cancellation completion, caller-buffer reuse, wrong queue role, invalid output tails and full-width aggregate/packet errors. Real default Windows event/clock calls are exercised without transfers.

Four real isolated child processes verify exit-70 containment for outstanding I/O, unknown helper return, failed completion observation and failed event release. Their jobs retire; no test worker remains alive. The test executable has no UsbDk DLL import, and no test loads the helper or submits USB. [Build/source, import and read-only preflight evidence](evidence/native-continuous-adapter-build.json).

## Next worker/session connection

The later [continuous worker checkpoint](continuous-worker.md) now supplies typed commands, the guarded native factory, destruction order and heartbeat watchdog. Connect its host session owner to the existing SDK queue pump, retire callbacks/buffers before disposal, and keep ASIO initialization unavailable until real readiness can be established.

Then perform the original owner-present Windows driver-load, traced input, silent output and analogue tests. Physical USB continuity, sample-clock/rate/control behaviour, latency, channel routing, current Serato/DVS and macOS remain unverified. [Engine ownership](continuous-engine.md), [host adapter](queue-to-asio.md), [physical test gates](bounded-duplex.md).
