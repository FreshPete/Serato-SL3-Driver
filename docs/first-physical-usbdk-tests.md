# First physical UsbDk input/output tests — 30 October 2026

The reviewed signed transport now works with the actual SL3 in bounded USB tests on this Windows 11 host. After the owner restarted Windows, descriptor listing, real input capture, silent duplex, an explicit rate change and the 48 kHz follow-up tests all completed successfully. Elevated before/after records confirmed **Secure Boot enabled** for every scenario. No signing enforcement, trust, firmware or installed Serato file was changed.

This establishes physical USB transfer results. It does not establish analogue playback, channel mapping, continuous low-latency operation, an ASIO application session or Serato DVS.

## Observed results

| Scenario | Actual result |
| --- | --- |
| Descriptor-only List | Exactly one high-speed SL3; complete descriptor fixture matches; no redirection. |
| 44.1 kHz input capture | Four requests, 256 successful nonempty packets, 1,411 six-channel frames, 25,398 repacked PCM bytes. No audio OUT. |
| 44.1 kHz silent duplex | Four input and four output requests completed; 25,398 output bytes requested and accepted by the API. Every saved output buffer is zero. |
| Explicit 48 kHz rate selection | Initial getter 44,100; setter followed by fresh getter 48,000. No audio or alternate changes in the rate diagnostic. |
| 48 kHz input capture | Four requests, 256 successful nonempty packets, 1,534 frames, 27,612 repacked PCM bytes. No audio OUT. |
| 48 kHz silent duplex | Four input and four output requests completed; 27,630 output bytes requested and accepted by the API. Every saved output buffer is zero. |

The 44.1 kHz capture contains **125 packets of 90 bytes** and **131 packets of 108 bytes**. The 48 kHz capture contains **9 of 90 bytes**, **240 of 108 bytes** and **7 of 126 bytes**. Thus actual lengths remain authoritative at either rate; a nominal 48 kHz setting is not evidence that every packet is exactly six frames. Both traces are short startup observations. Their planned 256 intervals are not proof of gap-free timing or an oscillator measurement.

For silent duplex, outgoing packet lengths and cumulative offsets were independently checked against the corresponding incoming packet lengths in each of the four pairs. Each direction has 256 packet records with successful statuses and terminal requests. The actual OUT buffer files were checked to contain only zero bytes, separately from the native record's `zero PCM only` label. API completion is not an analogue signal measurement, and returned OUT packet-length fields are not used to claim that measurement.

## Recovery and trace evidence

All six scenario runners report clean native completion, retired buffers, closed redirection where used, completed trace cleanup and matching selected before/after device/security/application state. Each decoded trace reports **zero lost events and zero lost buffers**. Unlike the earlier installation trace, these windows cover their complete native operations. The [sanitized checkpoint](evidence/usbdk-physical-checkpoint-20261030.json) pins the native executable/build, runner inputs, records, snapshots, ETLs and decoded statistics. Raw USB data, PCM and buffers remain local.

At rest, the SL3 returns to the original Rane `strmdrv` / `oem136.inf` binding and code-39 baseline. UsbDk temporarily redirects the exact device for the new user-mode transport; it does not repair the old Rane kernel driver or make the original ASIO DLL operational. A Device Manager warning after cleanup therefore remains consistent with these successful independent USB tests.

The rate diagnostic intentionally changed the hardware to **48 kHz** and verified that readback. Later capture/duplex runs independently read 48 kHz. No automatic rate rollback was attempted. `recoveryConfirmed` refers to the recorded PnP/security/application contract, not restoration of the earlier 44.1 kHz setting.

## Remaining work

The next bridge test should exercise a bounded real continuous worker session, SDK buffers and callbacks with zero output, without installing a COM registration or inventing a measured latency profile. Actual packet variation must continue to drive output layout. Longer operation, controlled analogue signal/loopback, channel ordering, timing measurement, reopening/reconnection and production ASIO deployment remain required before application testing.

The original timer-response comparison remains offline and has no runtime call site. The current Serato descriptor/control/handshake integration is still incomplete; Phase's resource definition does not solve that audio-interface requirement. No current Serato audio or DVS session has run.

Reproduce the read-only checkpoint verification with `.venv/Scripts/python.exe scripts/export-usbdk-physical-checkpoint.py`. It checks the saved real runs and output buffers, not live hardware. The earlier 29/29 Release, 29/29 Debug, 21/21 SDK-free and 42/42 Python results remain software checkpoints; they were not unnecessarily rerun for these hardware-only experiments.
