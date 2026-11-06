# Rane SL3 compatibility restoration

Restore the physical Rane SL3 for current Serato DJ Pro and two-deck DVS. Windows 11 x64 is first; macOS 26 Tahoe is second. Driver loading, independent audio, Serato recognition and working DVS are separate milestones.

## Latest status — 6 November 2026

**Passive runtime observation completed; Frida helper now on hold.** Two isolated no-install startup captures observed the expected receiver, popup return and SL3 arrival publication on the same thread. Both posted-close attempts still required forced exit. Defender quarantined a temporary Frida `idund.exe` helper; protections remain enabled and further Frida launches are held. Driver binaries and original installed files are unchanged. [Findings, security event and limitations](docs/passive-action-capture.md)

**Passive action probe integrated as opt-in:** the receiver diagnostic now shares the startup shim's arrival hook and its fields survive supervision. Combined guard/manual-click checks, preparation, supervisor and copied-kit checks passed. Normal kit preparation keeps the probe off; no live probe or automatic install action ran. [Integration and evidence](docs/session-action-observation.md)

**Original install action identified:** checked RTTI and code connect Download Driver to a popup callback capturing its controller. A bounded passive receiver/thread probe is prepared; nine mocked-boundary cases and actual offline guard/refusal checks passed. No live probe or automatic action ran. [Receiver evidence and limits](docs/serato-download-action-receiver.md)

**Automatic-start boundary clarified:** original Serato bytes show the installer-completion handoff depends on driver detection and a live descriptor. A generic message-helper address previously labelled “startup” is now labelled accurately in trace summaries. No click automation or live application change was made. [Handoff findings](docs/serato-installer-handoff.md)

**Shutdown investigation now covers posted window close:** two simulated integration cases exercise the actual ASIO fixture DLL and broker from a window-owning STA thread, with normal and deliberately blocked callbacks. Both passed, including retained-buffer safety after a failed stop. This does not reproduce or resolve Serato's recorded forced exit. [Test scope and next measurement](docs/asio-window-close-investigation.md)

**Launcher progress is no longer held until session exit:** ordinary helper output now streams to the caller, with bounded byte-preserving forwarding and support for installer launches without console handles. Three real process fixtures and nineteen copied-kit checks passed; the graphical launcher and live session validation remain outstanding. [Progress handling and evidence](docs/native-launcher-progress.md)

**Explicit recovery entry implemented:** prepared sessions now include a command that leaves clean state alone, refuses active/uncertain sessions and can request elevation for a recognised retired interruption. The native no-op/refusal and relocated-kit checks passed without prompts or device access. The actual elevated repair path still needs an attended test. [Recovery command and evidence](docs/session-recovery-command.md)

**Session-specific staging ownership added:** staging and recovery now use a protected record bound to one capsule, bundle and process lifetime. Ten Windows fixture cases passed, including duplicate claims, live/foreign-owner refusal and blocked file deletion. Live protected staging with this protocol remains untested. [Ownership protocol and evidence](docs/protected-session-ownership.md)

**Recovery check available:** prepared sessions now include a native read-only recovery-check command. It checks active/retired owners, protected resource witnesses and current cleanup state without repair or elevation. Real owned-process tests passed; an automatic recovery action remains unfinished. [Contract and evidence](docs/session-recovery-check.md)

**Interrupted staging recovery:** the recovery code now handles a verified archive stage that was never installed and a matching pending installer copy. It preflights all resource identities before permit/native rollback. Twelve new file-operation cases and the existing 22 archive cases passed in isolation; protected recovery against the installed application remains untested. [Recovery fixes and limits](docs/interrupted-resource-recovery.md)

**Shutdown investigation:** the supervisor now allows twenty seconds for exit after finding that its previous eight seconds was shorter than the driver's independent stop/close budgets. An actual delayed-child test passes without forced termination. Marker-free log inspection is also available; an archived markerless log contained no recoverable calls. These changes prepare the next test and do not establish Serato's root cause. [Evidence and limits](docs/asio-shutdown-evidence.md)

