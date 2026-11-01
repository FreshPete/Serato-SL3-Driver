# Continuous worker session and watchdog

**Update:** continuous protocol 2 adds clock inspection and host coordination; see [the current contract](host-session.md). The version-1 description below records the original checkpoint.

The actual native executable now has an isolated `--stream-worker` mode with typed hello/start/state/stop/quit commands, a persistent continuous loop and an independent heartbeat watchdog. It connects the exact-device/helper gates, native adapter, continuous engine and shared queues. **Positive lifecycle/data tests use a separately identified simulated target. The native executable is tested only for handshake, malformed commands and a deliberately absent-helper startup failure. No physical continuous session or available ASIO driver is claimed.**

## Protocol and ownership

Continuous-session protocol version **1** is separate from the finite diagnostic's version 1; shared audio transport remains version **3**. The old `--worker` finite capabilities and 64-command limit remain unchanged. The continuous mode has no finite command count or fixed 20-second lifetime. Conflicting worker modes are rejected before opening a channel.

| Command | Opcode | Behaviour |
| --- | --- | --- |
| hello | `0x200` | Empty body; compiled format, queue version and explicit native/simulated kind only |
| start | `0x201` | Strict 32-byte configuration; one start per fresh session identity |
| state | `0x202` | Empty body; current phase, original fault, counters and cleanup state |
| stop | `0x203` | Empty body; reply waits for stream retirement and device release |
| quit | `0x2ff` | Stop/release if needed, publish the final reply, then exit |

Hello never constructs the target or loads the helper. A valid start requires a prior handshake, supported metadata rate, 8–64 intervals in multiples of eight and bounded nonzero stall/drain policies. It carries no raw host pointer or arbitrary device/endpoint identity. Unknown, malformed or out-of-state commands cannot start the target. A stopped/failed identity cannot restart; create a new channel/worker.

The native start path queries the already-running reviewed driver, pins/loads the exact helper bytes, validates the exact SL3 descriptor fixture, redirects it, reads the existing `0x30` rate getter, checks that rate against the requested metadata, activates the two audio alternates and queues the first input requests. It uses no rate setter, reset, firmware or installer operation. **Snapshot rate fields describe the requested configuration; a failed start does not turn those fields into an observed device rate.**

A running reply means requests were accepted into this internal lifecycle. It does not prove sample-clock validity, analogue audio, latency, USB continuity or Serato/DVS readiness. Startup is synchronous on the worker owner; a state query cannot interrupt a blocked startup call. The heartbeat/process status and an owner-present USB trace are needed to investigate that case.

State replies have a checked 128-byte little-endian header, six full-width counters and at most 512 diagnostic bytes. Reserved words, enum ranges, masks, sizes, flags and counter relationships are validated. The two cleanup flags are **I/O resources retired** and **device release reported success**; neither is an audio-availability flag. Both also hold when startup never acquired anything. Native cleanup flags report API outcomes, not physical enumeration/binding/security readback. The traced test's before/after checks remain required.

The worker owner serializes commands with core polling. Stop/quit hold the control request lease while draining. A partially failed start can reply `draining` with a nonzero pending mask; it never reports completed cleanup early. Automatic stream faults preserve their original cause, retire I/O/device state and remain queryable until quit or idle expiry. Retained I/O/resource/device cleanup causes fail-stop of this worker rather than ordinary unwinding. Host close also initiates stop/release. The stream object is destroyed before its backend/device, preserving borrowed-handle/module lifetimes.

## Waiting and liveness

The native loop waits on the local command event, host-output event and events for actual pending requests. Synchronous/uncertain native submissions are polled immediately. It uses no forced `Sleep(1)` pacing for physical transfers. Control encoding may allocate on actual command handling, and no real-time or measured pacing guarantee is claimed.

Combined waiting exposed a lost-wakeup defect in the original mailbox reader: the loop could consume an auto-reset event before `receive` tried to wait on it again. The reader now checks published request ownership first, tolerates stale publication edges and keeps the original blocking deadline. Borrowed event handles do not extend object lifetime and must never be closed. Tests cover an externally consumed request event and a stale edge without sealing a valid channel. [Windows event-reset contract](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createeventw).

The heartbeat has a separate thread, lock-free deadline, private stop event and renewable phase budgets: **8 s startup, 1 s live native work, 8 s cleanup** by default. Test fixtures use shorter budgets. A pulse cannot revive an already expired deadline. The heartbeat requests exit-70 fail-stop of its own process when progress stops; it never targets the audio host. Healthy progress renews the deadline indefinitely. It uses millisecond system uptime for coarse liveness, separate from the native QPC observations and the unmeasured physical sample clock. [System timer contract](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-gettickcount64).

Neither the heartbeat nor a termination request proves kernel I/O or process teardown completed. The parent must observe its retained exact process/job handles and keep unproved resources retained. Fake stalled functions in these tests do not emulate an actually stuck kernel IRP. Stop acknowledgment also says nothing about an ASIO callback still executing in the host; the future host owner must retire its own callback/buffer leases separately.

## Verification actually performed

All **21 native tests pass in Release and Debug**; eighteen pass without the SDK at an intentionally absent SDK path. The new real-process session tests check strict codecs, full-width counters, native/simulated distinction, pre-handshake/malformed/duplicate commands, more than 64 status exchanges, start, 100 exact input batches through shared queues, echo output, stop/device release, immutable stopped counts and restart rejection. They also check failed factory rollback, delayed partial-start cleanup, exact data-plane mismatch faults, host close and final reply/process retirement.

Six isolated session failure cases cover hung factory, hung initial submission, hung polling, hung cleanup, failed device release and retained I/O. An additional standalone hung-heartbeat process is contained. The production executable's negative start uses an asserted-missing local helper path, so no helper can load or device/audio submission occur even if the service state changes. All these children retire under retained process/job handles.

A separate healthy Release heartbeat process ran **21,547 ms**, exited zero and left an empty job. This verifies survival beyond the old fixed 20-second cutoff. It is a liveness test with no USB/helper, not 21 seconds of physical audio. Read-only preflight still reports no installed UsbDk driver/helper/audio submission; Secure Boot query is recorded as unavailable from this unelevated process. [Source/build, long-run and process evidence](evidence/continuous-worker-build.json).

## Remaining host and physical work

The [audio-thread/callback owner](asio-audio-owner.md) now supplies independent processing and retained plane/DLL lifetime through actual thread exit. Implement the host control coordinator around it and the existing process supervisor/codecs, establish appropriate clock discovery/selection before a usable ASIO initialization, and coordinate the two ownership domains. Worker-side I/O cleanup alone must never permit freeing an executing host callback's memory. Keep the COM DLL unavailable and unregistered until the actual readiness/lifetime contract is satisfied.

The production happy path has not run: the driver must still pass its owner-present load test, then descriptor/rate/startup checks, traced input, silent output and controlled analogue audio. Measure completion/callback timing, continuity, clock/rate/control behaviour and logical-to-physical channel routing. Current Serato's discontinued-device and legitimate audio/DVS contract, plus macOS Tahoe, remain separate required work. [Native adapter](native-continuous-adapter.md), [host queue pump](queue-to-asio.md), [physical gates](bounded-duplex.md), [Serato routing](serato-audio-routing.md).
