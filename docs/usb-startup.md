# Original SL3 USB startup

Static analysis after the failed WinUSB trial identified a specific original-driver configuration sequence. It has not been replayed on hardware.

**Subsequent traced results:** the same WinUSB package started successfully at 22:50 UTC with all four interfaces at alternate 0, and read-only queries passed. The historical failure did not reproduce. The next authorized test at 22:59 UTC selected `[0,1,1,0]` through WinUSB, verified both audio pipes and restored both settings successfully, with matching USB trace statuses. The inbox route remains viable; status/clock/sample semantics are the next gate before transfers. [Binding result](windows-traced-test.md), [alternate-selection result](windows-audio-alternates-test.md). The investigation below retains the original-driver findings and pre-test reasoning.

Target is unchanged x64 `strmdrv.sys` 1.3.5f2, SHA-256 `e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5`, preferred image base `0x10000`.

## Decoded configuration path

- Embedded bind information at `0x16110` identifies `KmdfLibrary` 1.7.6001, 387 function entries, table VA `0x16220`.
- WDF function indices below 387 agree across the acquired 1.15 and 1.35 KMDF headers. This lets selected indirect calls be labeled without executing the driver. It is not a complete reconstruction of 1.7 ABI types.
- `0x19008` registers PnP/power callbacks. Prepare-hardware callback `0x19880` creates the USB target and calls `0x19b18` to retrieve its configuration descriptor. Callback identities are now checked against the registration instructions and the structure's field offsets.
- `0x19b18` calls `0x19c48`. For the four-interface personality captured from this unit, the latter builds 16-byte `WDF_USB_INTERFACE_SETTING_PAIR` entries by interface number:

| Interface | Selected setting index | Physical fixture |
| --- | --- | --- |
| 0 | 0 | Control-like interface, no endpoints |
| 1 | 1 | Isochronous OUT 0x06 |
| 2 | 1 | Isochronous IN 0x82 |
| 3 | 0 | Interrupt IN 0x81 / OUT 0x01 |

It passes configuration type **4 (`InterfacesPairs`)** to `WdfUsbTargetDeviceSelectConfig`, then obtains the configured pipes and prepares an interrupt reader. Setting index 1 corresponds to alternate value 1 in the captured fixture. A separate one-interface branch exists; it is not this unit's normal four-interface personality and must not be treated as the ordinary startup path.

[Mapped calls, callback registration, assembly and selected decompilations](evidence/rane-kernel-startup.json). Export with `scripts/export-kernel-startup-evidence.py`; full 45-function Ghidra output and the local project remain under ignored `analysis/`. The exporter verifies the SYS hash, embedded bind metadata, 387 common WDF indices and four callback-pointer stores. It never loads the driver. Fifteen selected functions contain 67 mapped WDF calls.

Microsoft documents the difference between an explicit setting-pair configuration and the framework's default-to-zero multi-interface configuration. [WDF configuration semantics](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdfusb/nf-wdfusb-wdf_usb_device_select_config_params_init_multiple_interfaces).

## Power-on ordering recovered on 26 October 2026

The zeroed callback structure is 0x88 bytes. Its established prefix registers these functions; the current headers contain a later extra field, so their complete structure size must not be substituted for the original's size.

| Callback field offset on x64 | Callback | Function |
| --- | --- | --- |
| +0x08 | EvtDeviceD0Entry | 0x1968c |
| +0x18 | EvtDeviceD0Exit | 0x197e0 |
| +0x28 | EvtDevicePrepareHardware | 0x19880 |
| +0x30 | EvtDeviceReleaseHardware | 0x19990 |

These offsets match the documented [callback structure prefix](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdfdevice/ns-wdfdevice-_wdf_pnppower_event_callbacks). The original register/store instructions are retained in the evidence, independently of Ghidra's incomplete inferred prototypes.

For the normal four-interface personality, the recovered path is:

1. **Prepare hardware:** select the interface settings above, obtain audio and interrupt pipes, and configure a 64-byte continuous reader on interrupt IN 0x81 with 15 pending reads and completion callback `0x114c8`. The reader's configuration is not its start. The driver then retrieves USB traits and rejects a device that is not at high speed (`traits & 4`, returning `0xC0000184`); remote-wake capability is merely recorded (`traits & 2`).
2. **D0 entry:** reset the audio IN pipe 0x82, then audio OUT pipe 0x06 (`0x196dd`, `0x196f7`). These are KMDF pipe-reset operations, not evidence of a USB-port power cycle or a firmware reset. Their return values are not checked here.
3. If request storage is absent, `0x11420` creates 15 requests per audio direction and associates preallocated 0x1358-byte buffers. This allocates request objects; it does not itself submit audio transfers. Failure here is propagated out of D0 entry.
4. Request 1 ms timer resolution. Send interrupt command **0x03**, with a zero payload, through `0x1184c → 0x116a0`. Then `0x118c4` attempts to retrieve a matching 3-byte response, starting from receive-ring sequence 1. Assembly recovers all six arguments that the decompiler omitted. The D0 code permits one attempt, not an unbounded retry, and compares the third payload byte to 0xC0. The meaning of that byte/branch is not yet established.
5. If the resulting context flag at +0x41 is zero, call `WdfIoTargetStart` on interrupt IN 0x81 (`0x19796`). This starts the previously configured continuous reader. Record successful start in +0xEC, then send command **0x36** with first payload byte **1** through `0x11a1c → 0x116a0`. This command is attempted even if starting the reader failed. Its physical meaning is not yet established.
6. Call `0x11a90`. **Only** if the requested-rate field at +0x2D180 is 44100 or 48000, send command **0x31** with the rate as two big-endian bytes, wait for a matching response, send **0x30** with zero payload, and verify the returned rate. The device context starts zeroed; this is not evidence that cold startup unconditionally selects either rate. The D0 callback does not propagate these command/response failures.