**Serato DJ Pro 5.0 on Windows 11 now runs an owner-confirmed two-deck Phase Essential tracking test with the rebuilt SL3 ASIO driver.** Phase A used inputs 3/4 and Phase B used 5/6, with both remotes on one physical turntable. The owner confirmed both decks followed platter movement in the requested REL test and Serato stayed responsive. A five-second software recording contains audio on both deck output pairs without clipped samples. [Two-deck result and limits](docs/evidence/phase-two-deck-session-20261105.json)

See the [phone video, working screenshot and version screenshot](docs/demo-20261105.md), [Phase Essential status](docs/phase-essential-status.md) and [latest return report](docs/RETURN-REPORT.md).

**Packaging prototype:** a copied kit verifies and prepares a complete session through its native executable, using its own runtimes and generating the exact tested Phase archive from the owner's original Serato installation. Preparation now binds a separate native package to current-account Windows paths without changing the driver binaries. Moved-kit and rebinding checks passed; the account-binding run passed 83 targeted checks. Another account/PC, combined live Start, a simple graphical interface and a public installer remain unverified or unfinished. [Account binding and evidence](docs/deployment-account-rebinding.md) · [Native kit entry](docs/native-kit-entry.md)

The native readiness check now reports this host's prerequisites passing before any administrator prompt, with no device open or package DLL load. Its 43 targeted checks passed; combined live startup is still untested. [Readiness scope and observation](docs/session-readiness-check.md)

An explicit native Stop command is now included in preparation records and passed owned-process checks without elevation or device access. Its 64 targeted checks passed; the real Serato close/rollback path still needs an attended test. [Stop request and evidence](docs/session-stop-channel.md)

Prepared sessions also include read-only Status. It distinguishes restored files from a clean shutdown and preserves timeouts, forced exits and broker errors. The copied-kit entry and related regressions passed 63 targeted checks without starting Serato or opening the SL3. [Status, evidence and remaining release tests](docs/session-status.md)

The latest supervisor records whether Windows accepted its close requests and which owned windows remain at timeout. A refreshed kit and 83 targeted checks passed offline; the real shutdown discrepancy remains open. [Next shutdown test and evidence](docs/serato-close-diagnostics.md)

An explicit session diagnostic can now request the existing DLL-owned ASIO log through shutdown while startup hooks detach normally. The exact packaged DLL passed default-off, failed-logger fallback and real 16-event capture/unload checks in isolation. Ordinary kit sessions keep logging off; live Serato use of this option remains untested. [Logging contract and evidence](docs/session-asio-owned-trace.md)

This remains an experimental temporary integration. Physical audible SL3 output, independent turntable control and sustained reliability remain unverified. The latest looped run retains the owner's report that both decks worked and closed normally, but the supervisor recorded viewing-limit termination; clean post-playback shutdown is unresolved. Automatic rollback with the pointer-path fix succeeded and original files were restored. The native audio build is unchanged; its latest Release build passed 71 checks and the deployment workflow passed 26 checks. [Latest looped result](docs/evidence/pointer-cleanup-live-retest-20261106.json) · [Software output recorder](docs/two-deck-output-capture.md)

## Earlier engineering status — 2 November 2026

**Compatibility is not restored. There is no installable replacement driver release yet.** Windows 11 is the current focus; macOS work is deferred. Secure Boot and driver-signature enforcement remain enabled in the attended test evidence.

The native software checks pass **65/65 Release**, **65/65 Debug** and **39/39 without the ASIO SDK**. Coverage includes a retained session-owner backend with separate simulated audio-client processes, COM/ASIO lifetimes and bounded rate-recording replay. Earlier physical tests demonstrate bounded capture, silent playback and control reads with their recorded worker versions; they do not demonstrate working analogue audio, safe repeated acquisition, measured latency, current Serato compatibility or two-deck DVS with this build.

[The read-only broker scope diagnostic](docs/broker-scope-probe.md) now exercises three independent client processes over one retained simulated worker, without a timing profile or audio capability. The server rejects audio starts in this mode; its [dedicated single-approval trace workflow](docs/broker-scope-trace.md) is now prepared and checked offline. Native physical broker validation still requires an attended run.

[An offline genuine-SL3 XML candidate](docs/serato-sl3-candidate.md) now passes the current original schema and reproduces exactly. Its replacement control-path choice is an explicit unverified hypothesis; no provider or application modification is deployed.

