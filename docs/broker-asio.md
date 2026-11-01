# ASIO callbacks and ordinary object lifetimes over the broker

The driver facade now supports a broker-backed session as well as its existing
private-worker session. The new path runs official SDK buffers and callbacks over
the [private broker connection](broker-pipe.md). It has been exercised through an
actual COM/IASIO test DLL in a separate process, without a custom factory-scope
request. Positive evidence is **simulated only**. The installed ASIO configuration,
registry, hardware binding and security policies were not changed.

## Worker and callback ownership

`windows/process_wait.hpp` supplies a shared, duplicated synchronize/query process
reference. It exposes no launch, job or termination operation. `AudioOwner` uses
this reference for liveness. The private-worker constructor additionally retains
its original shared `Process` as a lifetime lease, preserving that job until an
executing callback and audio thread actually retire. A broker client holds only
the duplicated reference; its destructor cannot terminate the broker's worker.

`asio/driver_session.{hpp,cpp}` adapts the existing `HostSession` to a common ASIO
control surface. `asio/broker_session.cpp` implements that surface with a
`BrokerClient`, fresh per-start data mappings, `BufferLease` and `AudioOwner`.
The ordinary facade and shared owner accept an explicit `BrokerAttachment` with
an already-established server-process reference and expected native/simulated
kind. No endpoint discovery or process launch occurs in this attachment path.

Callback metadata/position queries remain local. Stop and buffer disposal from a
callback are rejected. A stream stop separately drains worker I/O and waits for
the audio thread; disposing buffers cannot establish either USB release or
callback retirement. Unknown start/clock outcomes invalidate usable clock state
and seal the client rather than falling back to cached readiness.

## Reports preserve the ownership domain

`HostReport.domain` distinguishes `owned_worker` and `broker_client`. A broker
report keeps its `process`/job fields empty and uses the explicit `broker` fields
for attachment and worker liveness. It never fills in fictitious owned-job state
to satisfy the old stop checks.

| Observation | Broker client meaning |
| --- | --- |
| `broker.attached` | The client has an active connection/lease. |
| `broker.ever_attached` | Admission completed at least once. |
| `broker.detached` | The detach reply and terminal connection hand-off completed. |
| `broker.worker_alive` / `worker_exited` | Observation of the duplicated worker process object. |
| `audio.retired` | The callback/audio thread actually completed. |
| `io_retired` | Last accepted worker I/O observation, invalidated before stream publication. |
| `device_released` | Physical release; a normal client detach leaves this false. |

`driver_session_closed()` recognizes complete retirement in the appropriate
domain. A broker client may retire while its external owner keeps the device and
worker alive. The final client report therefore has `device_held=false` locally,
`device_released=false`, and a last device snapshot still showing the broker's
held ready state. Worker exit alone does not prove native release.

When an object disappears during an executing callback, the nonwaiting failure
path closes the control connection and requests local stop. The external broker
owns worker containment. Audio planes, mapping, wait reference and the executing
DLL remain leased until actual thread retirement; no callback thread is killed.
This protects callback resources, not a released COM object's interface pointer:
a host must not call methods on that object after its final `Release`.

## Consecutive objects and the pipe hand-off

Ordinary clients may release a metadata object and immediately create another
factory/object. Detach now waits for the server's terminal pipe disconnect after
the already-established reply/acknowledgement. A new connection performs one
bounded `WaitNamedPipe` availability wait and one `CreateFile`, with the expected
server process checked throughout admission. There is no reconnect loop, worker
launch or USB reacquisition. This is IPC availability, not a timed USB recovery
assumption.

Stop/detach client commands accept bounded deadlines shared across their control
writes/reads; cancellation storage still remains owned until I/O retires. On a
deadline/failure the session disconnects without fabricating a detach or physical
release. A blocked callback's planes remain unavailable for disposal/reuse.

## Actual component/process tests

`sl3_broker_asio_tests` creates a private simulated broker in one process and runs
the ASIO host in another. Its ordinary-object scenario loads the real test DLL,
configures its fixture-only provider, and creates a **fresh `IClassFactory` for
each object**, releasing the factory immediately after construction. It never
requests the custom `DeviceScope` interface and does not register a COM server.

One metadata object is followed by two audio objects. Each audio object performs
two starts/stops on stable 128-frame SDK planes, with at least twelve callbacks
per start. Tests check bank alternation, logical sample positions, clock metadata,
callback reentry refusal, synthetic profile binding and observed-rate-only ASIO
selection. Output is zero PCM. Exact audit counts require one acquisition, eight
fresh getters, four stream starts/ends and one final owner release. There is no
parent-side served barrier between successive objects.

A report scenario reuses a client across two facade objects and checks a fresh
clock plus acknowledged client retirement with no owned job or physical-release
claim. A blocked-callback scenario releases its COM object and the caller's DLL
reference while the callback is executing. The DLL remains loaded until that
callback returns and its thread/reaper actually retire; no extra callback lease
is admitted. The broker records its separate failure/cleanup outcome.

The existing private-worker/audio-owner tests also run after this refactor,
including retained owned-job/DLL lifetime, callback failure and steady processing
allocation checks. The production COM test explicitly rejects the new fixture
configuration export; that export is compiled only into the test DLL. Exact
counts, hashes and private checkpoint location are in
`docs/evidence/broker-asio-20261101.json`.

## Remaining boundary

**Later checkpoint:** [reviewed broker record binding](broker-configuration.md) now supplies the separate production configuration format and native-only runtime contract. Controller publication and installation remain unfinished. The paragraphs below preserve this ASIO component checkpoint's earlier boundary.

Production configuration still selects its existing private-worker path and
requires its reviewed measured timing profile. There is no installed broker
controller, reviewed rendezvous record or production broker configuration yet.
The fixture's 7/11 extra-frame values are synthetic test inputs, not measured SL3
latency. Passing COM tests does not demonstrate registry activation, an arbitrary
application's ASIO loading sequence, analogue audio, native clock continuity,
current Serato admission or two-deck DVS.

Next is reviewed controller/rendezvous configuration connecting the ordinary
production facade to the explicit session owner, followed by attended native
validation and real timing/audio measurement. Current Serato's discontinued-device
and separate audio/API/DVS admission still require their own implementation and
proof. Windows remains first; macOS is deferred.
