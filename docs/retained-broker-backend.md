# Retained worker ownership across audio-client processes

This checkpoint implements the control backend for a future explicitly started,
ordinary-user session broker. It is **not yet connected to the production ASIO
DLL**, and does not restore current Serato support. No broker was run against the
SL3, no administrator launch occurred, and no installation or security setting
changed during this work.

## Why this owner is needed

The existing [factory scope](factory-scope-controller.md) preserves a redirect
across IASIO objects only when a host deliberately uses the same factory and our
custom scope interface. Ordinary COM clients do not request that interface.
An object held in a separate controller process cannot share an in-process C++
owner with Serato. A timed global cache would also provide neither an explicit
final owner nor evidence that a second USB acquisition is safe.

`src/windows/retained_broker.{hpp,cpp}` instead owns one worker process/job and its
control mailbox independently of client audio processing. Explicit `open()`
launches the reviewed-hash executable, verifies its typed native/simulated
handshake and acquires once. Construction, attachment and stream start never
launch or reacquire. Native specification support is internal library code only;
there is no new native broker launcher or automatic discovery endpoint.

## Client and data ownership

- One live client is admitted at a time. Admission duplicates the supplied
  process handle with query/synchronize rights, checks that exact process object,
  then obtains a fresh clock on the already acquired worker before granting a
  lease. A PID is not reopened as a substitute for the process object.
- Local monotonically increasing lease numbers reject stale operations. They
  are stale-call guards, **not IPC authentication credentials**. Wrong-client or
  stale detach cannot release a newer lease.
- A client supplies a fresh, valid audio-mailbox name in the existing retained
  device start command. The worker claims that mapping directly. The broker
  does not relay PCM or execute callbacks. The worker independently checks the
  acquired device clock, mapping freshness and stream admission.
- Successful stop drains worker I/O and returns the existing redirect to ready.
  Successful detach drops the client claim while retaining that redirect. It
  does not certify that client callbacks have retired; that separate lifetime
  remains the client's responsibility.
- Explicit final `close()` requests worker quit, checks the typed release reply,
  observes process/job retirement and records containment separately. It is
  idempotent after successful close. A sticky failure flag survives clean
  physical-resource cleanup after an earlier fault.

All methods belong to one control thread. A frontend must service `poll_client()`
even when there are no requests. A dead idle client loses its claim without
reopening the worker. A dead running client ends the whole owner rather than
assuming its queues/callbacks can be recovered. Failed/unknown worker operations
seal the owner; there is no reopen, delayed retry, rate setter, control setter or
automatic restoration path. Last decoded worker snapshots are observations,
not continuously refreshed device state or USB readiness guarantees.

## Meaningful process coverage

`sl3_retained_broker_tests` starts the existing simulated device worker and
**two separate audio-client processes**. Each client creates its own mapping,
receives 24 ordered input blocks starting at frame zero and sends matching silent
output directly to the worker. Audit assertions require one acquisition, six
fresh clock getters, two stream begins/ends and one final release. Both explicit
stop/detach and detach while streaming are covered.

Other cases cover overlapping clients, old lease calls after client replacement,
locally malformed starts, invalid/mismatched clocks, failed admission without
cached fallback, failed acquisition/activation, stalled acquisition containment,
idle/running client death, exact owned-worker death without fabricated release,
final-close refusal to reopen and native/simulated
handshake mismatch. These are CPU/synthetic process tests, not USB audio tests.

The test is built without the ASIO SDK as well as in SDK-enabled builds. The
standard build script requires it and records its executable hash and scope.
Exact verification counts and evidence hashes accompany this checkpoint in
`docs/evidence/retained-broker-20261101.json`.

## Remaining integration work

The next stage is an authenticated local IPC frontend with explicit owner
start/stop, client identity/liveness handling and a reviewed rendezvous record.
It must bind an ordinary ASIO client's request and data-channel ownership to its
actual process, prevent arbitrary worker command forwarding, and retain pinned
configuration/file leases. This backend's process-handle parameter assumes that
trusted admission has already happened; it does not supply that admission.

`HostSession`/`AudioOwner` must then distinguish a broker client attachment from
their current privately owned worker/job. Releasing a client must retire its
callbacks, buffers and channel without claiming the broker process exited or
the physical redirect was released. Ordinary COM object creation must use that
path, with actual COM/process recreation and failure tests before deployment.
The current production DLL still uses its existing private owner unless a host
explicitly requests the custom factory scope.

Physical current-build transport, measured latency, analogue audio and current
Serato admission/two-deck DVS remain separate unproved requirements. Keeping one
redirect does not resolve Serato's discontinued-device/API handshake, and it
does not prove the final original-stack release leaves USB ready for another
acquisition. Windows remains first; macOS work is deferred.
