# macOS Tahoe route and first target preflight

Windows remains the first implementation/physical-validation target. This
checkpoint prepares the parallel Mac work with current primary-source research
and a read-only collection tool. No Mac is connected to this Windows workspace;
no Mac build, driver load, signature verification or audio/DVS test is claimed.

## Revalidated legacy package

The original `Sl3-2.0.1f2.zip` hash still matches the authentic archived package.
Its payload has an x86_64 `Sl3Driver.10.9.kext` using IOAudioFamily and USB host
kernel dependencies. The `Sl3Api.framework` has Intel slices, without ARM64.
The kext personality matches `IOUSBHostDevice`, VID 7365/PID 1. Its installer
requires root and a restart. These are package/structural observations, not
Apple signature or load results. [Pinned package evidence](evidence/macos-route-preflight.json),
[original Mach-O report](evidence/rane-mac-macho.json).

The Intel-only kernel image cannot serve as native Apple Silicon kernel code.
For Intel Tahoe, architecture alone neither proves nor disproves loading:
signature, dependencies, kernel interfaces and actual runtime admission remain
untested. Existing legacy kext presence must be recorded before any replacement
tries to obtain the device.

Apple documents Reduced Security as part of legacy kext installation on Apple
Silicon. That is outside this project's normal-security release target; no such
change is proposed or performed. A modern user-space route is the candidate.
[Apple kext installation requirements](https://developer.apple.com/documentation/apple-silicon/installing-a-custom-kernel-extension).

## Candidate transport and audio boundaries

Apple's public **IOUSBHost** framework supports app-level access to custom USB
devices, including isochronous pipe requests. It is distinct from **USBDriverKit**,
whose pipe class also provides isochronous transfers inside a driver extension.
These provide actual API candidates; they do not prove SL3 ownership, timing or
streaming works on Tahoe.
[IOUSBHost overview](https://developer.apple.com/documentation/iousbhost),
[app-level pipes](https://developer.apple.com/documentation/iousbhost/iousbhostpipe),
[USBDriverKit pipes](https://developer.apple.com/documentation/usbdriverkit/iousbhostpipe).

The app-level transaction-list overload is documented from macOS 12. It exposes
per-transaction requested/completed byte counts, offsets, status and timestamps.
That is a promising surface for SL3's variable packet lengths; exact high-speed
service-interval/frame-number semantics, buffer ownership and abort/completion
guarantees must be checked against the Mac SDK and observed on hardware before
implementing audio. The existing frame-list API is also documented for Tahoe.
Do not assume a Windows eight-interval batch maps to eight Apple API "frames."
[Transaction-list request](https://developer.apple.com/documentation/iousbhost/iousbhostpipe/enqueueiorequest(with:transactionlist:transactionlistcount:firstframenumber:options:completionhandler:)),
[transaction structure](https://developer.apple.com/documentation/iousbhost/iousbhostisochronoustransaction),
[frame-list request](https://developer.apple.com/documentation/iousbhost/iousbhostpipe/enqueueiorequest(with:framelist:framelistcount:firstframenumber:completionhandler:)).

**Do not use device capture in the initial probe.** Apple's `deviceCapture`
option terminates existing clients/drivers and resets the device on destruction;
it has entitlement/authorization or root requirements. A normal interface open
must first be tested without capture/seize, automatic unloading, reset or a
security change. An exclusive-access failure is evidence to investigate, not a
reason to terminate the existing owner automatically.
[Apple capture semantics](https://developer.apple.com/documentation/iousbhost/iousbhostobjectinitoptions/devicecapture).

For Core Audio exposure, the physical-driver candidate is **AudioDriverKit plus
the required USB transport**, with a single coordinated owner for audio IN,
audio OUT and interrupt control interfaces. AudioDriverKit supplies the HAL
communication layer and supports Intel and Apple Silicon. Apple's sample is
useful scaffolding, but its generated tone/loopback is not a hardware driver or
SL3 proof. The required USB matching, provider topology, normal distribution
signing/entitlements and activation still need to be established.
[AudioDriverKit](https://developer.apple.com/documentation/audiodriverkit),
[Apple audio-driver sample](https://developer.apple.com/documentation/audiodriverkit/creating-an-audio-device-driver).

A separate candidate is an **Audio Server Driver Plug-in with an isolated
app-level USB owner**. Apple documents the HAL plug-in model, but transport
permission, signed helper lifecycle, IPC, real-time buffers and failure recovery
would need their own implementation. Its isolation model must not put USB calls
or unbounded waits on Core Audio callbacks. A successful virtual plug-in demo
would not establish physical SL3 audio.
[Apple HAL plug-in sample](https://developer.apple.com/documentation/coreaudio/creating-an-audio-server-driver-plug-in).

DriverKit entitlements are a distinct distribution gate. Apple associates them
with the developer team/profile and the requested hardware transports. USB
matching uses device/interface identifiers. Membership, transport approval for
this legacy third-party VID/PID, provisioning and notarization have not been
established; no request or purchase was made. Development instructions that
disable checks are not the intended deployment route.
[Entitlement requests](https://developer.apple.com/documentation/driverkit/requesting-entitlements-for-driverkit-development),
[USB matching entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.driverkit.transport.usb).

## Protocol and ownership to carry across

Reuse verified identities, endpoint descriptors, alternate-setting restoration,
bounded `0x30` rate getter and raw six-channel signed-24-bit format. Keep firmware
and unexplained control writes excluded. The portable continuous core already
separates pending, terminal and unproved requests and retains unsafe storage.
The Mac backend must supply its own API-specific completion/abort ownership,
bus scheduling and worker containment; Windows handles/jobs/mailboxes are not
portable Mac mechanisms.

Keep USB bus-frame values, Apple host timestamps and nanoseconds distinct.
`IOUSBHostTime` is an absolute-time type; it must not be copied blindly into the
Windows adapter's nanosecond field. Establish and preserve the Mac timebase and
the Core Audio sample/host-time relationship, including suspend/disconnect,
before claiming clock or latency accuracy. Packet geometry, physical channel
mapping, duplex continuity and routing need Mac-specific tests.
[Apple frame timestamps](https://developer.apple.com/documentation/iousbhost/iousbhostisochronousframe).

## Concrete first Mac experiment

When a target Mac is available, record its model, hardware architecture, exact
Tahoe build and whether OCLP is in use. Do not infer those from an Intel/Rosetta
process alone. From this repository on the Mac, with the SL3 connected for that
scheduled test, run:

```sh
python3 scripts/preflight-macos.py --collect --output tests/results/macos-first-preflight.json
```

The destination must not already exist. Return that JSON and the OCLP status.
Python 3 must already be available; the collector does not install tools. No
`sudo`, kext installation/unload, USB user client, capture/seize, firmware,
control request or audio transfer is used. Default invocation without
`--collect` only emits a plan. A non-Mac `--collect` is rejected before commands
or output-file creation.

The collector queries version/model/process translation, IOKit USB registry,
loaded-extension/receipt status, SIP/assessment status and developer-directory
metadata. It retains only exact SL3 identity/service projections, omitting raw
USB trees and serial properties. Registry aliases with known identity are
deduplicated; distinct devices remain separate. Service labels are observations,
not proof that an interface is available. Failed permission/command queries
remain unknown, rather than being interpreted as absence.

If the legacy kext exists at its default path, the collector asks Apple's
`codesign` to verify it and records selected bundle metadata. This is separate
from admission, loading, notarization and compatibility. SIP/assessment output
does not prove the Apple Silicon boot policy. OCLP status remains an explicit
owner-supplied fact.

Seven new collector tests pass with synthetic registry/command fixtures; all
27 Python tests pass together. Tests cover no-command plan/non-Mac guards,
identity filtering, aliases/distinct devices, serial-property omission, failed
queries, translated-process separation and signature-versus-admission status.
Only plan mode ran on this Windows host. Native C++/ASIO sources did not change,
so their earlier test checkpoint remains separate.

After this preflight, prepare a Mac-built descriptor-only IOUSBHost probe against
the actual SDK. Its first test must leave current interface/driver ownership
intact. Only after ownership and restoration are verified should it issue the
bounded rate getter, then separate finite IN capture, duplex and Core Audio
tests. Build success, successful enumeration and actual audio remain distinct.

## Serato and remaining requirements

Serato documents Tahoe support beginning with DJ Pro/Lite 4.0.1, while its SL3
hardware page still names 2.5.5/Catalina as the last supported Mac configuration.
OS-level software support therefore does not restore SL3 support. Mac installer
artifacts and architecture-specific current Serato analysis are still missing;
do not transfer Windows preferred VAs or assume identical descriptor consumers.
[Tahoe software status](https://support.serato.com/hc/en-us/articles/12934808677007-macOS-26-Tahoe-supported-Serato-software-status),
[SL3 hardware status](https://serato.com/dj/hardware/rane-sl3).

The full target still requires normal-security installation/removal, actual
Core Audio capture/playback/routing, latency/stability/reconnect/reboot recovery
and current Serato two-deck DVS. None is established on Mac. Reproduce this
checkpoint's package/API/plan/test bindings with
`scripts/export-macos-route-evidence.py` and inspect its
[bounded evidence](evidence/macos-route-preflight.json).

On 27 October, the current official Mac artifact was rechecked: `Serato DJ Pro 5.0.0.pkg`, 1,051,590,750 advertised bytes. The anonymous endpoint returned 403 and the existing signed-in browser's Mac download control still showed a page error, with no installer obtained. These are separate observations, not a proved common cause. [Exact artifact and provenance limits](artifacts.md#current-mac-application-artifact-still-missing--checked-27-october-2026). Current Mac executable analysis remains pending that file; Windows VAs and older Mac metadata are not substitutes.
