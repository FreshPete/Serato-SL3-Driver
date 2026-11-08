# SL3 Windows handoff, 8 November 2026

The original Serato setup is restored and Serato is closed after the comparison. The 64-frame build passed the two-minute loop in Serato DJ Pro 5.0.0.1278. The 32-frame build stopped on an empty USB input packet. Use 64 frames for the next longer playback or reopen test. [Current results and remaining work](RETURN-REPORT.md#8-november-windows-handoff)

Before the comparison, the exact worker shared by both builds listed one high-speed SL3 through the reviewed UsbDk helper and matched its configuration descriptor. The listing used an ordinary Windows account without redirecting the device.

## Next attended test

1. With the SL3 connected and Serato closed, open the **64-frame** setup window. If using the ZIP, extract the whole archive and run `SL3_Compatibility_Setup.exe` from that folder. Choose **Check setup**, then **Install** and accept the Windows administrator prompt. Keep that folder for restoration. [Setup identities](one-time-setup-window.md#serato-playback-comparison)
2. Launch the existing Serato shortcut. Load the local latency test track on Deck 1 in INT and loop it. Confirm the playhead wraps before arming the capture. Keep the track looping for two minutes and close Serato normally. Save the app log, capture and worker result.
3. Use **Restore original setup** in the 64-frame window. After restoration, install the **32-frame** build and repeat with the same Serato settings and track. A failed start or early stream stop is a test result. Keep `worker-startup.tsv` and `result.json` before a retry.
4. Compare reported buffer, clip continuity and normal retirement. The optional RCA return test also needs verified output and separate LINE return wiring. [Paired capture](two-deck-output-capture.md#paired-rca-loopback-capture)

## 7 November checkpoint

The rebuilt Windows driver carried Phase Essential tracking in Serato DJ Pro 5.0.0.1278 through the temporary installer-assisted setup. The first one-time install succeeded, but both launches from the usual shortcut stayed on offline audio. The follow-up trace found that Serato processed the SL3 arrival with zero listeners. The later sign-in watcher and playback trials are recorded separately. [Startup trace](serato-usb-subscription.md#live-result-after-the-one-time-install) · [Later trials](one-time-setup-window.md#windows-sign-in-watcher)

## Verified on the bench

| Area | Observed result |
| --- | --- |
| Serato startup | Two installer-assisted traces show primary selection of the genuine SL3, loading the rebuilt ASIO DLL, accepting a 128-frame buffer and successful ASIO start at 44.1 kHz. [Startup trace comparison](evidence/serato-startup-routes-20261107.json) |
| Phase Essential | The left deck followed the Phase platter in the requested REL test through LINE inputs 3/4. In the two-deck test, Phase A used 3/4 and B used 5/6. Both remotes shared one platter and the owner confirmed both waveforms followed it. A five-second capture found audio on both software output pairs. [One-deck test](evidence/phase-rel-session-20261105.json) · [Two-deck test](evidence/phase-two-deck-session-20261105.json) |
| Physical audio | A separate ASIO callback loopback sent stereo markers through SL3 OUT 1/2 and captured them on IN 3/4 at 44.1 kHz. The offset was 596 frames, about 13.51 ms for that loopback path. Serato’s physical deck outputs and separate input/output latency measurements remain open. [Loopback evidence](driver-timer-diagnostic.md#successful-attended-callback-retest) |
| Retained USB | Two independent ASIO host processes completed 1,031 and 1,032 callbacks over a single retained USB connection. The controller and worker retired after both clients closed. This used a private host and silent output. [Retained hardware result](evidence/retained-normal-start-trial-20261107.json) |
| Shutdown | The installer-assisted session closed cleanly with playback stopped and reopened successfully without a requested power cycle. In the longer looped run, Windows recorded the supervisor's forced exit before the close confirmation reached the chat. The time of the manual window close remains unknown. The supervisor verified restoration afterward. [Stopped-playback reopen](evidence/serato-reopen-success-20261106.json) · [Looped playback timeline](serato-shutdown-diagnostic.md#timing-of-the-looped-playback-retest) |

Before the one-time install trial, a read-only check found the original Serato archive, no temporary ASIO package and no running Serato or project audio processes. Windows listed the SL3 under its original `strmdrv` binding with Code 39, the signed UsbDk service was running, and Windows reported Secure Boot enabled. A five-second idle libusb check returned four complete snapshots with one unchanged SL3 identity. The private observation file SHA-256 is `4f3826ee80f67b5fde7ad2b344e34fd2e60683c7a57a66d743f528a003559178`. This confirms idle visibility. [USB baseline](evidence/retained-release-identity-20261107.json) · [Original driver rejection](serato-usb-discovery.md#what-the-retained-usb-connection-exposes)

## One-time install trial

The portable r2 setup reported a successful install and passed its postcheck. Both starts used the original desktop shortcut. The first process exited normally before the second was launched, with the SL3 still connected and no repeat install. The owner reported offline audio on both launches. The candidate resource archive was in place, Windows still enumerated the SL3, and module snapshots from both Serato processes showed libusb loaded without the rebuilt ASIO DLL. No application-bound activation receipts appeared. These observations narrow the next check to Serato's device selection and request for ASIO. They do not show which selection step failed. [Arrival and selection boundaries](serato-usb-subscription.md)

The same setup window restored the original installation. A separate check matched the original archive hash and found no staged package, rebuilt ASIO or COM registration, or running Serato or SL3 audio process.

## Repeat after a device-selection change

1. Close Serato. In **SL3 Compatibility Setup**, click **Check setup**, then **Install** and approve the Windows prompt. Wait for **Installed — ready for a Serato startup test**, then close the setup window.
2. Open Serato from the usual shortcut. Check that it connects to the SL3 and shows deck controls. Leave any Download Driver notice untouched and report it if it appears.
3. If the SL3 connects, close Serato normally and reopen it from the usual shortcut with the SL3 still connected. The result should be the same without a second install, prompt or power cycle. This build has a ten-minute diagnostic audio limit.
4. If the trial fails, close Serato and use **Check setup** and **Restore original setup** in the setup window. Save any status message first. [Setup and restoration](one-time-setup-window.md)

After Serato closes, the existing application-bound driver records can corroborate the result. The [read-only startup readout](../scripts/read-installed-asio-start.py) takes the reviewed activation configuration and the new `application-<PID>-<creation FILETIME>` session folders in `%LOCALAPPDATA%\SL3RebuildActivated`. Use one `--session` argument for each launch. It checks that the startup receipt and readiness record match the configuration, then reports stream-start replies for the exact host identity and the worker retirement result. A missing or incomplete record stays inconclusive. The readout does not identify the host executable on its own. The two-process Windows fixture returned two start replies and application-exit retirement for each simulated host. Its readout SHA-256 is `ffbc19ed30cef5cee2d0abc1fc52978b702f8859e5f6343b74d40c6454e8c6df`.

If an incomplete receipt has a matching broker intent and an unpublished result, the readout can distinguish an explicit refusal by the exclusive redirect guard from another startup failure with the same Windows busy code. The guard refusal reports that the named ownership object already existed. It leaves the owner identity and Windows' readiness for another redirect open. The fixture checked both busy outcomes. [Earlier physical reopen result](native-asio-silent-stream-reopen.md)

## Fallback if ordinary startup fails

1. Remove USB and any external power for 30 seconds, reconnect the SL3 and wait another 30 seconds before starting the test. Close Serato. The settling interval is part of this trial because a previous redirect stalled shortly after reconnect. The traces do not establish a safe reopen delay.
2. Use the local **Run SL3 normal-start test** shortcut. Type `RECOVERED` after reconnecting the SL3 and closing Serato, then approve the Windows prompt. The runner checks the SL3’s USB identity and starts one retained connection. The module observer opens the installed Serato executable under the ordinary account once the connection is ready.
3. Leave playback stopped. Record what Serato shows and leave it open for five seconds after the hardware status appears. If it asks to Download Driver, leave the notice in place so the result reflects the normal launch.
4. Close Serato normally. Leave the test console open while it retires the connection, signals restoration and observes USB visibility for 15 seconds. After the setup process exits, the console independently checks the original archive and absence of the temporary ASIO package. It saves that check in `attended-setup/restore-postcheck.json`. [Runbook and recovery](retained-normal-start-trial.md)

| Result | Next check |
| --- | --- |
| SL3 stays visible while the broker is ready, but Serato stays offline | Compare arrival queueing, listener lookup and primary selection. A fallback trace is prepared and has passed software checks. [Dispatch boundaries](serato-usb-subscription.md) |
| The rebuilt ASIO module appears | Match its exact Serato process to the broker’s admission and stream-start replies. If only admission is recorded, look at ASIO initialization and start before testing playback. [Result readout](retained-normal-start-trial.md#read-the-completed-broker-result) |
| USB acquisition stalls or visibility changes while held | Save the failed stage or changed identity and verify cleanup. The earlier physical release trace shows that UsbDk retirement and Windows’ ability to reopen the device are separate events. [Release trace](attended-native-stream-release.md) |

The earlier attended trial completed setup and kept the same SL3 identity visible to Serato's libusb library before, during and after ownership. The manual launch window expired without a sampled Serato process. The test verified retirement and independently confirmed restoration. The refreshed retained trial in `analysis/sl3-on-demand-test-retained-reviewed-assets-20261107` uses the same package and opens Serato after arming the observer. Its read-only plans passed. The one-time installer uses the application-bound package, which starts the broker from ASIO. [Attended USB evidence](evidence/retained-usb-visibility-20261107.json) · [Application-bound package](application-bound-broker.md#stop-during-automatic-startup)

## Remaining for an install-once release

The one-time install has already selected the SL3 and activated the driver from the usual shortcut. Remaining live checks cover 64/32-frame playback, physical deck output, independent two-platter control and timecode vinyl, as well as close and reopen after playback, unplug/replug, long sessions and setup on another Windows account or PC. macOS Tahoe remains deferred until the Windows playback and recovery gates pass. [Full acceptance checks](installed-use-target.md#acceptance-checks)
