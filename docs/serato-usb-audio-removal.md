# USB-only removal reaches the USB audio manager

The original current Serato application has a more specific removal route than the previously recovered device-list publication. A conditional **0x2d5** message reaches `CUSBAudioManager`, whose matching branch requests a service change, clears its selected name and publishes **0x2ca with a zero scalar payload**. The [follow-up](serato-usb-audio-close.md) now establishes a conditional legacy ASIO Stop/dispose/Release call chain through the separate engine notification, while identifying the earlier service as authorization. This page preserves the preceding producer/subscriber evidence. No live SL3 audio failure or working admission path is claimed.

Target: Windows DJ Pro 5.0.0.1278, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. Addresses are preferred image VAs. [Checked instructions, RTTI, getters and limits](evidence/serato500-usb-audio-removal.json).

## Producer and payload

The earlier [conditional composite removal](serato-usb-removal-dispatch.md) reaches `DeviceManager` callback `0x142140100`. Near its ordinary tail, calls at `0x142140ca1` and `0x142140cb2` test two component-presence predicates. Their helpers test pointer slots at composite +0 and +0x10. Either present component skips the following message construction. This is an additional guarded branch; earlier returns and runtime admission still matter.

When both pointers are absent, the callback obtains the descriptor shared pointer from composite +0x30, then calls its shared identity slots +0x18/+0x20/+0x28. For `ControllerDescriptor`, checked RTTI places that interface at complete +0x738; exact leaf getters read complete fields +0xa8/+0xaa/+0xac for VID/PID/revision. These are the [previously recovered identity fields](serato-descriptor-precedence.md).

It zero-extends each getter result to sixteen bits and constructs:

```text
payload = (VID << 32) + (PID << 16) + revision
```

At `0x142140e17`, message ID 0x2d5 accompanies that value into `0x14185ee90`; publication follows through sink slot +0x58. The constructor installs `UserIO_VoidPtrMessageData` and stores the 64-bit payload at +0x38. Its slot +0x38 getter returns that field directly. Despite the RTTI's pointer-shaped name, this producer/consumer uses a packed scalar without dereferencing it. No bus/address or raw USB identity string is included.

This publication precedes the ordinary collection removal/device-list message 0x2df. Searching only for consumers of 0x2df misses this separate path.

## Concrete subscriber and conditional disconnect

| Stage | Original-image check |
| --- | --- |
| Construction | `0x14070fd70` installs complete and +0x10-interface vtables with RTTI `CUSBAudioManager`. |
| Subscription | `0x14070fdfd` selects 0x2d5; `0x14070fe06` subscribes the +0x10 interface through `0x14154cd50`. The neighbouring 0x2d4 subscription is separate. |
| Handler | Interface slot +0x18 targets `0x1407108e0`. Its arithmetic dispatch routes 0x2d5 to `0x140710974`; 0x2d4 goes to a different branch. |
| Decode | The removal branch calls payload slot +0x38, unpacks three sixteen-bit values into EDX/R8D/R9D and adjusts the receiver by −0x10. It tail-jumps to `0x1407103b0`. |
| Identification | That function constructs the exact diagnostic `Disconnecting USB device`. Its VID/PID transformation and comparison with a service result from virtual slot +0x98 guard the following state change. Full transformation/service semantics are not assigned here. |
| Matching branch | It obtains the service through `0x141960f80`, invokes virtual slot +0x90 with EDX zero, emits other notifications, clears the manager's string at +0x50 and calls `0x14070ff10`. It then publishes message 0x2ca with a zero scalar payload through sink slot +0x58. |

The handler spans multiple PE unwind fragments. Checks validate the dispatch instructions and actual target fragment independently; an individual unwind entry is not treated as the whole C++ method. RTTI and exact construction/slot/receiver arithmetic are checked together, rather than inferring an audio role solely from nearby code or a message number.

## What this changes

There is now a concrete application-side candidate for USB identity removal affecting selected audio state. The subsequent [engine/legacy close analysis](serato-usb-audio-close.md) resolves the service as authorization and separately follows 0x2ca into guarded engine disconnect, connection closure and conditional legacy ASIO teardown. Live delivery and selected-backend success remain unproved; neither follows merely from a class name or diagnostic string.

A future ownership/identity trace can measure sampled discovery behaviour; it still cannot establish these application callbacks or their guards. The current SL3 is not admitted for audio in Serato, and a future USB-only integration is not guaranteed to instantiate this route. No changed identity has yet been correlated with running Serato Stop/dispose/Release. The actual libusb baseline also showed slow enumeration, so absence of a sampled change cannot prove uninterrupted identity. [Measured observation limits](usb-identity-baseline.md).

No application modification, identity substitution, account operation, firmware request, driver rebind, ASIO registration or security change follows from this result.

## Revalidation

```powershell
.venv/Scripts/python.exe scripts/export-serato-descriptor-precedence.py
.venv/Scripts/python.exe scripts/export-serato-usb-removal-dispatch.py
.venv/Scripts/python.exe scripts/export-serato-usb-audio-removal.py
```

These checks read the original installed/extracted image and verify the original-byte links. They do not execute Serato or contact the SL3. Native sources/runtime binaries remain unchanged from the 39/39 Release, 39/39 Debug and 125/125 Python checkpoint; those suites were not rerun for this static-only change. SDK-free 25/25 remains preceding evidence.
