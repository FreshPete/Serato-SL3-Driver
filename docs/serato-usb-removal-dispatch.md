# USB removal: device-manager dispatch and remaining audio boundary

The original current application has a conditional path from composite removal to a scheduled `DeviceManager` callback and an updated device-list message. The [subsequent USB-only notification/engine investigation](serato-usb-audio-close.md) establishes a conditional legacy ASIO close call chain; an actual running SL3 removal/close remains unverified. This extends the [USB identity/removal analysis](serato-usb-discovery.md), without treating a possible discovery change as a captured audio failure.

Target: original installed/extracted Windows DJ Pro 5.0.0.1278, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. Addresses below are preferred image VAs. [Exact instruction, RTTI, selector and report checks](evidence/serato500-usb-removal-dispatch.json).

## Checked route

| Stage | Original-byte evidence |
| --- | --- |
| Composite removal | The earlier matched consumed-USB path reaches `0x1421c0970`. Its call at `0x1421c0aa7` reads the composite byte at +0x60 through the five-byte getter `0x14080e0a0`. Full lifecycle semantics of this flag remain unproved here. |
| Conditional notification | A zero byte skips notification construction. The nonzero branch stores action **1** at `0x1421c0ad0`, constructs `DispatchDeviceDeferredAction` through `0x1421de6b0` and queues it through `0x1421de0a0`. The constructor stores the selector at action +0x28. |
| Action dispatch | `0x1421de890` reads action +0x28. The checked jump-table entry for 1 targets `0x1421de965`, which selects observer slot **+0x10**. This is separate from the previously verified discontinued action 0x0e/slot +0x70. |
| Concrete observer candidate | `DeviceManager` RTTI validates the +0x88 interface and vtable `0x1431c3f28`; slot +0x10 is `0x142140060`. It schedules callback `0x142140100` through `0x14213ae20`, passing complete object `receiver-0x88`. This is static binding, not proof of the live instantiated receiver. |
| Ordinary callback path | `0x142140100` has earlier conditional branches/returns. Its ordinary tail calls collection removal `0x140bff5c0` at `0x142140e75`, using the collection held at complete object +0x150. The collection helper obtains its key via `0x140c00a40`, which copies the composite string at +0x40, then removes a found entry. This key is distinct from the raw USB record's string at +8. |
| List publication | The callback copies the remaining collection and invokes `0x142141ba0` with publication state at complete object +0x160. When configured and its change checks permit publication, that helper builds a `UserIO_TemplateMessageData<DeviceList>` object and dispatches through its configured sink slot +0x60. |
| Message identity | `DeviceManager` construction initializes that state from checked constants at `0x1431c4470`: message ID **0x2df** and zero auxiliary fields. Constructor, payload RTTI and original stores are checked together. |

The composite notification is conditional, callback paths differ, and publication itself has configuration/change guards. This analysis does not claim every enumerated disappearance necessarily reaches every subscriber. Subsequent analysis found a separate guarded **0x2d5** packed-identity message to `CUSBAudioManager` before list publication; its matching branch publishes 0x2ca with zero payload. [Checked USB audio removal path and remaining final-close boundary](serato-usb-audio-removal.md).

## What this changes for the next test

The [prepared one-acquisition USB/WPP/identity diagnostic](controls-probe.md#optional-identity-observation-in-the-shared-trace-window) can establish sampled identity behaviour while the rebuilt worker acquires and releases the SL3. It does not execute or trace these application callbacks. Current SL3 admission, the live +0x60 flag, observer identity and dispatch scheduling remain separate questions.

If a successful snapshot records changed bus/address or absence, use that as evidence for a possible discovery-removal input. Do not describe it as proof that Serato stopped audio. If no change is sampled, brief changes may still have been missed. The application-side follow-up is to trace the admitted device's audio consumer of the changed device collection and correlate an actual Stop/dispose/Release sequence with removal delivery. The existing [ASIO object lifetime](serato-asio-object-lifetime.md) and [reset path](serato-asio-reset.md) establish other close/recreation mechanisms independently.

An immediate-constant search located several subscribers to message 0x2df, but it is not exhaustive. RTTI identifies inspected candidates as preferences, device-name, deck, pad, layout and application controls. Their proximity to audio code or subscription alone is insufficient to label them an audio-backend close path. No second libusb opener, permanent identity substitution, arbitrary delay or resource patch follows from this result.

## Reproduction and limits

```powershell
.venv/Scripts/python.exe scripts/export-serato-usb-removal-dispatch.py
```

The exporter verifies the original installed/extracted image, exact instructions, raw flag getter, action-1 jump-table entry, receiver adjustment, action/manager/payload RTTI and list-message constants. Its report metadata lists selected PE unwind extents used with `FocusedDecompile.java` for the local focused reports. Decompiler parameter types are not ABI proof.

Verification passed. Native sources/runtime binaries and the previous 39/39 Release, 39/39 Debug, 105/105 Python and preceding 25/25 SDK-free evidence are unchanged; those suites were not rerun for this static analysis. No application/device/UAC, account/resource/registration, firmware or security operation ran. No actual SL3 removal-to-audio-close trace or current Serato/DVS session is claimed.
