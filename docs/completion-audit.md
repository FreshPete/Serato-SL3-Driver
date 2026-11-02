# Requirement audit — 2 November 2026

**The full Windows/current-Serato/two-deck-DVS objective remains incomplete.** This review checks current sources and files against the requested end state; it does not substitute passing software tests, decoded records or an offline descriptor for operational compatibility. Mac remains deferred until Windows works. [Machine-readable checks](evidence/requirements-review-20261102.json).

## Current software and installation facts

Release/Debug manifests each record 65 software tests and bind 149 current source inputs; the SDK-free manifest records 39 tests and 146 inputs. All manifest `inputs` entries were rechecked without rerunning those suites. The current Release worker is `790521dcd5120bd0eaf2c2036c501d8f00c49f95b9d557f0d075939b8b451b22`, and the Release ASIO DLL is `31fb37915a845082637be14aa0ad22200e4d2506dc1d2ad2b18f4bf3920784ec`. Historical hardware evidence must retain its own worker identities.

Read-only checks at the named x64 HKLM/HKCU ASIO and project CLSID paths found all four absent. This covers those paths, not every possible configuration or installation location. The installed original Serato executable remains `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`; original `userio_resources.bin` remains `872fc4fdad2eab2ddd34387d2d3c04dd9731c84798d9fdc7bd05ca54e1567db8`. Neither file was executed or modified by the review.

The [cached PnP evidence](evidence/sl3-return-packet-20261102.json) separately records original `strmdrv`/Code 39 and port 4. It supplies no fresh USB readiness result or new CI-cause diagnosis. Future operational windows still need their own security/device/recovery observations.

## End-state requirements still outstanding

| Requirement | Evidence now and its limit | Required next proof/work |
| --- | --- | --- |
| Normal Secure Boot/code integrity and recoverable transport | Historical enabled-window evidence and signed UsbDk; cached original-driver Code 39 | Fresh checks during each future operational window; no security weakening |
| Genuine clock/rate/control and routing behavior | Recorded getter/setting observations with archived workers; guarded control codec and IPC | Current-worker physical control/routing/readback and clock behavior |
| Bounded continuous capture/playback with correct samples | Native simulated suites, archived finite input/silent output and raw-byte preservation audit | Current-worker simultaneous nonzero playback/capture and sample continuity |
| Physical channel/deck/jack mapping and levels | Six logical stream channels and offline markers/packing | Known analogue source, verified wiring and controlled mapping/levels |
| User-mode ASIO/control integration | Production COM/ASIO and simulated retained/broker lifetimes; own unavailable-state trace fixtures | Measured profile, production configuration/registration and physical host behavior |
| Safe stop/reopen/reconnect and reboot recovery | Historical second-open stall, release timeout mapping and unarmed corrected observation packet | Demonstrated readiness/repair and ten recovery cycles; stop success is insufficient |
| Genuine current Serato SL3 descriptor/control/admission | Original-binary analysis and private schema-valid/additive archive hypothesis; original install intact | Approved actual parsing/selection, legitimate service/control path and ASIO/audio operation |
| Working two-deck DVS and Phase option | Recovered DVS fields and accessory requirements | Actual admitted primary interface, legitimate entitlement, signal/motion/calibration/scratch/pitch tests |
| Measured latency and four-hour stability | Bounded timing/analysis tools only | Numerical acceptance target, real round-trip measurements and four-hour stability |
| Reproducible replacement deployment/removal/recovery | Prepared source-bound ASIO/archive transactions and isolated recovery tests | Protected production deployment, positive activation and removal/recovery tests |
| macOS Tahoe route after Windows | Legacy architecture and route research; owner deferred implementation | Windows first, then actual target-specific implementation/signing/deployment/hardware validation |

The [unarmed attended packet](next-attended-packet.md) is current against these frozen inputs. Its future context and launch record are absent. No probe, trace or application role is running from that packet. The next hardware action needs the owner available for one administrator launch and possible recovery; that availability has not been established for another run. No new UAC prompt is requested while the owner is away.

Independent offline work has supplied bounded transport/control/ASIO software, resource/selection hypotheses and logging/analysis tools. The remaining decision points need real observations: readiness across the original-stack startup timeout, known analogue signals, a measured profile and an actual current-Serato session. Automatic reset/reopen, altered security policy, a guessed timing profile, a fabricated service/device response or trimming unexplained samples would not establish the requested end state.

The [current resource hypothesis](serato-sl3-candidate.md), [recoverable archive transaction](serato-archive-deployment.md), [general ASIO log reader](asio-general-trace-analysis.md) and [saved PCM origin audit](capture-origin-and-original-copy.md) are reviewable preparation with explicit limits. Protected deployment is not performed or granted by this review. No firmware, signing-policy, account or device-identity change is selected.

## Historical 1 November audit

The text below retains that checkpoint's original hashes, test counts and queue. Any use of “current” in this historical section refers to 1 November, not the present build. Its physical results remain scoped to their recorded versions.

### Original audit

The complete Windows 11/current Serato/two-deck DVS objective is **not achieved**. This audit keeps build success, bounded silent hardware results and application admission separate. macOS remains deferred by the owner's instruction until Windows works.

