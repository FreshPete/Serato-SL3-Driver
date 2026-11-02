# Findings

Evidence collected on 26 October 2026. **O** denotes observation, **I** interpretation and **H** untested hypothesis. Addresses below are preferred image virtual addresses, not runtime ASLR addresses.

## Current checkpoint — 1 November 2026

**O:** A [complete combined capture](combined-controls-image-capture.md) passed current-worker normal-token acquisition/getters/release, 44.1 kHz/full table, all 493 live/file state rows, matching USBHUB3 version metadata and selected recovery with Secure Boot enabled. This does not establish current-worker audio or Serato/DVS.

**O:** Explicit enumeration child identities now [map the 97-row post-release context to SL3 port 4](sl3-release-port.md). It enters stopped-enumerated success 47.4256 ms after probe completion and reaches port-disabled/stopped 10.0511163 s after completion. Normal-user cached connection querying also works; its single baseline reports `DeviceConnected` while the original driver node reports code 39.

**O:** The [observer and offline phase comparison](hub-port-observer.md) are implemented/tested, but the attempted live comparison never started: Windows cancelled the administrator launch after observer admission expired. No sample, trace or native device probe ran. The normal role's plan-only executable check precedes admission and does not open the device. The attempt is disarmed and retired.

**O:** Current Serato's [notification-object provenance](serato-notification-object.md) now binds the action-6 receiver to `DeviceNotificationController`, its engine-supplied `NotificationCenter`, and checked base/QML notification slot targets. Five RTTI tables, twenty-five instructions and two fresh complete constructors verify against the unchanged original executable. Callback Boolean values are not assigned licensing or audio-admission meanings; the genuine SL3 descriptor/handshake entry remains unresolved.

**I/H:** These ordinary-user fields have not been shown to distinguish the startup states. No readiness policy follows from software cases or from that cancelled experiment. Historical findings below retain their original scopes.

## F01 Host and connected unit

**O:** Windows 11 Pro 10.0.26300 x64; AMD Ryzen 9 5900X. PnP enumerated `USB\VID_1CC5&PID_0001`, revision 0000, with problem code 28 and no matched driver/service in the queried properties. Installed Serato executable is 5.0.0.1278 and SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`, identical to the extracted installer executable. Full local state: `tests/results/local/windows-before-install.json`.

**I:** This was a driver-absent baseline. The later original-driver test in F09 records the actual load failure. VBS reports running, but SecurityServicesRunning is `[0]`, so HVCI is not reported running. Its registry key is absent. Secure Boot was unavailable to the initial unelevated query; the elevated installation snapshot subsequently confirms it is enabled. Do not equate VBS with memory integrity.

## F02 Real USB topology

**O:** `scripts/usb-descriptors.py` obtained a complete 235-byte configuration through the hub driver without installing a function driver. Device descriptor: `12010002ffffff40c51c0100000001020301`. Configuration 1 has four interfaces. Current configuration was 0 before installation. All interface descriptors advertise class 0xFF.

| Interface | Alternate | Endpoints | Observation |
| --- | --- | --- | --- |
| 0 | 0 | None | Vendor-specific control-like interface |
| 1 | 0 / 1 | None / 0x06 OUT | Alt 1 is isochronous, attributes 0x05, max packet 126, interval 1 |
| 2 | 0 / 1 | None / 0x82 IN | Alt 1 is isochronous, attributes 0x25, max packet 126, interval 1 |
| 3 | 0 | 0x81 IN, 0x01 OUT | Interrupt, 64-byte maximum, interval 1; HID-like descriptor present |

Evidence: [descriptor record](evidence/sl3-descriptors-2026-10-26.json) and `tests/fixtures/sl3-configuration.hex`. These establish descriptors, not actual transfer timing, channel order or sample contents. The vendor-specific class means the current personality does not directly advertise standard USB Audio class binding. Renaming an INF does not establish class-driver compatibility.

## F03 Original Windows package

**O:** Rane's archived official page links Windows 1.3.5f2. The installer is signed by Rane Corporation. Inno extraction contains separate x64 and x86 variants with colliding filenames; using the last extracted copy would silently select x86. The preserved x64 variant is `strmdrv.sys$0` before normalization, SHA-256 `e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5` (36,240 bytes). Its normal filename copy has identical bytes.

**O:** x64 INF `[Manufacturer]` selects `NTAMD64`; the model matches `USB\VID_1CC5&PID_0001`. DriverVer is `06/11/2014,6.0.6001.18000`; the SYS resource says 1.3.5f2. Service `strmdrv` is kernel type 1, demand start 3, binary `%10%\System32\Drivers\strmdrv.sys`. KMDF library version 1.7 and `WdfCoInstaller01007.dll` are specified. The model section does not impose a Windows 10 maximum. Full installer OS gating has not been reconstructed.

**O:** SYS imports `ntoskrnl.exe` and `WDFLDR.SYS`, including `WdfVersionBind`, `WdfVersionUnbind`, MDL mapping, timer/event and allocation APIs. ASIO DLL imports SetupAPI enumeration, `CreateFile`, `DeviceIoControl`, registry and system APIs; its exported API matches Serato 2.5.5's expected names. No replacement transport is justified by the import list alone.

**O:** Normalized x64 CAT and SYS return Authenticode `Valid`. SignTool `/kp /v /c strmdrv.cat` verifies membership of SYS and INF with exit success, but also prints a timestamp trust warning `0x01000040`. Preserve this warning, rather than describing verification as unqualified. A renamed `.cat$0` produced `HashMismatch` in PowerShell; the same bytes named `.cat` verify. That filename-dependent result is a tool limitation, not evidence that the downloaded catalogue was modified. See [signatures](evidence/rane-windows-signatures.json) and the [kernel-policy check](evidence/strmdrv-kernel-signature.txt).

**I, before installation:** The authentic unchanged package was a plausible Windows 11 test candidate. Runtime testing subsequently established a load-policy rejection on this host (F09). Neither INF applicability nor offline signature verification proved that the present boot/security policy would admit it.

**O:** PE INIT section has characteristics `0xe2000020` (write and execute). Other code sections are not writable; SectionAlignment is `0x1000`, subsystem 1 (native). **I:** INIT's flags alone do not prove HVCI failure: Microsoft's FAQ explicitly describes Windows stripping the legacy INIT write flag. Executable pool and MDL mappings still require runtime/code-path review. [Microsoft memory-integrity guidance](https://learn.microsoft.com/en-us/windows-hardware/test/hlk/testref/driver-compatibility-with-device-guard).

## F04 Serato 2.5.5 application interface

Binary: extracted `Serato DJ Pro.exe` 2.5.5.83, SHA-256 `ba8641d0329fe0c955147d2b45f247eeea82ac0f812fe30a339834dbe0c0a503`, image base `0x140000000`.

**O:** Function range `0x14069afd0–0x14069b225` calls `LoadLibraryW` through IAT `0x140b02270`. `GetProcAddress` through IAT `0x140b023b8` resolves, in order, `sl3_open`, `sl3_close`, `sl3_driver_timer`, `sl3_get_usb_port_status`, `sl3_get_audio_controls`, `sl3_set_audio_controls`, `sl3_set_thrustate_callback`. At `0x14069b0e7` it calls the saved `sl3_open` pointer and stores the returned handle at object offset 0x68; the success flag at offset 8 is set only after a non-null result. Failure references the SL3 driver API initialization message at file offset `0x47ba4c0`.

**O:** A separate function at `0x1400866e0` references UTF-16 `RaneAsioSL3.dll`, string VA `0x1447bbe50`, file offset `0x47ba450`. Function `0x14069aef0` references `software\asio\Rane SL 3`. `RaneSL3API` RTTI also exists. Evidence: [instruction references](evidence/serato255-api-references.json); MOV/LEA candidates were bounded using PE unwind entries and disassembled with Capstone. The IAT slot names were independently resolved from the PE import directory.

**O:** Rane's x64 DLL has image base `0x180000000` and exports all seven names. Selected RVAs: `sl3_open` 0x7070, `sl3_close` 0x7080, `sl3_driver_timer` 0x7140, get/set audio controls 0x74f0/0x75f0, USB-port status 0x7cb0 and thru callback 0x7d80. It separately exposes firmware-update exports; none were called. See [DLL report](evidence/rane-asio-x64-pe.json).

**I:** Serato's SL3 integration involves proprietary control exports in addition to ordinary ASIO registration. An arbitrary audio endpoint or generic ASIO wrapper does not supply this interface. The API's argument structures, stream ABI, device registration and DVS connection remain to be traced.

## F05 Current Serato

Binary: 5.0.0.1278, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`, image base `0x140000000`.