The [offline additive archive builder](docs/serato-sl3-archive.md) now preserves all 229 original resource members while adding our genuine-SL3 XML hypothesis. Original CRCs and codec inverses pass; it remains private and undeployed, with runtime Serato/audio/DVS unverified.

[Saved PCM byte-origin checks](docs/capture-origin-and-original-copy.md) now reproduce both archived captures from their saved registered packet slices. Large prefix values persist under the selected original-style copy; this does not diagnose their cause or justify trimming. No new hardware test ran.

[The general ASIO log reader](docs/asio-general-trace-analysis.md) now decodes completed logs and analyzes arbitrary selected-call sequences offline. Both build configurations reproduce archived fixture records exactly; actual Serato/device capture remains unperformed.

[USB component completion tracing](docs/serato-usb-completion.md) now binds identity-record attachment, component-count equality and an internal completion byte. These metadata checks narrow the genuine USB-only hypothesis; current admission, physical audio and DVS remain unverified.

[DLL-owned opt-in logging](docs/asio-owned-trace.md) now passes actual Release/Debug capture and default-off/failure fallback checks under an ordinary token. This prepares ASIO metadata capture without a separate elevated logger; current Serato execution and hardware validation remain unfinished.

[Actual private ETW capture](docs/asio-private-trace.md) now verifies 16 events/eight complete call pairs from each Release/Debug production DLL under an ordinary token, with no device access or Serato launch. The first-party logging round trip works without UAC; current Serato capture and physical audio/DVS remain unverified.

[Bounded ASIO call tracing](docs/asio-call-tracing.md) now records selected activation/control metadata when an ETW session is enabled, with production/fixture separation and a per-module cap. Release/Debug 65/65 and SDK-free 39/39 pass. Fresh review bundles validate; current Serato capture/audio/DVS remain unverified.

[USB-only arrival tracing](docs/serato-usb-arrival.md) identifies a conditional event bridge, minimum-version check and message-updated state result. The unchanged SL3 remains discontinued; current eligibility, audio and DVS are unverified.

[Primary-pointer tracing](docs/serato-primary-pointer.md) now identifies registered-instance selection and one conditional USB-only publisher. A selected pointer or notification remains separate from current SL3 admission, audio and DVS.

[Current HID task tracing](docs/serato-hid-task.md) identifies descriptor-specific verification. Its [notification receiver](docs/serato-wireless-notification.md) now leads to wireless-deck handling and additional primary-manager/state gates, consistent with Phase remaining an accessory. No admitted SL3 or working current DVS result is established.

[The finite input recording diagnostic](docs/input-record-probe.md) now preserves a nominal three-second six-channel callback prefix with zero output. Both-rate simulated recordings match every expected PCM byte and export unchanged to WAV for offline marker analysis. Its [distinct single-approval traced workflow](docs/input-record-trace.md) is now prepared offline; an attended native run remains unperformed.

[UsbDk rollback checks](docs/usbdk-rollback-contract.md) now verify a failure-specific extra port cycle in the unchanged released binary and prepare two offline decoder formats. They do not diagnose the historical stall or establish a safe reopen delay; no new acquisition ran.

[Known-input tone analysis](docs/known-input-tone-analysis.md) is prepared for a future bound capture: all six stream channels, full-capture statistics and fixed request windows, with no startup trimming or timing-profile generation. Both the original 32 ms capture and the separate three-second recorded-prefix schema are supported. All 28 tone checks plus 21 PCM/recorder-validator regressions pass; no new physical audio test ran.

[Current MIDI field-source checks](docs/serato-midi-field-sources.md) now name the processor-creation byte vector and product-derived MIDI identifier. This clarifies a current control requirement without supplying key values, a substitute handshake or admitted SL3/DVS behavior.

[Journal-witnessed copy recovery](docs/asio-copy-recovery.md) now aborts incomplete staging from original file identities and verified bundle bytes. All 65 new checks and 269 affected regressions pass. Unwitnessed creation gaps are preserved; protected deployment, actual audio and current Serato/DVS remain unfinished.

