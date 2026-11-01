# Public development checkpoint — 1 November 2026

This is an engineering investigation and source snapshot, not a working replacement-driver release. Windows 11 is the current target; macOS is deferred. The aim is independent audio, a usable ASIO driver and eventually current Serato DJ Pro with two-deck DVS. Each needs its own demonstration.

## Findings and implementation

| Area | Established so far | Remaining boundary |
| --- | --- | --- |
| Original driver | Rane ASIO 1.3.5f2 installs, but this Windows host blocks its kernel driver under Code Integrity, reporting code 39. | No admitted original-driver revision has been established. Signing enforcement is being kept enabled. |
| USB transport | Signed UsbDk has supported bounded physical input capture, silent output and control reads in separately recorded experiments. | Results belong to their exact worker hashes; current-build analogue audio and reliable repeated acquisition are unproved. |
| Release/startup | Offline decoding of the last attended port trace reports successful SL3 redirect removal followed later by original-stack startup timeout. | Successful removal is not a readiness barrier for the next acquisition. |
| Worker and ASIO | C++ packet/queue processing, isolated worker lifetime, COM/IASIO components, explicit shared owner and fresh retained-device clock reads have software coverage. | No production registration, measured latency profile or working current-build physical ASIO session is demonstrated. |
| Metadata scope | A bounded probe models one acquisition, three facade lifetimes, three clock reads and final release, without audio or rate changes. | Positive lifecycle coverage uses simulation; the physical scope branch remains unrun. |
| Current Serato | Actual 5.0.0 observation displays “Rane SL3 Discontinued”. Static work identifies the discontinuation path and separate audio, handshake and DVS requirements. | A flag change or driver success alone does not establish application admission or DVS. No working integration is claimed. |
| Historical cutoff | All 156 startup resources in 2.5.5 and 157 in 2.5.6 were inventoried. Their scalar SL3 declarations contain identical XML. | Static resource presence does not establish runtime eligibility in either version. |

Detailed provenance and limits are in the [return report](RETURN-REPORT.md), [findings](findings.md), [metadata probe](metadata-scope-probe.md), [USB lifecycle analysis](attended-port-lifecycle-20261101.md), [resource comparison](serato-cutoff-registration.md) and [Serato integration decision](current-serato-integration-decision.md).

## Latest integration work

The source snapshot includes work in progress to reduce an attended scope experiment to one administrator approval. The ordinary user runs the probe; a separate elevated collector records USB/WPP/state evidence. Plans pin tested inputs, are single use, allow one acquisition and require a post-retirement trace window. There is no persistent elevated service or automatic retry. Default launcher inspection performs no device test.

The scope plan path has been exercised, but the elevated launcher and physical experiment have not. The separate kernel-image-version-qualified scope window is unfinished. Neither a controls-only result nor a simulated scope result qualifies as that experiment.

See [publication verification](evidence/publication-verification-20261101.json) for fresh test counts and source identities. These software checks do not attest physical audio, latency, deployment or Serato compatibility. No hardware/UAC test ran for this publication.

## Building and reproducing

The native core uses C++17 and CMake. SDK-free targets can be configured with `cmake -S . -B artifacts/build/core`; build that directory and run CTest there. Windows-specific components additionally require the Windows SDK and toolchain. The existing Windows build script targets Visual Studio 2019 and Windows SDK 10.0.19041.0.

ASIO component builds are optional and require a separately obtained official ASIO 2.3.4 SDK. Its headers are not redistributed; CMake verifies the expected header hashes. See [ASIO component instructions](asio-buffer-component.md). Live transport also needs the separately acquired, reviewed UsbDk installation. Building does not install or register a driver.

The full local Python suite uses private artifact fixtures and current build manifests. A public checkout does not contain those dependencies and is not expected to reproduce every test immediately. Historical evidence JSON records original local paths and hashes; references to ignored artifacts are provenance, not bundled downloads. Consult [analysis workflow](analysis-workflow.md) before reproducing artifact-dependent checks.

## Publication boundary

The public repository retains its existing GPLv3 license. The two UsbDk interface headers retain their upstream Apache-2.0 notices and license. Vendor installers, application/kernel binaries, the external ASIO SDK, raw USB/event captures, local tools, build outputs and the owner's planning DOCX remain outside this publication. The inspected screenshot shows the empty Serato UI and discontinued-device notice. Small research summaries, protocol fixtures and historical evidence records are included.

This is a clean source snapshot on top of the public repository's initial commit. The detailed private Git history remains local; the dated progress documents preserve the investigation history. No firmware, account, licensing or security-policy change is part of publication.
