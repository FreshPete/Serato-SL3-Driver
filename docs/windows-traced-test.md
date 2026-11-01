# Traced WinUSB binding — 26 October 2026

**Result: WinUSB started successfully and the read-only probe passed. The earlier startup failure did not reproduce.** This is one successful transport-start observation, not a complete audio driver or a diagnosis of the historical failure.

**Later follow-up:** the subsequent authorized audio-alternate test selected `[0,1,1,0]` and restored it successfully under tracing. [Follow-up result and current next gate](windows-audio-alternates-test.md). The next-gate section below records the plan at the time of this binding-only trial.

The owner authorized one binding test with USB tracing enabled. The same previously approved public development certificate and unchanged signed INF/catalogue were used; their private key remains deleted. Secure Boot and code-integrity policy were unchanged. Temporary machine Root/TrustedPublisher trust, experimental package and project interface registration were removed at the end.

## Observations

| UTC | Observation |
| --- | --- |
| 22:50:04 onward | USBHUB3/UCX/USBXHCI tracing active before binding |
| 22:50:10.888 | Installer recorded the binding request after verifying the live trace session |
| 22:50:11.255 | PnP event 400 configured `oem152.inf` / WINUSB |
| 22:50:11.440 | SL3-correlated hub start and D0 power-completion statuses were zero |
| 22:50:11.442–11.445 | URB function 0 (`SELECT_CONFIGURATION`) completed with USBD status zero |
| 22:50:11.445–11.449 | URB function 1 (`SELECT_INTERFACE`) completed with USBD status zero |
| 22:50:11.451 | PnP event 410 explicitly reported the WinUSB device started |
| 22:50:16.658 | Elevated descriptor/pipe probe initialized WinUSB and opened all four associated interfaces |
| 22:50:50.467 | A second read-only probe queried the active setting: interfaces 0, 1, 2 and 3 were **all at alternate 0** |
| 22:50:51.637 | Hub query confirmed high speed, configuration value 1, normal device/configuration descriptor bytes |
| 22:51:06 | Recording finished; 8,519,680-byte ETL, **22,044 events, zero lost events and buffers** |
| 22:51:07–08 | Targeted cleanup restored `oem136.inf` / `strmdrv`, removed `oem152.inf`, project GUID and both temporary trust entries |
| 22:52:18 | Independent final check confirmed Rane SL3/code 39; no experimental INF, project GUID or temporary certificates remained |

The probe queried alternate descriptors without selecting them. Audio alternates 1 expose isochronous OUT 0x06 and IN 0x82, each 126 bytes per interval. Interface 3 alternate 0 exposes interrupt IN 0x81 and OUT 0x01, each 64 bytes. Neither audio alternate was activated. No interrupt commands, vendor-control requests, pipe reset, audio transfers or firmware operations were sent by our probes.

The later PnP event 411 is **the restored original Rane driver's known code-39 rejection**, with `strmdrv` / `oem136.inf` / `0xC0E90002`. It is not a WinUSB failure. No unplug, full power cycle or restart was needed for cleanup this time. Original device/configuration descriptor bytes still match the initial fixture after cleanup.

## Trace correlation and limits

The SL3's VID/PID identity event supplies the USB device pointer used to select its hub/controller events. Two hundred events correlate to that device; selected start, power and configuration events are exported with timestamps and event indexes, without raw USB payload or kernel pointers. All 21 correlated UCX IRP-completion statuses are zero; the selected hub NTSTATUS and USBD completions are also zero. Constants 0/1 for select-configuration/select-interface were checked against the installed Microsoft SDK `shared/usb.h`.

The xHCI configuration events record configuration 1 / interface 0 / alternate 0 with endpoint-configuration status zero. The independent `WinUsb_GetCurrentAlternateSetting` queries establish the active settings of all four interfaces; descriptor enumeration alone would not establish that.

This trace covers a successful start. It cannot identify the exact failed transaction from the untraced 22:18 attempt. The device was fully power-cycled during recovery from that earlier failure, and tracing/timing differed here. Those are uncontrolled differences, not a demonstrated cure. One success does not establish reliable reconnect/start behaviour.

The earlier hypothesis that audio setting 1 might be required to start the generic transport is **not an unconditional requirement**: this run started with all settings at zero. A replacement KMDF driver is therefore not justified as the immediate next step solely by that hypothesis.

## Preparation and recovery details

Local result directories `winusb-traced-01` and `winusb-traced-02` contain readiness-only aborts: a concurrent manifest read initially caused a file-sharing error; the next launch caught PowerShell 7's timestamp deserialization/culture mismatch. Both occurred before any trust import or binding. The unused first trace definition was removed; the second passive capture finished and cleanup verified no introduced package/trust. Both issues were corrected before the single actual binding attempt in `winusb-traced-03`. Old evidence was preserved.

The installer now supports a fresh result directory and checks that a named trace is live immediately before binding. Cleanup uses that test's own record, including the exact SL3 instance, and can remove the owned GUID even if startup makes the node absent. `test-winusb-traced.ps1` coordinates capture, one installation, descriptor-only probing if started, and cleanup. Its execution requires PowerShell 7, elevation and the existing explicit development-trust authorization.

## Next transport gate

Prepare a bounded WinUSB alternate-setting test: after successful binding and handle initialization, verify all interface identities, select alternate 1 on interface 1 and then interface 2, query the active settings and pipe map, then restore settings and the baseline. Keep tracing active and log each operation/status. Do not submit audio or replay the recovered startup commands in that test. It should stop on the first failure and retain recovery evidence. This has **not** been run yet.

If a future startup fails, preserve its trace and compare against this successful control. Interrupt command semantics and clock/sample representation remain separate work before streaming. Stability, ASIO integration and current Serato's support-state handling remain unproven.

[Sanitized machine-readable evidence](evidence/winusb-traced-binding.json) is regenerated by `scripts/export-traced-winusb-evidence.py`. Raw ETL/XML, transcripts and full state captures remain ignored under `tests/results/local/winusb-traced-03`.
