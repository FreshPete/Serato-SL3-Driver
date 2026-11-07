# SL3 Windows handoff, 7 November 2026

The rebuilt Windows driver has carried Phase Essential tracking in Serato DJ Pro 5.0.0.1278 through the temporary installer-assisted setup. The next test is whether Serato selects the SL3 when opened from its usual shortcut, with the rebuilt driver staged and one USB connection already held open. That separates Serato’s selection decision from a failed first USB open. [Normal-launch trial](retained-normal-start-trial.md)

## Verified on the bench

| Area | Observed result |
| --- | --- |
| Serato startup | Two installer-assisted traces show primary selection of the genuine SL3, loading the rebuilt ASIO DLL, accepting a 128-frame buffer and successful ASIO start at 44.1 kHz. [Startup trace comparison](evidence/serato-startup-routes-20261107.json) |
| Phase Essential | The left deck followed the Phase platter in the requested REL test through LINE inputs 3/4. In the two-deck test, Phase A used 3/4 and B used 5/6. Both remotes shared one platter and the owner confirmed both waveforms followed it. A five-second capture found audio on both software output pairs. [One-deck test](evidence/phase-rel-session-20261105.json) · [Two-deck test](evidence/phase-two-deck-session-20261105.json) |
| Physical audio | A separate ASIO callback loopback sent stereo markers through SL3 OUT 1/2 and captured them on IN 3/4 at 44.1 kHz. The offset was 596 frames, about 13.51 ms for that loopback path. Serato’s physical deck outputs and separate input/output latency measurements remain open. [Loopback evidence](driver-timer-diagnostic.md#successful-attended-callback-retest) |
| Retained USB | Two independent ASIO host processes completed 1,031 and 1,032 callbacks over a single retained USB connection. The controller and worker retired after both clients closed. This used a private host and silent output. [Retained hardware result](evidence/retained-normal-start-trial-20261107.json) |
| Shutdown | The installer-assisted session closed cleanly with playback stopped and reopened successfully without a requested power cycle. In a longer looped playback session, the owner reported a normal close but the supervisor recorded forced termination. It verified restoration afterward. Clean shutdown after sustained playback remains open. [Stopped-playback reopen](evidence/serato-reopen-success-20261106.json) · [Looped playback](evidence/pointer-cleanup-live-retest-20261106.json) |

The last read-only check found the original Serato archive, no temporary ASIO package and no running Serato or project audio processes. Windows listed the SL3 under its original `strmdrv` binding with Code 39, the signed UsbDk service was running, and Windows reported Secure Boot enabled. The SL3’s descriptor was visible in the idle libusb checks. That is the resting configuration. [USB baseline](evidence/retained-release-identity-20261107.json) · [Original driver rejection](serato-usb-discovery.md#what-the-retained-usb-connection-exposes)

## Next attended test

1. Confirm the SL3 recovery and close Serato. If recovery is needed, remove USB and any external power for 30 seconds before reconnecting. A previous redirect stalled shortly after reconnect. The traces do not establish a safe reopen delay.
2. Use the local **Approve temporary SL3 setup** shortcut when ready for the test. After one Windows approval, the desktop runner checks the SL3’s USB identity, starts one retained connection and checks what Serato’s libusb library can see during ownership. Wait for the module observer to be armed.
3. Open Serato from its usual shortcut and leave playback stopped. Record what Serato shows. If it asks to Download Driver, leave the notice in place so the result reflects the normal launch.
4. Close Serato normally. The runner retires the retained connection and signals restoration, then observes USB visibility for 15 seconds. Verify the broker’s retirement and original setup independently. [Runbook and recovery](retained-normal-start-trial.md)

| Result | Next check |
| --- | --- |
| SL3 stays visible while the broker is ready, but Serato stays offline | Compare arrival queueing, listener lookup and primary selection. A fallback trace is prepared and has passed software checks. [Dispatch boundaries](serato-usb-subscription.md) |
| The rebuilt ASIO module appears | Match its exact Serato process to the broker’s admission and stream-start replies. If only admission is recorded, look at ASIO initialization and start before testing playback. [Result readout](retained-normal-start-trial.md#read-the-completed-broker-result) |
| USB acquisition stalls or visibility changes while held | Save the failed stage or changed identity and verify cleanup. The earlier physical release trace shows that UsbDk retirement and Windows’ ability to reopen the device are separate events. [Release trace](attended-native-stream-release.md) |

The prepared retained trial is in `analysis/sl3-on-demand-test-retained-idle-guard-20261107`. Its experiment and launch-record hashes are recorded in the software verification. Both read-only plans passed against the restored host. The separate application-bound package starts the broker from ASIO and remains a follow-up after the selection comparison. [Prepared inputs](evidence/retained-desktop-trial-20261107.json) · [Application-bound package](application-bound-broker.md#automatic-asio-activation)

## Remaining for an install-once release

The Windows target still needs normal Serato selection and automatic broker activation together, followed by physical deck output, independent two-platter control and a timecode-vinyl run. Phase RCA and vinyl use the same driver channels with source-appropriate input settings. Reliable close/reopen after playback, unplug/replug, long sessions, installation and uninstall on another Windows account or PC also need verification. macOS Tahoe remains deferred until Windows works. [Full acceptance checks](installed-use-target.md#acceptance-checks)
