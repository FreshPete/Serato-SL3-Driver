# Explicit broker controller and session publication

The controller now opens one reviewed worker session, publishes the immutable
[broker record/configuration](broker-configuration.md), serves ordinary clients
and closes on an explicit stop request or lifetime ceiling. The native entry
point defaults to an inert plan. This checkpoint has **no positive native run,
installation, registry change, physical audio or current Serato/DVS validation**.

The later [COM activation checkpoint](asio-com-activation.md) adds STA/MTA `CoCreateInstance` clients to the software lifecycle checks; it does not install the component.

## Commands and scope

`sl3_broker_controller.exe` with no arguments or `--plan` writes a JSON plan only:
no configuration read, session files, helper load or device access. Run accepts
only these explicit options:

```powershell
sl3_broker_controller.exe --run --input "C:\path\reviewed-input.conf" --output "C:\path\new-session-directory" --limit-ms 60000
sl3_broker_controller.exe --stop --config "C:\path\new-session-directory\sl3-asio.conf"
```

The input uses the existing reviewed private-worker configuration format,
including worker/helper/timing/measurement hash pins. A live broker configuration
cannot be used as another controller's input. The output directory must be new
on a local fixed drive. The lifetime is required, canonical decimal, and bounded
to 1,000..43,200,000 ms. It triggers shutdown; it is not a claim that all cleanup
finishes at that exact time or that USB is ready for another acquisition.

Native execution requires a genuine reviewed timing/measurement record. The
synthetic profiles used in software tests are not measurements and are not
installed. The compiled simulated controller is a separate test target; the
native command has no `--simulate` option and refuses a simulated worker before
acquisition.

The controller does not register or copy an ASIO DLL, modify an installed Serato
file, create a Windows service, request elevation, set a rate or modify firmware.
The produced `sl3-asio.conf` is a session artifact, not an installation. The [session locator](asio-session-locator.md) now connects an adjacent stable
record to per-session configuration through an explicitly published pointer.
Protected staging, pointer replacement and installation/registration remain
unfinished. The metadata-only `--publish-pointer --config ABS --pointer ABS`
command creates a new owner-only pointer without opening the device.

## Publication and lifetime

Before device access, the controller pins its own image and input bytes, requires
an ordinary user, creates a fresh owner-only directory and saves immutable intent
plus a controller startup journal. A unique owner-only stop event is derived from
the fresh private pipe identity. The explicit lifetime timer can signal that
event without another approval prompt.

Only successful acquisition and a clock matching the reviewed timing profile
permit publication. The controller creates `broker-session.txt`, derives the
broker configuration from the unchanged input fields, pins its own image/hash,
and re-loads the result through the production binding validator. It rechecks
the live worker, typed retired-I/O observation and stop event before writing
`ready.json`. Files are written through to new pending names and atomically moved
to new final names without replacement, then held read-only with write/delete
denied. Existing output directories/files are never reused or overwritten.

`ready.json` is a snapshot, not a liveness handle or continuing USB/clock guarantee.
Clients still validate the live process/creation identity, image/record pins,
native/simulated kind, worker hash and acquired clock. Stop, failure or process
exit invalidates the session without automatically opening another one. All
records remain on disk as evidence; stale records fail binding/admission.

The stop command validates the selected published configuration and exact live
server reference, then signals only that session's named event. Its response
acknowledges the **request**, not native release. Final worker/job/typed cleanup
observations are recorded independently by the controller. Stop during a live
client lease ends that owner; it does not certify that callbacks in the client
have retired. Closing the ASIO client normally before stopping the controller
allows the independent idle owner to retire cleanly.

There is no reconnect/reacquisition loop. A lifetime expiry, failed owner or
destructive client release ends this invocation. Forced process termination is
containment, not a successful final release or original-stack readiness proof.

## Evidence and unknown outcomes

The output includes `intent.json`, `controller-startup.tsv`, immutable session
and consumer records, `ready.json` when publication completes, and `result.json`.
Native workers are passed a fresh absolute `worker-startup.tsv` journal path;
positive native journal collection is unrun. Simulation has its separate
`worker-audit.txt` and never claims a native startup trace.

The backend now records whether acquisition was attempted and whether a typed
snapshot was actually obtained for the latest operation. An unanswered
acquisition cannot turn a default empty snapshot into release evidence. Final
release/retirement verification also requires successful acquisition, preventing
a native-mode kind-refusal test from claiming physical release based on an empty
simulated worker's quit reply. Last snapshot diagnostics, native error, phase,
fault, rate and actual process exit facts remain available as bounded metadata.

Controller `successful` means this session lifecycle met its stated cleanup
conditions. It does not establish analogue audio, timing accuracy, restoration,
safe successive USB acquisition, current Serato admission or DVS. The result
keeps next-acquisition readiness and rate-restoration verification false.

## Actual software coverage

The lifecycle test launches the actual controller executables and reads their
published files while retaining authoritative subprocess handles. It verifies:

- Default plans write nothing and access no device; malformed/duplicate options,
  invalid lifetimes and existing output directories refuse safely.
- A simulated controller publishes hashed, write-locked records. A separate host
  consumes them through the production reader and an explicit test-only simulated
  provider, exercising three ordinary COM objects and four official SDK callback
  streams over one worker acquisition. Its worker-hash contract is enforced.
- The native stop command requests shutdown through that exact published binding;
  worker/job retirement and one final simulated release are checked separately.
  A post-exit stop refuses the stale record.
- Idle lifetime expiry closes without audio. A clock/profile mismatch publishes
  no session/configuration/ready records and performs no rate write.
- Blocked-callback object destruction preserves failure and resource lifetime;
  the controller exits without reopening the worker.
- The native controller refuses a truthful simulated worker before issuing
  acquisition. It publishes no ready/config/session record and infers no native
  device release. No positive hardware operation is hidden in this case.

Each invocation retains a fresh software-evidence directory under the build's
`controller-lifecycle-artifacts`; the build-specific latest pointer identifies
its completed index/hash. These are test artifacts, not execution authorization
or a live-controller certificate. Exact source/binary/log hashes and the private
checkpoint are in `docs/evidence/broker-controller-20261102.json`.

Native attended testing, real timing and audio measurement, deployment, and the
separate current-Serato audio/API/DVS admission path remain unfinished. Windows
remains first; macOS is deferred.
