# Current Serato: explicit audio routing and legacy backend

Serato 5.0.0 retains an explicit legacy PortAudio route as well as its newer audio-device manager. The SL3 stub's empty audio fields would select the **default OS connection branch**, if the stub reached this audio selector. Its true legacy flag is not consulted in that branch. This narrows the integration problem beyond the discontinued-support flag; no application or driver registration was changed.

The target remains Windows x64 5.0.0.1278, SHA256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. These are static findings, not an observed call trace or successful application connection. [Machine-code evidence](evidence/serato500-audio-routing.json).

## The audio-field gate comes first

`AudioConnectionController` setup `0x141379A70` calls selector `0x1421B8B80` with its audio-descriptor interface. The selector first calls interface slot +0xC0. For `ControllerDescriptor`, that slot is getter `0x1405C7E00`.

The complete getter checks **four string lengths**, not three. Its receiver is the interface at complete-object +0x10; the apparent +0x360/+0x380/+0x3A0/+0x3C0 displacements address string lengths at complete-object +0x370/+0x390/+0x3B0/+0x3D0. Parser references and destinations identify their names:

| String | Complete-object string offset | Default |
| --- | --- | --- |
| `win_audio_api` | +0x360 | Empty |
| `mac_audio_api` | +0x380 | Empty |
| `win_audio_device_name` | +0x3A0 | Empty |
| `mac_audio_device_name` | +0x3C0 | Empty |

The getter returns true if **any** length is nonzero. The constructor initializes all four to zero. The identity-only SL3 helper does not populate them. This is an explicit-string predicate; it does not query channel counts, clock state, a driver or licensing.

When false, selector `0x1421B8B80` logs `Attempting to get Default OS connection` and calls `0x1421B8030`, which obtains default names through the newer audio-device manager and then uses the generic connection wrapper. It does not query legacy flag slot +0x08 along this branch. A true legacy flag by itself therefore does not create an explicit SL3 audio route.

## Explicit Windows selection

When the predicate is true, the selector obtains the Windows audio-device name through shared virtual-base slot +0x38, getter `0x1405C6500`. Validated RTTI places that base at complete +0x738; the getter copies from receiver −0x398, yielding complete +0x3A0. This is separate from interface +0x38 in the supported-app map interface.

| Windows device-name length | Selector | Additional inputs |
| --- | --- | --- |
| Zero | `0x1421B80C0` | Descriptor VID/PID, API string, legacy flag |
| Nonzero | `0x1421B8580` | Device name, API string, legacy flag |

Both reject missing required identity/name inputs. Both use the legacy flag obtained from audio-interface +0x08. When false, they refresh `AudioDeviceManager`, select matching device information, and use generic connection creation through `0x1421B7F50` → `0x1421E9820`. When true, they use the embedded `PortAudioConnectionFactory`.

The embedding is established by manager constructor `0x1421B7E50`, which constructs its +0x08 member through `0x1421C27A0`. That leaf constructor installs vtable `0x1431D48F8`; its validated RTTI names `serato::device::audio::PortAudioConnectionFactory`, with enumeration at slot zero `0x1421C2840`.

## Legacy matching and API forwarding

The legacy VID/PID selector `0x1421C2DF0` compares both identifiers against enumerated connection getters. The legacy named selector `0x1421C2F80` uses **case-sensitive substring matching**: it searches each enumerated device name for the requested descriptor name. The call resolves through thunk `0x1421202B0` to `VCRUNTIME140.dll!strstr`, verified against the PE import table. Both selectors retain the last matching entry encountered; enumeration order is not established. A unique rebuilt device name will be needed to avoid ambiguity.

The named selector's Ghidra declaration lists only three parameters. Machine code shows the incoming API argument remains in R9 at the indirect enumeration call, while the device-name string is forwarded as the fifth stack argument. Do not infer that the API is ignored from the shortened decompilation. The enumerator checks the requested API's mapped type against each host API's type and passes its name list into the initialization call.

Legacy API-map initializer `0x1421E5810` stores `ASIO` → 3. This agrees with the stable `paASIO` value in [PortAudio's public header](https://github.com/PortAudio/portaudio/blob/master/include/portaudio.h). It does not establish the exact bundled fork/version or prove initialization succeeds. Enumeration includes initialization and connection construction; treat it as potentially exercising an ASIO driver, not as a passive registry read.

## What this changes for the rebuild

There is now a concrete **candidate** route for the future driver: an explicit Windows ASIO API/name configuration, a unique enumerated driver name, and deliberate selection of the retained legacy or newer backend. This is a requirement for a later integration experiment, not a discovered supported configuration mechanism. The application's SL3 support state is still 2, its aggregation defaults still expect a MIDI component under a support-1 counterfactual, and no external descriptor override has been established.

The [development ASIO DLL](asio-com-server.md) still needs an admitted isolated audio session and timing configuration before production initialization can succeed. Real audio, clock/latency and buffer retirement must be validated before deployment. Product/account checks remain independent. [Input endpoint](serato-endpoint-consumers.md) and [output routing](serato-output-routing.md) consumers have separate conditional evidence; actual device admission, physical mapping and DVS operation remain unverified. Obtaining a matched audio connection would not establish DVS compatibility.

The subsequent [packed-24 path](serato-packed24-path.md) verifies the original legacy backend's type-17 mapping, byte width and conditional float converter table selection. It supplies the candidate sample-format bridge while preserving the distinction between static format support and an admitted, working SL3 session. Runtime backend choice, final audio invocation and physical routing still need validation.

Reproduce the evidence with `.venv/Scripts/python.exe scripts/export-serato-audio-routing-evidence.py`. It verifies the original PE hash, field/parser destinations, getter offsets, selector machine instructions, concrete factory RTTI, forwarded ABI arguments and the actual imported matcher. Full focused reports remain locally under ignored `analysis/`; exported evidence is bounded and does not require running Serato. [Earlier supported-device contract](serato-supported-contract.md).
