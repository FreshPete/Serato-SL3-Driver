# Current Serato ASIO reset path

Original installed Serato DJ Pro 5.0.0.1278 bytes now establish the previously unresolved writer of the JUCE recreation flag. An ASIO reset or resynchronisation request can schedule a Timer callback that closes the device, sets the flag and reopens it. Open then releases and recreates the stored IASIO interface. This makes successive interface lifetime a concrete integration requirement beyond the already passed within-object retained transport test.

This is static analysis of the unchanged installed/extracted x64 executable, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. No Serato execution, USB test, registration, policy or firmware change ran. [Checked original-byte evidence](evidence/serato500-asio-reset.json).

## Callback binding and selector dispatch

The constructor stores the complete device pointer in active-slot array `1440b7530`. Both dummy-buffer setup and ordinary Open have a special slot-zero path: the callback structure at complete-object `+0x40` receives leaf `14220a820` in member `+0x10`. The official local x64 ASIO SDK identifies this member as `ASIOCallbacks.asioMessage`; the structure is passed to IASIO `createBuffers`. The leaf loads active slot zero, returns zero if absent, and otherwise passes the complete device plus selector/value to common handler `14220a8e0`.

The leaf has no PE unwind entry. Its explicit byte extent `14220a820:14220a83b`, including both tail-jump and null-return paths, is checked separately. An unwind-only caller search missed it. The handler's switch table is inline data at `14220a94c`, decoded as 15 image-relative destinations rather than instructions.

| Selector | SDK meaning | Direct dispatch | SelectorSupported result |
| --- | --- | --- | --- |
| 2 | Engine version | Returns 2 | 1 |
| 3 | Reset request | Schedules Timer with interval argument 500; returns 1 | 1 |
| 4 | Buffer-size change | Same scheduling path; returns 1 | 0 |
| 5 | Resynchronisation request | Same scheduling path; returns 1 | 1 |
| 6 | Latencies changed | Returns 1 | 1 |
| 10 | Input monitoring support | Returns 0 | 1 |
| 15 | Overload | Increments complete-object `+0x7b8`; returns 1 | 1 |

The support-query mask is exactly `0x846c`. Its disagreement with direct dispatch for selectors 4 and 10 is preserved. In particular, this does not advertise buffer-size-change support. Selectors 7–14 directly return zero; selector 1 implements the support query itself. Names and callback order are verified against the local official ASIO SDK, not guessed from the switch.

## Timer receiver and recreation

Both complete-object and secondary-vtable Microsoft RTTI identify `juce::ASIOAudioIODevice`, with its `juce::Timer` base at complete-object **+24**. Construction installs secondary vtable `1431dd7d0`; its callback slot points to `142212da0`.

The callback receives that Timer subobject. Consequently its write at `142212df8` to receiver `+0x79d` is the complete-object flag **+0x7b5** tested by Open. Searching only for the complete-object displacement missed the writer.

The checked non-modal path stops the timer, saves the existing audio callback, calls complete-object Close through virtual slot `+0x38`, sets the flag and invokes complete-object Open through slot `+0x30`. It supplies the stored buffer size, sample rate and channel selections. Afterward, if the saved callback is non-null, it passes it to complete-object Start through slot `+0x48`. The modal branch instead schedules the same Timer with interval argument 100. These are scheduling arguments; no runtime deadline was measured.

Open at `14220f663` tests complete-object `+0x7b5` and enters the release/create/init chain already verified in [object lifetime evidence](serato-asio-object-lifetime.md). The [upstream JUCE implementation](https://github.com/juce-framework/JUCE/blob/master/modules/juce_audio_devices/native/juce_ASIO_windows.cpp) corroborates these method roles; its version and constants are not substituted for the installed executable.

## Consequence and next physical gate

The [native retained test](retained-physical-test.md) passed two silent streams and buffer recreation under one acquisition. This does not prove a second IASIO object can reacquire the SL3 after the first is released. The earlier repeated-redirect diagnostic stalled, and the [reviewed UsbDk detach path](usbdk-detachment.md) still does not supply a proven reacquisition-readiness condition.

Before application deployment, the implementation must survive initialization dummy I/O and explicit interface destruction/recreation, with independent retirement of callbacks, buffers, worker and USB ownership. A future traced test must establish those boundaries and kernel detach/readiness after a reviewed startup change. The 500 interval argument is not permission to replace readiness with a fixed delay or repeat the known failing rapid reopen. Sharing transport between COM objects would require an explicit lifetime and client-exclusion contract; this investigation introduces no broker or indefinite device hold.

Actual SL3 backend selection, other active-slot callback bindings, external device-change window dispatch, runtime reset timing, physical cross-object startup, analogue/timing measurements and current Serato/DVS remain unverified.

## Reproduction

```powershell
.venv/Scripts/python.exe scripts/export-serato-asio-reset-evidence.py
.venv/Scripts/python.exe scripts/export-serato-asio-lifetime.py
```

The reset exporter checks original PE hash, installed-image equality, both RTTI locators/base descriptors, constructor vtables, callback binding, explicit leaf boundaries, dispatch data, SDK names and exact instructions. It does not require a new Ghidra report or execute vendor code. Native build inputs remain unchanged; the existing 39/39 Release, 39/39 Debug, 25/25 SDK-free and 71/71 Python software checkpoint is not a new physical or application result.
