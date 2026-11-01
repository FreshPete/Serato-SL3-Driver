# Current Serato ASIO object lifetime

The installed Windows Serato DJ Pro 5.0.0.1278 has concrete ASIO object release/recreation paths. **Keeping the SL3 acquired across Stop/Start within one driver object does not establish compatibility with the full application lifecycle.** The legacy backend releases an inspected interface and loads/initializes it again for actual stream open. The JUCE backend performs dummy I/O during device setup and can conditionally recreate its ASIO interface.

This is execution-free analysis of the original installed/extracted executable, both SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. Serato, its vendor libraries and native USB operations were not executed. No application/descriptor/account state, driver registration or security setting changed. [Machine-checked original-byte evidence](evidence/serato500-asio-object-lifetime.json).

## Legacy PortAudio path

| Stage | Preferred image VA | Verified behavior |
| --- | --- | --- |
| Enumeration setup | `142218a91` | Calls driver setup `142217040` on the selected/eligible name. Nonzero setup status skips this successful query path. |
| Setup | `142217050`, `14221709b` | Loads through `142222980`, then initializes through `142222020`, whose actual interface call at `14222207e` is IASIO `init`, slot `+0x18`. |
| Manager load | `142222a6f`, `142222a80` | Removes the current driver, then opens the selected registry entry. |
| COM creation | `142222410` | Actual PE import is `CoCreateInstance`, with in-process class context and the driver's CLSID also passed as IID. The returned interface is stored at driver-entry `+0x298`. |
| Successful enumeration unload | `142218ce9` | Calls `142221e80` after querying metadata/channel information, before completing the enumerated entry. |
| Interface release | `1422222f9` | Calls IUnknown `Release`, slot `+0x10`, then clears the stored entry pointer. The manager/global interface state is cleared through `142222af0` / `142221e80`. |
| Actual stream open | `142217361` | Calls the same setup/load/init chain again. Enumeration metadata is not a retained IASIO object for this open. |
| Ordinary stream stop | `1422182b1` | Calls wrapper `142222180`, which dispatches IASIO `stop`, slot `+0x40`. |
| Stream close | `142216ce4`, `142216ce9` | Disposes buffers, then performs the interface unload/release chain. Stop and Close have different lifetimes. |

This statement is conditional on the eligible named-driver enumeration path being reached. The initializer has name/API filtering; it does not prove that every registered ASIO driver is always initialized. Successful load/setup and later stream open nevertheless have separate interface lifetimes along this path.

