# Traced broker metadata diagnostic

This adds a distinct `BrokerScope` scenario for the [read-only broker diagnostic](broker-scope-probe.md). It prepares an attended test; it does not establish a successful native run, reliable reopening, physical audio or Serato admission.

## Roles and bounds

`scripts/prepare-broker-scope-trace.py --prepare analysis/broker-scope-trace-NAME` creates a fresh fixed plan. `scripts/start-broker-scope-trace.ps1 -Plan ABSOLUTE_PLAN` inspects that plan without starting a child. Only an explicit `-Run` requests the attended launch. No launch was performed for this checkpoint.

The normal-user waiting role and the administrator trace collector remain separate. One Windows approval is requested for the collector; the collector never launches the device probe. The normal role admits only the same live collector process within its fresh observation window and requires the reviewed images, scripts and build manifest. The sixty-second USB/WPP capture includes the existing state-observer consumer attempt. This is observation, not readiness admission.

The native diagnostic requests one retained acquisition, seven clock getters, three authenticated client processes and one final release. No timing profile, audio start, rate/control write, ASIO configuration, registration, firmware operation or security change is requested. The diagnostic has a twenty-second watchdog; its outer probe deadline is thirty seconds. Final validation requires at least twelve seconds of trace after the probe retires. These user-mode limits do not prove kernel quiescence or safe reopening.

A plan is pinned to its runtime and used once. An attempted launch cannot be rearmed, including a cancelled UAC launch. Plan inspection and direct non-elevated invocation of the internal collector role are tested without presenting UAC or opening the SL3.

## Evidence separation

`BrokerScope` has its own plan/run schemas and component validator. The facade-scope and controls schemas cannot qualify this result. The wrapper reads `probe/result.json` and `worker-startup.tsv`, rather than the older probes' filenames. Native grammar requires exactly one acquisition, seven getter pairs, release and helper unload, without audio stages.

The observed normal-user parent, probe and worker must have distinct process IDs and matching image/token evidence. In addition, the broker session's server PID and creation time must match the observed probe process. The native probe itself authenticates each client against held process objects, checks client creation identities and waits for client retirement. Saved records remain consistency evidence, not cryptographic attestation that a physical test took place.

The collector now checks for remaining broker-scope and broker-controller processes as well as the older probes and worker before and after tracing. It refuses a leftover process rather than killing it or opening another device session.

## Verification and remaining work

On 4 November the attended native run passed. Three successive ordinary-user client processes shared one retained UsbDk acquisition. The worker journal recorded seven clock reads at 44.1 kHz and one final release. The traced-run validator confirmed recovery to the selected baseline and reported 17,783 USB events with zero events or buffers lost. The run exercised read-only broker ownership across process lifetimes. Physical audio, independent reacquisition and Serato DVS still require separate validation.

The accompanying [verification record](evidence/broker-scope-trace-20261102.json) records native build results, launcher/admission regression checks and source hashes. Launcher checks inspect a fresh plan, reject ordinary-token collector execution and verify that no probe context or attempted-run marker is created. Synthetic composition tests check dispatch, cross-scenario refusal and server creation-identity binding; their mocked component is explicitly not a native trace result.

No attended native broker test, UAC prompt, device redirect, audio stream, protected installation or current Serato run occurred. The existing supervised recovery/port-observer queue remains relevant before selecting an attended acquisition. Native IPC, actual analogue audio/timing, stable repeated operation and current Serato/two-deck DVS remain unverified. macOS remains deferred.
