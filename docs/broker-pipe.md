# Private broker connection and direct audio channels

The [retained owner](retained-broker-backend.md) now has a Windows named-pipe
frontend and client library in `src/windows/broker_pipe.{hpp,cpp}`. Real separate
client processes can attach, query the held clock, start and stop audio on fresh
shared-memory channels, and detach while one worker acquisition remains alive.
Positive transport evidence is **simulated only**. The production ASIO DLL does
not yet use this path; no native broker, service or registration was installed.

## Admission and process identity

An explicit ordinary-user controller constructs a listener with a random
128-bit pipe name, an owner-SID-only DACL, first-instance exclusivity and remote
client rejection. There is one connected client at a time. Construction does
not launch a worker or acquire hardware; the controller must separately open
the retained owner. The listener is reused after disconnect, including clients
that disappear before acceptance.

The client requires an already-held reference to the expected server process.
It verifies the actual pipe server PID against that live process object, and
compares user SID, logon authentication ID, session, non-elevated status and
integrity level. Integrity must match and be at least medium. Endpoint strings
and PIDs received over this protocol are not accepted as server credentials.

The server reads the typed native/simulated greeting before granting a client
lease. A kind mismatch refuses before a clock refresh or audio operation. It
obtains the actual pipe client's process ID from Windows, opens that process,
and checks both its primary token and the identified pipe token against the
owner's token. Impersonation is reverted before worker operations.

A PID/token check alone is insufficient against process-ID reuse. The server
duplicates a fresh event into that exact opened process with only event-modify
rights. The pipe client must signal it and reply to the challenge before
admission. The server then retains that process object for liveness. The client
receives only synchronize/query rights to the worker process; the process tests
verify its handle cannot terminate the worker.

This authenticates a process in the same ordinary-user identity, not a code
signature or an isolated security sandbox. A future deployment still needs a
reviewed, locked rendezvous/configuration record that establishes the expected
server process and pinned executable. There is no automatic discovery record,
background auto-start or arbitrary process selection in the production DLL.

## Mapping and control contract

Control frames have a strict versioned 24-byte header, monotonically increasing
per-connection sequence, a bounded 2,048-byte payload and exact message length.
The only operations are greeting/proof, clock, stream start, stream stop and
detach. There is no raw worker-command forwarding, acquisition command, rate or
control setter, firmware command or application identity change.

For start, the client supplies its audio-mapping handle value and the existing
typed stream request. The server duplicates that reference from the authenticated
process and compares it with the mapping opened by the supplied channel name.
The comparison uses Microsoft's [CompareObjectHandles API](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-compareobjecthandles).
Because this SDK lacks the import library, resolution uses only the already
loaded system KernelBase module; a missing export refuses admission.

The server holds the verified mapping reference through worker admission and
stream retirement, preventing replacement of that mapping while it is being
claimed. This proves the client holds that exact object, **not that it originally
created it**. The worker separately verifies channel freshness and stream/clock
admission. Events and mapping access remain within the same-user trust model;
this is not an isolation claim against hostile code running as that user.

PCM travels directly between the client's mailbox and worker. No pipe message
contains audio samples, and the broker executes no client callback. Stop retires
worker I/O; detach removes the client claim while its reply still reports the
physical device held. Callback retirement in the client remains separate.

Detach has a final client acknowledgement after the held-state reply is read and
validated. The server waits for that acknowledgement before disconnecting: Windows
[discards unread pipe data on disconnect](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-disconnectnamedpipe).
This avoids an unbounded flush and is exercised with a deliberately delayed reader.

## Failure and lifetime

Every overlapped pipe operation has a bounded wait and cancels/drains before its
buffer or event is freed. If retirement cannot be established, the owning process
fail-stops rather than releasing live I/O storage. Idle liveness is serviced every
50 ms; this is process observation, not a USB-readiness delay. A controller stop
ends an active owner rather than silently restarting it.

Malformed requests after admission, unknown outcomes and running-client death
seal and close the owner. There is no reconnection or second USB acquisition.
Before admission, malformed/oversized messages or failed process proof reach no
client device operation and leave the independently controlled idle owner intact.

Pipe teardown can precede a process's exit signal. After an idle connection
failure, the server observes that **same process object** for at most one second.
Only a signalled process permits the backend's idle-death release of the client
claim. A still-live process with a broken connection ends the owner. This wait
does not infer callback retirement, native release or readiness for a new USB
acquisition. An explicit detach needs no such wait.

Challenge and worker handles granted into a client are closed by that client.
On a deliberately incomplete protocol, the server does not try to close a remote
numeric value that might have been reused for another object. Such granted
references are limited to the event or wait/query process handle and close on
client exit; there is no native device handle grant.

## Verification and remaining work

`sl3_broker_pipe_tests` exercises real Windows pipes, process tokens, handle
duplication and mapping-object comparison with the simulated worker. Two
independent clients each receive 24 ordered input blocks from frame zero and
send silent synthetic output. Audits require distinct mappings, the same worker
process, one acquisition, seven fresh clock getters, two starts/stops and one
final release. Separate checks cover delayed detach reply/acknowledgement, pre-accept disconnect, malformed and
oversized frames, wrong server, wrong worker kind, failed proof, bad sequence,
forbidden worker opcode, exact wrong-object rejection, live idle disconnect,
idle death/replacement and running death. No cross-account/elevated attack test
or forced PID-reuse test ran.

Exact build/test counts and local evidence hashes are in
`docs/evidence/broker-pipe-20261101.json`. The SDK-free build also includes this
test. No hardware, UAC, security-policy or installed-driver operation ran.

Next, `AudioOwner` needs a retained wait-only peer reference distinct from its
current owned `Process`, and `HostSession` must represent client detach separately
from worker/job and physical-device release. The ordinary COM path then needs
the reviewed rendezvous/configuration and actual IASIO recreation/failure tests.
Measured timing, physical current-build audio and current Serato's audio/API/DVS
admission remain unproved. Windows remains first; macOS is deferred.
