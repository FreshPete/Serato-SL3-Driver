# SDK-facing ASIO buffer component

The original buffer controller now builds against official local ASIO 2.3.4 declarations. Tests use actual `ASIOBufferInfo`, `ASIOCallbacks` and `ASIOChannelInfo` layouts. **This is a static library and internal test executable, not an IASIO device, COM server, registered driver or live transport.**

A subsequent [COM DLL checkpoint](asio-com-server.md) adds the real host vtable and object lifetime tests. That DLL remains unregistered and unavailable, and is not yet connected to this component by a live session.

## Implemented contract

`src/asio/buffer_set.cpp` validates channel selection and block size before publishing any double-buffer pointer. Requests may mix logical channels/directions in arbitrary order; duplicates and invalid values fail. A failed create leaves caller pointers untouched. Proposed blocks are 64–1024 power-of-two frames; physical performance is unverified.

The component owns a callback-table copy and stable planar storage. Metadata reports Int24LSB type 17, logical channel names and selection state. Group zero avoids inventing physical jack/deck relationships. Buffer-flow start/stop/restart and disposal delegate to the core; repeated live start and callback-triggered stop/disposal fail.

Disposal stops this **buffer flow**, not a USB driver or worker. The future session owner must retire those operations and serialize access before freeing storage. This component is single-owner and does not establish live thread/object lifetime safety by itself.

Legacy `bufferSwitch` is required. It receives the bank and `ASIOTrue`, suggesting direct processing on the ordinary user-mode caller thread. The core also permits deferred completion before the next switch. No time-info support query is made and no time-info callback is invoked: host observation times are not yet established as hardware sample timestamps. Time-info-only hosts are rejected.

Invalid states/rates and handled allocation failures map to SDK error values. A throwing C++ callback faults the core and restores its callback-scope guard so controlled disposal remains possible. Buffer observations retain position/time for the future owner without advertising a proven clock.

## Verification

**Eight native CTest entries pass in Release and Debug** with this component enabled. The SDK tests cover real x64 structure sizes/sample type, shuffled channel mapping, double pointers, synchronous/deferred function-pointer callbacks, copying caller callbacks, exact startup delay, stable restart addresses, stop/disposal, reentrant-free rejection, atomic create failures, metadata, unsupported rates and callback-exception cleanup.

An initial Debug fault-injection test exposed an MSVC default-vector constructor that could terminate before the reserve error handler. Selection now uses fixed arrays followed by exception-propagating range construction. Both full suites pass without disabling iterator checking. Debug reports go to stderr; the SDK test has a 15-second timeout to prevent an unattended diagnostic dialog from stalling verification.

A separate build with SDK support off and its SDK path deliberately nonexistent passes **seven** tests. A modified-header configuration is rejected by the expected hash gate. The downloaded original SDK is unchanged. [Build and rejection evidence](evidence/asio-buffer-component-build.json).

These tests contain no USB/Serato/registration path. They do not prove live synchronization, callback deadlines, transport availability, IASIO/COM lifetime, latency or physical audio.

## Build and provenance

```powershell
./scripts/build-native.ps1 -WithAsioComponent
./scripts/build-native.ps1 -Configuration Debug -WithAsioComponent
```

This target is off by default. It reads the official SDK already under ignored `artifacts/references/asio-sdk-2.3.4/ASIOSDK`; CMake checks exact `asio.h`/`asiosys.h` hashes first. Manifests record external header inputs and whether SDK tests built/passed. No SDK source is copied into tracked files or linked as an implementation. Upstream license files remain with the local package; no distribution agreement or registration is implied by this private build.

Ordinary diagnostics/core tests remain independent of SDK availability. The original Rane ASIO registration is preserved.

## Remaining integration

Implement a real device/session owner that validates transport availability, marshals controls against streaming, retains I/O/callback leases and retires them before disposal. Establish actual clock/latency provenance before exposing a distinct IASIO/COM driver. An unconnected transport must fail initialization.

Current Serato descriptor/backend/DVS routing is still separate work. This component supplies tested buffer ABI/lifecycle behaviour without claiming restored support. [Serato requirements](serato-supported-contract.md), [stream-core contract](audio-bridge.md).