[Interrupted-install abort recovery](docs/asio-install-recovery.md) now handles witnessed partial registration with an intact completed stage, including journalled handoff to partial-file recovery. All 41 isolated checks pass; [journal-witnessed copy recovery](docs/asio-copy-recovery.md) separately handles interrupted staging. Unwitnessed creation gaps and protected production deployment remain unfinished.

[Current handshake-consumer checks](docs/serato-handshake-consumers.md) now bind descriptor-to-MIDI processor provenance and a separate HID comparison. Processor creation and response validation have distinct conditions; no substitute kind or response is adopted, and actual SL3 admission remains unresolved.

[Current Serato path-state checks](docs/serato-path-callers.md) now bind seven direct call sites to module-path consumers, a GPU-preference query and lifecycle cleanup. This narrows a configuration hypothesis without establishing an external SL3 profile route or current DVS admission; installed application bytes remain unchanged.

The original Rane kernel driver is blocked by this host's Code Integrity policy (code 39). A signed UsbDk transport supports the investigation. The last attended control-and-port experiment remains failed as a whole, although its control-read component and subsequent offline USB lifecycle decoding provide useful evidence. Successful redirect release does not establish readiness for a second acquisition.

The [broker-backed ASIO component](docs/broker-asio.md) now runs ordinary COM object recreation and real SDK callbacks over one simulated retained worker, with separate callback/client/physical lifetimes. The [reviewed record configuration](docs/broker-configuration.md) now binds the broker image, process identity and worker contract. The [explicit controller](docs/broker-controller.md) now publishes records and supports validated stop/lifetime handling in actual simulated process tests. [Windows COM activation tests](docs/asio-com-activation.md) now cover STA/MTA production refusal and separate simulated audio clients through `CoCreateInstance`, without registration. The [stable session locator](docs/asio-session-locator.md) now resolves a separately published pointer to a pinned live broker session; pointer publication is explicit and create-new only. [Explicit reviewed pointer withdrawal](docs/asio-pointer-withdrawal.md) now permits create-new republication without redirecting an attached client. The [local deployment builder](docs/asio-deployment-bundle.md) now prepares verified binaries and a registration/ACL plan in a writable review bundle, with 26 package checks. The [registry engine](docs/asio-registry-engine.md) now passes 26 actual Windows registry cases in temporary private HKCU namespaces; its public CLI is read-only. [File staging primitives](docs/asio-file-staging.md) now pass 24 workspace ACL/file tests, and the [volume-anchor review](docs/asio-volume-anchor-review.md) now lets read-only production preflight pass without changing host ACLs. [Owned file cleanup](docs/asio-file-cleanup.md) now passes 26 actual workspace cases, including reader/image-section refusal and truthful partial failure; the 24 staging and 16 ancestor regressions pass again. [Installer lock/journal primitives](docs/asio-install-journal.md) now pass 31 workspace process/file/cleanup checks. [Serialized owned removal](docs/asio-uninstall.md) now passes 20 actual workspace/private-HKCU coordination cases with exact partial results. [Runtime-gated installation coordination](docs/asio-runtime-install.md) now passes 17 runtime and 20 isolated installer cases, including install/remove round trip; 330 direct symbols resolve through native System32 dependencies without loading package code. [Reviewed interrupted-registry recovery](docs/asio-registry-recovery.md) now passes 22 isolated cases with an intact stage. [Reviewed file-removal recovery](docs/asio-file-recovery.md) now passes 35 isolated cases across all deletion boundaries and absent-stage reconciliation, with explicit legacy receipt-ID limits. [Protected-base preparation and stronger directory leases](docs/asio-install-base.md) now pass 17 new and 211 affected regression checks; a native calibration exposed and fixed weak metadata-only rename pins. Production creation/deployment/activation and interrupted install/copy recovery remain unperformed. Protected installation and positive native validation remain unfinished. The source also includes single-use traced scope/rate diagnostics; their current positive physical runs remain unperformed. No elevated service or automatic native broker is installed.

Start with the [public development checkpoint](docs/public-development-status.md), [return report](docs/RETURN-REPORT.md), [metadata probe](docs/metadata-scope-probe.md) and [current Serato integration boundary](docs/current-serato-integration-decision.md). The historical notes below preserve their original dates and limits; they are not cumulative proof of a working driver.

