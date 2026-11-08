# One-time SL3 setup window

The current local build binds the setup window to the [application-bound ASIO package](asio-on-demand-deployment.md#application-bound-candidate). The window still offers **Check setup**, **Install** and **Restore original setup**. Install and Restore request separate Windows approvals when invoked. Serato starts separately from its usual shortcut.

Follow-up: [administrator result capture and local diagnostics](setup-result-diagnostics.md) now preserve failure details across the postcheck and show the existing ten-minute diagnostic bound. The earlier build/visual evidence below is historical; the latest rendered review was interrupted by the locked desktop.

The simple Windows setup window is now implemented and built. It offers **Check setup**, **Install**, **Restore original setup** and optional diagnostic details. Opening it runs no command. Sixteen checks pass, and the ordinary/expanded layouts and selected keyboard behavior were inspected on this host. **Administrator installation/restoration and normal Serato startup have not run through this window.** [Source, build and observation evidence](evidence/one-time-setup-window-20261106.json)

The prebound build and the portable development build both use the [reviewed native entry](native-on-demand-experiment-entry.md). Install once, close the setup window and use the original Serato shortcut. Phase and timecode vinyl share the driver.

## Actions and state

| Action | Behavior |
| --- | --- |
| Check setup | Runs the native read-only experiment check in the background. It checks the selected files and registration, whether Serato is closed, and whether Windows reports the UsbDk kernel driver running. |
| Install | Enabled only for a recognized install/retry state with Serato stopped. It rechecks before requesting Windows administrator approval for the fixed native setup action, then observes the resulting state. |
| Restore original setup | Enabled only for a recognized non-clean state with Serato stopped. It requests Windows approval for the fixed native restore action, then observes the resulting state. |
| Diagnostic details | Shows bounded, read-only command output. No upload or message is sent. |

Unknown/conflicting states do not enable privileged actions. The reported running-Serato Boolean disables both installation and restoration; that rule and typed parsing are tested with fixtures without launching Serato. A successful installer exit alone is insufficient for the success label: the following read-only check must observe the expected installed or restored state. Installation success is labelled readiness for a **startup test**, not working audio or DVS.

If UsbDk is unavailable, **Install** stays disabled and **Restore original setup** stays available for recognized recovery states. The administrator entry rechecks the service before installation. This checks Windows service status without starting the service or opening the SL3.

Commands run on a worker thread. While busy, command buttons are disabled and closing the window is refused. The existing read-only job timeout is retained; privileged transactions are not terminated by the window. Cancelled elevation or failed commands do not trigger another operation automatically. The Install/Restore UAC sequence, failure receipts and real partial-state recovery still need an attended test.

## Interface brief and review

Mode: **Operate**. This extends the existing `DESIGN.md` native Windows world: system colors, standard controls, Segoe UI, scaled layout, visible keyboard focus and optional details. It adds no visual identity or web styling. The skill's platform classifier does not recognize Win32; the established Windows implementation was retained rather than relabelled as a web/mobile platform.

Check setup is the default button; Install is not the default. Access keys are C, I, R and D. Live inspection confirmed the Details access key expands the read-only area and reverse Tab skips disabled installer actions back to Check setup. Both ordinary and expanded views were inspected. Windows reports Segoe UI for body and heading. The native-C++ mechanical detector reported no findings, with limited coverage. Minimum-size interaction, high DPI and high contrast are not claimed validated.

Sixteen actual checks cover clean/installed/partial/conflicting eligibility, the running-state gate/parser, inert opening and preview behavior, command disabling, refusal to close mid-check, a real native read-only check and normal idle close. Preview never dispatches commands. No installer button was clicked in desktop inspection, and all inspected windows were closed afterward.

## Current private candidate

```text
artifacts/build/native-setup-window-usb-prerequisite-20261107/build/Release/SL3_Compatibility_Setup.exe
SHA256 14656a4b63eaf1b004b2a00ee5ca9fefd97ef3e7753527612dc2a762635c2368
```

All three native build checks and 19 window cases passed. The actual Windows check found the running UsbDk kernel service, and the simulated unavailable-service case preserved restoration while disabling installation. The window is bound to this PC's prepared record, and the live test still uses one install and two ordinary Serato launches. [Test steps](return-to-testing.md#next-attended-test)

The same kit renders the expected archive scripts and deployment plan from reviewed sources before running PowerShell. It compares the pinned local files with that recipe and the known candidate archive hash. The earlier 34-case moved-entry check refused edited wrappers, helper, plan and archive even when the caller supplied new matching hashes. The native fixture report SHA-256 is `429844ee721d39f4d12c19fe3e3399293d31d7c1cdffde58ef8900af114eabed`.

### Portable development build

The private portable package keeps the setup window, native entry and `kit` together. **Check setup** locates Serato through Windows and prepares local files on first use. Reopening the window selects the same verified record. Opening the window alone is idle. Windows holds an exclusive file handle during selection, and the installer publishes the complete record by renaming its preparation directory. An interruption before publication leaves the unfinished files separate, so the next check can retry with Serato's original setup in place. Ambiguous published records still require review.

The fresh portable fixture passed 20 cases and the prebound fixture passed 19. The first build exposed an output race where the window could miss the helper's last reply. Both builds passed after checking the pipe again after helper exit. The portable window SHA-256 is `2f9a0740c2740572fd52119741bb4d986b49ef77c0e7c8c622a31d9caf933efe`. The local package still needs an attended Install and Restore test, and normal Serato startup on another PC remains unverified.

The private archive `artifacts/build/SL3-Portable-Setup-20261107.zip` contains 762 reviewed files, including the two setup executables and the kit. It omits generated setup state and the Serato executable and archive. The [packaging command](../scripts/package-setup-window.py) verified every ZIP member against the reviewed build and kit. A fresh extraction into a path with spaces and Unicode passed all 20 window cases, including local preparation and reopening. Its SHA-256 is `38eb3a229c6870227bd1002178f8e315da6af21cb336af7e8807a15b8d31cea1`. Extract the entire ZIP to a local folder and open `SL3_Compatibility_Setup.exe`. The trial uses Serato DJ Pro 5.0.0.1278 and requires the UsbDk service running.

The interruption recovery build is `artifacts/build/SL3-Portable-Setup-20261107-r2.zip`, SHA-256 `66596c2a92471e62dd3c8d99e10cfb6614ff786999638b03801e29344436b999`. The relocated native entry passed 40 cases, including refusal while the selection lock was held, preparation after a simulated interruption, and reuse of the exact committed record. The window passed 20 checks and the ZIP packager verified all 762 files. These checks left the original Serato setup in place.

### Windows sign-in watcher

The portable setup accepts a reviewed watcher DLL through `prepare-setup-window.py --watcher-dll`. Its archive includes the watcher, DLL and setup helper, and the window pins all three before running the helper. Install first stages the driver and Serato resources using the existing administrator action. The window then copies the reviewed watcher files into the current user's local application data, registers one entry under that user's Windows Run key, and verifies that the watcher is running in the current session. Restore removes the owned entry and watcher files. Diagnostic logs are retained locally.

The initial integrated trial installed the driver but inherited a module path that prevented Windows PowerShell from loading `Get-FileHash` during watcher setup. After restoration, the corrected bundle passed the 20 setup window checks, verified all 765 ZIP members, and installed cleanly. The watcher reported ready in the same Windows session that ran setup, and its sign-in entry was present.

Serato started the SL3 from the desktop shortcut in that installation session. The next Windows session did not have a ready watcher. Its first observation still held the previous session's status file. A Windows PowerShell 5.1 reproduction showed that `File.Replace` rejected the original null argument when replacing that file. The final bundle uses the explicit .NET null string and records start, readiness and failure markers so a Windows sign-in can be checked independently of the installer. Its 20 setup checks and all 765 ZIP member checks passed. The original setup was restored before opening the final bundle for the clean retest.

The final private test archive is `artifacts/build/SL3-Portable-Setup-20261107-signin-final.zip`, SHA-256 `a75c37ded09aa1b03c5f43d59036b1cf34812a49e84232e6fd228b62fabcf526`. After one clean install, the operator signed out and back in. Windows Explorer started a new watcher in the new session about 14 seconds after Explorer started. The watcher replaced the previous status receipt and reported ready before Serato opened.

Two launches from the original desktop shortcut both matched the SL3 notice, requested selection once, loaded `sl3_asio.dll` and logged SL3 audio start at 44.1 kHz with a 192-frame application buffer. The same watcher handled both launches without an installer click, reinstall or SL3 power cycle. Playback stayed stopped. Both Serato windows closed through the normal window close path. The final setup and watcher remain installed.

Each broker acquired the SL3 and acknowledged one stream start. Each then reported `worker_exited` with exit code 1 and unverified USB release about five seconds after acquisition, while Serato was still open. The broker result hashes are `7d7b31dab339ccb74494df38fa8cda9619065d3ba67554339d3bcb43f586d06a` and `40d71d814226b6ac529d987f967584392f153573436a1afca3541cb0753f9bf4`. The same symptom was present on the earlier launch before sign-out. Startup and reopen are verified for device selection and ASIO start. Sustained audio through this install remains open.

### Playback keepalive retest

The two sign-in trial journals put the redirect close 125 ms and 328 ms after the broker reported the device ready. Both controllers began their cleanup 5,078 ms after worker entry. In the retained worker, a stream fault can release the USB device immediately. The worker then has no device or stream, so its five-second idle deadline, measured from entry, accounts for the later process exit. The old journals did not preserve the original stream fault code.

The installed diagnostic profile had disabled the existing playback keepalive mode and the bounded startup packet handling that accompanies it. The new private package selects both through `SL3-ASIO-DIAGNOSTIC-TIMING-2` and journals a stream fault before releasing the redirect. All 73 native tests, three setup entry checks, 20 window cases and 765 package member checks passed. The private archive is `artifacts/build/SL3-Portable-Setup-20261107-playback-keepalive.zip`, SHA-256 `b034463e824d7a057ebd29d9b8d97dd955cb384f002db74400ff92ab505ffd3e`.

Serato DJ Pro 5.0.0.1278 opened from the usual desktop shortcut and loaded the rebuilt SL3 driver with the new profile. The same worker stayed active for the entire 120.61-second Deck 1 loop observation. A five-second sample at the end verified 220,500 frames of nonzero software output on each of channels 3 and 4. The operator reported clean sound and a responsive interface. The clip remains private. Its PCM SHA-256 is `a58026bc98776f959bd38ead77cc545a15356a32623e125231c843ef020cc78d`.

The keepalive loop ran for approximately 342 seconds from ASIO stream start through the end of playback. On normal Serato close, the broker verified I/O retirement, USB release and worker exit with code 0. The broker result SHA-256 is `8cdae342340262d02769c324a8e72ab45694725cc339410cb6901bd2e995c80c`. The package remains installed. This test exercised internal playback on one deck.

A separate 128-frame startup on 8 November reached ASIO start with the same keepalive worker. The worker later reported `invalid_input` after publishing 4,473 one-millisecond input blocks. The redirect-close call returned in the journal. The broker saw worker exit code 1 and did not receive a valid final snapshot to verify retirement or release. The journal does not distinguish an invalid packet length, packet status or batch count. The worker now records the first rejected input position and the observed packet count, index, length and status before closing the stream. Packet index 64 means the rejection was at batch level. The stream still stops on invalid input. [Bound records](evidence/serato-128-input-fault-20261108.json)

### Lower buffer measurement

#### Original-driver reference

Serato lists DJ Pro **2.5.5** as the last supported SL3 version and identifies **2.5.6** as the start of the cutoff. Rane's original SL3 manual gives **1.8 ms at 44.1 kHz** and **1.6 ms at 48 kHz** for the device itself. The manual adds driver buffering for a Windows ASIO round trip and describes reliable operation below 8 ms on suitable PCs. [Serato SL3 support](https://serato.com/dj/hardware/rane-sl3) · [Serato cutoff notice](https://the-drop.serato.com/announcements/important-information-about-discontinued-hardware/) · [Rane SL3 owner’s manual](https://www.ranecommercial.com/legacy/pdf/sl3_manual_dj.pdf)

The original Windows x64 ASIO DLL version 1.3.5.302 falls back to an 8 ms setting when reading `BufferSizeMillisecs` fails. Its buffer selector rounds that setting down to a 6 ms target, selects an 88-frame bank at 44.1 kHz and advertises that bank as the minimum, maximum and preferred size. The latency method reports one selected bank for input and two for output. At that default this is 88 input and 176 output frames, about **5.99 ms combined as reported to the host**. With a 1 ms setting the same path selects the 45-frame floor, about **3.06 ms combined as reported**. These values come from static inspection of the driver. A direct performance comparison needs the same physical loopback on the original supported setup and the rebuild. [Binary observations and calculated examples](evidence/rane-original-asio-timing-20261108.json)

#### Rebuilt-driver loopback

The physical RCA loopback used SL3 OUT 1/2 to IN 3/4 set to LINE. Two independent short callback tests used the same installed UsbDk worker, keepalive mode, 44.1 kHz clock and eight-interval USB requests. Serato was closed for these measurements.

| ASIO buffer | Left return | Right return | Callback count |
| --- | --- | --- | --- |
| 128 frames | 592 frames, 13.42 ms | 594 frames, 13.47 ms | 1,034 |
| 64 frames | 466 frames, 10.57 ms | 468 frames, 10.61 ms | 2,068 |

Both tests verified the returned stereo markers, callback sequence and native release without a pump or stream fault. The measured reduction was 126 frames, or 2.86 ms, on both channels. At 64 frames, the number of host callbacks doubled. The short loopback measures the driver and analogue path together. Serato's own processing and a sustained dropout check at 64 frames remain to be tested.

The separate 64-frame driver bundle passed all 73 native tests, the passive native configuration check, and package verification. Its exact worker repeated the physical loopback at 464 and 466 frames, or 10.52 and 10.57 ms, with 2,068 callbacks, no pump or stream fault, and verified device release. The bundle is `artifacts/build/deployment-bundles/latency-64-20261108` with manifest SHA-256 `8b955355d67378dd9e83cf766d8b160091d311ab11113dc882b2ba913a62c787`. The tested 128-frame setup remains installed and Serato is closed.

The follow-up used the same RCA wiring, 44.1 kHz worker and one-millisecond USB requests. A separate synchronous probe read each output bank after its own callback completed. It could do that because it owned the callback and filled every output before returning.

| ASIO buffer and output handling | Left return | Right return | Maximum callbacks per USB batch |
| --- | --- | --- | --- |
| 32 frames, standard | 400 frames, 9.07 ms | 402 frames, 9.12 ms | 2 |
| 64 frames, synchronous probe | 402 frames, 9.12 ms | 404 frames, 9.16 ms | 1 |
| 32 frames, synchronous probe | 370 frames, 8.39 ms | 372 frames, 8.44 ms | 2 |

All three short runs verified both markers and released the SL3 without a pump or stream fault. A separate 60-second standard 32-frame run completed 82,660 callbacks and 59,979 USB output completions, with zero pump or stream faults and verified device release. The probe used its own callbacks and did not run Serato. The 64-frame synchronous result is close to standard 32 frames while avoiding the paired callbacks within a USB batch.

The pinned Serato DJ Pro 5.0.0.1278 executable queries the ASIO `outputReady` wrapper at `0x142217141` and saves whether it returned zero. In its audio callback it conditionally calls the same wrapper at `0x142216281` after the output routine. The wrapper at `0x142222120` dispatches to IASIO slot `+0xb8`. This identifies the code path for an attended early-output test. The deployed driver still uses standard bank ownership. It needs a positive completion signal from the host before it can read a bank early.

The separate standard 32-frame bundle passed all 73 native tests, the passive native configuration check and package verification. The bridge test covers two callbacks completing in one USB batch and verifies output order and exact sample values. The bundle's worker repeated the physical loopback at 402 and 404 frames, or 9.12 and 9.16 ms, with 4,135 recorded callbacks, zero pump or stream faults and verified device release. The bundle is `artifacts/build/deployment-bundles/latency-32-20261108` with manifest SHA-256 `3d8e7f3dbddfa25e5cda236c5ca5d1c98c47fe54142fbe79d3fae87a18ba99e3`. The 128-frame setup remains installed. The first attended comparison should check standard 32-frame playback against 64 frames from the same Serato shortcut, including actual playback, the selected host buffer and the shutdown report.

### Serato playback comparison

The 128-frame setup was subsequently removed through **Restore original setup**. The original Serato resource hash matched and the protected driver stage was absent. The private comparison installers below use identical ASIO DLL, broker and USB worker binaries, with different buffer records. This build includes the rejected-input packet journal and optional paired capture for an RCA return. It passed all 73 Windows native tests. Each installer passed its three entry checks and 20 setup window cases against the original installation. These checks exercised setup eligibility, without elevation, Serato playback or USB streaming. The earlier physical loopback figures refer to the earlier bundles above. [Paired capture procedure](two-deck-output-capture.md#paired-rca-loopback-capture)

| ASIO buffer | Local setup build under `artifacts/build` | Setup executable SHA-256 |
| --- | --- | --- |
| 64 frames | `native-setup-window-worker-loopback-64-20261108` | `2dc103e71e5038af139b2cee718d3356bd1deecdda084486f0868eb822841f3d` |
| 32 frames | `native-setup-window-worker-loopback-32-20261108` | `497db229c2ae2b9ef0af668d9099fdd4b48326ab13b37a5c84feab9cd1e9e400` |

The same builds are available as local private archives under `artifacts/build`. All 765 members in each archive were verified against their source hashes. The extracted kits also passed a read-only check from a path with spaces and Unicode, using their bundled runtime. They require the pinned Serato 5.0.0.1278 installation and a running UsbDk service. The archives contain setup and recovery tools, with the compatibility resources generated locally at setup time.

| ASIO buffer | Private archive | Archive SHA-256 |
| --- | --- | --- |
| 64 frames | `SL3-Private-Serato5-64-Frame-20261108.zip` | `02e9eecdf3cc91515b19b0d09509b5cc159408545e26571c696b3479c09011a0` |
| 32 frames | `SL3-Private-Serato5-32-Frame-20261108.zip` | `a0bfa98d82faa061c41d3a5df6e11c1e8b5e2ae802ab88c4660d70349373a8e7` |

1. Use `build/Release/SL3_Compatibility_Setup.exe` in the 64-frame build. With Serato closed, check setup, install and approve the Windows prompt. Read `sl3-timing.conf` in the protected driver folder and verify that it says `buffer_frames=64`.
2. Launch the usual Serato shortcut with a fresh, process-scoped `SL3_OUTPUT_CAPTURE_DIRECTORY`. Load `artifacts/audio/SL3 Latency Loop Test.wav` on Deck 1 in INT, keep playback level low and use the same Serato Audio settings for both trials. Enable the loop and watch playback cross its wrap point before creating `arm.txt`. The earlier one-minute WAV ended before its capture began and that clip contains silence on all channels. If the test track has no usable beat grid, set the loop start and end manually.
3. Let the loop play for two minutes. Save the Serato audio-start record, the verified Deck 1 capture and the broker result after normal close. The Serato log's application buffer and the ASIO buffer configured by the package are separate values. Record any audible gaps if the deck output is monitored. The exported clip reports the longest digital-silence and identical-sample runs on each stereo pair. A clean five-second clip covers dequeued software samples during that window.
4. Restore through the 64-frame setup window and verify the original state. Install the 32-frame package and repeat with a fresh capture directory, `buffer_frames=32`, the same track and the same settings. Compare startup, software gaps, any audible gaps and normal worker retirement alongside the earlier physical loopback figures. If a worker stops early, retain `worker-startup.tsv` as well as `result.json`. The worker journal can preserve the rejected-packet record even when the broker misses the final snapshot.

The comparison track has continuous quiet stereo tones under a half-second beat envelope. Its SHA-256 is `0c454d41d2de59953fba038efe1049d265ca265e874629faedaf326ce699284c`. The two Serato playback trials still need an administrator at the PC to switch packages. [Capture contract](two-deck-output-capture.md#recording-contract)

After closing Serato, run `python scripts/read-installed-asio-start.py --diagnostic-timing --activation BUNDLE/sl3-asio.conf --session SESSION_DIRECTORY`. Use the selected private bundle and its exact `application-<PID>-<creation FILETIME>` session under `%LOCALAPPDATA%/SL3RebuildActivated`. The readout binds the configured buffer to the session's published worker configuration and readiness receipt. It reports the broker's stream-start and retirement evidence separately. Read the Serato log and saved output clip alongside that report for the application buffer and sample continuity.

On 8 November, the 64-frame build started from the usual shortcut. Serato used a 128-frame application buffer. The operator confirmed an eight-bar INT loop on Deck 1, and the worker stayed active for the 120-second observation. A late five-second capture contained continuous signal on software channels 3/4, with zero silent stereo frames and no repeated stereo frames. Serato reported zero callback dropouts at SL3 disconnect. On normal exit the broker verified I/O retirement, device release and worker exit code zero. [Run evidence](evidence/serato-500-looped-buffer-comparison-20261108.json)

The matching 32-frame build also started from the usual shortcut, using a 96-frame application buffer. The worker stopped about 72 seconds into the confirmed loop observation. The first packet of an eight-packet USB input batch reported success with zero bytes at stream frame 4,739,000. The worker rejected the batch and exited before the capture was armed. Its journal records the redirect-close return, and the broker lacked a valid final snapshot to verify device release. Serato still reported zero callback dropouts at disconnect, so that counter alone would miss this interruption. **64 frames is the lowest setting that passed this comparison.** The two runs establish different outcomes without isolating buffer size as the cause of the empty packet. [Run evidence](evidence/serato-500-looped-buffer-comparison-20261108.json)

### Isolated empty-packet recovery at 32 frames

The 32-frame diagnostic worker can conceal one successful zero-byte input packet at 44.1 kHz. It checks the seven other packets and the previous nine batches for the expected five- or six-frame packet sizes. It uses the nominal 441-frame total over those 80 USB intervals to estimate the missing packet length, and accepts only an estimate of five or six frames. It inserts silence for the missing input interval and keeps the other PCM in order. The estimated length can differ from the device's actual cadence. Recoveries must be at least ten seconds apart, and a transfer error, multiple empty packets in the same batch or insufficient cadence evidence still stops the stream.

The worker records the recovery count, last affected block frame, packet index and estimated frames in `worker-startup.tsv` at stream retirement. A looped run from the regular Serato shortcut should check uninterrupted worker life, software output, UI responsiveness and clean retirement. The recovery record shows whether a live run exercised the fix.

The private `SL3-Private-Serato5-32-Recovery-20261108.zip` passed 73 native tests, three setup entry checks, the 20-case setup window check and the ZIP inventory check. Archive SHA-256 is `7f18c424e33fe01787485ba1cd59fc3479a816e6354bbf5ad6e1fea0d80580ed`.

The 8 November retest started the SL3 from the usual shortcut with the 32-frame driver and a 96-frame Serato buffer. The operator confirmed the 8-bar loop, but reported severe lag. The session was force-closed before the planned five-minute observation. The worker stayed active long enough to capture five seconds of continuous Deck 1 software output, starting about 149 seconds into the stream. Serato reported main-thread hangs before the SL3 audio start and during playback. Around the forced exit, the worker reported output starvation. The journal contains no empty-packet recovery or invalid-input event, so this run did not verify recovery on physical hardware. **64 frames remains the verified fallback.** [Retest evidence](evidence/serato-500-32-empty-input-recovery-20261108.json)

### Serato lag with the SL3 disconnected

With the original setup restored and the SL3 physically unplugged, Serato 5.0 opened from the usual shortcut. Its first main-thread hang warning arrived 5.1 seconds after launch, before the offline audio connection started at 6.4 seconds. Windows later reported the window unresponsive and Serato logged stalls up to 11 seconds. The operator could not start the test loop and had to force-close Serato. This establishes that the lag can occur independently of SL3 audio. Serato also logged an automatic library import during the offline run. Its contribution to the stalls has not been isolated.

In the earlier hardware runs, the first main-thread hang warning preceded SL3 audio start by 6.4 seconds at 64 frames and 7.3 seconds at 32 frames. The new matched 64-frame run also reported its first warning about 5.1 seconds after launch, before SL3 audio started at 16.6 seconds. The operator could not load the WAV. After Windows responsiveness polling was stopped, Serato still reported a 15.4-second main-thread stall. Serato reported zero callback dropouts at disconnect, and the broker verified normal I/O retirement and device release. The matched 64- and 32-frame packages share the same ASIO, worker and broker binaries. [Lag comparison evidence](evidence/serato-500-lag-comparison-20261108.json)

The exact earlier 64-frame package reproduced the same problem when monitored only through Serato's log. The first main-thread warning arrived 5.1 seconds after launch. SL3 audio started at 12.6 seconds. The operator still could not load the WAV and the longest recorded stall was 12.2 seconds. Serato reported zero callback dropouts when it disconnected, and the broker verified normal USB release again.

At 32 frames, the first main-thread hang warning also arrived 5.1 seconds after launch, before SL3 audio started at 12.4 seconds. The operator still could not load the WAV. Serato reported a 22.8-second stall while the worker was active. The worker later reported output starvation around shutdown and its journal records the redirect-close return. The broker did not verify I/O retirement or USB release, and the journal contains no invalid-input or empty-packet recovery marker. The original Serato files were verified after restore. The stalls prevented an equal-loop comparison, so these runs establish when the lag starts without ranking the buffer sizes for playback responsiveness.

### Earlier install-once build

```text
artifacts/build/native-setup-window-install-once-startup-stop-20261107/build/Release/SL3_Compatibility_Setup.exe
SHA256 bf412432079280204e5defdf285a30d8874c0db171655cb73b81b09339789989
```

This build wraps the reviewed [application-bound startup package](application-bound-broker.md#stop-during-automatic-startup). Its three native entry checks and all 18 window cases passed. A separate check through the compiled entry found the original Serato archive, Serato closed and no temporary driver installed. The kit manifest SHA-256 is `4eb3ac3e1f925dcf46d36609bc31f4b13563f8c1c17aa6df6081f74a4574b196`. The native entry and kit are bound to their local paths. The setup window is ready for the first live install-once test, with a ten-minute diagnostic audio limit. [Test steps](return-to-testing.md#next-attended-test)

The exact rebound package (`ed0b35e9576b9b927acc843f06e570ccaa4af4c569706fbd53cfee02d0f4ff3b`) passed 20 isolated setup and restore checks. The repeat install returned no write steps and preserved the staged archive witnesses. Restore removed the fixture package, and the real registration was unchanged. The fixture used a synthetic archive and private registry keys. Its report SHA-256 is `fd2ba3a4edd5d01405e45a4968e0345e6184a419c20956f42c36f7a6f52cb862`.

The current setup engine and its kit also passed all 27 checks when both were copied to a different folder with spaces and Unicode in the kit path and an empty `PATH`. The engine pinned 760 files, prepared a fresh local record, preserved application-bound activation and verified the original installed state. The test covered read-only preparation and refusal cases. Its report SHA-256 is `fb427fddd7601fcffec14c73f39cdf77ac3aa965df810fe45fa49b0e07e00abc`. A distributable setup window still needs to prepare and reuse the exact local record through its interface. [Relocation test](../scripts/test-on-demand-entry.py)

### Earlier idle-guard build

```text
artifacts/build/native-setup-window-application-idle-guard-20261107/build/Release/SL3_Compatibility_Setup.exe
SHA256 4cdcbbb74ea55a85527ef93e90a74179808ec70a24e8eccbbc846624f39bd23e
```

The setup-only kit is `artifacts/build/sl3-on-demand-kit-application-idle-guard-20261107`. It carries the same application-bound driver with the updated setup check for running controller and worker images. All 27 moved-kit checks and 18 window checks passed. The read-only host check found the original Serato archive, Serato stopped and no temporary native package. This build used the existing window code and had no new visual inspection or privileged actions. Normal Serato startup and physical use of this package still need an attended test. [Current build evidence](evidence/on-demand-idle-guard-20261107.json) · [Application-bound driver evidence](evidence/application-claim-failure-20261107.json)

### Earlier review build

```text
artifacts/build/native-setup-window-release-review-20261106/build/Release/SL3_Compatibility_Setup.exe
SHA256 b0a976b9f2def6a07abda8966c70aa0f865dfac2541dcb98de8806fa5d27ff8e
```

Build metadata binds the exact native entry, setup-only kit, generated experiment and source/header files. The review build is an x64 Windows GUI executable with no CLR or external MSVC runtime imports. Each window build requires the selected kit, its prepared state and the native entry at their bound paths.

`prepare-setup-window.py` creates the bound project; `build-setup-window.ps1` builds and runs the owned-window tests. Preparation on this host generated fresh local compatibility resources from the original Serato installation; no vendor archive or application is published with the source. Final postchecks show original installed resources, no occupied session paths or temporary registration, no action lock and no running SL3/Serato process. The earlier standalone normal-start candidate remains source-current. Actual installation, normal Serato selection, physical output/vinyl and reliable native lifetime remain separate requirements.
