# Phase Essential with Rane SL3 on Windows

Updated 4 November 2026. The target is to use Phase Essential for two-deck DVS in Serato DJ Pro 5.0 on Windows 11, with the Rane SL3 handling audio. The first milestone is one deck tracking from Phase through the SL3, with Serato playback returning through the SL3 outputs. The current tests use the signed UsbDk transport with Windows driver-signature enforcement enabled.

## What works on the bench

- A paired Phase remote spinning on a platter sent its analogue control signal into the left deck's SL3 inputs 3 and 4. The independent Windows recorder captured both channels at 44.1 kHz. Each measured about −12.4 dBFS RMS with a dominant component near 834 Hz. This verifies that the Phase signal reaches the rebuilt capture path. [Physical input capture](input-record-trace.md)
- A separate stereo loopback from SL3 OUT 1/2 to IN 3/4 set to LINE passed through the native host callback path. Both markers returned with a measured round-trip offset of 596 frames, or 13.51 ms at 44.1 kHz, with clean device release. [Callback loopback](driver-timer-diagnostic.md#successful-attended-callback-retest)
- An ordinary-user ASIO host activated the registered rebuilt driver and queried its name. That registration test used an unavailable-state profile without a live streaming broker. [ASIO host and Serato trace](serato-archive-deployment.md#registered-asio-host-and-serato-registry-trace)

## Where Serato 5.0 stops

In Serato DJ Pro 5.0.0.1278, the temporary SL3 definition let Serato identify the unit and enumerate the rebuilt ASIO driver. The USB-only trace saw the SL3 arrival, but the traced USB audio manager did not initialize or receive it. The separate cause of that startup state remains open. [Live device selection and USB audio manager traces](serato-archive-deployment.md#live-device-selection-trace)

Replacing an existing spec in the archive, replacing a descriptor entry in memory, and applying a process-local USB alias each left Serato on its fallback `Offline Device`. The combined test also failed to associate the virtual MIDI endpoint until a narrowly scoped diagnostic reserved the port for the SL3's own matcher. Serato then paired the port and added the SL3 on the first attempt. The 80-second trace still showed no named audio selection or ASIO DLL load. The virtual MIDI port was an association test. Phase's analogue control signal and any SL3 control messages are separate from that port. [MIDI and descriptor experiments](serato-handshake-consumers.md#adding-a-midi-port-to-the-sl3)

The original Serato resources were restored and the temporary ASIO registration and MIDI ports were removed. Serato playback through the SL3 and Phase DVS tracking inside Serato remain unverified. The current test boundary is the application-to-ASIO handoff.

## Resume point

The installer completion callback is a separate route to primary-device selection. The first attended test opened a driver download page that returned 404 and observed no local installer launch. The next trace will distinguish the browser action from the local installer and capture the device ID and bundle lookup. [Driver-install completion experiment](serato-archive-deployment.md#driver-install-completion-experiment)

The diagnostic package can show whether Serato reaches the rebuilt ASIO driver. A live audio session is needed to verify one Phase deck on inputs 3 and 4 and playback through the SL3 before testing the second deck.

A workspace test isolated the missing-driver notice to the candidate's x64 detection field. Suppressing the notice preserved SL3 arrival and left Serato on default audio. A separate 44.1 kHz preference variant also preserved startup recognition and default audio. That rate matches the verified bench loopback. The live Serato rate request and playback remain to be observed. [Workspace startup comparison](serato-archive-deployment.md#workspace-startup-comparison)

The candidate maps Serato Deck 1 to logical channels 3 and 4 in both directions. The saved Phase capture verifies the input pair. The earlier bench loopback played on logical outputs 1 and 2, so physical Deck 1 output still needs a separate check. The callback probe now has an inert `--plan-loopback-deck1` preview for a bounded output 3/4 test. The native preview and simulated recording lifecycle passed. The ASIO facade's simulated clock and restart test also passed at both 44.1 and 48 kHz. Neither check exercised physical Deck 1 output or Serato playback.
