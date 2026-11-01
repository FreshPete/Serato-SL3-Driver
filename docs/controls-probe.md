# Bounded controls diagnostic and traced test

The native probe now exposes an explicit **`--controls`** mode. It acquires one retained device, reads the actual rate, performs the [read-only audio-control transaction](held-controls.md), records the result and finally releases the device. It creates no audio buffers, starts no audio, requests no alternate change and sends no rate/control setter or firmware-programming command. **This mode has not run positively on the physical SL3.** [Current source/build evidence](evidence/held-controls-build.json).

## Saved observation and independent cleanup

The fresh output directory contains `probe.json`, schema `sl3.controls-host-probe.v1`, plus one native worker journal when requested. Progress is flushed before acquisition, control inspection and final close. Acquisition, after-query and final owner states remain separate. A successful observation retains all 22 defined table bytes, the received-frame count and the three logical control-group views. Unknown sensitivity codes retain their raw values and have no guessed mV value.

Failure before a validated reply records a missing sample, raw table, receive count and interpreted inputs as `null`. A successfully observed table survives a later cleanup failure. That case remains an unsuccessful, unretired probe; an observed table does not certify final device release. The record's no-audio counters and ownership domains are checked independently. No physical jack order, calibration, analogue signal, latency or application readiness is inferred.

The probe has a 30-second watchdog. The wrapper allows 40 seconds for its process inside a 60-second USB trace. The worker's control and cancellation/drain budgets remain separate, and native helper/kernel operations can outlive a requested process-termination deadline. Unproved retirement preserves evidence and fails the test. There is no automatic retry, power cycle, rebind or reboot.

## Operator-attended tracing

Inspect the plan without creating an evidence directory or accessing the device:

```powershell
pwsh -NoProfile -File scripts/test-controls-host-traced.ps1 -ResultDirectory tests/results/local/controls-host-traced-20261030-01
```

With the owner present, a normal SL3 resting identity, no remaining test worker and an already elevated terminal:

```powershell
pwsh -NoProfile -File scripts/test-controls-host-traced.ps1 -Run -ResultDirectory tests/results/local/controls-host-traced-20261030-01
```

Use a fresh local output directory. This read-only, no-audio test needs no signal fixture or capture/duplex prerequisite. It obtains its rate from the acquired device. The wrapper checks Secure Boot, the reviewed running transport and the tested probe/worker/source dependencies. It starts the USB-stack trace before launching the probe, validates the observation/journal, records trace loss/window coverage and compares selected before/after Windows state. It does not elevate itself, install/register anything or change security settings.

Raw USB tracing stays in the ignored local results tree. The USB trace includes other devices on the host stack. Default operation retains the existing USB providers. The [separate UsbDk WPP sidecar](usbdk-detachment.md) remains available independently.

## Optional shared UsbDk lifecycle trace

The controls wrapper and USB capture script now accept **`-WithUsbDkLifecycle`**. Plan-only inspection:

```powershell
pwsh -NoProfile -File scripts/test-controls-host-traced.ps1 -WithUsbDkLifecycle -ResultDirectory tests/results/local/controls-lifecycle-traced-01
```

For the next owner-attended test, from an already elevated terminal, add `-Run` to that command. No live combined capture has run yet.

This option adds the reviewed UsbDk WPP provider at flags `0x650`, level 4, to the **same bounded 60-second ETW session and ETL** as the USB-stack providers. It introduces no second capture process or manually aligned window. The capture checks the running driver image and Secure Boot, verifies the pinned source/TMF inventory and prepares 32 selected message formats at `trace/lifecycle-decoder/lifecycle.tmf`, with its source plan beside it. The trace becomes ready only after all provider-update commands and session start. The controls wrapper checks the requested mode and successful WPP configuration before admitting the device probe.

Final validation binds the requested option, exact provider/flags/level, prepared plan/TMF/source hashes and successful update-before-start command order. It preserves the existing one-acquisition/no-audio operation, trace window/loss and independent recovery gates. A configured provider is not evidence that it emitted messages: results explicitly leave `emissionVerified` and `decodedMessagesVerified` false. Offline WPP decoding and actual lifecycle coverage still need inspection using the [Tracefmt procedure](usbdk-detachment.md). Missing messages cannot certify readiness or locate a stalled operation.

The original USB-only invocation stays available, and the separate passive WPP sidecar is unchanged. The new option does not authorize a rapid second redirect, retry, power cycle, installer, registration or policy change.

## Optional identity observation in the shared trace window

Add `-WithUsbIdentity` to the runner to observe the actual installed, SHA-pinned Serato libusb discovery inputs alongside the USB/WPP control trace. It remains plan-only unless `-Run` is supplied:

```powershell
pwsh -NoProfile -File scripts/test-controls-host-traced.ps1 -WithUsbDkLifecycle -WithUsbIdentity -ResultDirectory tests/results/local/controls-identity-traced-01
```

The opt-in observer starts only after USB trace readiness and successful requested provider configuration, with at most five seconds of the 60-second trace used. It requests 45 seconds of identity observations at 50 ms intervals. Before admitting the single controls acquisition, the wrapper allows three seconds to obtain a fresh, complete snapshot with exactly one SL3 identity. The observer and supervisor are hidden child processes; neither binds a libusb device-open, claim or transfer API. The control probe still requests only one rate getter and one controls getter, with no audio, setters or retry.

