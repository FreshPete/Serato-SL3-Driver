# Implementation sequence and decisions

Current checkpoint updated 1 November 2026; earlier decision history follows below. The owner's request supersedes the supplied plan's mandatory Windows 10 baseline. No Windows 10 VM is required, and macOS is now deferred until Windows works. The [requirement audit](completion-audit.md) distinguishes implemented code, archived hardware proof and remaining work.

## Current architecture and unresolved decision

The development implementation uses reviewed signed UsbDk with an isolated user-mode worker, bounded capture/output queues and an original COM/ASIO facade. It preserves one redirect across ordinary stop/start and buffer recreation; final owner release is separate. Archived bounded silent transport passed with a different worker. The current worker now passed a complete normal-user control acquisition/release, while current-worker streaming and successive COM-object lifetimes remain unverified physically. No measured timing profile or production registration/configuration is installed. [Current report and evidence](RETURN-REPORT.md).

The [one-approval combined capture](combined-controls-image-capture.md) proved normal-user controls, complete retained state events and same-window driver-version metadata. The [release context is mapped to the SL3 port](sl3-release-port.md). Next compare ordinary-user port/devnode observations across its startup timeout before choosing readiness or changing owner lifetime. The first phase-observer attempt was cancelled before trace/device access and is permanently consumed. Kernel handoff/reacquisition, analogue routing/latency, normal-user streaming and sustained/recovery testing remain. A watchdog is containment, not proof that blocked kernel work immediately retires.

Current Serato's admitted SL3 connection remains an independent unresolved interface. [Published requirements and local evidence](current-serato-integration-decision.md) do not establish that a rebuilt ASIO driver, Phase or external master routing supplies it. Continue identifying an interoperable registration/descriptor/control path while preserving real device identity and legitimate account/product behaviour. No archive/executable or account modification is selected by this checkpoint. A generic audio-driver milestone will not replace the requested current-Serato/two-deck-DVS end state.

## Completed first milestone work

Environment inspected; Git initialized; supplied plan read including tables and reference relationships. Original Rane Windows and Mac packages acquired and statically extracted. Serato 2.5.5, 2.5.6 and 5.0.0 Windows installers extracted, hashed and signature checked. A real SL3 descriptor fixture was collected. Original Windows package installed interactively; actual load rejection and correlated Code Integrity events retained. REA/Ghidra confirmed the legacy API-loader path. See findings and artifact inventory for exact identities and limits.

## Selected next architecture decision

The original Rane package is installed, but its kernel component is **blocked on this host's current policy**. This establishes a signing-policy obstacle, not defective USB streaming code. There is no evidence yet that its audio engine needs rewriting.

The first approved development trial established package acceptance but generic WinUSB startup failure: code 10 / `STATUS_DEVICE_POWER_FAILURE`, followed by descriptor failure. It was fully rolled back and the original identity/descriptors recovered. The original kernel's explicit interface/setting selection, power callback order and interrupt framing are now statically decoded. A passive USB ETW capture/decoding smoke test and subsequent traced binding have completed. See [first trial and recovery](windows-development-test.md), [startup evidence](usb-startup.md) and [traced experiment specification/result](usb-startup-next-test.md).

**Traced follow-up:** one later authorized binding with the same package started successfully; PnP event 410, read-only queries and an all-zero active-alternate snapshot establish that basic WinUSB startup can work. The trace has 22,044 events and no losses. The original failure was not reproduced or diagnosed. Targeted cleanup restored the original baseline. Test bounded WinUSB alternate selection next; defer a new KMDF transport unless a specific WinUSB limitation is demonstrated. [Actual result](windows-traced-test.md).

**Audio-alternate follow-up:** the authorized next test selected interface 1/2 alternate 1, verified `[0,1,1,0]` and the expected isochronous pipes, then restored both to zero. USB events independently confirm all four operations; 37,990 events/no losses. Cleanup and security state are verified. Investigate the status/clock/sample contract before data transfers; the inbox route remains viable for further work. [Actual result](windows-audio-alternates-test.md).

**Clock/control follow-up:** the 0x30 getter reports 44,100 Hz. Original kernel/ASIO analysis establishes packed 24-bit little-endian containers and distinct notification framing. Capture-first work can proceed, but full-duplex playback needs a transport feasibility check: the original variable packet-offset schedule is not shown representable by documented WinUSB write APIs. Do not conflate successful alternate selection with a complete audio transport. [Contract and test](clock-control-audio.md), [active goal checkpoint](goal-progress.md).

Evaluate these routes in order:

