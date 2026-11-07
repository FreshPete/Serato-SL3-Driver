# Lazy activation through the ASIO entry path

The [version 2 follow-up](application-bound-broker.md#automatic-asio-activation) adds an opt-in process-lifetime mode. This page describes the version 1 activation and retirement behavior.

The ASIO configuration provider now understands a stable activation record. It can construct an ordinary driver or explicit factory scope without starting a process; the first `IASIO::init` attempt activates the configured controller and attaches to its authenticated broker. This connects the earlier [activation component](broker-on-demand-activation.md) to the native driver path. Nothing has been installed or validated in Serato through this new mode.

## Stable record

The adjacent `sl3-asio.conf` can select this exact ordered format, with lowercase SHA-256 identities, absolute local paths, canonical decimal limits and a final newline:

```text
SL3-ASIO-ACTIVATION-1
controller=ABSOLUTE_REVIEWED_CONTROLLER_PATH
controller_sha256=REVIEWED_CONTROLLER_SHA256
input=ABSOLUTE_REVIEWED_PRIVATE_WORKER_CONFIGURATION
input_sha256=REVIEWED_INPUT_SHA256
startup_timeout_ms=15000
startup_failure_grace_ms=5000
lifetime_ms=600000
```

This is a schema illustration, not an installable configuration. The production parser always selects the native worker kind; the record has no simulation field. It validates and pins the input/controller and the input's transitive worker/helper/timing files before constructing the lazy owner. Broker inputs and unknown/malformed versions or fields are rejected. The existing direct and locator formats retain their behavior. Diagnostic timing still limits lifetime to ten minutes; no production latency measurement or longer-session approval is inferred.

Configuration inspection, ordinary COM object creation and optional factory `BeginScope` remain acquisition-free. A lazy owner attempts activation once; a failed attempt does not automatically reacquire or fall back to another backend. The ordinary and explicit-scope factory paths use the same configured provider logic.

## Current-user runtime state

An actual activation resolves the current user's LocalAppData rather than embedding the developer's session path in the record. It creates or verifies `SL3RebuildActivated` as an owner-only, protected directory, rejects a redirected or differently owned/permissioned root, retains its directory handle and chooses a fresh random child name. It does not rewrite an existing root's permissions. The controller creates its own fresh child directory and immutable metadata there. No global session pointer, process watcher, scheduled task, service, registry change or elevation is added by this path.

The root helper itself is exercised separately in the software fixture: two distinct fresh paths are selected under the same verified private root without starting a controller. This may create the empty per-user metadata root. Actual simulated controller records in the test stay in the owned test output directory through a test-only provider override.

## Callback and shutdown ownership

The broker attachment now has an optional activation lifetime reference. Its worker wait reference carries that lifetime into the audio owner's shared state, so a blocked callback keeps both its planes/module and activation lease alive even after the public ASIO object is destroyed. Existing attachments without an activation remain unchanged.

Final lazy-owner destruction first retires the delegate/client and drops its configuration. It keeps normal controller cleanup on the control thread while a retired audio thread's reaper releases its final reference. It does not wait for that cleanup from inside an audio callback. Destructive release with an executing callback preserves failure and defers activation retirement; it is not converted to a clean shutdown.

A final close can also queue nonwaiting retirement before the public object is destroyed. No new configuration borrows are allowed after that request; the last configuration/callback lease posts the controller stop. This matters when initialization rejects a rate mismatch and the host retains the failed ASIO object. The regression first failed in that state with the controller still reserved; it now verifies retirement while the failed object remains alive, and a second init cannot reacquire or stream.

## Software evidence and limits

The unregistered fixture DLL uses the actual COM/IASIO implementation and the common configuration/provider/session code. Its **test-only** provider changes the expected kind to simulated and supplies an owned test output location; no such override or exported configuration hook is present in the production DLL.

The test validates native-only passive parsing, eight malformed-record refusals, current-user root ownership, lazy object/scope creation, ordinary initialization, a second ordinary factory open, explicit scope initialization and normal retirement for three simulated owners. The fourth case rejects a rate mismatch and verifies owner retirement before releasing the failed object. A fifth case deliberately releases an ASIO object while its callback is blocked. It releases the caller's DLL reference, verifies the module remains loaded, then permits that one callback to finish on its original planes and checks eventual unload. The corresponding controller record must retain `client_control_abandoned` while independently confirming simulated I/O/worker retirement. That negative case is not evidence of a successful stop or a reproduction of the earlier real Serato timeout.

Real native acquisition, Serato loading this mode, physical outputs/vinyl, long operation, unplug/replug and public installer/uninstaller behavior remain unverified. Serato's normal-start primary-device selection is still separate: automatic ASIO initialization cannot make Serato select a driver it has not chosen.

The final Release build passed all **73 CTest checks** (95.51 seconds). The [source/image-bound checkpoint](evidence/asio-activation-entry-20261106.json) records 5,007 callbacks across the five simulated scenarios and their separate outcomes. Read-only postchecks found the original Serato resource archive, no occupied session paths or temporary registration, and no remaining matching test/controller/worker or Serato processes. Existing installed files, firmware and security policy were not changed.