The actual imports and calling-register setup are checked against the original PE. Slot meanings are checked against the official local ASIO SDK and Windows SDK IUnknown method order. The [upstream PortAudio ASIO implementation](https://github.com/PortAudio/portaudio/blob/master/src/hostapi/asio/pa_asio.cpp) corroborates the load/query/unload terminology; it does not identify the exact Serato fork/version. Original executable instructions are the evidence for this build.

## JUCE ASIO path

Validated Microsoft x64 RTTI identifies vtable `1431dd708` as `juce::ASIOAudioIODevice`; constructor `142208150` installs it. Its own virtual slot `+0x30` points to `14220f230`, the open operation. These JUCE-object slots are distinct from slots on its stored IASIO interface.

The constructor calls setup `142210950`. Setup releases an existing interface through `142211340`, creates one through `142212f30` and calls the real `CoCreateInstance` import at `142212f54`. The interface pointer is stored at complete-object `+0x38`; the CLSID is at `+0x60`. Initialization helper `14220e8c0` calls IASIO `init` at `14220e91a`.

On the successful setup path, dummy-buffer helper `14220d6f0` invokes IASIO `createBuffers`, slot `+0x98`. Setup then calls IASIO Start at `142210bee`, passes `0x50` to delay helper `142205170` and calls IASIO Stop at `142210c02`. The delay's selected branch forwards **80 ms** to the actual Windows `Sleep` import. This is a concrete requirement to survive initialization-time I/O; it is not a statement that Serato successfully ran our driver.

An ordinary open does **not** unconditionally recreate the interface. It runs setup if the stored pointer is absent. A separate branch at `14220f663` tests byte `+0x7b5`; when nonzero, it calls the release helper and creates/initializes another interface at `14220f688` / `14220f695`. The repeated release-helper calls are not proof of a double release: the helper clears the pointer after its first actual `Release`. Subsequent [reset-path verification](serato-asio-reset.md) identifies the flag writer: a Timer callback uses its +24 subobject receiver, closes the complete object, writes receiver `+0x79d` and reopens it. A bound ASIO message leaf reaches reset/resynchronisation scheduling. Runtime triggering/timing remains unverified. Device destruction also reaches the release helper at `142208ea3`.

The [upstream JUCE ASIO implementation](https://github.com/juce-framework/JUCE/blob/master/modules/juce_audio_devices/native/juce_ASIO_windows.cpp) provides semantic corroboration for dummy initialization and conditional reset/reload. It is not substituted for the installed executable or used to infer its exact bundled version or constants.

## Consequence for the rebuilt driver

Our currently built factory creates a new COM Device. Each successfully configured Device owns a DriverFacade containing one HostSession. The retained session survives successful Stop/Start and buffer recreation, but final owner destruction releases its device/process. The verifier checks these current source hashes against the tested Release manifest and built DLL.

Therefore the prepared [one-acquire/two-stream native probe](retained-lifecycle-probe.md) remains a necessary within-object transport test. Passing it will not prove safe enumeration-release/actual-open or successive-object recreation. The earlier staged hardware diagnostic already stalled during a second redirect after a successful getter/close. Application timing could differ; the static findings do not predict that every Serato open must fail. They make the cross-object boundary an explicit acceptance requirement rather than an untested assumption.

Before claiming application readiness:

1. Preserve the [passed retained native audio test](retained-physical-test.md) and its recovery evidence; it covers within-object lifetime only.
2. Inspect helper/kernel detachment and a defensible reacquisition readiness condition. Cached enumeration alone already failed to guarantee redirect readiness; an arbitrary delay is not proof.
3. Validate explicit successive IASIO object release/recreation and the appropriate initialization-time dummy I/O under tracing, after a reviewed startup change. Do not simply repeat the known failing rapid-reopen scenario.
4. Select any shared user-mode transport lifetime only after defining ownership, configuration identity, concurrent-client exclusion, blocked-callback retirement and final release. Do not hold a USB redirect indefinitely merely because an application inspected a driver, or infer that an elevated service is necessary.

The actual supported SL3 descriptor/backend route is still unresolved. The unchanged stub's empty audio fields do not establish either explicit ASIO route; discontinued support, current handshake integration and actual DVS remain separate requirements. There is no descriptor, executable or product/account-check patch in this work.

## Checked handle ownership

An execution-free source check excludes an easy but incorrect cleanup change. At the reviewed UsbDk commit `84752c30037956149d53b498005b5368616f9257`, [RedirectorAccess.h](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDkHelper/RedirectorAccess.h) returns its internal system handle; [DriverFile.h](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDkHelper/DriverFile.h) owns/closes that handle. The helper's StopRedirect destroys the redirector owner. The caller's system handle is borrowed, so an extra independent CloseHandle would be incorrect. This does not establish completed kernel/USB re-enumeration when StopRedirect returns. Header/source hashes are retained in the evidence; runtime ownership code was not changed.

## Reproduction and limits

```powershell
.venv/Scripts/python.exe scripts/export-serato-asio-lifetime.py
```

The verifier requires the exact installed/extracted original PE, local focused reports, reviewed SDK/reference files and current tested owner/DLL. It checks instruction boundaries against PE unwind regions; four small wrappers with no unwind metadata have explicit byte extents. Logical functions can span multiple unwind regions, so focused decompilation completion is not full control-flow coverage. No complete indirect-call recovery, debugger trace, actual backend selection, application timing, physical cross-object result or restored Serato/DVS operation is inferred.

The original lifetime investigation used the **38/38 Release, 38/38 Debug, 25/25 SDK-free and 64/64 Python** checkpoint. Subsequent controls-probe work brought the software baseline to **39/39 Release, 39/39 Debug, 25/25 SDK-free and 71/71 Python**. Neither static investigation is a newly executed application test.

The subsequent [USB-only removal/engine close investigation](serato-usb-audio-close.md) now links a guarded removal notification to these legacy Stop/dispose/Release calls, conditionally on an active selected legacy ASIO connection. It separates an authorization-service call from the actual audio notification. This extends static reachability; it does not supply live application dispatch, current SL3 admission or successful physical reacquisition.