1. Find an authentic WHCP-signed revision of the same required components, or a vendor-supported certification route. No suitable revision is currently in hand; Update Catalog searches for Rane and the SL3 ID returned no results. Microsoft's current policy documentation rules out a simple individual-driver allow exception. See [driver trust](driver-trust.md).
2. Evaluate inbox WinUSB for a user-mode transport. Subsequent traced starts, audio-alternate selection/restoration and a getter-only control exchange have passed. Implement bounded IN capture next. Resolve the documented write API's packetization gap against the original input-length-driven OUT schedule before committing to playback. No audio data has been transferred. WinUSB startup/queries alone do not establish complete SL3 timing, ASIO or Serato compatibility.
3. If the required kernel contract cannot be preserved using an existing supported driver, specify a minimal replacement transport component, with verified IOCTL contracts and a modern build/signing route. Preserve usable ASIO/control code only where its documented behaviour and redistribution terms permit. Decompiled output is not buildable vendor source.

For a new kernel driver, identify a current supported VS/WDK toolchain, NX-safe allocations, non-writable code and correct buffer/IRQL handling. Development signing is a separate laboratory result. A normal-security release needs an appropriate Microsoft hardware-dashboard/WHCP signing route and relevant HLK/HVCI tests; no account, certificate or signing approval is assumed available. Confirm current signing requirements before committing to that route. [Microsoft signing options](https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/driver-signing-offerings).

## Application work remains an early gate

2.5.5 and 2.5.6 both contain the seven-export SL3 API loader. In 5.0.0 that visible legacy loader is absent from the same scan, but the binary still constructs an explicit `Rane SL3` identity associated with VID 0x1CC5 / PID 1. Trace how that identity is consumed and whether it enters the discontinued-device event path. Establish capability/routing/stream/DVS registration before writing an adapter or replacing the audio driver.

Runtime check subsequently confirms 5.0.0 displays “Rane SL3 Discontinued” for this connected unit while the original kernel driver is blocked. It recognizes the identity independently of usable audio. Trace the static-to-runtime path and any remaining functional integration; driver trust and application support are separate observed obstacles.

The initial static path is now recovered: SL3 descriptor `supported_apps` value 2 → `DeviceAggregationThread` → deferred action 0x0E → observer slot +0x70 → `DeviceManager` → UserIO message 4 → discontinued dialog. [Addresses and evidence](serato-discontinued-path.md). The next gate is the support-1 branch's actual stream/control/capability contract and what the SL3 generic descriptor lacks. No application patch is justified by the notification path alone.

Do not patch an identity list merely because it exists. First recover the relevant object contract and call graph, then demonstrate a minimal supported entry into current Serato. If the old implementation is absent, account for the missing audio/control integration explicitly.

## Protocol work

Use the recorded real descriptors as the first verified fixture. The Linux repository supplies hypotheses for the command protocol, not authoritative command meanings. Trace original DLL/kernel operations, identify safe queries and collect small controlled traces when each question is specific. Do not issue firmware commands. A Windows 10 comparison is justified only if a necessary operation cannot be observed efficiently on Windows 11 and its exact question is documented.

## Mac work

Legacy package is Intel kext/IOAudioFamily-based. For Apple Silicon, evaluate an application-level IOUSBHost prototype followed by an AudioDriverKit/USBDriverKit extension if required. For Intel Tahoe, test legacy-package feasibility separately. Confirm actual Mac model, CPU, OS build and OCLP use when a Mac experiment is ready. Signing, DriverKit entitlements, notarization, installation and Serato integration are separate gates.

## Validation gates