## Investigation history — started 26 October 2026

The entries below record successive checkpoints. Earlier statements about missing components are superseded by later implementation evidence and the current status page.

Research and static analysis are underway. **Compatibility has not been restored or demonstrated.**

- Host: Windows 11 Pro x64, build 26300, Ryzen 9 5900X.
- Connected SL3: `VID_1CC5&PID_0001`. Read its real USB descriptors successfully through the hub driver.
- Acquired authentic Rane Windows ASIO 1.3.5f2 and Mac 2.0.1f2 packages from inMusic's CDN using an archived official Rane page.
- Extracted signed Serato 2.5.5.83 and 5.0.0.1278 installers without installing them. The owner installed 5.0.0 separately; its executable hash matches our extraction.
- Serato 2.5.5 and 2.5.6 retain an SL3 API loader. **Current 5.0.0 identifies this connected unit and displays “Rane SL3 Discontinued”**, while its kernel driver is blocked. The device's identity is retained; usable audio/DVS integration remains unresolved.
- Traced current Serato's `supported_apps` value 2 through a deferred device action, `DeviceManager` and UserIO message 4 to the discontinued dialog. See [the static path](docs/serato-discontinued-path.md). Changing that state has not been shown to restore audio/DVS.
- Acquired and extracted owner-provided 2.5.6.1001 as well; no historical Windows installer is now missing.
- **Original Windows driver test: installed and bound, then blocked from loading by the active cross-certificate Code Integrity policy (code 39 / event 3077), including after restart.** Offline signature verification passed; it did not establish current policy admission. Secure Boot was enabled in the elevated pre-reboot snapshot. Restart completed both x64 and x86 ASIO/DLL registration; the kernel driver remains blocked.
- Mac package has an Intel-only legacy kernel extension; it cannot load natively on Apple Silicon. Intel Tahoe compatibility remains untested.

Read [findings](docs/findings.md), [artifact inventory](docs/artifacts.md), [implementation sequence](docs/implementation-plan.md) and [next tests](docs/next-tests.md).

[Driver trust decision](docs/driver-trust.md): no suitable WHCP-signed SL3 revision found; catalog searches returned no results. The owner's generic WinUSB selection was rejected as incompatible. The device-specific INF passes Inf2Cat and its separately development-signed copy has been tested, including audio-alternate selection/restoration. Release signing and audio/control transfers remain unvalidated; INF-only package trust is separate from signing a new kernel binary.

**Development hardware trial completed:** with explicit approval, Windows accepted the locally signed package, then WinUSB failed startup (code 10 / `STATUS_DEVICE_POWER_FAILURE`) and USB descriptor enumeration failed. The package, temporary trust entries and signing key were removed. After a full power cycle, the SL3 returned with its original descriptors and Rane binding/code 39. [Test and recovery](docs/windows-development-test.md). Static analysis now identifies the original driver's explicit audio-interface alternate-setting selection as a comparison target; [startup evidence](docs/usb-startup.md).

**Traced binding succeeded:** the unchanged WinUSB package started on the subsequent authorized attempt, and descriptor/pipe queries passed with all interfaces active at alternate 0. The trace recorded 22,044 events with no losses. The earlier failure did not recur; its cause remains unknown. Cleanup restored the original Rane/code-39 baseline without a power cycle. [Result and evidence](docs/windows-traced-test.md).

**Audio interfaces activated and restored:** the next authorized WinUSB test reached `[0,1,1,0]`, verified both isochronous pipes, and returned both interfaces to zero. API and USB trace statuses confirm success; 37,990 events/no losses. Cleanup is verified and Secure Boot remains enabled. No audio or device commands were sent. Next: establish status, clock and sample semantics before streaming. [Result and evidence](docs/windows-audio-alternates-test.md).

**Clock and format investigation:** the original-driver rate getter returned **44,100 Hz** in a bounded traced test; cleanup is verified. Static kernel/ASIO analysis supports six packed 24-bit little-endian containers and recovers distinct notification tags and input-length-driven playback timing. A capture-first test is specified. WinUSB's documented output packetization presents a separate unresolved playback constraint. [Contract and evidence](docs/clock-control-audio.md). The owner's [active rebuild goal checkpoint](docs/goal-progress.md) records implementation direction and pending tests.