Microsoft explicitly distinguishes [configuring and starting a continuous reader](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdfusb/nf-wdfusb-wdfusbtargetpipeconfigcontinuousreader). The command-0x03 response lookup occurs **before** this start in the original instructions. On a first start, a fresh ring may therefore time out; a captured working trace is needed before treating this as a successful identity handshake or moving it after the reader. Do not silently reorder it in a purported faithful reproduction.

### Interrupt framing, not a vendor-control recipe

`0x116a0` allocates and zeroes 64 bytes, places the command in byte 0, stores literal bytes **1C C5 00 01** in bytes 1–4, and copies 59 payload bytes into bytes 5–63. It writes the complete frame to interrupt OUT 0x01 with a 100 ms timeout. `0x1184c` supplies a zero-filled payload with a two-byte argument at its beginning. `0x118c4` checks command and the same four literal bytes on received frames, scans at most four ring positions, and uses 50 ms waits when data has not arrived.

The interrupt completion callback only enqueues exactly 64-byte completions into a 500-frame ring and signals an event. These facts recover framing and call order; they do not establish every command's effects or authorize replay. In particular, 0x36 is not yet named “enable audio”, “LED” or “power”.

The helper has error recovery that stops the parent I/O target and cycles the USB port on `STATUS_INVALID_PARAMETER` (0xC000000D). That behavior must **not** be copied into a first probe; record and stop on the first failure instead. The EP0 control-transfer helper `0x11b80` belongs to the separate firmware-related paths and is excluded from the proposed startup experiment. No such request has been sent.

### Stop and release

`0x197e0` stops the interrupt reader if it had started, clears the streaming-active state through `0x12408`, and releases the timer-resolution request in the normal personality. It does not send a matching “0x36 = 0” command here. `0x19990` marks removal, waits in bounded increments for outstanding work, stops the USB target and selects configuration type 1 (`Deconfig`). Neither path proves a USB bus power-off sequence.

## Rationale for the traced test (now completed successfully)

The required change was **startup observability before the driver binds**. The earlier probe could not open the failed devnode, so adding `WinUsb_SetCurrentAlternateSetting` or interrupt commands to that probe could not repair the already-failed startup. Microsoft requires an initialized interface handle for [alternate-setting selection](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_setcurrentalternatesetting). That handle gate passed in the subsequent traced trial.

The controlled reproduction collected USB ETW spanning binding and read-only queries. Configuration, interface selection and start succeeded, so there is no failed startup transaction in this capture. The first run had only final PnP status. The original diagnostic specification and conditional decision table remain in [the test specification](usb-startup-next-test.md); see the subsequent result above before choosing a new kernel transport.

If the trace implicates configuration/alternate selection, the implementation candidate is a **minimal KMDF transport** that selects `[0,1,1,0]` during prepare-hardware and logs each operation/status. This is a distinct driver implementation and signing task; an INF-only WinUSB package does not provide our own prepare-hardware callback. First prove configuration and enumeration with no vendor/control or interrupt writes; later gate pipe resets and device commands separately. Do not put an unverified command sequence into an installer.

If the trace instead shows a hub enumeration or D0 transition failure before that selection, fix that earlier failure before writing a replacement driver. A global power-management tweak is not justified: the tested INF sets no idle values, and Microsoft's [WinUSB defaults](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/winusb-power-management) leave selective suspend disabled when `DeviceIdleEnabled` is absent. The current device's corresponding values are also absent; that current observation alone cannot reconstruct its exact registry state at the time of the failed trial.

## What remains unknown

The WinUSB trial failed during device startup, before our probe found an interface. We have not captured its actual configuration requests, alternate settings, USB status returns or power transitions. The original driver's explicit pair selection is therefore a concrete comparison target, **not a proven cause** of `STATUS_DEVICE_POWER_FAILURE`. Neither electrical damage nor firmware modification follows from that status; full power removal recovered the original descriptors.

The callback ordering and interrupt framing above are now recovered statically. A successful WinUSB-start trace exists. Still missing are a successful original-driver bus trace, the actual historically failing WinUSB request, and validated meanings for the startup command response/flag. Do not send undocumented commands or enter the one-interface firmware personality. Static inspection is not authorization to invoke firmware operations.
