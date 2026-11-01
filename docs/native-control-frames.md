# Bounded control frames and original device exchange

The later [offline timer-reply comparison](timer-verification.md) now implements the recovered two-word calculation with a caller-supplied key and parsed reply. It has no runtime call site and performs no device I/O. Its current superset checkpoint is 29/29 Release and Debug, 21/21 SDK-free and 42/42 Python; the earlier counts below are historical.

Later extension: the [rate-selection transaction](rate-selection.md) now privately constructs the known 0x31 setter and requires fresh readback. A separate explicit native diagnostic now connects it to bounded I/O; streaming/IPC/ASIO startup do not change rates. No physical setter has run. The 27/19-test evidence below is the earlier getter/device-exchange checkpoint; the later rate evidence records current 28/20-test builds.

An original fixed-storage C++ codec now supplies the known SL3 getter frames,
strict reply/notification parsing and a four-received-frame budget. The native
UsbDk rate query uses this codec. New audio-control, overload and driver-timer
requests are constructed and tested offline only; they are not exposed through
worker IPC or invoked by a startup path.

Release and Debug each pass all **27** native tests. The SDK-free build passes
all **19** tests with a deliberately missing ASIO SDK path. No device access,
new USB command, application execution, driver installation, trust or security
change occurred in these tests. Positive native USB/audio and current Serato
DVS remain unverified.

## Original driver-API exchange recovered

The [historical descriptor](serato-legacy-sl3-descriptor.md) selects
`HANDSHAKE_TYPE_DRIVER_API`. A concrete original exchange is now recovered:

1. Serato 2.5.5's `RaneSL3API` loader `0x14069AFD0` resolves the actual export
   `sl3_driver_timer` into object +0x80.
2. Its API vtable `0x1447B9B08` slot +0x70 points to `0x140691980`. When the
   API is initialized, this function builds an eight-byte challenge, calls
   that export with eight-byte input/output sizes, transforms a copy locally
   and compares the real reply with it. Instructions `0x140691AA2` and
   `0x140691AB6` preserve the comparison and conditional success result.
3. The original Rane DLL export at `0x180007140` jumps to `0x1800068A0`.
   It requires input/output sizes of at least eight and calls helper
   `0x180009AC0` with selector **0x44**, operation 0 and the challenge.
4. That helper submits IOCTL **0x220010**, using a 0x48-byte request and
   0x40-byte reply. Kernel callback `0x1A168` handles that IOCTL and calls
   dispatcher `0x11E80` at `0x1A45F`.
5. The dispatcher's get-selector 0x44 branch selects interrupt command
   **0x37**, sends through `0x116A0` when the existing reader mode requires
   it, and consumes **eight reply bytes** through `0x118C4`.

Thus selector 0x44 is not the USB command byte. This path uses the ordinary
interrupt exchange, not the firmware-write helper. It is more than a registry
presence check. No constant-success result or locally emulated device reply
has been substituted for it.

Ghidra loses the Boolean return comparison in one focused pseudocode result.
The verifier checks the actual compare/conditional-move instructions. The
function also has three adjacent unwind regions; the checked comparison is
in the middle region. Do not infer its result from the truncated entry range
or the decompiler's inferred `void` declaration.

This establishes a static exchange path in the original software. It does not
prove current firmware acceptance, effects, timing or a completed application
handshake. The [current handshake map](serato-clock-handshake.md) still lacks
the historical DRIVER_API name. A real device response and a legitimate
current integration remain necessary. The codec itself provides framing only;
the separate offline comparison has no embedded key or application integration.

## Codec contract

Implementation is in `src/core/control_frames.hpp` and `.cpp`, with protocol
conformance/failure tests in `tests/native/control_frames_tests.cpp`.

| Request | Defined request payload | Defined reply bytes |
| --- | --- | --- |
| 0x30 rate | Zero | 2, big-endian; only 44100/48000 accepted |
| 0x32 audio-control table | Zero | 22, opaque bytes |
| 0x35 overload status | Zero | 6, preserved bytes |
| 0x37 driver timer | Exactly eight caller-supplied challenge bytes | 8, raw device response |

