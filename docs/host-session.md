# Host control coordinator and clock inspection

`HostSession` now connects the pinned private worker process, typed continuous
commands, shared data queues, SDK buffers and dedicated audio owner. Its positive
tests use explicitly simulated I/O. The production ASIO COM DLL remains
unavailable and unregistered; this checkpoint does not establish physical audio,
current Serato/DVS support or macOS compatibility.

## Clock contract

Continuous-session protocol **2** adds empty-body `inspect` (`0x204`). Its hello
rejects version-1 peers; finite diagnostic protocol 1 and audio queue version 3
are unchanged. Only a greeted idle session may inspect, including repeated
inspections. Active, stopped and failed sessions reject it. A malformed body is
rejected before invoking the inspector.

A successful reply is exactly eight little-endian 32-bit words:
`[2, observed_rate_hz, 6, 3, 18, 3, 0, 0]`. The accepted rates are 44,100 and
48,000; six logical channels use three-byte signed samples, eighteen bytes per
frame. Flags `3` certify that the inspector has retired its I/O and released its
temporary device handle. All fields and reserved words are checked. This says
nothing about measured clock stability, physical channel mapping or streaming
readiness. The compiled format remains based on the existing driver analysis.

The native inspector uses the existing exact service/helper/device gates, opens
a temporary redirect, issues the bounded interrupt rate getter (`0x30`) and
closes the redirect before replying. It does not select the audio alternates or
submit isochronous audio. There is no rate setter, firmware write or reset. A
provider must roll back on exception or contain the isolated worker if cleanup
cannot be proved. Inspection uses the startup heartbeat budget; a stalled call
cannot renew an expired watchdog after returning.

Inspection leaves the streaming snapshot idle, with rate/interval fields zero
and no PCM published. Failure instead seals the worker lifecycle as failed;
subsequent start on that identity is rejected. A successful inspection's rate
is separate from streaming configuration. The native streaming constructor
already repeats the rate getter and rejects a mismatch before activating audio.

## Host ownership

Inspection launches a fresh hash-pinned worker, verifies the typed kind/protocol,
queries the clock and then stops/quits and verifies its exact process/job
retirement. It keeps the observed rate as metadata, with no idle worker left to
expire while the host waits. This is an observation, not a live device lease.

Each start creates another fresh process and channel. It verifies the kind and
observed rate again; a changed rate rejects startup before creating the audio
owner and requires explicit re-inspection. Prepared SDK plane pointers survive
fresh sessions. The audio thread is armed before the typed worker start, so its
queues have a consumer before native audio is submitted. A running reply must
match the requested rate and interval count, and the audio owner must still be
running when startup completes. Running is an internal software state.

Stop closes the host callback gate first, then requests worker stop/quit. A
single caller-supplied deadline, capped at five seconds, covers reply waits,
process/job observation, containment observation and audio-thread retirement.
Worker I/O/device acknowledgements, exact process/job observations and actual
audio-thread retirement remain separate report fields. Unproved native cleanup
is not converted to success when the process exits. Forced cleanup applies only
to the owned private job; executing host threads are never terminated.

Windows can signal a process before job accounting becomes empty. The host now
observes both through the stop deadline before requesting containment. This
fixed a test-discovered orderly-shutdown race that incorrectly reported forced
termination. Incomplete stop retains all handles and callback planes. Further
inspection, restart or buffer disposal is rejected until both process and audio
ownership domains retire. Destruction requests worker containment without
waiting on blocked user code; the audio owner's existing shared state/module
leases retain its planes and code until the actual thread exits.

Control operations have one owner and may allocate/wait. Callback reentry into
inspection/start/buffer mutation is rejected immediately; callback stop returns
an explicitly reentrant report without issuing worker commands, claiming device
cleanup or closing its own gate. `observation()` exposes the audio owner's
logical frame/host-time snapshot. There is no automatic host callback timer,
measured sample clock, MMCSS policy or implemented rate-changing control yet.

## Verification and remaining work

The real-process host tests cover three fresh sessions using stable SDK planes,
8/64-interval batches, callback reentry, a blocked callback after complete worker
cleanup, control-owner destruction while that callback retains planes, callback
exceptions, wrong executable hash, truthful simulated/native kind mismatch,
failed/partial/stalled worker startup and failed/invalid/stalled clock inspection.
A file-backed simulated clock changes from 48 to 44.1 kHz between inspection and
start: startup rejects it with no callback, then explicit re-inspection permits
44.1-kHz metadata. This is not a physical clock-change test.

The actual native executable is exercised only with an asserted absent helper
path, so it rejects before loading the helper or opening hardware. Strict codec
tests reject bad formats, reserved fields, versions and lengths. The previous
audio-owner DLL retain/unload tests continue to pass. Release and Debug pass
23/23 native CTest cases; the SDK-free configuration passes 18/18 with a
deliberately absent SDK root. [Hash-pinned build evidence](evidence/host-session-build.json).

Next work is the production IASIO facade and reviewed worker-path configuration,
including initialization/readiness semantics, buffer/clock/latency reporting and
normal host lifecycle. The native happy path still needs runtime driver
admission, traced capture-first validation and actual physical audio/timing and
recovery checks. Current Serato's discontinued-device/support and explicit-audio
selection contracts remain separate from ASIO transport availability; see
[the recovered routing](serato-audio-routing.md). macOS follows Windows.