A [real standalone read-only baseline](usb-identity-baseline.md) now shows host enumeration itself taking about 1.3 seconds, with 1.58-second return gaps at a requested 250 ms post-call sleep. The integrated 50 ms mode remains untested. Its interval setting is not measured sampling resolution; inspect actual call durations and gaps, and do not infer held-device continuity from an unchanged sampled identity.

The wrapper waits for independently supervised observer termination, saves/rechecks its validation and preserves partial records on failure. Thirteen diagnostic scripts are pinned by the native build manifests, adding observer, supervisor and admission/coverage helper. Default USB-only and USB/WPP modes do not start the observer. No combined physical run has occurred.

Final validation rechecks the admitted complete-line prefix and its hash, the saved supervisor/JSONL bindings, clean direct-child retirement, and observer/probe inclusion in the USB trace window. It requires complete samples before probe start and after probe completion. Reported samples inside the **probe process window** are distinct from actual held-device coverage: short changes or the held subwindow may be missed. Results explicitly keep `heldDeviceCoverageVerified` and `seratoCoexistenceVerified` false, including when no sampled identity changes occur. Complete post-probe absence is diagnostic data, not a readiness claim. Secure Boot and selected recovery remain independently checked.

The live admission helper reads a bounded complete-line prefix while the observer writes; an incomplete suffix is ignored, not treated as a sample. Descriptor/list errors cannot become a false disappearance. The [discovery/removal contract and process supervisor](serato-usb-discovery.md) explain why bus/address changes matter and the limits of process termination. Inspect actual observed identity changes and decoded WPP coverage before choosing a startup/lifetime modification.

This integration checkpoint passes 39/39 Release, 39/39 Debug and 105/105 Python checks, including five new admission/window/prefix tests and the existing native/supervisor failure checks. The five current build/original-contract exporters pass. SDK-free 25/25 is preceding evidence for unchanged native sources. Runtime worker/probe/ASIO hashes match the control-selection checkpoint; no native source changed. [Exact manifest/script/test/plan bindings](evidence/controls-usb-identity-build.json). The local `identity-controls-20261030` checkpoint preserves both manifests/logs/runtime binaries, thirteen scripts and current test/evidence files. No hardware query or UAC launch ran.

## Evidence validation

`validate-controls-host-probe.py --probe DIRECTORY --worker-sha256 HASH` requires a finished successful native record, exact kind/hash/protocol, complete byte table and correct UI-derived values. It rejects nonzero audio/setter/programming counters, incorrect types, stale or inconsistent owner states and incomplete journals. Native evidence requires one PID, one redirect, one clock getter, one control write, the recorded number of control reads and one final close/unload. Simulated results require an explicit `--expect-simulated` flag and no native journal.

`--run DIRECTORY --worker-sha256 HASH --probe-sha256 HASH` additionally checks the traced wrapper result, exact dependency inventory, saved-file hashes, unchanged selected recovery, enabled Secure Boot and complete loss-free trace coverage. It recomputes probe consistency instead of trusting the saved validation flag. These are record-consistency checks, not hardware attestation or electrical calibration.

The actual native/simulated probe executables are exercised by `sl3_controls_probe_lifecycle`. Positive cases use the explicitly simulated worker. Fault cases cover failed/malformed/stalled queries, a valid observation followed by failed/stalled final release, kind mismatch, invalid CLI and no-overwrite behavior. The real native negative case uses an asserted absent helper and never reaches hardware. Seven new Python tests mutate payloads, counts, types, ownership, journal order/completion, trace bindings/window/loss and safe plan/output-directory gates.

Fresh full suites pass **39/39 Release, 39/39 Debug and 80/80 Python** checks. SDK-free 25/25 remains preceding evidence for unchanged native inputs. Ten control-diagnostic script dependencies are now pinned, including the lifecycle preparer. The ten targeted controls-evidence checks include both plan modes, exact provider/mode/order, decoder bytes/plan/hash mutations and existing payload/ownership/window/recovery/loss failures. Synthetic trace-statistics fixtures do not exercise real ETW/WPP emission or decoding.

The initial nine-dependency diagnostic checkpoint remains at `artifacts/build/checkpoints/controls-probe-20261030`; the combined option is preserved at `artifacts/build/checkpoints/controls-lifecycle-20261030`. Production sources and runtime binaries remain unchanged. Earlier native silent-stream results retain their original bindings and do not certify this controls query or combined trace. No device-test process, UAC prompt, hardware operation, firmware update, trust or security change was left by this preparation.

The later [offline setting engine](audio-control-selection.md) extends two core headers and rebuilds the worker/probe/DLL with new hashes; it has no runtime caller and the native controls adapter still accepts only the getter. The current manifests pin those new binaries. Old capture prerequisites were explicitly rejected under the new worker identity. Do not carry the preceding unchanged-binary statement or any archived physical result forward as validation of this build. The next live command remains the read-only test above, not a setting write.

Next run the supervised diagnostic and inspect the actual control values and selected Windows recovery. Physical routing/calibration, sustained audio/timing, normal-user streaming, safe successive ASIO-object startup, production deployment and current Serato/DVS remain required. macOS remains deferred.
