# ASIO audio-thread and callback ownership

`AudioOwner` now runs the real SDK queue pump on a dedicated CRT thread while `BufferLease` retains the published ASIO planes. It accepts an already-owned worker process and channel; it deliberately leaves typed worker control to a separate control owner. **This is a tested host data/callback component, not the complete production host coordinator. The registered-driver COM DLL remains unavailable and unregistered. Positive I/O tests still use the explicitly simulated worker.**

## Buffers, callback leases and stop

The control owner prepares buffers before starting the audio thread. A `BufferLease` permits only one acquired audio owner and rejects creation/disposal while acquired. The audio thread exclusively owns queue processing and buffer-flow mutation. It is started before the worker's typed start, so input can be consumed while the control thread waits for replies. The process, channel and buffers have shared lifetime; their borrowed handles and pointers cannot be destroyed underneath a blocked thread.

Every host callback acquires an atomic gate lease. Stop closes the gate and signals the audio thread; callbacks already admitted may finish, but no later callback lease is admitted. A callback cannot synchronously stop/wait for its own owner: `stop` returns a reentrant result immediately. The explicit nonblocking `request_stop` is separate. C++ host callback exceptions remain contained by the buffer core, release their gate lease and become a recorded pump failure. This does not promise recovery from arbitrary host access violations or invalid third-party state.

`stop` waits at most the caller's bounded timeout (capped at five seconds) for actual thread retirement. Timeout returns `retired=false` and leaves the planes, channel, process reference and code alive. It never kills a host callback thread. A worker stop reply can already report I/O/device cleanup while the host callback is still executing; those are independent proofs. Buffer disposal remains rejected until the audio owner has retired.

Each `AudioOwner` is one thread/run. After it retires, a new owner can reuse the **same** prepared `BufferLease` and plane addresses with a fresh worker/channel identity. The bridge resets its stream positions/banks for that new run. This supports the repeated start/stop contract without reusing old shared-queue counters or reallocating published buffers. Control configuration remains single-owner; callers still must retain their own normal object/DLL and callback-state lifetimes.

Atomic observation publication exposes a consistent logical position, bank and host observation stamp without reading mutable buffer-core state from another thread. It is not a physical sample-clock or latency measurement. A known worker exit prevents new processing/callback admission and closes the data channel. Pump/callback/wait failures also close it so the worker can retire its own resources. This component does not independently claim worker exit, empty-job accounting or physical recovery.

## DLL lifetime through the CRT epilogue

A normal shared pointer alone cannot protect executable code from `FreeLibrary`. Before starting an audio thread in a DLL, the owner acquires a normal module reference using the thread entry address. It does **not** use permanent `GET_MODULE_HANDLE_EX_FLAG_PIN`. Tests linked into the main executable need no extra DLL reference. [Module-reference contract](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-getmodulehandleexw).

The thread runs through `_beginthreadex` and returns normally through its CRT epilogue. A one-shot Windows thread-pool wait observes its real kernel thread handle. Only after that signal does the retirement callback release the buffer acquisition and signal `retired`. Thus a thread-ID guess, a callback-return counter or an early "done" marker cannot substitute for thread exit.

The retirement callback schedules the DLL reference for release with `FreeLibraryWhenCallbackReturns`, closes its wait object and drops retained resources. Windows releases the module only after that final callback returns, preserving its own return instructions/destructors too. An unproved retirement observation retains the context/module/buffers instead of guessing cleanup succeeded. [Asynchronous wait-object release](https://learn.microsoft.com/en-us/windows/win32/api/threadpoolapiset/nf-threadpoolapiset-closethreadpoolwait), [callback-safe module release](https://learn.microsoft.com/en-us/windows/win32/api/threadpoolapiset/nf-threadpoolapiset-freelibrarywhencallbackreturns).

Destroying an active owner closes its callback gate and channel but does not free the active thread's shared resources. A callback that never returns can therefore retain memory/code until process exit. This intentional incomplete-retirement state is preferable to freeing executing code or using forced thread termination. The host control coordinator must surface/retain that state and manage the separate worker process; this data component performs no installation, registration, native-worker kill or availability promotion.

## Full-duplex work wakes

The existing input/output events now also signal when a consumer frees publication space in the opposite direction. Consuming IN wakes the worker; consuming OUT wakes the host. A producer can therefore retry a retained full-queue block without a timed spin or requiring unrelated new PCM. The event is a work hint: a wake may have no new input/output block. Queue counters remain authoritative, and existing empty/stale wakes remain valid. No wire/layout version or extra named object was needed; shared transport stays version 3.

The audio thread waits on stop, exact worker-process exit and the host work event. It polls queue ownership before waiting. This supplies event-driven backpressure handling, not a hard scheduling, page-residency or real-time guarantee.

## Verification actually performed

All **22 native tests pass in Release and Debug**; eighteen pass without the SDK at an intentionally absent path. The new test uses real worker processes, checked queues, actual SDK planes/callbacks and the dedicated owner thread. It checks all six logical input channels/bytes, reversed output selection, callback bank/position observations, reentrant-stop rejection, live-disposal rejection, published output and zero observed C++ `new` allocations during a successful steady EXE-linked processing interval. That measurement does not cover all kernel/CRT or separately linked DLL allocations.

Two fresh sessions reuse the same plane addresses. Separate tests prove worker-exit handling, C++ callback-failure recording and lease release, and a deliberately blocked callback: the worker is stopped first, a 20 ms audio stop remains incomplete with one callback lease, buffers cannot be disposed, and releasing the callback permits actual retirement without another admitted callback. The blocked case uses a 64-interval batch containing six host banks, so the gate also suppresses the remaining callback switches inside the already-running processing call.

An additional **unregistered test DLL** starts a simulated session and blocks its host callback. The test destroys all caller-owned driver resources, releases the caller's `LoadLibrary` reference and verifies the DLL remains loaded. The private worker exits while the callback/planes remain leased. After the callback is released, it successfully reads the still-valid planes, returns, and the DLL actually unloads. This exercises the return path through buffer processing, CRT thread exit and final retirement callback. It does not load or register the production ASIO COM DLL.

Queue regression tests separately prove that retiring OUT wakes a blocked host producer without inventing IN, and retiring IN wakes the worker. No native test worker remains alive. Read-only preflight still shows the UsbDk service absent, no helper/audio submission and no freshly available Secure Boot query from this unelevated process. [Pinned source/build, DLL and process evidence](evidence/asio-audio-owner-build.json).

## Remaining production connection

Add the host control coordinator: launch/pin the real worker, validate native kind/protocol, establish actual clock discovery/selection, pre-arm the audio owner, issue typed start and handle failure without losing either ownership domain. Coordinate audio gate closure, worker stop/quit replies, exact process/job observation and audio-thread retirement. Unknown worker cleanup and an active host callback must remain separately retained states.

Then connect this contract to IASIO initialization/buffer/start/stop/disposal while retaining appropriate COM/module lifetime. Keep initialization unavailable until actual readiness can be established. Driver loading, traced physical capture/silent output, clock/control/routing/latency, analogue audio, current Serato/DVS and macOS remain unverified. [Worker protocol](continuous-worker.md), [SDK pump](queue-to-asio.md), [ASIO COM interface](asio-com-server.md), [physical gates](bounded-duplex.md).