Every request is exactly 64 bytes, using tag `1C C5 00 01`; unused request
payload bytes are zero. Typed factories offer no arbitrary opcode or setter.
The complete defined reply is copied into a zero-initialized fixed event.
Remaining bytes are omitted, not interpreted as extra status or response data.

Asynchronous notification tags remain distinct:

| Command | Tag | Defined payload bytes |
| --- | --- | --- |
| 0x34 | `00 00 00 01` | 6 |
| 0x38 | `00 00 00 02` | 3 |
| 0x39 | `00 00 00 03` | 4 |

Up to three such notifications may precede the matching reply. A reply in the
fourth frame is valid; four notifications end the exchange with an explicit
budget error. Short/long/null frames, bad tags, unexpected commands and
unsupported rate values fail terminally. A late reply cannot revive failure
or extend the budget. Further input after success is rejected without
changing the earlier successful state.

Only a valid 0x30 reply establishes `rate_hz()`. Other replies never establish
a clock, device-response verification or audio readiness. A reported rate
continues to be readback rather than an oscillator measurement.

## Native integration and unchanged I/O lifetime

`read_rate` in `src/windows/usbdk_main.cpp` now constructs the typed rate
request and feeds replies through the codec. Existing `Transfer` ownership,
completion-byte checks, 100 ms OUT / 300 ms IN waits, cancellation/draining and
private-process fail-stop behavior are preserved. The actual native helper
still requires its pinned, already-running service and the exact device
fixture before opening or submitting anything.

No runtime call site constructs the additional three queries. There is no
new command-line mode, IPC command, rate setter, route setter, status-enable,
reset or firmware operation. The next live transport experiment remains the
prepared capture-first test with its existing getter; it does not silently
add a handshake exchange if capture fails.

## Historical control slices: further evidence, no writes

Original Serato function `0x140691C10` reads one-byte slices through the bound
`sl3_get_audio_controls` function. Its paired writer `0x140691CB0` uses the
bound `sl3_set_audio_controls` function and maps API channel indices as follows:

| API channel index | Table index | Slice size |
| --- | --- | --- |
| 0 | 14 | 1 byte |
| 1 | 20 | 1 byte |
| 2 | 8 | 1 byte |

The writer uses incoming byte XOR 1. The nearby callback export names and
descriptor through capability connect this area to through-state handling,
but physical jack order and which UI Boolean means enabled are not established
here. The native 0x32 reply remains an opaque 22-byte table. No native write
factory is supplied, and these indices are not used to change the device.

## Verification and reproduction

`scripts/build-native.ps1` now requires `sl3_control_frames_tests` and records
its binary hash and explicit physical-validation limits. Tests cover exact
original request layouts, both accepted rates, all three interleaved
notification types, reply in the final allowed frame, every short length,
oversized/null input, every reply tag byte, unrelated commands across all 256
opcodes, incorrect notification tags, unsupported rates, notification-only
exhaustion, terminal-state reuse and exclusion of undefined reply tails.

The full suites also exercise the existing process, queue, callback, ASIO and
missing-driver rejection paths. The read-only process check found no remaining
test/native worker process after completion. These remain simulated/negative
checks, with no positive native transport validation implied.

Run the following from the repository to reproduce the normal builds:

```powershell
./scripts/build-native.ps1 -Configuration Release -WithAsioComponent
./scripts/build-native.ps1 -Configuration Debug -WithAsioComponent
```

The separate `artifacts/build/native-without-sdk` configuration has
`SL3_BUILD_ASIO_COMPONENT=OFF` and a deliberately missing SDK root. Its 19-test
result is recorded independently.

Run `.venv/Scripts/python.exe scripts/export-control-frames-evidence.py` to
verify the [bounded evidence](evidence/control-frames-build.json). It checks
the three original image hashes, loader/export/vtable/IOCTL/interrupt path,
comparison instructions, focused reports, current native source/manifests,
Release/Debug logs and binaries, plus the separate SDK-free configuration.
The evidence contains no application key or full vendor implementation.

Remaining work includes a traced real-device exchange, the full current
connection adapter, physical control/through mapping, rate setting and
recovery, positive native PCM/timing and two-deck DVS.