**Native capture diagnostic built:** the original C++ IN-only diagnostic builds and passes packet/lifecycle fault tests in Release and Debug. It defaults to a plan, enforces completion ownership and deadlines, and rejects the original-driver state before submitting audio. The traced capture run is prepared but has not been executed; [implementation, commands and limits](docs/native-capture.md).

**Playback core and candidate transport:** native packet layout/PCM tests now pass, and source review confirms libusb over WinUSB retains the variable-packet constraint. A nested Microsoft hardware-publisher signature in UsbDk's released Windows 10 driver passes explicit kernel verification. No alternative driver was installed or audio OUT submitted; [candidate evidence and remaining tests](docs/playback-transport.md).

**SDK-facing ASIO buffers built:** optional code now passes real SDK layout/callback/lifecycle tests in Release and Debug. This remains an internal component; a live device/session owner and IASIO/COM driver are still needed. [Component and limits](docs/asio-buffer-component.md).

**Bounded duplex test prepared:** a finite IN/OUT pipeline now preserves validated packet lengths and drains both directions on failure. The explicit native mode can send only silent PCM and has not been run on hardware. [Ownership, evidence and pending sequence](docs/bounded-duplex.md).

**ASIO DLL interface prepared:** an unregistered development DLL passes direct SDK ABI and COM lifetime tests. Initialization remains unavailable until the real isolated audio session is implemented. [Current implementation and limits](docs/asio-com-server.md).

**Worker lifetime boundary tested:** real Windows child/job tests now verify targeted termination, descendants, owner death and conservative cleanup. A live audio worker remains to be implemented. [Component and evidence](docs/worker-process.md).

**Worker messaging implemented:** a bounded per-user channel passes real-process binary, timeout, stale-message and peer-exit tests. Continuous audio and live ASIO integration remain pending. [Channel and evidence](docs/worker-mailbox.md).

**Typed diagnostic worker implemented:** the real executable now handles a capability handshake and finite-input commands over IPC. Fifteen native tests pass in Release/Debug, including real missing-driver failure handling. Physical worker capture, continuous audio and ASIO integration remain unverified. [Protocol, evidence and limits](docs/typed-worker.md).

**Audio queues connected to SDK buffers:** the host adapter now decodes input, invokes logical-channel callbacks and publishes output while preserving packet lengths and backpressure. Seventeen native tests pass in Release/Debug, including 2,400 full-path synthetic process blocks. Continuous USB streaming, live ASIO availability and physical audio remain pending. [Implementation, evidence and timing limits](docs/queue-to-asio.md).

**Shorter batches supported:** the software path now preserves 8–64 active intervals, allowing planned one-millisecond transfer shapes for the future continuous worker. The expanded test checks 7,200 full-path synthetic process blocks per configuration. Physical callback timing and the live USB/session loop remain unverified. [Contract and evidence](docs/audio-transfer-granularity.md).

**Continuous request engine implemented:** the core now rearms four input slots, validates matching output schedules and retains unproved I/O leases through bounded shutdown. The original eighteen-test checkpoint includes 18,000 fake input/output batches. The production worker session still needs connection. [Ownership, evidence and next implementation](docs/continuous-engine.md).

**Native continuous adapter built:** the UsbDk/Windows request adapter and worker queue peer now pass simulated completion/cancellation tests through the actual engine and queues. Nineteen native tests pass in Release/Debug. The production session dispatcher/watchdog, driver loading and physical audio remain unverified. [Implementation, evidence and next work](docs/native-continuous-adapter.md).

**Continuous worker connected:** typed session control and a heartbeat watchdog now connect the production native path. Twenty-one native tests pass in Release/Debug; simulated real-process sessions verify startup, audio queues, stop and fault containment. A healthy heartbeat survives 21.5 seconds. The ASIO host owner and all physical audio/Serato validation remain pending. [Current checkpoint and evidence](docs/continuous-worker.md).

