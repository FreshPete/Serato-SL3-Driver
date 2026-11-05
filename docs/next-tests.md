# Next tests

Current queue updated 4 November 2026. Sections T01 onward retain the original experiments. See the [return report](RETURN-REPORT.md) and [requirement audit](completion-audit.md) for the Windows and current Serato work still open.

1. The [traced host callback loopback](driver-timer-diagnostic.md#successful-attended-callback-retest) passed with SL3 OUT 1/2 connected to IN 3/4 set to LINE. Both channels returned at an offset of 596 frames, with a complete trace and clean device release.
2. Measure directional latency for the production profile against a common analogue and callback reference. Use a shared or calibrated clock to place an electrical input edge and its callback delivery on the same timeline, then do the same for callback output commitment and the electrical output edge. The callback and standalone worker round trips used different paths. Keep the 596- and 340-frame observations as separate cross-checks.
3. Validate the deployed ASIO path with the approved timing profile, then check all three stereo pairs, control/through behavior, sustained audio and bounded recovery. The successful restart used one retained redirect. The [second acquisition stall](usbdk-detachment.md) remains open.
4. Validate [current Serato admission](current-serato-integration-decision.md) for the genuine device, then test two-deck DVS with a physical signal and motion. The captured Phase signal establishes input capture on the tested pair. Current account entitlement remains uninspected.

macOS remains deferred until the Windows path works.

## T01 Original Windows driver — completed before reboot

Host Windows 11 Pro x64 build 26300; Secure Boot true; HVCI not reported running. Owner authorized testing without rollback preparation. Used original signed Rane 1.3.5f2 installer; no security settings or firmware operations changed.

Observed installer exit 0, binding to `oem136.inf`, service `strmdrv`, then PnP code 39. Installer requested restart and deferred DLL registration until next logon; no automatic reboot performed. Code Integrity 3077 enforced the cross-certificate exceptions policy against the exact x64 SYS hash. This test proves install/bind success and an initial policy-level load failure; it says nothing about audio performance.

Local records: `tests/results/local/before-original-driver.json`, `after-original-driver.json`, `rane-original-install.log`, `rane-original-exit.json`. Sanitized evidence is in `docs/evidence/windows-original-test.json` and the correlated Code Integrity JSON files.

## T02 Requested reboot and state capture — completed

Owner restarted on 26 October 2026; last boot was 21:33:15 UTC. The post-reboot collector confirms both x64 and x86 ASIO entries and their COM server paths, with the DLLs present. SL3 still binds `oem136.inf` / `strmdrv` and reports problem 39. New boot-time 3077 events at 21:33:29 and 21:33:30 enforce the same cross-certificate policy. Restart therefore completed registration but did not resolve kernel loading. See `docs/evidence/after-reboot-summary.json` and `after-reboot-code-integrity.json`. No further restart or repeated installation is justified by this result.

For future state captures after an identified component changes:

Equipment: this Windows 11 host, SL3 and its present USB cable. No decks required. Leave security settings unchanged. Run from the project:

```powershell
./scripts/collect-windows-state.ps1 -Output tests/results/local/after-reboot.json
```

Run elevated if possible to read Secure Boot and policy metadata. Expected observations after a changed component: PnP/CI state, installed INF/service identity, ASIO registration and installed app/driver versions. A normal PnP state would justify an audio/control test; continued policy rejection sends work to signing/transport options. Deferred registration is already complete.

## T03 Signing-policy diagnosis — initial checks completed

Completed elevated `CiTool -lp -json` and export of the verified Rane package `oem136.inf`. Exported INF, CAT, SYS and KMDF coinstaller all exactly match the extracted originals. SignTool verifies exported SYS catalogue membership, with the same timestamp trust warning `0x01000040`. The policy named in event 3077 is present, signed, authorized and enforced; the separate audit policy includes `Enabled:Audit Mode`. Evidence: `docs/evidence/exported-driver.json`, `exported-driver-kernel-signature.txt` and `ci-cross-certificate-policies.json`.

Correlated 3077 and 3089 by activity ID; the audit-only 3076 event does not establish successful loading. VerificationError 21 is an App Control policy failure, not proof of a corrupt download. Next investigate a current Microsoft signing route or an inbox transport against the actual required USB operations. No disable-policy or test-signing changes are part of this test.

## T04 Historical and current registration analysis

No hardware change needed. Compare these exact Windows executables:

- 2.5.5.83, loader `0x14069afd0`, registry helper `0x14069aef0`.
- 2.5.6.1001, loader `0x14069d900`, registry helper `0x14069d820`.
- 5.0.0.1278, Rane identity construction in `0x140503a40`; SL3 name immediate at `0x14050446d`, VID/PID writes at `0x14050449b` / `0x1405044a5`.

Establish incoming callers, device-record layout and dispatch to current events/capabilities. The 2.5.6 loader's presence disproves a blanket claim that it was removed exactly at the official support boundary. Determine what actually changes there. Expected output is a small cited call graph, not a speculative patch.

Completed initial 5.0.0 runtime observation: it displays “Rane SL3 Discontinued” for this connected unit while the original driver is blocked. The screenshot is saved under `docs/evidence/serato500-sl3-discontinued.png`. No need to repeat that observation until an identified component changes.

Completed current static support-state path: see `serato-discontinued-path.md`. Next inspect `0x1421db390`'s support-1 branch and the required descriptor/audio-driver capabilities. Recover the original SL3 registration selection in 2.5.5/2.5.6 independently. Do not patch value 2 merely to remove a notification.

## T05 Independent audio — conditional on successful driver load

Equipment: SL3, low-level line source, suitable line-level loopback leads, ASIO host capable of simultaneous six-channel capture/playback. Use line inputs where appropriate; do not feed a line source into phono-level inputs.

Identify each channel and L/R order; test all six inputs/outputs together, sample formats, 44.1/48 kHz where actually exposed, USB/analogue routes, source switches, stop/start and reconnect. Capture firmware version only through an established read-only getter. Record sample rate/buffer settings, expected vs observed channel map and errors. Do not invoke firmware-update exports or controls. If loading is blocked, there is no useful audio result to claim.

## T06 Current Serato and DVS — conditional on working transport/integration

Use installed 5.0.0.1278 after proving the required application interface. Connect two decks, Serato control media, mixer and appropriate RCA/ground wiring. Record exact recognition/error text, opened device/API path, calibration, forward/reverse, scratching, pitch, start/stop and needle drops. Measure loopback latency separately, set a numerical acceptance target, then complete the plan's four-hour stability and ten-cycle recovery tests.

## T07 WinUSB package and transport — trial failed at startup; baseline restored

Explicit owner approval permitted the temporary local certificate trust import. Windows accepted the package as `oem152.inf`; WinUSB then failed startup with code 10 / `STATUS_DEVICE_POWER_FAILURE` and the device disappeared before probing. One USB reconnect did not recover it. Package/trust cleanup followed by full USB/external-power removal recovered the original descriptors and Rane/code-39 baseline. The signing key was removed too. See `windows-development-test.md`. Do not repeat the unchanged package.

The generic inbox-INF selection was rejected on this host, and the project interface is absent. Do not repeat Have Disk attempts with that same file. The original Rane binding remains installed. `scripts/build-winusb-package.ps1` generates an unsigned package under `artifacts/build/sl3winusb`; Inf2Cat `10_GE_X64` passes with no errors/warnings. This is not a signature, InfVerif/HLK pass or hardware result.

The unsigned build remains under `artifacts/build/sl3winusb`; the development-signed copy and public certificate remain as evidence under `artifacts/build/sl3winusb-development`. Their former local trust has been removed. The next hardware attempt requires an evidence-supported startup change and an appropriate signing/binding arrangement. No certificate purchase or signing submission is authorized by these instructions. See `driver-trust.md` for release signing and `usb-startup.md` for the identified startup sequence.

After that prerequisite is met, keep the SL3 connected and run:

```powershell
python scripts/probe-winusb.py tests/results/local/winusb-probe.json
```

Expected: one opened project interface, four associated USB interfaces, alternate descriptors and pipe metadata matching the physical fixture. The current run returns `initialized: false`, zero matching interfaces, exit 1 and performs no device I/O. The successful-query path is prepared but untested. Do not issue vendor requests or stream audio merely because enumeration passes; first establish the exact control requests and sample/clock semantics.

## T08 Original startup comparison — static recovery completed

The original kernel's `0x19c48` explicitly selects settings `[0,1,1,0]` for interfaces `[0,1,2,3]` using KMDF setting pairs. Registration assembly confirms prepare/D0-entry/D0-exit/release callbacks. Normal D0 entry resets audio IN then OUT, allocates requests, attempts interrupt command 0x03 before starting the continuous reader, conditionally starts that reader and sends 0x36 with payload byte 1, then conditionally sets/verifies a requested 44.1/48 kHz rate. These are interrupt frames, not EP0 vendor requests. Command meanings and the successful bus sequence remain unvalidated. See `usb-startup.md` and its reproducible 15-function binary/header evidence.

## T09 Startup capture and transport decision — completed, startup succeeded

The owner authorized one traced binding attempt. Following two readiness-only aborts with no trust/binding changes, the actual attempt started WinUSB successfully and passed descriptor/pipe/current-setting queries. Interfaces `[0,1,2,3]` were all active at alternate 0. Correlated select-configuration and select-interface requests completed successfully. The 60-second trace contains 22,044 events with no events/buffers lost. Cleanup restored Rane/code 39, removed the experimental package/GUID/trust, and retained Secure Boot. No power cycle was needed. See `windows-traced-test.md`; the historical failure remains unexplained.

## T10 Bounded WinUSB audio-alternate selection — passed once

Owner authorized activation under tracing. WinUSB started, interface 1 then 2 switched to alternate 1, active `[0,1,1,0]` and expected isochronous pipes were verified, and interfaces 2 then 1 returned to zero. All four API calls and corresponding USB configuration completions succeeded. Trace: 37,990 events, zero events/buffers lost. Cleanup restored original Rane/code 39 and removed package/GUID/trust; Secure Boot remained true, no power cycle required. No audio or interrupt transfers, vendor commands, resets or firmware operations were sent. See `windows-audio-alternates-test.md` and evidence.

## T11 Status, clock and sample contract — initial recovery and getter test completed

Original kernel/ASIO recovery establishes six packed 24-bit little-endian containers, distinct notification tags, rate setter/getter sequencing, one declared Internal ASIO clock source and input-length-driven output packet scheduling. One traced 0x30 getter returned **44,100 Hz**; no rate setter, 0x36, route or audio command was sent. Trace: 21,382 events, no losses. Cleanup/security are verified. See `clock-control-audio.md`. Physical jack mapping, converter valid bits, clock lock/drift and status-enable semantics remain unmeasured.

## T12 Bounded IN-only capture and playback transport feasibility — next work

Implement the capture-first specification in `clock-control-audio.md`, with packet-stride/result validation and safe cancellation/draining before memory release. Audio has not been transferred yet. Playback is a separate feasibility gate: the original driver sets variable per-packet offsets from IN lengths, while documented WinUSB write APIs packetize by endpoint maximum and expose no packet-descriptor input array. Resolve this gap before attempting OUT or promising full-duplex ASIO. Do not pad to maximum packet size or replay unidentified commands.

Implementation is now built and tested offline: see `native-capture.md`. Release/Debug native core cases pass; the executable defaults to plan-only mode and the missing-WinUSB gate returns zero submissions. `test-winusb-traced.ps1 -CaptureAudio` is prepared with tested-build hash checks, one bounded IN-only transaction and existing cleanup. Physical capture, native API scheduling/cancellation and live packet results remain untested; no UAC prompt was raised while the owner is away.

## Removal and recovery

The original Rane package has a vendor uninstaller under `C:\Program Files\Rane\SL 3` and an installed-app entry. Prefer that for full ASIO/control-panel removal. Confirm the current installation and package name before changing it. If driver-store cleanup is separately needed, first verify `oem136.inf` is still this exact Rane package; only then consider `pnputil /delete-driver oem136.inf /uninstall` from an elevated terminal. Do not remove similarly named packages or shared KMDF components indiscriminately. The original Rane package has not been removed; the experimental WinUSB package was removed after its failed trial.

## First Mac target collection (after scheduling the Mac work)

Confirm Mac model, hardware architecture, exact Tahoe build and OCLP status. Connect SL3 for that test and, from the repository on the Mac, run `python3 scripts/preflight-macos.py --collect --output tests/results/macos-first-preflight.json` using a fresh destination. Return the JSON plus OCLP status. This opens no USB client, changes no driver/security setting and submits no audio. Permission failures remain unknown; signature checks are separate from admission. See [route, prerequisites and subsequent descriptor-only gate](macos-tahoe-route.md).

## Current Serato resource-boundary comparison (offline)

The [resource trace](serato-resource-loading.md) establishes first-matching-reader dispatch and the `userio` archive's precedence over QRC. Its filesystem text fallback does not prove that loose files are listed or selected. The [original SL3 descriptor](serato-legacy-sl3-descriptor.md) is now recovered from both 2.5.5/2.5.6, with identical XML and verified startup registration-array membership. Next compare current resources and trace duplicate identity precedence and complete root/provider initialization. Trace the original driver-API handshake, 48 kHz selection and buffer-alignment consumer before adapting the current facade. Expected evidence: exact identities, fields, consumer units and matching/selection call sites. Do not install speculative XML, repack application archives or change product/account state to test an unestablished route.

The [clock/handshake trace](serato-clock-handshake.md) now establishes latency alignment in application frames and a separate original fixed ASIO bank contract. It also establishes that current enum initialization lacks DRIVER_API; historical kind 5 now means AKAI. Next trace the original driver-API consumer and rate selection, plus the retained backend's application-buffer/ASIO-bank adaptation. Do not use an unmatched handshake fallback or another kind as a substitute for legitimate integration, and do not change bank constraints solely from the alignment value.

The [original driver-timer exchange](native-control-frames.md) is now traced to interrupt command 0x37 and an eight-byte real-device reply comparison. A bounded native codec is tested, with only the existing rate getter connected at runtime. A later explicit traced exchange must use a fresh recorded challenge, preserve transfer storage through cancellation/draining and record only the defined reply bytes; round-trip completion alone is not proof of verification. No such mode is exposed yet. Keep the first live transport experiment capture-first and do not add this command as an automatic recovery action. Control-table indices 14/20/8 remain evidence for later physical mapping, with no native writes enabled.

The [bank adaptation trace](serato-bank-adaptation.md) resolves the backend-size question above: the current ASIO opener retries driver preferred frames and passes separate user/host counts to an adapting processor. The actual unregistered DLL passes rejected 240 → preferred 128 retry and repeated sessions with a simulated worker. Retain measured-profile production bank constraints. Next resolve rate selection and the legitimate current descriptor/handshake boundary; eventual application testing must measure adaptation delay and recovery as well as native timing.

The [rate transaction, diagnostic and trace workflow](rate-selection.md) now implement inspect, optional setter and mandatory fresh readback with bounded replies, a total control budget and uncertainty-preserving failures. The wrapper requires an explicit target and prior same-build capture; synthetic evidence and plan tests pass. No live wrapper or physical setter has run. After descriptor-only/capture prerequisites, schedule an owner-present traced rate test and inspect actual USB payload correlation and pending-I/O retirement. Keep it separate from automatic startup/recovery and the first capture-only experiment; unchanged driver/security state does not prove restoration of the old rate.

The [numeric descriptor precedence](serato-descriptor-precedence.md) is now verified: resource descriptors precede stubs, first exact revision wins, while equal older fallbacks favor later entries. An earlier name matcher and callers explicitly passing revision zero prevent a universal physical-selection claim. Next trace the relevant real connection caller and complete provider/root configuration; do not install a speculative descriptor or change USB identity to force selection.

The [resource-root default](serato-resource-loading.md#module-derived-root-default) is now traced through its own module-path query and `.` component initialization. Do not assume a `Data` override. The next resource question is any supported provider configuration beyond that default; prior archive selection and QRC listing still constrain discovery. Keep runtime validation and exhaustive later-mutation claims separate from this static result.
