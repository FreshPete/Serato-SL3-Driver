# Install once, then open Serato normally

The owner clarified the intended product on 6 November 2026: setup should normally be a one-time operation. After that, opening the existing Serato application with the SL3 connected should select the interface without a session launcher, repeated Download Driver actions, repeated installation or routine administrator prompts. The prepared-session window is an engineering tool, not that final experience.

## Source-independent audio

The driver transports the SL3's audio channels. Serato performs DVS decoding. Phase Essential's RCA signal and timecode vinyl therefore use the same driver/audio path; the driver must not require a Phase-specific mode or recognize the controller brand. Source-appropriate LINE/PHONO settings, Serato control-source settings and calibration remain user setup. Current evidence demonstrates Phase RCA tracking; it does not establish a physical timecode-vinyl test.

Historical helper names containing `phase` refer to the tested development profile and its channel/rate mapping, not a proposed Phase-only driver product. The installed experience should use SL3-oriented names and describe the input/source settings separately.

## What still depends on each temporary session

| Component | Current implementation | Installed target |
| --- | --- | --- |
| Native audio driver | Temporary ASIO/COM registration and protected package staging | Stable installed registration and verified files, with explicit uninstall |
| USB transport | An ordinary-user, bounded session owner publishes an authenticated broker locator | Ordinary-user broker available automatically to Serato, with restricted device operations and application-lifetime ownership |
| Serato device definition | A locally generated SL3 definition temporarily replaces the owner's resource archive | Version-checked local compatibility definition; preserve originals and handle upgrades/removal |
| Initial device selection | Startup shim plus genuine Download Driver action and real installer-completion handoff | Genuine SL3 admission/primary selection on ordinary application startup or device arrival, without reinstalling |
| Startup instrumentation | Supervisor starts the application, supplies missing installer-panel identity and detaches after ASIO starts | Remove the installer workaround if possible; any remaining activation component must work with normal Serato launch, be explicitly installed/removable and scoped to the reviewed application |
| Lifetime/recovery | Diagnostic viewing limit, per-session paths, rollback after the run | Normal-duration sessions, reliable close/reopen/unplug/replug, recovery after an interrupted run, uninstall on request |

No persistent service, automatic process watcher or system-wide loader has been installed by this design work. No existing shortcut has been replaced. Normal Secure Boot/code-integrity protections, firmware and Serato account/entitlement checks remain unchanged.

## The first engineering boundary

Registering the ASIO DLL permanently is insufficient: Serato's checked installed-driver branch can acknowledge detection without selecting it. The working route currently gets primary selection through actual installer completion. The [installed-startup analysis](serato-installed-startup-boundary.md) and [completion-handoff analysis](serato-installer-handoff.md) establish this distinction.

The current startup shim observes genuine SL3 arrival and the genuine install click. It supplies VID/PID/revision only when the install panel's identity fields are empty, then observes the rebuilt DLL's ASIO start. It does not implement an automatic normal-start connection path. Keeping that shim and hiding a session launcher would not, by itself, resolve this requirement.

Next investigate the installed-device connection/admission route and the producer of the panel's missing identity. Prefer a proper registered device/provider path that removes the install panel entirely. Establish the live descriptor, owner thread/lifetime and actual ASIO selection before changing event delivery; a scalar message or arbitrary callback is not enough. Do not use account, entitlement or DVS-license state changes as a startup mechanism. The old stock Frida runtime remains held; future live work must use the separately reviewed candidate and preserve its scope/protection limits.

In parallel, design on-demand transport availability. The existing broker already runs as an ordinary user: its endpoint rejects elevated tokens, and the current session helper starts it without `runas`. Earlier physical control evidence independently queried normal parent/probe/worker tokens. Administrator prompts currently cover protected staging/registration (and optional trace collection), not a requirement for an elevated audio broker. Prefer ordinary-user on-demand activation and reuse the existing authenticated broker contract; an elevated Windows service is not established as necessary. Activation must open only the intended SL3 through the reviewed transport, accept no arbitrary executable/path/firmware commands and release acquisition when its audio owner exits. A stable driver install must not retain the general development scripting environment as an elevated service.

The [first installed-startup investigation](installed-startup-investigation.md) records the ordinary-user contract and inventories the pinned schema's declared connection options without executing Serato.

A [native on-demand activation component](broker-on-demand-activation.md) now exercises controller ownership, configuration binding and lease-driven retirement with simulated workers and the real ASIO facade. The [stable activation record and lazy ASIO entry path](asio-activation-entry.md) pass unregistered COM/IASIO tests with simulated transport, including software reopen and callback ownership. [Two production control-only hardware initializations](native-asio-control-reopen.md) now also pass through registration-free COM, including reopening without a power cycle and normal native owner retirement. Sustained streaming and normal Serato primary selection remain open; no installed service or automatic normal-start mechanism has been deployed.

The [subsequent native silent-duplex test](native-asio-silent-stream-reopen.md) completed three seconds of callbacks and normal stream retirement, but the next acquisition failed at USB redirect startup. Reliable post-stream reopening is therefore unresolved. Hardware testing stopped pending attended recovery and lifecycle tracing; the earlier control-only result must not be promoted to full lifecycle readiness.

The [on-demand deployment package](asio-on-demand-deployment.md) now binds its entry/worker/timing records to final protected paths. Isolated workspace/private-HKCU staging, registration, removal and recovery pass; native binaries are preserved and the temporary session route refuses this mode. This is installer-library validation, not production installation or ordinary Serato startup. The ten-minute unmeasured diagnostic limit still applies.

A [no-shim normal-start experiment](on-demand-normal-start-test.md) is now prepared with source-bound setup/restore and a successful read-only host Plan. It leaves Serato for manual ordinary launch and explicitly preserves the distinction between component setup and actual device selection. Production setup has not run. The separate control-only hardware probe does not validate installed Serato selection.

## Acceptance checks

1. Setup installs the required reviewed components once and records exact installed/original identities for repair and uninstall.
2. Launch the original Serato executable through its normal entry, without the development window or session commands. Observe actual rebuilt ASIO initialization and callbacks, with no repeated installer click or routine elevation.
3. Demonstrate two-deck Phase RCA tracking and actual SL3 output. Separately test timecode vinyl when the physical source is available; use the same installed driver.
4. Close and reopen normally without reinstalling or power-cycling. Preserve actual process, broker and USB retirement evidence rather than relying only on restored files.
5. Exercise long playback, unplug/replug and an interrupted application, with recoverable device ownership and no leftover audio worker.
6. Verify on another Windows account/PC, handle unsupported Serato versions without applying an unverified compatibility change, and uninstall back to the original state.

These checks remain open. The existing two-deck tracking, native audio tests and temporary-session recovery evidence remain useful, but do not prove install-once operation.