**ASIO audio ownership implemented:** a dedicated thread now owns SDK callbacks/queues and retains planes/DLL code through incomplete callback shutdown. Twenty-two tests pass in Release/Debug, including actual DLL retain/unload after a blocked callback. The full host control coordinator and production IASIO connection remain pending. [Lifetime contract and evidence](docs/asio-audio-owner.md).

**Current Serato audio routing recovered:** the SL3 stub's empty audio fields select a default-device branch if reached. Explicit name/VID/PID routes retain both legacy PortAudio and newer backends. This defines a candidate integration contract; no support patch or working Serato audio is claimed. [Selector, matching rules and evidence](docs/serato-audio-routing.md).

## Resume

**Audio buffer bridge built:** fixed host buffers and variable USB packet layouts now pass simulated stream/lifecycle tests, including deferred host output. This is a core component; ASIO registration and real audio remain pending. [Bridge and verification](docs/audio-bridge.md).

**Current-Serato contract recovered further:** the discontinued stub lacks concrete audio/MIDI setup, while a generic ASIO backend remains present. The separate DriverAPI readiness query is a registry check, not proof of audio or kernel loading. [Contract and remaining integration gaps](docs/serato-supported-contract.md).

**UsbDk capture adapter built:** the alternate transport diagnostic now builds and passes plan/gating checks; read-only preflight is available. Its live driver and device behaviour remain untested. [Adapter, verification and pending gates](docs/native-usbdk.md).

From this project in PowerShell:

```powershell
python -m unittest discover -s tests -v
./scripts/collect-windows-state.ps1
python scripts/usb-descriptors.py tests/results/local/sl3-descriptors.json
./scripts/test-original-driver.ps1
```

These commands do not install drivers. The last command validates the original installer and records the current state. See next-tests.md for the explicitly gated installation command and rollback.

Analysis dependencies are isolated in `.venv` and `tools`. Use `.venv/Scripts/python.exe` for PE reports and `./scripts/rea.ps1` for REA. See [analysis workflow](docs/analysis-workflow.md) for extraction and setup. REA uses a local CLI; Codex's global MCP configuration was not changed.

## Repository layout

| Path | Purpose | Git |
| --- | --- | --- |
| `docs/` | Findings, provenance and small evidence | Tracked |
| `scripts/` | Acquisition, static inspection and diagnostics | Tracked |
| `src/` | C++ transport, worker, ASIO components and diagnostics | Tracked when populated |
| `tests/fixtures/` | Small descriptor and protocol fixtures | Tracked |
| `tests/results/` | Small repeatable test reports | Tracked except `local/` |
| `DJPro/` | Owner-provided Serato installers | Ignored |
| `artifacts/` | Vendor downloads and extracted files | Ignored |
| `analysis/` | Full reports, snapshots, caches and intermediate output | Ignored |
| `tools/`, `.venv/` | Isolated third-party tools | Ignored |

No firmware operations, driver binary patches or replacement kernel binaries have been performed. The original Windows driver was installed for the authorized test. Temporary development-certificate trust for the WinUSB trial was explicitly approved and then removed; Secure Boot and CI policy were not changed. Preserve the optional working Windows 10 system; it is not a prerequisite for continuing.

**Host control and clock inspection connected:** temporary clock queries and fresh continuous sessions now connect worker supervision to SDK audio ownership, with separate worker/callback retirement and changed-rate rejection. Release/Debug pass 23 native tests; SDK-free builds pass 18. The production ASIO DLL remains unavailable and physical audio/Serato/DVS/Mac validation is still pending. [Contract, evidence and next work](docs/host-session.md).

**ASIO session facade tested:** a separate unregistered DLL now runs actual COM/IASIO callbacks and repeated worker sessions with simulated I/O. Release/Debug pass 25 native tests, and SDK-free builds pass 18. Timing values are explicitly synthetic; the production provider/configuration and physical audio/Serato/DVS/Mac validation remain pending. [Contract and evidence](docs/asio-driver-facade.md).

**Production ASIO provider connected:** strict adjacent configuration now binds reviewed worker/helper bytes and a rate/bank-specific timing record to the actual COM DLL. Release/Debug pass 26 native tests; SDK-free builds pass 18. Tests reject a simulated worker through the real native provider before device access. No production timing config or registration is installed; physical audio/Serato/DVS/Mac remain pending. [Configuration and evidence](docs/asio-native-configuration.md).