| Requirement | Evidence and scope | Outstanding proof/work |
| --- | --- | --- |
| Authentic inventory and reproducible research | [Artifact inventory](artifacts.md), original-image exporters, pinned local inputs and Git history. | Maintain exact version/hash binding for further tests. |
| Normal Windows security | Original driver failed active Code Integrity; signed UsbDk installed/restarted and archived tests recorded Secure Boot enabled. [Installation result](usbdk-installation-result.md). | Verify each future operational window; no security weakening is selected. |
| USB startup, clock and PCM transport | Archived finite 44.1/48 kHz capture, rate readback and silent output; [retained hardware test](retained-physical-test.md) passed two one-second 44.1 kHz streams within one redirect. An archived worker passed [normal-user control ownership and a complete trace](combined-controls-image-capture.md). | Current-build audio, normal-user streaming, sustained operation and sample continuity. |
| Control and routing behavior | Recorded normal-user 44.1 kHz/full-table baselines and selected recovery passed. The later [16:40Z native component reassessment](attended-port-controls-20261101.md) passes separately while its combined experiment remains failed. Original control contract and guarded selection diagnostic have software coverage. | Physical sensitivity/through checks, actual selected settings and verified routing. |
| Physical channel mapping and simultaneous audio | Software six-channel packing and zero-output duplex are established in their stated scopes. The [offline marker tool](offline-audio-markers.md) identifies synthetic file routes at both rates; no playback/device access is included. | Controlled analogue input/output, physical jack mapping and real simultaneous playback/recording. Correlation offsets do not establish measured latency. |
| Safe close/reopen/reconnect | [Saved second open stalled](reopen-usb-timeline.md). A complete trace [maps the release timeout to the SL3 port](sl3-release-port.md), with matching image-version metadata. Later [decoded WPP](attended-port-lifecycle-20261101.md) reports successful detachment/removal; the ordinary-user sampler failed during handoff, leaving phase discrimination incomplete. | Physically validated readiness/ownership repair, actual repeated objects, ten reconnect/reopen cycles and reboot recovery. |
| ASIO integration | Original COM facade, retained within-object transport, [simulated object recreation](asio-recreation-tests.md), [cross-facade owner](facade-owner-scope.md) and [explicit factory controller](factory-scope-controller.md) are implemented/tested. | Measured timing profile, production configuration/registration, genuine current-Serato backend/interprocess integration and physical host/application operation. |
| Current Serato admission | Discontinued stub and missing DRIVER_API map recovered; [2.5.6 retains the historical loader](serato256-sl3-api-path.md). | Implement and validate a concrete SL3 descriptor/control/admission route preserving real identity and legitimate product/account behavior. Retained old code is insufficient. |
| Two-deck DVS and Phase | Static DVS/deck contracts and published accessory requirements are documented. | Actual compatible primary-device opening, entitlement requirements, calibration, playback/reverse/scratch/pitch tests with real signals/motion. |
| Latency and stability | Bounded silent callback/retirement evidence only. | Measured latency with justified acceptance threshold and four-hour stability; callback spacing is insufficient. |
| Reproducible product installation/removal | Original Rane and UsbDk installation observations; build outputs/configuration guards retained. | Deployable complete ASIO/control product and actual install/remove/recovery validation under normal protections. |
| macOS route | Legacy package architecture/dependencies and [Tahoe route](macos-tahoe-route.md) researched. | Deferred implementation/target-specific signing, deployment and physical validation after Windows. |

The original audited Release manifest was SHA-256 `8cd1143da61d312c7ca587b0215156f532a9f8971b8260506182a501324bf62d`; capture-only runtime revisions subsequently changed the manifest while preserving native inputs/binaries. The current capture-runtime manifest is `0d875f3d3e438e1f296cfc3b73e9f14c80b656df1e78bd0a8825a341461ab3da`, and the worker remains `5fe2a44f1020032994c2b2e1a5ea868f87650caa9e23bc2077913760d0e88fe5`. The last retained audio hardware sequence binds worker `578ae92c5e77d76f0bc2d6815c1a1c41f86d133813de348a93f37d143f01a880`. The different worker hashes prohibit assigning that audio result to the current worker. Existing test counts describe their archived/checkpoint inputs, not freshly rerun complete suites.

The [31 October current-worker read](attended-controls-20261031.md) remains a failed wrapper because circular capture overwrote early rows. The fresh [1 November combined capture](combined-controls-image-capture.md) independently passed complete normal-user controls/recovery, sequential retention, all 493 state rows and matching image-version coverage. Decoder warnings remain explicit. Native hard file limits, timer cause, loaded-memory identity and safe successive acquisition are not proved. The new pass does not retroactively change an earlier failed wrapper or qualify its overwritten window.

The current next physical step is the [normal-user port/devnode phase observer](hub-port-observer.md) alongside a fresh one-approval control capture. The attempted run expired awaiting admission and Windows cancelled its administrator launch. No trace, hub sample or device probe started; the attempt is disarmed and cannot be reused. Twelve observer and six phase-comparison software cases pass, including direct process retirement and refusal paths. They do not prove live phase discrimination or admit a second acquisition. Another source-only logging run is unnecessary without a changed input or concrete logging fault.

The cancelled phase attempt's observer and waiting normal controls role were observed retired; no consent prompt or native device process remained in its inventory. No new source, firmware, signing, registration or application operation ran in that attempt. Its specific tool handles are terminal. This is not a blanket attestation about unrelated logging sessions. The full goal remains active and incomplete; actual current-worker audio, physical measurements and current Serato/DVS still require their own evidence.
