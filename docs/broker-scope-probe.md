# Read-only retained-broker diagnostic across separate processes

`sl3_broker_scope_probe.exe` prepares a control-only test of one acquired worker
across three independent client processes. Each client binds the immutable
session record and exact live server/image identity, authenticates through the
existing pipe protocol, queries the clock and detaches. The owner retains the
worker until one explicit final close. This exercises the broker path without a
measured timing profile, ASIO configuration, COM registration or audio stream.

**Only simulation and pre-device native refusal have run.** Release and Debug
pass 61/61 native checks; the SDK-free build passes 38/38. All three actual
simulated diagnostic runs have three distinct process identities, one worker
acquisition, seven clock reads and one final release. The seven separate evidence
validator tests also pass. No SL3 acquisition or administrator prompt ran.

## Why a separate diagnostic

The production [controller](broker-controller.md) still requires a real reviewed
timing profile before publishing an ASIO consumer configuration. This diagnostic
does not weaken that requirement. It tests control ownership and authentication
without producing a profile or a configuration that could report invented audio
latency. It also differs from the existing
[facade scope probe](metadata-scope-probe.md): clients here are separate processes
using the broker record/pipe rather than three C++ facade objects in one process.

The native and simulated executables are separate compiled targets. Native mode
has no fixture/simulation switch. A truthful simulated worker is refused before
the native acquisition command; its empty state cannot be called native release
evidence. The simulator never loads a helper or opens hardware.

## Server restriction and file/process lifetimes

`BrokerAccess::metadata_only` permits clock and detach after authentication.
Audio start/stop and unknown operations are rejected before any audio mapping or
worker start. A rejected active operation follows the existing sealed-owner
failure path. Actual IPC tests attempt an audio start and confirm no simulated
worker `begin` operation occurs. Existing production callers retain the explicit
default audio mode and their full regression coverage.

Run preflight requires an ordinary token, canonical fixed-drive paths, a pinned
worker SHA and, for native mode, the reviewed helper bytes. Parent directories,
self/worker/helper images and the new owner-only result directory are held by
read leases. Reparse points and unexpected final paths are refused. Evidence is
created new-only and flushed/read back, then retained without write/delete
sharing. Existing directories or files are not overwritten. These are trusted
ordinary-user diagnostic artifacts, not protected production installation.

After acquisition the owner publishes only `broker-session.txt`. Each child uses
the existing file/image/hash/process-creation binding and pipe process challenge.
Its recorded PID and creation time are compared with the actual held child
process object. Each child must exit normally with its private job empty; all
three return the same worker identity and clock. Parent observations require
the worker to remain idle and no input/output submission. Detach retains the
worker; it is not final physical release.

There is one initial clock read plus an admission and explicit read per client:
seven getter calls. No clock setter, firmware operation, buffer creation, audio
start, ASIO configuration, pointer or registration operation exists in this
scenario. Helper loading occurs only in an explicitly launched native worker;
the probe and client processes do not load it.

## Commands and limits

Default and `--plan` are inert:

```powershell
artifacts/build/native/Release/sl3_broker_scope_probe.exe --plan
```

The explicit attended run interface is prepared, **not authorization to execute
it without the trace/recovery wrapper and an owner-present window**:

```powershell
sl3_broker_scope_probe.exe --run --worker <absolute-native-worker> `
  --worker-sha256 <reviewed-lowercase-sha256> --helper <absolute-reviewed-helper> `
  --output <fresh-absolute-directory>
```

A process-wide 20-second watchdog covers the device phase. Child connection and
retirement checks have their own bounded waits. Timeout/forced containment is a
failed experiment, retaining the last immutable `phase-*.json`; it does not
prove immediate kernel quiescence. The supervising runner must bound preflight
and preserve USB/WPP recovery observations separately. There is no automatic
relaunch, reconnect or second acquisition. The
[internal rollback finding](usbdk-rollback-contract.md) remains relevant.

The result distinguishes acquisition attempts, successful acquisition, typed
release/retirement, client retirement and forced termination. Kernel quiescence,
next-open readiness, physical audio and Serato admission remain false. Failed
acquisition does not publish a session record. No measured input is manufactured.

## Offline validation and future attended test

`validate-broker-scope-probe.py` checks recorded result/client identity, clock,
no-audio and retirement fields plus the typed session record. Simulation requires
the exact one-acquire/seven-read/one-release audit. Native mode requires one
complete `worker-startup.tsv`, one worker PID and exactly one acquisition, seven
ordered getter pairs and one final release, with no audio/control-write stages.
This is recorded consistency, not attestation of physical provenance. Synthetic
native journal grammar tests are labelled and are not positive native runs.

All three real simulated outputs were independently passed through this
validator. Native plan/hash/helper/option guards and truthful-kind refusal run
without device acquisition. The [checkpoint evidence](evidence/broker-scope-20261102.json)
binds exact binaries, source, tests and immutable private artifacts.

The native worker binary remains byte-identical to the preceding Release
checkpoint. The ASIO DLL and broker-linked binaries have changed through the
server-policy addition and are freshly software-tested. Existing review bundles
and prior hardware results retain their own historical versions; they are not
implicitly upgraded. No new deployment bundle or installed configuration was
created for this checkpoint.

A future attended test still needs a dedicated traced runner, fresh plans/source
pins and before/after recovery/security evidence. Existing controls/facade-scope
validators cannot be reused as a broker-scope pass. Actual native broker IPC,
analogue audio/timing, reliable reopening, protected deployment and genuine
current Serato/two-deck DVS remain unverified; the full goal stays active and
macOS remains deferred.