**Current Serato DVS requirements narrowed:** static analysis now identifies the DVS capability enum/manager predicate, software calibration formula and separate endpoint maps. The unchanged SL3 stub is predicted to lack the required DVS capability setup; audio-driver success alone remains insufficient. Original/installed binaries are unchanged. [Contract, reproducible evidence and remaining integration](docs/serato-dvs-contract.md).

**Descriptor resource boundary recovered:** current Serato assigns `userio` to an archive reader before its Qt filesystem fallback; both text reads and directory listings stop at the first matching reader. A loose SL3 XML file is therefore not established as a registration route. Original/installed binaries remain unchanged. [Dispatch, reproducible evidence and next comparison](docs/serato-resource-loading.md).

**Original SL3 descriptor recovered:** 2.5.5 and 2.5.6 retain identical SL3 XML and include it in their startup registration arrays. It declares driver-API handshake, ASIO “SL 3”, a 48 kHz profile, no MIDI, DVS and Deck3/Deck1/Deck2 endpoint order. These are original declarations, with runtime selection and physical mapping still unverified. [Comparison and rebuild implications](docs/serato-legacy-sl3-descriptor.md).

**Clock/handshake difference verified:** the current handshake map lacks the original DRIVER_API name; historical numeric 5 now means AKAI. Current latency alignment produces an application frame count, while the original ASIO driver advertises one configured bank size. Copying the old descriptor or changing bank rules alone is insufficient. [Verified fields, arithmetic and remaining adaptation](docs/serato-clock-handshake.md).

**ASIO bank retry verified:** the retained current Serato backend retries the driver's preferred bank and adapts separate application/host frame counts. Our unregistered DLL passes the rejected-240/preferred-128 retry over repeated simulated sessions; all 27 native tests pass in Release/Debug. Production bank rules stay unchanged. Physical audio and current Serato/DVS remain unverified. [Evidence and next-test implications](docs/serato-bank-adaptation.md).

**Rate-selection logic prepared:** a bounded transaction now supports inspect, optional 44.1/48 kHz change and mandatory readback, preserving uncertainty after a possible write. All 28 native tests pass in Release/Debug and 20 SDK-free tests pass. No physical rate setter has been exercised; the production ASIO facade remains observed-rate-only. [Contract and evidence](docs/rate-selection.md).

**Explicit rate diagnostic prepared:** a separate native mode now connects that transaction to bounded interrupt I/O and durable progress reporting. The traced wrapper requires an explicit target and prior same-build capture; nine new synthetic/plan checks pass, with all 36 Python tests passing. No live wrapper or physical rate write has run; ASIO/startup remain getter-only. [Current boundary and evidence](docs/rate-selection.md).

**Descriptor precedence recovered:** current Serato registers resource descriptors before discontinued stubs, but numeric selection differs for exact and older-revision matches. An earlier name matcher and callers requesting revision zero constrain that result. Original/installed binary verification passes; an external integration route and current audio/DVS remain unestablished. [Selection rules and evidence](docs/serato-descriptor-precedence.md).

**Resource-root default recovered:** the current executable obtains its module path and defaults the resource component to `.`. This narrows the loose-file hypothesis; archive precedence and QRC listing still prevent treating it as a proven descriptor-installation route. No application state changed. [Verified default and limits](docs/serato-resource-loading.md#module-derived-root-default).

**Control codec implemented:** the original driver-timer exchange maps selector 0x44 to USB interrupt 0x37 with an eight-byte real-device reply. A bounded C++ codec now handles the known getter/reply/notification frames, and the native rate query uses it. All 27 native tests pass in Release/Debug and all 19 SDK-free tests pass. New queries remain unexecuted on hardware, with no emulated handshake result. [Implementation, original path and evidence](docs/native-control-frames.md).

**Mac Tahoe workstream prepared:** current Apple transport/audio/entitlement research and a tested read-only Mac preflight now give a concrete first experiment. All 27 Python tests pass; only plan mode ran on Windows. Native Mac transport/Core Audio/Serato DVS remain untested. [Route, first command and evidence](docs/macos-tahoe-route.md).