**O:** Same ASCII/UTF-16 scan finds no Rane SL3 DLL name, SL3 control exports or `RaneSL3API` RTTI. It does find `kDiscontinuedDevice` and notification resource identifiers. Function range `0x14137b790–0x14137c928` references `failed cast for kDiscontinuedDevice` at instruction `0x14137bab1`. [Evidence](evidence/serato500-discontinued-reference.json).

**I:** There is an explicit discontinued-device path and a substantial change in visible SL3 integration symbols. F11 confirms its runtime UI; F14 now traces the support-state mechanism statically. Whether an equivalent current stream/control implementation remains available is unresolved. No authentication mechanism or sufficient one-byte fix has been established.

**O:** Official Serato support says SL boxes are unsupported from 2.5.6 onward. This is a vendor support statement, separate from our binary findings. [Serato announcement](https://the-drop.serato.com/announcements/important-information-about-discontinued-hardware/).

## F06 Mac package

**O:** Package identifier `com.rane.pkg.Sl3`, version 2.0.1f2; distribution checks minimum OS 10.11 and requests restart. It includes `Sl3Driver.10.9.kext`, `Sl3Api.framework`, an x64 settings helper and preference pane. Kext is x86_64 only; framework has x86_64 and i386 slices, no ARM64. Its IOKit personality matches VID 7365 / PID 1 and `IOUSBHostDevice`. Dependencies include IOAudioFamily, IOUSBFamily, IOUSBHostFamily and kernel IOKit/libkern/mach KPIs. [Mach-O report](evidence/rane-mac-macho.json).

**I:** This is a legacy kernel-extension/Core Audio architecture, not AudioDriverKit. It cannot load natively on Apple Silicon. Intel Tahoe loading and deployment remain untested. Package and Mach-O signatures have not been verified with Apple's tools on a Mac; a XAR signature structure is not a verification result.

## F07 Independent Linux research

Reviewed `nvgeele/snd-rane-sl3` commit `01099892261b55ec5ee814292d840eeb664c1904`. Its root licence is GPL-3.0 and source headers say GPL-3.0. No code was copied into our implementation. Consult the exact licence and kernel-module distribution requirements before any reuse.

**O:** This unit's descriptor IDs, interface numbers and endpoint addresses agree with constants in that source. Its description of an HID control interface needs qualification: the descriptor class is vendor-specific 0xFF despite a HID-like descriptor and interrupt endpoints. Standard HID binding must not be assumed.

**H:** Commands 0x03/0x31/0x32/0x33/0x36, routing IDs, rate encoding, channel order, implicit feedback and recovery semantics are research leads. Source comments claiming prior captures/assembly do not constitute independently available evidence. No captures accompanied the reviewed checkout, and we have not reproduced its streaming result. [Repository](https://github.com/nvgeele/snd-rane-sl3).

## F08 Tools and limits

REA 6.8.0, Ghidra 12.1.4, Temurin JDK 21.0.9 and Node 24.22.1 installed locally. Ghidra provider prerequisite checks pass; other providers/client registration are absent and unnecessary for this CLI workflow. The DLL inventory completed with 11,676 procedures. Initial Serato import exceeded REA's 330-second startup budget; diagnostic retained under `analysis/rea255-overview.json`. A retry with the recommended increased budget completed the API-loader decompilation. Evidence [ev_b4ce215d…](evidence/rea255-api-init.json) confirms F04's calls; [ev_3ba827b1…](evidence/rea-asio-open.json) shows DLL `sl3_open` forwarding to `FUN_180009ee0(1)` after logging and initialization wrappers. The inferred four-parameter decompiler prototype is not a verified ABI. Standalone PE inspection continued during the timeout. REA Windows P0 supports native PE EXE/DLL inspection, not arbitrary Mach-O/kernel-driver workflows; standalone readers cover those artifacts.

## F09 Actual Windows installation and rejection

**O:** The owner explicitly authorized proceeding on this Windows 11 host without rollback preparation. The original signed installer ran interactively, reported x64 administrative setup and installed its components. Log exit 0 at 21:13 UTC. The old bootstrapper reports Windows 6.2.9200 through its legacy OS-version API; the independent host query is Windows 11 build 26300. That log value is not the actual host OS.

**O:** SL3 now binds `oem136.inf`, class MEDIA, service `strmdrv`, but reports problem 39. Installed SYS flat SHA-256 is `e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5`, exactly the extracted original. The installer requests restart and delays DLL registration; ASIO registration is not yet present in the queried key. No automatic reboot occurred.

**O:** Correlated event 3077 blocks that exact SYS under **Microsoft Windows Cross Certificates for Code Integrity Exceptions Policy**, GUID `{8f9cb695-5d48-48d6-a329-7202b44607e3}`, reported policy version `10.29611.0.0`, status `0xc0e90002`. Related 3089 names Rane Corporation / GlobalSign CodeSigning CA - G2 and reports VerificationError 21. Audit event 3076 is from a separate audit policy and does not negate the enforced rejection. Event 3004 also appears. [Event fields](evidence/code-integrity-driver-fields.json), [messages](evidence/code-integrity-driver-events.json), [test summary](evidence/windows-original-test.json).

**I:** This establishes current load-policy rejection rather than an installer version gate or demonstrated audio-engine incompatibility. Microsoft documents removing default cross-signed kernel-driver trust starting April 2026. Its event documentation defines error 21 as failure to pass App Control policy. Offline Authenticode/catalogue checks use a different trust context and were insufficient to predict admission. [Current policy guidance](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/design/custom-kernel-signers), [event interpretation](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/operations/appcontrol-debugging-and-troubleshooting).

**H:** A suitable current Microsoft-signed transport/package may address loading without rewriting the audio engine. None has been located yet. Modifying driver bytes or the INF invalidates catalogue coverage; a local test signature does not meet the release goal. Security policy was not weakened.

**O:** Subsequent elevated read-only checks exported the verified `oem136.inf` package. All four files (INF, CAT, SYS and KMDF coinstaller) exactly match the extracted originals. SignTool verifies exported SYS catalogue membership with the same timestamp warning. Elevated CiTool enumerates the event's cross-certificate policy as signed, authorized and enforced, version `10.29611.0.0`; its policy options do not include audit mode. [Exported hashes](evidence/exported-driver.json), [catalogue check](evidence/exported-driver-kernel-signature.txt), [selected policy metadata](evidence/ci-cross-certificate-policies.json).

## F10 Narrow comparison and current identification

**O:** Owner-provided 2.5.6 installer verifies as Serato Limited; MSI version 2.5.6.1001. Its main executable SHA-256 is `3b04472cd5597fd56266e1c2c86dc298431b0026001aefe4b43aa3b909ee35c5`. It retains the SL3 DLL-name reference, registry helper and seven-export loader. Corresponding ranges: DLL-name initializer `0x1400870c0–0x1400870ed`, registry helper `0x14069d820–0x14069d8fe`, API loader `0x14069d900–0x14069db55`. [References](evidence/serato256-api-references.json).

**I:** Official loss of support at 2.5.6 does not mean all SL3 code was physically deleted in that release. Remaining code does not prove runtime selection or DVS operation. Device registration and capability selection are the next comparison targets.

**O:** In current 5.0.0, function `0x140503a40` constructs an inline eight-byte name at `0x14050446d`: immediate `0x334c5320656e6152` decodes as `Rane SL3`. The following record stores VID 0x1CC5 at `0x14050449b` and PID 1 at `0x1405044a5`. Function `0x1405033d0` calls it at `0x140503568`. This inline string is missed by a contiguous data-string scan. [Assembly](evidence/serato500-rane-identification-assembly.json).

**I:** Current Serato still contains explicit SL3 identification data. That is distinct from retained streaming/control/DVS implementation. The relationship between this record and `kDiscontinuedDevice` is not yet established by a complete call graph; no arbitrary list modification is justified.

**O:** A standalone Ghidra 12.1.4 import with auto-analysis disabled decompiled these selected ranges. The constructor's vtables at `0x142808488` and `0x1428084c8` resolve through PE RTTI to `PrimaryDeviceManager`. This constructor invokes the identity-population routine conditionally on its fourth argument. The latter builds device records and passes them to `FUN_1405d02e0`, then queries `FUN_140502ae0` before adding them to an object vector. Further decoding confirms that query is a shared-pointer null test, not a capability check. F14 traces the descriptor's support-state mechanism. [Focused output and coverage limitations](evidence/serato500-focused.json).

## F11 Current application runtime

**O:** Launched the installed, hash-matched Serato 5.0.0.1278 on this host with SL3 still connected and the kernel driver reporting code 39. The application displayed a panel titled **Rane SL3 Discontinued**, explaining that the hardware is no longer supported and offering the last supported version. The owner dismissed the optional startup/sign-in overlay during observation; no account sign-in, licensing purchase, firmware control or audio playback was performed by the agent. [Full-window screenshot](evidence/serato500-sl3-discontinued.png).

**I:** Current Serato recognizes this physical device's identity despite the unusable original driver. The discontinuation message is an independently observed application-level obstacle. This does not prove how the event is produced internally or establish that restoring a driver and suppressing a message would recover the absent/disabled stream and DVS path. No application patch has been made.

## F12 Post-reboot validation

**O:** Owner restarted; Windows reports last boot 26 October 2026 at 21:33:15 UTC. Collected state at 21:35:11 UTC. Both x64 and x86 Rane ASIO registry entries now exist, with their COM registrations pointing to present `raneasiosl3.dll` files in System32 and SysWOW64 respectively. The unit remains class MEDIA, bound to `oem136.inf` / `strmdrv`, problem 39. New boot-time events 3077 at 21:33:29 and 21:33:30 reject the driver under the same policy `{8f9cb695-5d48-48d6-a329-7202b44607e3}`. HVCI is still not reported running; this unelevated capture cannot independently re-query Secure Boot. [Summary](evidence/after-reboot-summary.json), [post-boot event fields](evidence/after-reboot-code-integrity.json).

**I:** Deferred ASIO registration completed, but reboot did not resolve the enforced kernel-signing rejection. Audio streaming and DVS remain untested. Repeating the unchanged installation or another reboot has no demonstrated benefit.

## F13 Trust routes and WinUSB binding assessment

**O:** Microsoft's current Windows Driver Policy documentation names our exact enforced GUID and explicitly states there is no individual-driver exception. Its normal publisher route is WHCP certification. Custom kernel signers require a policy rooted in Secure Boot PK/KEK trust. No such provisioning or security change was performed. No suitable signed SL3 revision was found in the reviewed vendor sources or the two Update Catalog searches. [Decision and sources](driver-trust.md).

**O:** Read-only SetupAPI enumeration finds the signed inbox WinUSB driver node. The owner reports the Have Disk attempt rejected its generic INF as incompatible. PnP remains bound to the original Rane driver with code 39. The project WinUSB probe finds zero registered matching interfaces and performs no device I/O. An original SL3-specific INF passes Inf2Cat signability for `10_GE_X64` with no errors/warnings, using isolated Microsoft WDK NuGet 10.0.28000.2526. Its catalogue is generated but unsigned; it has not been installed. [Assessment](evidence/winusb-binding-assessment.json), [preflight](evidence/inbox-winusb-preflight.json), [build result](evidence/winusb-package-build.json).

**I:** WinUSB remains a transport candidate, not a completed trust repair or audio implementation. A trusted kernel binary and an applicable installation package are separate requirements.

## F14 Current discontinued-device mechanism

**O:** `0x1405d02e0` creates a generic RTTI-identified `ControllerDescriptor`, assigns identity fields and sets `supported_apps` values to 2 for `Serato DJ` and `Serato DJ Lite`. `DeviceAggregationThread`'s worker `0x1421db390` queries this map, branches on value 2 at `0x1421db822`, and queues action 0x0E. RTTI-identified `DispatchDeviceDeferredAction::Execute` (`0x1421de890`) invokes observer slot +0x70 for this action. `DeviceManager`'s matching observer table maps that slot to `0x14213f290`, scheduling `0x14213f330`. This callback emits UserIO message 4. The notification handler's case 4 calls `0x14137d800`, constructing the named discontinued-device dialog. [Full static path and limits](serato-discontinued-path.md).

**I:** A product-support state deliberately directs the SL3 descriptor toward the observed discontinuation UI. The map and concrete callback chain provide substantially more evidence than an identity-string scan. This is static reconstruction, not a captured debugger trace, and does not prove that changing the state recovers audio/control or DVS.

## F15 Approved WinUSB development trial and recovery

**O:** The owner reported no signing access and explicitly approved a seven-day local test certificate in machine Root and TrustedPublisher stores. Windows accepted the project's signed INF/catalogue as `oem152.inf` and selected `WINUSB`; Authenticode became Valid. Secure Boot was true before and after. Kernel-PnP event 411 then reported code 10, status `0xC000009E` (`STATUS_DEVICE_POWER_FAILURE`). The unit disappeared and the port reported USB descriptor request failure. The probe found no interface and never reached WinUSB initialization. [Test record and limits](windows-development-test.md).

**O:** One USB reconnect did not recover enumeration. After removing the experimental package and trust entries, the owner fully disconnected USB and external power and reconnected. Rane SL3 returned with `oem136.inf` / `strmdrv`, code 39. Device and configuration descriptors exactly match the first capture. Final elevated state confirms Secure Boot true; the temporary signing identity/private key was also removed. [Verified final state](evidence/winusb-development-final-state.json).

**I:** Development INF package trust can be satisfied while retaining Secure Boot and CI enforcement on this host. Generic WinUSB startup is a separate demonstrated failure. Its reported power status does not establish the underlying electrical or protocol cause, and this trial does not establish physical compatibility, audio or DVS.

## F16 Original kernel configuration sequence

**O:** Embedded bind information in the original SYS identifies KMDF 1.7.6001, 387 function entries at `0x16220`. Selected table indices agree across acquired WDK 1.15 and 1.35 headers. The prepare-hardware path `0x19880 → 0x19b18 → 0x19c48` builds explicit interface/setting pairs and calls `WdfUsbTargetDeviceSelectConfig`. In the captured four-interface personality it selects settings `[0,1,1,0]` for interface numbers `[0,1,2,3]`, then obtains pipes and prepares an interrupt reader. [Startup analysis and mapped calls](usb-startup.md).

**H:** The original driver's explicit configuration/control ordering may matter to the WinUSB failure. No failing WinUSB request trace has been captured, so this is a comparison target rather than a proven fix. No alternate-setting or vendor-command replay was performed.

## F17 Original power callbacks and next startup test

**O:** Callback-pointer registration instructions establish D0 entry `0x1968c`, D0 exit `0x197e0`, prepare hardware `0x19880` and release hardware `0x19990`. After setting-pair configuration, normal D0 entry resets the audio pipes, allocates requests, sends interrupt command 0x03 and checks for a response before starting the configured status reader. It then conditionally starts that reader and sends 0x36 with first payload byte 1. A requested 44100/48000 rate gates commands 0x31/0x30. Frames are 64 bytes: command, literal bytes `1C C5 00 01`, then 59 payload bytes. These facts are statically recovered; the startup commands have not been replayed. [Sequence, evidence and limits](usb-startup.md).

**I:** The first failed WinUSB request must be captured before assigning a cause to the final power-failure status. User-mode initialization changes cannot repair a failure that precedes an openable interface. A passive USB ETW collector and explicit experiment/decision specification are prepared; no new binding or temporary trust import was performed. An explicit-pair KMDF transport is a conditional candidate, with a separate kernel-signing requirement. [Next-test specification](usb-startup-next-test.md).

**O:** A five-second elevated passive smoke capture recorded 5,215 events with zero lost events/buffers; built-in tracing tools decoded all three USB providers. One system-metadata schema mismatch was handled with relaxed XML. The unique trace collector was deleted and SL3 remained on its original code-39 baseline. No failure reproduction was attempted. [Smoke evidence](evidence/usb-startup-trace-smoke.json).

## F18 Traced binding succeeds with all audio alternates idle

**O:** The owner authorized the traced binding test. One actual installation attempt with the unchanged development package succeeded: PnP event 410 names WINUSB/oem152.inf, problem code 0, and two read-only probes initialized WinUSB and queried all four interfaces. `WinUsb_GetCurrentAlternateSetting` returned 0 for each interface. Hub query confirmed high speed/configuration 1 and original descriptor bytes. SL3-correlated hub events show select-configuration and select-interface completions with USBD status zero. The 60-second trace contains 22,044 events, zero lost events/buffers. [Test report](windows-traced-test.md), [sanitized evidence](evidence/winusb-traced-binding.json).

**O:** Cleanup restored oem136.inf/strmdrv and its prior code-39 rejection, removed the experimental INF, project GUID and both temporary certificate trust entries. Secure Boot remained enabled; no power cycle or firmware/control/audio operation was required. Two preceding readiness-only aborts occurred before any trust/binding changes and their evidence is retained.

**I:** The historical power-start failure is not reproduced or diagnosed by this successful trace. Original audio alternate 1 selection is not an unconditional prerequisite for WinUSB startup. The next gate is a bounded WinUSB alternate-selection test before any transport rewrite; reliability, device commands, streaming, ASIO and current Serato integration remain unvalidated.

## F19 WinUSB selects and restores both audio alternates

**O:** One authorized traced activation test started WinUSB and selected alternate 1 on interface 1 then 2. Readback confirmed `[0,1,1,0]` and isochronous OUT 0x06 / IN 0x82 with 126 bytes per interval. It held for two seconds, then restored interfaces 2 and 1, verifying `[0,0,0,0]`. All four API calls, corresponding xHCI configuration statuses and hub USBD completions succeeded. The trace has 37,990 events, zero lost events/buffers and no correlated SL3 isochronous or bulk/interrupt dispatch events. [Report](windows-audio-alternates-test.md), [evidence](evidence/winusb-audio-alternates.json).

**O:** Targeted cleanup restored original Rane/code 39 and removed the development INF, project GUID and temporary trust entries; Secure Boot remained enabled and no power cycle was needed. Device/configuration descriptors still match the original fixture. Three fault-injection recovery checks and all six project tests pass. No audio, device-command replay, reset or firmware operation was performed.

**I:** Inbox WinUSB supports the original driver’s audio alternate topology on this host in this one trial. This supports continued user-mode transport work but does not validate clocking, sample format, scheduling, stable streaming, ASIO or Serato/DVS. Status/clock/sample-contract recovery is the next gate.

## F20 Clock getter, control framing and packed sample contract

**O:** Original kernel rate setup sends 0x31 then reads/verifies 0x30. One traced getter-only experiment sent exactly one 64-byte 0x30 frame and received prefix `30 1C C5 00 01 AC 44`, reporting **44100 Hz**. Only two payload bytes are consumed by the original rate reader; the unused 57-byte reply tail is not interpreted. The trace has 21,382 events/no losses and no correlated ISO dispatch; cleanup restored original driver/trust/security state. [Physical evidence](evidence/winusb-clock-query.json).

**O:** Original ASIO declares six input/output channels, sample type 17 (packed Int24LSB), and one Internal clock source. Kernel input conversion independently walks six 3-byte values per 18-byte frame. Newly recovered notification parser checks distinct tags `00 00 00 01/02/03` for commands 0x34/38/39. Audio-control exports link to 0x32 get/22-byte result and 0x33 indexed setter. [Contract and original-code evidence](clock-control-audio.md).

**O/I:** Original input completions drive OUT packet offsets and lengths from actual received IN lengths. Documented WinUSB write APIs do not expose a per-packet descriptor argument and describe maximum-packet packetization. Matching that original playback contract remains unproved; no OUT audio write was attempted. Capture-first testing is specified separately. Physical channel order, converter valid-bit alignment, clock accuracy, streaming, ASIO and Serato/DVS remain unvalidated.

## F21 Native IN-only diagnostic builds; hardware capture still pending

**O:** New original C++ source implements strict packet decoding and a finite capture transaction with cancellation/draining ownership. The Windows adapter validates the device/configuration/speed/pipe fixture, reads the rate using 0x30, selects audio alternates, schedules four 8 ms IN requests, records packet results and restores settings. It includes a 20-second process watchdog and fail-stop behaviour if pending memory cannot be retired safely. It contains no audio OUT, firmware or driver-installation path. [Implementation and source links](native-capture.md).

**O:** Release and Debug MSVC x64 builds pass with warnings treated as errors. The expanded suite now passes six CTest entries per configuration: packet/lifecycle fault cases, playback layouts, and plan-only/conflicting-mode checks for both Windows adapters. The existing 12 Python tests pass. With the original `strmdrv`/code-39 baseline confirmed, the native device gate rejects opening before any capture submission: submitted/completed requests are zero. The traced runner's capture mode checks executable/source hashes against this build. [Build and negative-gate evidence](evidence/native-capture-build.json).

**I:** This is an implemented, build-verified diagnostic, not a demonstrated audio transport. Native WinUSB scheduling, packet data, continuity, separate buffer registrations and cancellation on this hardware still need the prepared traced test. No new UAC/binding/trust operation was initiated while the owner is away. Full playback, ASIO, Serato/DVS and Mac scope remain open.

## F22 UsbDk capture adapter built; live backend validation pending

**O:** An original adapter pins helper/service-image hashes, validates full SL3 descriptors, uses bounded capture/completion ownership, and reports ASAP continuity as unverified. Six native tests pass in Release/Debug. Read-only preflight verifies the Microsoft signature and finds no installed UsbDk service; a negative invocation rejects with error 1060 and zero capture submissions before helper load. No new driver, DLL execution, redirection or streaming was attempted. [Adapter and evidence](native-usbdk.md).

**I:** This is concrete implementation progress toward a transport with variable packet support, not evidence of working playback/ASIO/Serato or of live UsbDk loading under host policy. A separate owner-present system-filter installation and recovery gate remains necessary.

## F23 Current supported-device and ASIO host requirements narrowed

**O:** The current SL3 stub leaves MIDI/API/device-name strings empty and explicitly defaults legacy PortAudio to true. A support-1 prediction still expects one MIDI aggregation component. Readiness helper 0x1421DAD00 obtains a separate DriverAPI object: its generic detection check returns true for an empty registry key, or tests HKLM key access otherwise. No SL3-specific branch exists in that factory's seven Rane product matches. Those queries are not ControllerDescriptor audio capabilities or proof of Windows driver admission.

**O:** Validated RTTI and focused code locate the generic ASIO backend, HKLM ASIO/CLSID/description lookup, device-name/CLSID creation and an initial buffer/start/stop probe. Machine code confirms the setup buffer helper calls IASIO createBuffers. A further bridge/descriptor route must be implemented; no current Serato patch, rebuilt ASIO registration or streaming result is claimed. [Contract and reproducible evidence](serato-supported-contract.md).

## F24 Fixed-block audio core and host processing window implemented

**O:** Original native code now bridges variable six-channel frames and packet layouts to stable selected-channel double buffers. It consumes the offered host bank at the next switch, allowing deferred processing, and maintains bounded queues, explicit faults and restart accounting. Seven native tests pass in Release/Debug, including synthetic 44.1/48 kHz streams over all proposed block sizes, deferred/partial writes, channel mapping and zero observed C++ new allocations on successful stream paths. [Implementation and evidence](audio-bridge.md).

**I:** This is the data-flow core for future ASIO/session integration. It owns no USB I/O or thread, uses host observation times rather than measured sample timestamps, and is not an installed ASIO DLL or proof of real capture/playback. Transport deadlines, broker/lifecycle integration, actual latency and current-Serato routing remain open.

## F25 SDK buffer ABI and lifecycle implemented; runtime driver still pending

**O:** An optional original static component uses pinned official ASIO headers and real SDK buffer/callback structures, preserves deferred-host timing and maps create/start/stop/disposal failures. Eight native tests pass in Release/Debug, including atomic allocation-failure handling after a Debug-construction fix. A separate SDK-free build passes seven tests and changed SDK headers are rejected. No SDK implementation is redistributed, and no IASIO/COM device, registration, USB streaming or Serato patch was created. [Component and evidence](asio-buffer-component.md).

**I:** This advances the API-facing buffer layer. Live session availability, cross-thread ownership, hardware clock/latency, transport and full IASIO/COM lifecycle remain necessary before a host can use it.

## F26 Bounded duplex ownership and native silent-output mode prepared

**O:** New core/native code prepares both directions before I/O, stages zero-only OUT from validated completed IN packet lengths, and cancels/drains all pending directions before release. Fault tests cover input/output failures, retained requests and shared deadlines. Ten native tests pass with SDK support in Release/Debug, and preflight remains read-only. The real duplex command was not invoked. [Implementation and evidence](bounded-duplex.md).

**I:** This prepares a finite transport experiment without proving hardware output, clock/timing, analogue mapping or continuous ASIO/COM integration. Windows OUT packet length results are not used as proof of transmitted bytes; requested sizes and statuses are distinct.

## F27 ASIO COM ABI and unavailable-state lifecycle implemented

**O:** An original, distinct-identity x64 DLL now exposes the official IASIO vtable and COM class-factory/unload functions. Direct DLL tests call all ASIO slots and cover canonical identity, refcounts, server locks surviving factory release, unknown/null/aggregation errors and 1,600 concurrent lifetime cycles. Eleven native tests pass in Release/Debug; SDK-free tests and a changed-IASIO-header rejection also pass. The DLL is unregistered, performs no USB access and explicitly fails device initialization. [Implementation and evidence](asio-com-server.md).

**I:** This establishes a real host ABI/lifetime boundary, not a live ASIO driver. The existing buffers still require an isolated continuous transport/session with verified availability, clock, latency and safe callback retirement. Current Serato admission and DVS routing remain separate open requirements.

## F28 Explicit audio-field gate and legacy/newer backend selector recovered

**O:** `ControllerDescriptor` audio slot +0xC0 checks four Windows/Mac API/name string lengths. Selector `0x1421B8B80` uses default OS connection creation when all are empty; only explicit audio fields enter VID/PID or name selection with the legacy flag. Concrete RTTI/constructor evidence identifies the retained `PortAudioConnectionFactory`. The legacy name selector uses imported `strstr` and retains the last match; API forwarding omitted by the decompiler is present in machine code. The exporter checks the exact original executable, getter/parser offsets, interfaces, branches and ABI/import evidence. The installed app remains unchanged. [Contract and bounded evidence](serato-audio-routing.md).

**I:** A supported-app edit or true legacy flag alone would still not define a working SL3 audio connection. A unique explicit ASIO device name/API and deliberate backend choice form a concrete candidate for later integration; no supported external descriptor override, physical stream, Serato admission, licensing result or DVS mapping is established.

## F29 Windows worker-process lifetime boundary implemented

**O:** Original control-thread code now pins a private executable's bytes, creates it suspended without inherited handles, assigns a private kill-on-close job and resumes it. Real-process tests cover exact arguments/Unicode paths, file pinning, malformed-image rejection, normal/259 exit codes, live timeout, targeted descendant termination, surviving unrelated jobs, owner destruction and abrupt owner-process death. Scoped thread error mode prevents launch error UI from blocking malformed-image handling and is restored afterward. Twelve native tests pass in Release/Debug; ten pass without SDK support. No fixture remains alive, and read-only preflight still shows UsbDk absent/no helper/audio submission. [Component and build evidence](worker-process.md).

**I:** This supplies the process boundary for containing future stuck USB work without terminating an audio host. It is not yet an IPC/audio worker and proves no physical USB/callback retirement, clock, latency, ASIO streaming or Serato result. Nonzero Windows job accounting remains conservatively incomplete even after root process exit.

## F30 Bounded cross-process message ownership implemented

**O:** A new per-user named mapping/event channel carries bounded binary messages with one outstanding request, fixed wire layout, fresh identities, ordered ownership and retained expected-peer handle checks. Real-process tests cover 100 exact binary round trips, invalid/stale request/reply fields, wrong worker identity, peer exit, timeout, late response after closure and host destruction while a peer mapping remains valid. Thirteen native tests pass in Release/Debug; eleven pass without SDK support. No worker fixture remains alive. [Component and build evidence](worker-mailbox.md).

**I:** This adds actual host/worker framing while keeping USB and user-host buffer pointers out of the wire. It allocates/copies/waits and is not a real-time audio queue or a device/session dispatcher. Continuous transport, callback retirement, ASIO availability, hardware clock/audio and Serato/DVS integration are still missing.

## F31 Typed finite-input worker implemented; hardware branch unrun

**O:** The actual native diagnostic now handles a strict capability handshake, descriptor probe, finite-input capture and quit over IPC. Its input implementation reuses the real bounded backend, validates full-width packet results, excludes padding and publishes a compact maximum-32,544-byte reply only after successful transfer/alternate/redirection API cleanup. Fifteen native tests pass in Release/Debug; thirteen pass without SDK support. Actual executable handshake/order/error/final-reply tests pass, and an explicit missing-service test returns Win32 1060 before helper load. No worker process remains alive. [Protocol and evidence](typed-worker.md).

**I:** This connects diagnostic commands to a real isolated worker without equating its handshake with device/stream readiness. The hardware capture branch has not executed. Repeated finite batches are not a continuous stream, and physical clock/audio, output scheduling, callback retirement, ASIO and current Serato/DVS remain unverified.

## F32 Fixed shared input/output queues implemented

**O:** Shared transport version 2 adds separate eight-slot data queues with actual packet frame counts and bounded PCM copies. Single-producer/consumer ownership, full-queue retry, logical position/rate/time faults, data events and unsigned counter wrap are implemented. Sixteen native tests pass in Release/Debug; fourteen pass without SDK support. Synthetic real-process tests check every actual PCM byte over 2,000 round trips. A 1,000-pair local run observes zero C++ `new` allocations. No worker remains alive and preflight remains read-only with UsbDk absent. [Queue contract and evidence](shared-audio-queues.md).

**I:** This supplies a data-plane component for the continuous session; it is not yet a USB streaming loop, callback lease owner or working ASIO driver. Synthetic times/rates do not establish hardware clock, latency or continuity. Concurrent close can overlap in-flight calls; the future session owner must retire callers before disposal.

## F33 Host queue/SDK callback path implemented

**O:** A new fixed-storage single-owner adapter decodes shared input PCM into the SDK buffer component, invokes host callbacks and renders output with the original packet schedule. Full output retains the exact pending block before any later input/callback processing. First local failures latch; callback lifecycle reentry and same-object restart are rejected. Seventeen native tests pass in Release/Debug and fourteen pass without the SDK. Full-path tests check every PCM byte over 2,400 synthetic process blocks per configuration, plus extrema/all logical channels, exact startup delay, backpressure, stop/discard, closed/wrong-role/rate/callback faults and zero observed C++ allocations in 1,000 successful local blocks. [Implementation and evidence](queue-to-asio.md).

**I:** This connects the internal SDK callback path to a real cross-process data plane without enabling the ASIO COM DLL. A 64-interval batch can bunch callbacks for small host banks; suitable continuous transfer granularity and real timing need validation. No live USB/session owner, worker I/O retirement, physical input/output, ASIO availability, Serato/DVS or Mac result is proven.

## F34 Short-transfer software path implemented

**O:** Shared transport version 3 adds a checked active packet count for 8–64 intervals in complete high-speed USB frames; zero inactive counts and exact actual PCM sizes are required. The SDK adapter processes/renders only active packets. Seventeen tests pass in Release/Debug and fourteen without the SDK, including count/tail/version rejection, unchanged caller output on faults, mixed-count real-process queue flow and 7,200 complete SDK-path process blocks per configuration. Eight-interval steps invoke at most one minimum-bank callback; mixed-batch local measurement still observes zero C++ allocations. [Contract and evidence](audio-transfer-granularity.md).

**I:** This removes the fixed eight-millisecond batch shape from the future continuous path. It does not prove that callbacks are paced in time: successive steps can drain a backlog in a burst. Native request rearming, pipeline scheduling, session supervision and physical timing/audio remain necessary. The finite native diagnostic and unavailable-state COM DLL are not promoted to live streaming.

## F35 Continuous request lifecycle core implemented

**O:** `ContinuousStream` now rearms individual input slots, preserves ordered actual-packet publication, validates output schedules, imposes request/peer deadlines and drains all pending directions under one deadline. Completion observation failure remains distinct from terminal error, partial failed startup can remain draining, and exact unproved/release-failed leases are retained. Eighteen native tests pass in Release/Debug and fifteen without the SDK, including 18,000 fake input/output batches, zero observed successful-path C++ allocations and fault/cleanup injection. [Implementation and evidence](continuous-engine.md).

**I:** This supplies an actual continuing state machine rather than repeated finite captures, but its test backend performs no USB I/O. Stable native overlapped request rearming, shared-queue peer, typed session/watchdog ownership, callback retirement and physical continuity must still be connected/validated. The ASIO COM DLL remains unavailable and no current Serato/DVS or Mac result is claimed.

## F36 Native continuous adapter and queue peer implemented

**O:** A fixed-storage UsbDk/Windows backend now implements actual request layout, event/overlapped reset, stable rearming, packed variable-length output, full-width results, conservative completion/cancellation ownership and worker-only fail-stop destruction. The production queue peer connects it to both actual shared data queues. Nineteen native tests pass in Release/Debug and sixteen without the SDK, including 8,000 input batches/7,984 output submissions under simulated helper/completion calls, zero observed successful-path C++ allocations and four isolated exit-70 cleanup cases. [Implementation and evidence](native-continuous-adapter.md).

**I:** The adapter's real Windows event/clock path is exercised, but helper I/O is simulated. No helper is loaded, driver installed or USB/audio transfer submitted. Typed continuous commands, a heartbeat/session owner, callback retirement and physical timing/control/audio remain necessary before ASIO availability or Serato/DVS restoration can be claimed.

## F37 Continuous worker lifecycle and heartbeat implemented

**O:** A production `--stream-worker` mode now connects typed commands, exact helper/device/rate gates, native request engine, shared queues and a renewable watchdog. Stop replies wait for I/O/device release; partially failed starts can remain draining; retained cleanup contains only the isolated worker. Twenty-one native tests pass in Release/Debug and eighteen without the SDK, including simulated real-process lifecycle/data/fault cases and actual absent-helper rejection. A healthy heartbeat survives 21,547 ms and exits zero with an empty job. Combined waiting exposed an auto-reset command-event lost wake; publication-aware receive and consumed/stale-edge regression tests now pass. [Implementation and evidence](continuous-worker.md).

**I:** Positive native hardware startup/streaming is still unrun. Internal running/cleanup states are not physical audio, clock, recovery-readback or ASIO-callback retirement proof. The host session owner, usable clock/control contract, physical timing/audio and current Serato/DVS/macOS requirements remain necessary; the ASIO COM DLL remains unavailable/unregistered.

## F38 Host audio-thread/callback lifetime implemented

**O:** `AudioOwner` and `BufferLease` now own SDK data processing on a dedicated CRT thread, gate callback leases and retain buffers/channel/process/code through timeout/destruction. A real thread-exit observer releases acquisition and schedules DLL release after its final callback returns. Twenty-two native tests pass in Release/Debug and eighteen without the SDK, including exact logical-channel input, stable planes over fresh sessions, zero observed steady EXE-linked C++ allocations, worker/callback faults, blocked-callback stop and actual DLL retain/unload. Opposite-endpoint space wakes unblock full-queue producers without new PCM. [Implementation and evidence](asio-audio-owner.md).

**I:** This proves a host-side lifetime component under simulated I/O, independently of worker cleanup. It does not yet supply the production control coordinator, clock discovery/selection, complete IASIO availability or physical audio/Serato/DVS/Mac validation. The normal ASIO COM DLL remains unavailable and unregistered.

## F39 Host control and temporary clock inspection implemented

**O:** A typed version-2 clock query now performs the bounded native getter through a temporary device handle without activating audio. `HostSession` verifies worker kind/hash, retires inspection workers, rechecks the observed rate before each fresh start, arms SDK audio ownership before worker submission and tracks both cleanup domains independently. Twenty-three native tests pass in Release/Debug and eighteen without the SDK. Tests include rate-change rejection/re-inspection, repeated stable planes, blocked callbacks, control-owner destruction, callback faults, kind/hash rejection, partial/stalled startup and real native absent-helper rejection. A Windows process/job accounting race found by these tests is fixed. [Contract and evidence](host-session.md).

**I:** This connects host and worker software lifecycle components under simulated I/O; it does not certify native runtime admission, physical audio/timing/control, current Serato/DVS or macOS. The production COM DLL still fails initialization and remains unregistered. A usable host-facing facade and physical capture-first verification remain necessary.

## F40 ASIO facade and actual vtable sessions implemented

**O:** `DriverFacade` now maps initialization, buffers, observed rate, clock/channel metadata, latency input, current-bank position and start/stop to the host coordinator. A separate unregistered DLL runs the same COM server through real IASIO callbacks and repeat sessions using simulated I/O. Twenty-five native tests pass in Release/Debug and eighteen without the SDK. Export checks keep the test provider out of production. [Implementation and evidence](asio-driver-facade.md).

**I:** ASIO latency must include device/transport delays. One input bank plus one output bank accounts for the tested two-bank software round trip; it does not measure physical extra delays. The new timing profile is supplied explicitly and synthetic in tests. Production configuration/provider wiring, physical driver/audio/timing validation and current Serato/DVS/Mac remain necessary. The production DLL stays unavailable and unregistered.

## F41 Production native ASIO configuration/provider implemented

**O:** The production COM DLL now loads strict adjacent worker/helper/timing configuration and delegates to the native facade. Read leases pin reviewed files; profiles bind one rate, bank size and native pipeline. Twenty-six native tests pass in Release/Debug and eighteen without the SDK, including actual production DLL config consumption and rejection of a truthfully simulated worker, retained file leases, changed/malformed/non-local evidence rejection and bound-mode facade checks. [Implementation and evidence](asio-native-configuration.md).

**I:** The parser verifies consistency, not measurement truth or physical compatibility. Synthetic records are test inputs only. No production timing record/configuration or registration is installed, so current production initialization still fails. Positive native runtime/audio/timing, deployment/host, current Serato/DVS and Mac validation remain required.

## F42 Current Serato DVS descriptor/manager/calibration contract recovered

**O:** Descriptor parsing maps DVS names to integers 0/1/2/3 at +0x464. RTTI-validated `CDVSPluginManager` has a predicate that rejects null/kind-zero descriptors and tests additional manager state for hybrid/requires-auth cases. The calibration field at +0x318 feeds a typed DVS decoder's software setter, whose actual imported `powf` and constants yield `10^((gain+4)/20)`. Separate endpoint collections/maps and `hw_src`/`hw_dest` schema remain. The original/installed PE is unchanged, and the evidence exporter validates binary identity, RTTI, instructions and report ranges. [Full contract and limits](serato-dvs-contract.md).

**I:** The previously recovered zeroed identity-only discontinued stub is predicted to retain DVS kind zero unless another component changes it. If reached unchanged, this is an additional failed DVS condition; current support handling can block earlier. Neither a support/dialog edit nor arbitrary ASIO registration establishes DVS. Descriptor injection, correct physical stereo/deck mapping, legitimate product/account connection and physical DVS validation remain open. No bypass or application change was made.

## F43 Tahoe route and read-only target preflight prepared

**O:** Original Mac archive/Mach-O/plist identities are revalidated. Official Apple documentation exposes app-level IOUSBHost and USBDriverKit isochronous APIs; device capture explicitly terminates drivers and resets on release. AudioDriverKit/HAL and entitlement boundaries are documented. A read-only collector now projects exact SL3 registry/services, host model/architecture/translation, legacy signature/loaded status and security queries. Seven new synthetic collector tests and all 27 Python tests pass; only plan mode ran on Windows. [Route and evidence](macos-tahoe-route.md).

**I:** App-level USB plus isolated HAL or AudioDriverKit/USBDriverKit are candidates, not proven Tahoe implementations. Normal interface access, service-interval semantics, timebase/clock, signing/entitlements, Mac model/OCLP and physical transport/Core Audio/Serato DVS remain open. Intel-only legacy code is not an Apple Silicon route; Intel Tahoe legacy admission is also untested. No security reduction, driver action or Mac runtime result is claimed.

## F44 Current Serato descriptor resource dispatch recovered

**O:** Device registration lists `resource:` folders, then the descriptor factory's type/product-ID parser reads through the resource manager. Both text/listing managers stop at the first matching provider. The QRC factory constructs a base manager that maps `userio` to `userio_resources.bin` and appends that archive reader before QRC. RTTI/vtable slots, literal bytes, append/dispatch instructions and original/installed PE hashes are checked by the evidence exporter. QRC has an optional filesystem text fallback, but its listing uses colon-prefixed Qt paths. [Full trace and evidence](serato-resource-loading.md).

**I:** A loose `Data/userio/audio/SL3.xml` file is not established as a registration route. Earlier archive selection and non-merging enumeration constrain that candidate; runtime provider changes and full root initialization remain untraced. Original descriptor content, duplicate identity precedence and a legitimate current integration boundary still need investigation. No archive/configuration/application/account/driver changes or physical audio/DVS result occurred.

## F45 Original SL3 descriptor and historical registration membership recovered

**O:** Pinned 2.5.5 and 2.5.6 PEs contain the same 2,968-byte embedded SL3 resource, IDs 203 and 207 respectively, with identical decoded XML. Both resource IDs appear in the arrays consumed by their startup parser loops. An original offline Blowfish reader passes three published vectors in both directions per PE, verifies tables/calls/ranges and projects original fields: USB/driver-API handshake, ASIO/CoreAudio “SL 3”, HZ48000/alignment 48, three decks, DVS yes, no MIDI, and Deck3/Deck1/Deck2 endpoint order. [Recovery, hashes and evidence](serato-legacy-sl3-descriptor.md).

**I:** A simple deletion of SL3 descriptor/registration data in 2.5.6 is ruled out; runtime connection and official support are separate. The declared 48 kHz profile differs from the last 44.1 kHz physical getter and exposes unfinished rate-control work. Alignment units, endpoint consumer/physical mapping, current integration and legitimate handshake/account behavior still need verification. No vendor code, application, driver or physical audio operation ran.

## F46 Current handshake map and rate/alignment consumers recovered

**O:** Historical DRIVER_API maps to 5; the complete recovered current map has no such name and maps 5 to AKAI. Its parser defaults unmatched names to zero/NONE. The current audio interface returns optional recognized rates and converts latency milliseconds/rate Hz into frames, adding the default one-ms overhead below five ms and aligning on the legacy branch. The original ASIO buffer getter reports min=max=preferred with granularity 1. A verifier checks three exact images, enum/parser stores, slots/leaf extent, arithmetic constants, floating-point ABI and original buffer outputs. [Evidence and limits](serato-clock-handshake.md).

**I:** Neither copying historical XML/numeric enums nor using the unmatched fallback implements the original SL3 handshake. Application alignment and ASIO bank size are separate contracts; host-backend adaptation must be established before changing bank rules. Rate/control adaptation, current descriptor integration and physical timing/audio/DVS remain unverified. No fallback/check was patched, no production profile installed and no device operation sent.

## F47 Original device exchange and bounded control codec implemented

**O:** The original Rane API's eight-byte challenge goes through `sl3_driver_timer`, IOCTL 0x220010/get selector 0x44 and kernel interrupt command 0x37, returning eight bytes. Actual Serato assembly compares that reply with a transformed challenge. A fixed-storage C++ codec now constructs known getters and strictly parses defined replies/notifications within four received frames; the native rate getter uses it. Release/Debug pass all 27 tests and SDK-free passes all 19. Source/binary/log hashes and the original static chain are verified. Historical one-byte control slices at indices 14/20/8 are also recorded. [Implementation and evidence](native-control-frames.md).

**I:** The codec does not verify/emulate a device response or expose new hardware queries. Getter/notification byte tests do not establish acceptance, timing, routing, physical controls, native PCM or current Serato/DVS. A traced real exchange and legitimate application integration remain open. No hardware command, firmware/security change or control write occurred.

## F48 Current ASIO backend retries preferred banks and adapts user/host sizes

**O:** The pinned current executable's retained PortAudio ASIO opener retries the driver's preferred size after a failed requested-bank creation. It passes original user frames and selected host frames separately to a buffer processor whose callback path supports adaptation. Our actual unregistered IASIO test DLL rejects 240, then accepts preferred 128 and completes two fresh callback sessions. A bound-profile test rejects 64/240 before accepting 128. Both native configurations pass 27/27 tests; exact instruction and build evidence verification passes. [Path and evidence](serato-bank-adaptation.md).

**I:** Alignment 48 does not alone justify expanding our ASIO bank constraints. Production rules stay tied to a measured timing profile. This static path and simulated-worker retry do not establish physical timing/audio, a descriptor override, legitimate handshake integration or current Serato/DVS success. No vendor code or device operation ran.

## F49 Offline rate-selection transaction implemented

**O:** Exact original kernel instructions verify target restrictions, 0x31 big-endian setter, opaque two-byte acknowledgement and fresh 0x30 readback comparison. A new original state machine implements a bounded inspect/no-op-or-set/verify sequence, rejects malformed exchanges and retains possible write effects on failure. It has no native/ASIO/IPC caller. All 28 native tests pass in Release/Debug and all 20 SDK-free tests pass; source/log/binary identity verification passes. [Implementation and evidence](rate-selection.md).

**I:** This supplies transaction logic for later explicit rate testing, not physical selection or safe streaming reconfiguration. The caller still needs exclusive idle ownership, a total deadline and I/O retirement. Production remains observed-rate-only; no device write, rollback, firmware/security change or audio/DVS success occurred.

## F50 Explicit bounded native rate diagnostic prepared

**O:** An injected runner now enforces an overall control deadline and per-transfer limits, with failure/short/cancel tests at all fifteen maximum operations. A separate native CLI mode takes a fresh redirect and uses existing retained transfer/cancel/drain handling without activating audio. It saves progress before each transfer and preserves possible effects after failure. Release/Debug pass 28/28, SDK-free 20/20; both real executables reject thirteen invalid argument cases and confirmed service absence stops valid mode before helper load or device access. [Contract and evidence](rate-selection.md).

**I:** The explicit diagnostic is prepared, not physically validated. Its real pending-transfer handling, rate selection, cleanup and tracing still need supervised tests; the traced wrapper does not yet expose this mode. Streaming/ASIO remain getter-only, with no automatic rate change or rollback. No device command, security change, native audio or current Serato/DVS result occurred.

## F51 Supervised rate-trace workflow and evidence checks prepared

**O:** The traced wrapper now requires an explicit rate target and same-build validated input capture, retains uncertain effects on failed/timed-out children, and validates successful native reports before recording a known result. New read-only checks reject failed/inconsistent native state, wrong readback/counts, trace loss/identity/window mismatch, altered files and changed selected recovery contracts. All 36 Python tests pass, including nine new synthetic/plan tests; existing native source/build/binary hashes remain current. [Workflow and evidence](rate-selection.md).

**I:** Plan/synthetic success does not prove live orchestration, pending native I/O, USB command correlation, clock/audio or application integration. Unchanged driver/security snapshots do not imply restoration of the earlier rate. No live wrapper, physical rate write, automatic rollback or current Serato/DVS test ran.

## F52 Current numeric descriptor precedence recovered

**O:** RTTI identifies `PrimaryDeviceManager`; registration appends resource descriptors before identity-only discontinued stubs and its immediate predicate only checks null. Numeric lookup reads VID/PID/`bcd_device`, returns the first exact match, otherwise selects the highest older revision with later equal ties winning. Virtual-base/slot arithmetic verifies the revision getter. The wrapper has an earlier name-match branch; a separate caller passes revision zero explicitly. Exact original/installed PE, instruction and focused-range verification passes. [Contract and evidence](serato-descriptor-precedence.md).

**I:** Registration order alone does not settle selection: exact and fallback cases differ, and callers may not forward a physical revision. No external provider, descriptor injection, legitimate handshake integration or current audio/DVS result is established. Provider/root and actual connection input tracing remain next; no application/archive/account/driver/USB identity changed.

## F53 Module-derived resource-root default recovered

**O:** Path-state initialization obtains its own module path through verified `GetModuleHandleExW`/`GetModuleFileNameW` imports, initializes subsequent components to `.`, and the root builder joins the module-directory result with component `+0x20`. Exact original/installed PE, import, argument/default-store and focused-report verification passes. The filesystem helper is conservatively described as validation; a directory-only predicate was not proved. [Trace and evidence](serato-resource-loading.md#module-derived-root-default).

**I:** Default root behavior does not establish a `Data` override or loose descriptor discovery, and earlier archive/QRC constraints remain. Later mutations, alternate provider configuration and the relevant real connection caller are not exhaustively recovered. No vendor code, registry/shell path, application modification or device operation ran; current audio/DVS integration remains unverified.

## F54 Later Windows transport and software checkpoints

**O:** The archived retained native run passed two one-second 44.1 kHz silent streams with buffer recreation: 339/344 callbacks, 980/994 successful OUT completions, independent retirement and a loss-free 58,075-event trace with Secure Boot/recovery checks. The current read-only controls extension, actual unregistered COM object-recreation audits and optional shared USB/WPP trace have software coverage; fresh full suites pass 39/39 Release, 39/39 Debug and 80/80 Python. A 30 October read-only host observation reports the original SL3 failed-load resting binding, UsbDk Running and no SL3 test process. [Evidence-bound return checkpoint](evidence/return-report-20261030.json), [physical limits](retained-physical-test.md), [current report](RETURN-REPORT.md).

**I:** Silent transport and simulated object recreation do not establish analogue correctness, safe physical reacquisition, deployed ASIO, measured timing or current Serato/DVS. The controls query and WPP emission/decoding remain physical gates. Historical observations above remain scoped to their original checkpoints.

## F55 Published primary-device requirements checked

**O:** Serato's current Windows compatibility/discontinued tables recommend Windows 10/DJ Pro 2.5.5 for SL3. Its Phase page requires compatible hardware plus DVS licensing; WIR documentation retains the DVS-supported-hardware requirement. The external-soundcard article describes OS-selected master output and still requires compatible hardware. [Direct sources and local integration analysis](current-serato-integration-decision.md).

**I:** Phase HID and master-output routing are not documented substitutes for admitting the rebuilt SL3 as primary DVS hardware. No supported generic-ASIO primary-device registration mechanism was identified in the reviewed material. That is an unresolved boundary, not an exhaustive impossibility proof. No account entitlement was inspected, no vendor message sent and no purchase, application/account, firmware or security change made.


## F56 Finite callback PCM collection prepared in software

**O:** [The input recording diagnostic](input-record-probe.md) preserves 132,352 nominal 44.1 kHz frames or 144,000 nominal 48 kHz frames in complete 128-frame banks, with all six packed channels and explicit trailing-callback counts. Separate-process simulation matches every expected byte at both rates and exports an unchanged WAV payload; the existing marker analyser correctly rejects that synthetic input as a route. Release/Debug pass 64/64 each, SDK-free 39/39; nine evidence tests pass. The current USB worker, ASIO DLL and broker diagnostic bytes remain unchanged. No physical capture, nonzero output, registration, new binding/security change or timing profile ran. [Exact source/build/test evidence](evidence/input-record-20261102.json).

**I:** Longer known-input data can now be collected through a specific diagnostic implementation rather than only planned. The actual native recording still requires its own traced/guarded attended workflow and recovery. Logical sample positions and software timestamps supply no independent ADC/DAC origin, so the file offset is not measured latency. Physical levels/channel mapping, packet continuity, stable reopening, protected deployment and current Serato/two-deck DVS remain unfinished.
