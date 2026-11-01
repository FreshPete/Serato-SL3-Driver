# Continuous request engine

An original `ContinuousStream` core now keeps four input requests and four output slots in circulation until stop or fault. It rearms individual completed input slots, instead of repeatedly starting finite capture transactions. The original checkpoint used a fake backend/echo peer. A later [native adapter checkpoint](native-continuous-adapter.md) connects real request/Windows API code and the actual shared queues through simulated helper I/O, followed by a [production worker dispatcher/watchdog](continuous-worker.md). **The native physical session remains untested. No physical stream or working ASIO device is claimed.**

## Request and data ownership

The backend prepares all eight resources before the first submission. A rejected prepare owns no resource; a rejected submission owns no pending request. An accepted submission retains its native storage and overlapped state until a poll explicitly proves terminal success/failure. `unproven` is separate from a terminal transfer error. An observation failure cannot justify freeing memory.

Input completion can arrive out of order, but publication follows original submission order. A completed slot is not reused until its actual packet data has been validated, compacted and copied to the peer. Full publication retains the exact private batch, including its original observation timestamp. Retry does not advance positions or rearm that slot. No later input can overtake it.

The core validates full-width packet lengths/statuses before narrowing: each active interval must contain 1–7 complete 18-byte frames, and the returned interval count must match the configured 8–64 count. It copies actual slices from fixed 126-byte input strides, excluding padding. Logical positions advance only on successful input publication. The observation timestamp is sampled when the ordered batch is prepared for publication; it is not a device timestamp, USB frame number or measured sample-clock time.

Up to sixteen outstanding input schedules are retained separately from PCM. Host output must exactly match the oldest schedule's logical position, observation timestamp, metadata rate, active count and count array before native submission. Unexpected, reordered or retagged output faults the stream. Output bytes are copied into backend-owned storage before submission returns, because the core immediately reuses its caller buffer. Accepted output submission is not proof of physical playback. The backend must validate aggregate/per-packet output statuses and must not interpret Windows OUT `ActualLength` as accepted audio bytes.

This layer is one non-reentrant worker owner with fixed storage and no thread, sleep or heap allocation in construction/processing. Backend/peer implementations must not call back into it and must outlive it. `AudioBlock` now lives in a portable core header; the existing Windows type is an alias, so shared transport remains version 3 with unchanged wire sizes. The ASIO host remains outside this worker and its native I/O ownership.

## Faults, deadlines and shutdown

Per-request and peer-flow stall deadlines use a monotonic nanosecond clock, with a separately bounded drain interval. Defaults are 20 ms stall and 2 s drain; these are initial policy values, **not measured audio deadlines or latency guarantees**. Preparation time is excluded from pending-I/O time. Already late requests/outputs are rejected before handling new data, so a long owner pause cannot silently reset their ages. Missing output, input backpressure, input/output request timeout, packet errors and peer errors are distinct first-fault causes.

Stop/fault first requests cancellation of **every** pending direction, then begins polling. Cancellation failure does not release or change a request's lease. Terminal resources retire independently under one common drain deadline. If any completion remains unproved, the engine ends in `retained` with an exact bitmask. A failed terminal resource release also produces retained cleanup, and is never automatically retried. The original fault remains available even when cleanup also fails.

**A false `start` return is not cleanup proof.** Partial startup may already have accepted I/O and remain `draining`; its owner must continue stepping to `stopped` or `retained`. Neither stopped nor retained sessions can restart. A fresh session identity is required. Retained native storage must stay alive until the isolated worker is contained; ordinary backend/device unwinding is unsafe.

If the clock regresses, cancellation begins and the engine does not rely on that clock to wait indefinitely. It polls once and retains any still-unproved slots. The caller must keep stepping during a normal drain. Native method calls themselves can still stall in Windows/helper code; this core cannot guarantee their wall-clock duration. A real worker needs an independent watchdog and the existing retained process/job supervisor, without terminating the audio host.

## Verification actually performed

All **18 native tests pass in Release and Debug**; fifteen pass without the SDK at an intentionally absent SDK path. The new engine test runs **18,000 input/output batches** across both declared rates and 8/16/64-interval shapes. For each combination, 3,000 input batches are compacted, echoed, checked byte for byte and submitted as fake output while the same four slots repeatedly wrap and rearm. Four later input requests remain queued until explicit stop; outstanding fake output is cancelled during stop. These counts do not claim 18,000 completed physical transfers. Successful processing observes zero C++ `new` allocations after setup.

Fault tests cover completion reordering, exact full-queue retry, all preparation failure positions, partial initial submission and rearm failures, output submission rejection, all full-width invalid packet cases, mismatched output schedules, terminal errors in both directions, peer errors, every distinct stall policy, failed cancellation, unprovable observation, failed resource release and regressed clock. Tests verify cancellation of all eight active directions precedes any drain poll, exact retained masks, no release of pending memory, first-error preservation and partial-start retention. A Debug stack overflow in initially oversized test fixtures was corrected by reserving output buffers only for output slots and using the real queue's eight-slot capacity; the default executable stack was not enlarged.

[Pinned source/build and retained test-log evidence](evidence/continuous-engine-build.json). No driver, certificate, device binding or security policy changed. Read-only preflight and process inventory remain separate from physical validation.

## Native connection and remaining ownership

The [native adapter](native-continuous-adapter.md) now implements this backend contract with stable per-slot request/result/length/PCM/event/overlapped storage, short batches, terminal snapshots and private output copies. Its positive I/O tests remain simulated. The [continuous worker](continuous-worker.md) supplies the guarded factory, queue peer, typed commands and a renewable heartbeat, verified beyond the old fixed twenty-second cutoff.

Tie worker cleanup state to process containment and callback retirement in the host session supervisor. Keep the COM DLL unavailable until that real session contract exists. Physical input, traced silent output, analogue audio, clock/control, current Serato/DVS and macOS remain required.
