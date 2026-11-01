# Windows physical-validation gate — 30 October 2026

## Installation completed — 14:27 UTC

The owner acknowledged the notice. The installer completed with MSI exit 0, captured its final state and exited. Secure Boot remained enabled, installed driver/helper hashes match the reviewed files, and UsbDk reports Running. The helper's explicit restart requirement is preserved separately from the MSI-only restart flag. The remaining immediate dependency is now an owner-performed Windows restart, followed by fresh preflight and traced List; no physical USB/audio test has run. See the [verified installation result](usbdk-installation-result.md). Earlier live-process/acknowledgement gates below are historical.

## Superseding installation update — 14:26 UTC

The owner authorized and accepted a new administrator prompt. Unlike the earlier cancelled launch, the installation is now active: elevated runner PID 39328, Windows Installer PID 51720 and helper PID 60036 were revalidated alive with the original creation times. The helper's visible window still says “Please restart your computer to complete the installation” and offers OK. Its acknowledgement is blocking the MSI transaction; `installerExitCode` remains null. The same notice has persisted across three consecutive goal turns. The automation click did not dismiss it, and the owner has been asked to acknowledge it manually. Do not interpret the continued wait as process failure, terminate the transaction or launch another installer.

Windows reports UsbDk running. Installed SYS/helper hashes match the reviewed binaries, and the elevated preflight confirmed Secure Boot enabled. No automatic restart, device redirection or audio transfer has occurred. The initial 60-second USB trace decoded with zero reported event/buffer loss, but the entire transaction exceeded that window. The visible restart requirement must be preserved even if the eventual MSI exit code does not itself request a restart.

The current user-dependent gate is **click OK, leave the PC running for final result collection, then arrange the required restart**. The final post-install snapshot and exit code are not yet available. The full goal is blocked at this acknowledgement; the running installer remains intact. Local evidence is under `tests/results/local/usbdk-install-20261030-02/`. The earlier absence/cancellation audit below is historical.

The full rebuild remains incomplete. The owner has deferred Mac work and requires Windows signing enforcement to stay enabled. The next required result is admission and actual operation of the reviewed signed USB transport. More arithmetic, simulated streaming or descriptor inspection cannot establish that result.

## Latest authoritative check

The read-only host check at **11:32 UTC on 30 October** found one SL3 with problem code **39**, bound to original `oem136.inf` / `strmdrv`. No UsbDk service or project test workers were present. The prepared installation's result directory does not exist. The earlier elevation launch returned that the operation was cancelled, with no child process ID; it is terminal, not a pending installer or verified wait. A fresh unelevated Secure Boot query remains unavailable, not evidence that Secure Boot is disabled.

The same missing admitted transport has persisted across multiple resumed goal turns. Independent work continued through Serato name matching, aggregation registration, resource-container decoding and the original timer-response comparison. Those checkpoints are saved and tested. The next implementation and integration decisions need actual completion/packet/clock/recovery behavior; replacing those observations with more simulation would not satisfy the goal.

No new security, trust, firmware, binding, installed application or account changes were made during this resumed work. The cancelled elevation request is not automatically repeated.

## Current evidence against the requested outcome

| Requested outcome | Evidence and remaining dependency |
| --- | --- |
| Normal-security Windows transport | Original signed Rane driver is still blocked. Reviewed UsbDk nested signature passes offline, but installation/load/admission are untested. |
| Real six-channel capture/playback | Native transport and conversion software build; simulated checks pass. No physical PCM capture or audio OUT has run. |
| Clock/control behavior | Earlier real rate getter reported 44.1 kHz. Bounded rate diagnostic and timer-response comparison are prepared; physical rate change, timer verification and control behavior remain unverified. |
| Usable ASIO | Original production component and lifetime/ownership tests pass against simulations. Real transport, measured timing configuration, deployment and actual audio-host behavior remain unverified. |
| Current Serato compatibility | Descriptor/provider/aggregation/audio/DVS boundaries are narrowed. The current archive has no SL3 identity in the inspected scalar nodes. No complete current descriptor/control/handshake integration is installed or working. |
| Two-deck DVS | Phase's current HID resource is present. Actual Phase connection, audio-input calibration, realistic motion and two-deck DVS operation are untested. |
| Latency, long-run stability and recovery | No measured loopback, four-hour physical session, required reopen/reconnect cycles or release installation/removal validation. |
| Mac | Deferred by the owner; prior preparation is historical and does not establish a Mac build or hardware result. |

The latest software checkpoint is **29/29 Release, 29/29 Debug, 21/21 SDK-free and 42/42 Python**. Source/build/log bindings are in [timer verification evidence](evidence/timer-verification-build.json); these are not physical results. The working tree was clean at the start of this audit.

## Concrete resumption

When the owner is available for the administrator prompt, rerun the prepared `scripts/test-usbdk-install.ps1` test with a fresh result path. It keeps Secure Boot enabled, verifies the unchanged signed package, records USB tracing and before/after state, suppresses automatic restart and preserves the original Rane package. Review the installer exit, code-integrity events, driver service/image identity and any restart requirement before proceeding. Installation is a system USB filter change; a successful MSI exit alone is not admission proof.

After admission, run the existing traced **List** test first. Then run a separate bounded **Capture** test. Only validated capture permits bounded silent duplex or an explicit rate test. Audio wiring and Phase are not required for listing or a silent transport test; analogue signal/mapping and actual DVS need a later controlled setup. No timer exchange is automatically added.

The full goal must remain unachieved until these physical/application acceptance requirements have real evidence. The owner-present installation is now the blocking dependency for the next meaningful validation step.
