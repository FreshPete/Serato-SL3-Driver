# Retained SL3 worker lifetime

The new isolated `--device-worker` entry implements a native device lease that survives successful audio stop/start. It addresses the observed repeated-redirect stall without claiming that a cached device list makes another redirect safe. The original finite diagnostics and single-open worker remain separate. This section describes the initial worker-only checkpoint. Subsequent host integration and the [archived native two-stream pass](retained-physical-test.md) supersede its preparation-only state. The latest worker uses protocol v2 and adds [explicit idle control inspection](held-controls.md); that extension has not run positively on native hardware.

**Subsequent host checkpoint:** the retained lifetime is now connected to the host/facade and selected by the production configuration provider, with positive simulated host/actual-IASIO tests and independent blocked-callback/DLL retirement coverage. [Current integration and remaining physical gate](retained-asio-host.md). This supersedes the owner-integration preparation status above and below; it does not establish native retained hardware success or install a timing profile.

## Lifetime and protocol

`src/core/device_session_protocol.*` defines a separate exact handshake, commands and snapshot format. It cannot be mistaken for the existing temporary-inspection protocol. Hello identifies native versus simulated implementation, queue version and format only; it acquires no device. Acquire opens the reviewed transport/exact fixture once and obtains a fresh actual clock. A successful ready reply reports `io_retired=true`, `device_released=false`.

Start names a newly created owner-only local audio mailbox, separate from the persistent control mailbox. The worker claims it once, requires pristine queues, reads the actual clock on the held device and rejects a rate mismatch before alternate activation or ISO submission. It then creates a fresh backend/request engine. Only matching actual input packet layouts admit output, as before. Each new stream begins its logical frame sequence at zero in its new queues; shared queues are never reset or reused.

Successful Stop drains every native request, destroys the request engine/backend and restores audio alternates to zero. It closes that stream's audio channel and reports ready while retaining the same redirect. Quit, closed host control channel and ordinary operation failures release the redirect after audio retirement. An idle held device remains available through application setup pauses; the pre-acquisition idle timeout does not silently release it. The existing independent heartbeat and parent-owned process job remain the containment mechanisms. A stalled native helper call still may outlive the watchdog's process-termination request in the kernel; this change does not guarantee bounded Windows kernel teardown.

The native implementation splits alternate deactivation from final redirect release. A partial activation exception restores attempted alternates or contains the isolated process. A target cannot release its owner device while active. Unproved I/O/backend/alternate/device cleanup fails the isolated worker rather than reporting ordinary success. Failures seal the session; there is no automatic reacquisition or audio retry.

Native completion and audio-space wakes remain event-driven. During streaming, separate control requests are checked between work steps, with a five-ms maximum completion-wait argument. No claim of a measured control-response deadline is made; helper/Windows execution can block and is supervised independently.

## Software verification

`sl3_device_session_tests` uses real private processes and explicitly simulated device/backend boundaries. It checks one acquire and one final release across eight- and 64-interval streams, fresh clock reads, a setup pause beyond the pre-acquisition timeout, zero-based fresh audio positions and correct target/device release order. It rejects acquisition before hello, double acquire, control-as-audio mapping, preloaded queues, a reused peer mapping, invalid clock and clock mismatch. It verifies partial accepted input startup drains before release, explicit live quit, idle host closure and eight watchdog/cleanup containment cases.

The real native executable is exercised only with an asserted absent helper path, proving its new handshake and pre-device failure path. The shared simulated backend was extracted unchanged from the existing fixture; existing continuous/ASIO tests still cover the old path. [Build evidence](evidence/retained-device-worker-build.json) records exact source/binary/log bindings. Neither these tests nor the earlier physical single-open result certify this new native lifetime on hardware.

## Next integration and test

The host ASIO owner must acquire during initialization, retain the control process and device across buffer creation/disposal and successful Stop, and create a new audio channel/owner for each Start. It must retire callbacks independently before disposing SDK planes; final owner release must close the held device/process. The production facade's current stop requirement includes process/device release, so it must be changed deliberately alongside its tests. Blocking callbacks must continue to retain their buffer/module/process leases. Do not enable production registration using fabricated clock or latency metadata.

After that host path has meaningful simulated IASIO coverage, build a dedicated bounded retained-lifetime hardware probe and tracing wrapper. The new native worker has a different binary identity; repeat same-build capture and silent-duplex prerequisites before its audio test. First check one acquisition, two fresh streaming channels and final release, preserving errors and every retirement domain. No repeated redirect or automatic retry is needed within that test. Sustained timing, analogue channel mapping, measured timing profile and current Serato/DVS remain separate requirements.

## Ordinary-session access finding

The reviewed UsbDk source at commit `84752c30037956149d53b498005b5368616f9257`, `ControlDevice.cpp:46`, allocates its control device with `SDDL_DEVOBJ_SYS_ALL_ADM_RWX_WORLD_RWX_RES_RWX`. On this host, the unchanged reviewed worker successfully listed exactly one high-speed fixture-matching SL3 from an explicitly non-administrator token at 18:17:39 UTC. Local record: `tests/results/local/medium-list-20261030-01/run.json`.

That proves ordinary-session cached listing, not actual ordinary-session redirect, streaming or ASIO operation. The tracing wrappers require elevation for system trace/security inspection; those prompts alone do not establish a transport requirement for an elevated broker. Test actual process permissions before introducing such a service. Security policies remain unchanged.
