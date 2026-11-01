# Native UsbDk adapter — built, hardware run pending

**Superseding result, 30 October:** installation and restart are complete. Actual descriptor listing, input capture and silent USB output passed at 44.1 and 48 kHz, with normal security retained. See [first physical tests](first-physical-usbdk-tests.md). The original preparation and historical verification below are retained; its statements that no physical UsbDk run has occurred no longer describe the current checkpoint.

An original Windows x64 enumeration/capture adapter builds against UsbDk 1.0.22's C interface. Default execution is plan-only. **No UsbDk installation, helper load, device redirection or physical capture occurred in this work.** This candidate exposes the packet lengths needed for later playback; capture mode submits no audio OUT; an additional explicit silent-duplex mode is now prepared but unexecuted. [Transport/signature evidence](playback-transport.md).

## Dependency and device gates

Explicit list/capture modes first require an already-running UsbDk kernel service. The configured image path is resolved and its SYS file must match the reviewed `UsbDk.sys10` SHA256. This checks the service image **on disk**, not the admitted in-memory image or enforced policy; an actual traced load test is still necessary.

An explicit helper path is required. Its hash must match reviewed x64 `UsbDkHelper.dll10`; the file remains locked against changes/deletion while loaded. Dependency search is limited to its directory and System32. The helper imports only Windows system DLLs. Installation, hide-rule and reset exports are not resolved.

Before redirection, require exactly one VID 1CC5/PID 0001 device, high speed, and the complete recorded 18-byte device/235-byte configuration descriptors. List mode stops here. Two unchanged upstream Apache-2.0 interface headers and their license are tracked with commit/hash attribution under `third_party/usbdk`. No third-party kernel code is built or binary linked into the diagnostic. Build records cover these dependencies.

## Capture and completion ownership

Capture requires a fresh evidence directory. It redirects the selected SL3, performs one 0x30 rate getter, and selects alternate 1 on interfaces 1 and 2. The upstream fresh redirector selects the configuration. This helper has **no current-alternate getter**: API success is not claimed as readback. Cleanup explicitly returns both attempted audio interfaces to zero and stops redirection.

Four requests each contain 64 interval capacities of 126 bytes: 8 ms/request, **32 ms planned total**. The shared transaction engine distinguishes synchronous completion from asynchronous pending status. Buffers, packet arrays, request structures and OVERLAPPED events remain live through completion. Cancellation uses the redirector **system handle**, not the opaque device handle. A cancel request is not completion proof. Errors cancel all pending requests, then drain under a shared two-second bound. Unretired storage triggers process termination without C++ unwinding. A 20-second watchdog also bounds blocked synchronous APIs and teardown, without waiting on stream logging before termination. [Pinned helper I/O implementation](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDkHelper/DriverFile.cpp), [handle implementation](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDkHelper/UsbDkHelper.cpp).

UsbDk schedules ASAP URBs. This backend cannot enforce the shared engine's continuity hint and reports `continuity_verified: false`. Four completions do not prove a gap-free 32 ms recording or full-duplex timing. The WinUSB adapter retains its separate continuity requirement.

Native 64-bit packet status/length fields are validated **before** narrowing. Nonzero status, lengths over 126, partial 18-byte frames, invalid slices and overlap fail. Zero packets prevent success. Padding is ignored. Valid samples are repacked offline against the observed length sequence, with no output submission.

Records include request UTC bounds, Win32/USB/packet status, lengths, IN offsets, submission/completion counts and separate capture/cleanup outcomes. Raw buffers and PCM remain ignored local evidence. Progress is flushed before redirection, clock query, alternate selection and capture. Unknown values stop the test; they do not trigger 0x36, rate setters, routing, reset or firmware operations.

## Actual verification

- Release/Debug MSVC `/W4 /WX` builds pass. Request/result/device ABI sizes and offsets are compile-time assertions.
- The initial adapter checkpoint passed six CTest entries; the expanded suite now passes seven per configuration, adding the fixed-block bridge. [Latest combined build](evidence/audio-bridge-build.json).
- Read-only preflight verified artifacts, source/executable hashes and Microsoft driver signature index 1. It found **no installed UsbDk service** and the Rane SL3 error baseline. Unelevated Secure Boot querying lacked privileges: its field is **unknown**, not disabled. No security setting changed.
- After independently confirming service absence, a negative capture invocation exited 1/error **1060**, before helper load or redirection, with zero submitted/completed capture requests and audio OUT submissions.

These checks do **not** exercise live helper/driver code, redirection, alternates, native completion/cancellation, packets or hardware recovery. Shared core fault tests cannot replace those platform tests. [Build/preflight/negative-gate evidence](evidence/native-usbdk-build.json).

## Commands and pending gates

Read-only commands:

```powershell
./scripts/build-native.ps1
./scripts/build-native.ps1 -Configuration Debug
./scripts/preflight-usbdk.ps1
./artifacts/build/native/Release/sl3_usbdk.exe --plan
```

Preflight optionally saves a fresh JSON with `-OutputPath`. It never installs/starts a driver, loads the helper, redirects USB, changes trust or requests elevation.

After a **separate owner-present traced installation/load test**, descriptor-only enumeration would be:

```powershell
./artifacts/build/native/Release/sl3_usbdk.exe --list --helper ./artifacts/extracted/usbdk-msi/UsbDkHelper.dll10
```

After that result is reviewed, bounded capture would be:

```powershell
./artifacts/build/native/Release/sl3_usbdk.exe --capture --helper ./artifacts/extracted/usbdk-msi/UsbDkHelper.dll10 --output ./tests/results/local/usbdk-capture-01
```

Neither command installs UsbDk. Retain the prepared WinUSB capture-first test and establish the system-filter installation/recovery gate separately. No elevation prompt was left pending while the owner is away.

The additional bounded output mode is described separately in [duplex ownership and silent-output testing](bounded-duplex.md). Its real hardware command has not been invoked.
