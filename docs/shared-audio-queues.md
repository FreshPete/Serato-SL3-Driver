# Fixed input/output data queues

The host/worker channel now has separate fixed-capacity input and output queues alongside its control mailbox. Real processes verify packet-preserving flow and backpressure. A later [host adapter checkpoint](queue-to-asio.md) connects these queues to SDK buffer callbacks in software. **The USB streaming loop and live ASIO session owner remain unconnected. No physical audio was captured or played in these tests.** The diagnostic worker continues to advertise finite-input capabilities only.

## Storage and ownership

Shared transport version **2** originally added two eight-slot queues to the mapping. Current version **3** adds an active packet count for [8–64 intervals in multiples of eight](audio-transfer-granularity.md). Each 8,192-byte slot contains fixed metadata, storage for 64 packet frame counts and up to 8,064 PCM bytes. An active packet contains 1–7 complete six-channel, three-byte-container frames: 18–126 bytes. Inactive counts must be zero. The complete mapping remains 196,800 bytes. Layout/offset assertions compile in both configurations. The typed finite-diagnostic command protocol remains version 1; it is a separate layer.

The worker produces input and consumes output. The host consumes input and produces output. Each direction has exactly one producer and one consumer; the API rejects the opposite endpoint roles. One control owner can run independently after construction because its local state and shared fields are separate. This does not permit concurrent producers or consumers for one direction.

Each producer finishes writing its slot before publishing the write counter. Each consumer finishes copying actual bytes before publishing the read counter, so storage cannot be reused while that consumer still reads it. Windows interlocked operations provide atomic counter access and ordering. [Exchange contract](https://learn.microsoft.com/en-us/windows/win32/api/winnt/nf-winnt-interlockedexchange), [compare/exchange alignment and ordering](https://learn.microsoft.com/en-us/windows/win32/api/winnt/nf-winnt-interlockedcompareexchange).

Counters use unsigned modular differences and an eight-slot occupancy limit; a test seeds them across 32-bit wrap. Logical frame positions remain separate 64-bit values. Full publication returns `full` without advancing a counter or the producer's expected frame position. The caller must retain/retry the same block or fail the stream explicitly; silently dropping it and retagging later audio is not allowed by the session contract.

## Packet, rate and fault contract

Every block preserves its active packet count and the complete count array, with zero inactive entries. The valid byte count is the sum of actual frame counts × 18. Only those PCM bytes are copied; unused caller output storage is zeroed and must not be interpreted as extra audio. Maximum-size blocks are checked through their final byte. No nominal-rate packet-length generator or fabricated recovery samples are involved.

Logical positions must begin at zero and advance exactly by the actual frame count. Observation times cannot regress. The first producer declares the metadata rate; both directions must then retain that same 44.1/48 kHz value for this channel identity. This is consistency checking, **not device rate negotiation or sample-clock measurement**. Changing rate/restarting requires a new session identity and real device control outside this queue.

Invalid packets, discontinuity, time regression, changed rate or impossible wire occupancy latch the first data fault. New data operations then report `faulted`. Packet/sequence/rate data faults do not seal otherwise valid control framing, allowing a later shutdown command. Corruption of the control header itself can still invalidate the whole channel and require process-level containment.

`try_push_audio` and `try_pop_audio` use fixed storage and perform no C++ allocation in their successful code paths. They still copy bytes, invoke interlocked operations and signal Windows events; this is not a hard real-time or kernel-allocation guarantee. `wait_pop_audio` is a separate bounded waiting API for a worker/audio-owner thread, not a callback deadline promise. Data events are independent of control-reply events, so audio wakes cannot be mistaken for command replies. A previously signalled event can produce an explicit empty wake after the queue has drained.

The [audio-owner integration](asio-audio-owner.md) also wakes the opposite endpoint when a consumer retires a block and frees publication space. Input/output events are therefore full-duplex work hints, not proof of new PCM. Counter checks and explicit empty wakes preserve the existing version-3 contract. This lets a retained full-queue publication retry without a timed polling loop.

## Shutdown remains a session-owner responsibility

Explicit close prevents newly entered data operations and wakes waiters. An operation already in flight can overlap close/fault and complete; close is not proof that an ASIO callback has retired. **All callers must stop/join or release their leases before their process disposes its `Mailbox` object.** Another process retaining its own mapped view remains responsible for that view.

Data waits do not independently authenticate or monitor peer-process exit. The control/session supervisor must observe the retained process handle, close/fault data flow when appropriate, and retire callbacks separately. The queues are not a security boundary against hostile code running as the same user. No in-place fault reset or queue restart exists.

## Validation actually performed

The original version-2 checkpoint passed **16 native tests in Release and Debug**; the SDK-free build passed fourteen with an absent SDK path. Current version-3 verification passes seventeen and fourteen respectively, including active-count/tail/version rejection and the [full SDK path with short batches](audio-transfer-granularity.md). Local queue tests cover empty/full state, unchanged caller output on failure, all eight slots, retry after full, FIFO order, maximum PCM size, unsigned counter wrap, malformed wire sizes/occupancy, fault latching and control availability after a data fault. Separate producer/close threads exercise data-event waits.

In each configuration, a test fixture copies **2,000 blocks across real processes and both queues**, with synthetic metadata rates 44.1/48 kHz and varying packet lengths. Every actual PCM byte and packet count is checked. This is a software echo, not analogue loopback, physical clock, USB continuity, channel mapping or latency evidence. A measured run of 1,000 successful local push/pop pairs observes zero C++ `new` allocations. Page residency and scheduling jitter are unmeasured. No worker remains alive. [Build/source evidence](evidence/audio-ring-build.json).

## Remaining integration

Connect a real continuously queued USB transport to the worker-side queues. The fixed-block/SDK component now has a tested [host-side queue adapter](queue-to-asio.md); it still needs a live owner, suitable transfer granularity and measured callback timing. Define start/stop/fault commands and a callback/buffer lease owner. A full queue, absent data or dead worker must produce a controlled stream fault, not invented samples or readiness. Physical input/output, timing, ASIO availability and current Serato/DVS require their original validation gates. [Typed diagnostic worker](typed-worker.md), [ASIO component](asio-buffer-component.md), [active checkpoint](goal-progress.md).