| Gate | Current state | Exit evidence |
| --- | --- | --- |
| USB enumeration | Passed on this unit/host | Exact descriptors and hardware IDs |
| Installer execution/package binding | Passed, restart requested | Installer log; bound `oem136.inf` |
| Driver load | Failed before and after reboot | Code 39, enforced CI event 3077 |
| Post-reboot state | Captured; x64/x86 ASIO registered, kernel still blocked | `after-reboot-summary.json` and boot-time CI events |
| Development WinUSB package acceptance | Passed with explicitly approved temporary local trust | `winusb-development-installation.json` |
| Generic WinUSB device startup | Failed, code 10 / power-start status, before user-mode probe | `winusb-development-pnp-events.json` |
| Recovery from WinUSB trial | Passed after package/trust cleanup and full power cycle | Original descriptors match; Rane binding/code 39 restored; `winusb-development-final-state.json` |
| Original USB power-on sequence | Statically recovered; command semantics and runtime traffic unvalidated | `rane-kernel-startup.json`, `usb-startup.md` |
| Passive USB startup capture tool | Five-second recording/decoding passed; no induced failure | 5,215 events, zero events/buffers lost; `usb-startup-trace-smoke.json` |
| Traced WinUSB start and descriptor/pipe queries | Passed once; previous failure did not recur, stability unproven | PnP event 410, all active alternates 0; 22,044 trace events/no losses; `winusb-traced-binding.json` |
| WinUSB audio-alternate selection/restoration | Passed once; audio engine/streaming not tested | Active `[0,1,1,0]`, restored `[0,0,0,0]`; API + USB statuses zero; `winusb-audio-alternates.json` |
| Clock getter and static sample/control contract | Getter reports 44100 Hz; format/control structure recovered; audio untested | 21,382 trace events/no losses; `winusb-clock-query.json`, `rane-clock-audio-contract.json` |
| Native capture implementation/build | Release/Debug + three native test entries/configuration passed; no live capture | `native-capture-build.json`; negative device gate proves zero submissions |
| Independent audio and controls | Not tested | Correct 6-in/6-out full-duplex operation and controls |
| Current Serato recognition | Identifies SL3; explicitly reports discontinued | Usable device open with the required audio/control interface |
| Two-deck DVS | Not tested | Calibration, forward/reverse/scratch/pitch/needle-drop |
| Stability and recovery | Not tested | Four-hour session, ten reopen and reconnect cycles, reboot/power recovery |

Measure target loopback latency directly if Windows 10 reference is unavailable. Before audio acceptance, select and record a numerical threshold justified by the scratching use case and actual buffer/rate configuration. Do not report nominal buffers as measured round-trip latency.

The [Tahoe route and read-only preflight](macos-tahoe-route.md) now pin current Apple API choices, capture/reset limitations and entitlement boundaries, with a concrete first target command. No Mac build/runtime is established; Windows remains the physical-validation priority.

Current Serato's [descriptor resource loading](serato-resource-loading.md) now has a verified static boundary: first-reader text/listing dispatch and an earlier `userio` archive mapping constrain the apparent QRC loose-file fallback. Do not treat adding a loose descriptor as an established adapter. Compare original descriptor content and duplicate VID/PID precedence, and trace complete root/provider setup before selecting a concrete integration change.

The [historical SL3 descriptor comparison](serato-legacy-sl3-descriptor.md) now recovers identical XML and startup registration membership in 2.5.5/2.5.6. It adds concrete USB/driver-API, 48 kHz/alignment and logical endpoint requirements. Resolve actual rate selection, alignment units, handshake adaptation and physical channel mapping before claiming the current observed-rate-only ASIO facade supplies equivalent integration.

The [clock/handshake consumer trace](serato-clock-handshake.md) now resolves alignment as application frames and documents the original fixed-bank ASIO getter. Current handshake enum initialization lacks DRIVER_API and reuses historical value 5 for AKAI. Implement the legitimate connection behavior through a verified integration boundary; neither an unmatched fallback nor a copied enum value supplies it. Trace backend bank adaptation before revising the facade's accepted sizes.

The [bounded control codec](native-control-frames.md) now supplies tested getter/notification framing, with native rate-query integration and the original 0x44-selector/0x37-device-exchange path recorded. New queries have no runtime/IPC exposure and no hardware validation; rate setting, physical controls, real response verification and the current connection adapter remain required.

The subsequent [bank adaptation checkpoint](serato-bank-adaptation.md) establishes preferred-bank retry and separate application/host sizes in the retained current backend. The real IASIO test DLL passes rejected-240/preferred-128 retry and repeated simulated sessions; production bank rules stay unchanged. Continue rate/control and legitimate descriptor integration work, then validate adaptation and measured latency in a real host.

The [rate transaction, diagnostic and trace workflow](rate-selection.md) now supply bounded rate inspection/change/readback logic and preserve possible effects after a failed write. The wrapper requires an explicit target and same-build capture, with tested read-only evidence checks; live orchestration remains untested. The ASIO facade remains observed-rate-only. Physical selection, transfer retirement, actual trace correlation and matching measured timing remain prerequisites to changing production ASIO rate support.

The [numeric descriptor precedence](serato-descriptor-precedence.md) now resolves duplicate VID/PID/revision selection in `PrimaryDeviceManager`. Exact and older-fallback cases differ, and one verified caller requests revision zero explicitly. Continue complete provider/root and actual connection-caller tracing; no external descriptor route or current integration is established by this lookup result.

The [module-relative resource-root default](serato-resource-loading.md#module-derived-root-default) is now verified: its own module path plus a `.` component, subject to filesystem validation. No `Data` override, supported alternate provider or runtime descriptor injection follows. Focus remaining integration work on the actual connection caller and an established provider boundary, retaining archive/listing constraints.
