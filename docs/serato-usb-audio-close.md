# Conditional USB removal to legacy ASIO close

The original current Serato image connects the USB-only removal notification to an engine disconnect and, **conditionally on the legacy PortAudio ASIO backend being active**, IASIO Stop, buffer disposal and interface Release. This resolves the static final-close boundary left by the preceding [USB audio removal investigation](serato-usb-audio-removal.md). It does not prove live callback delivery, successful physical teardown or current SL3 audio admission.

The separate service call previously left opaque is an authorization service. It is not used as evidence for audio close and has not been modified or bypassed.

Target: unchanged Windows DJ Pro 5.0.0.1278, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. Addresses are preferred image VAs. [Exact original-byte, RTTI and leaf checks](evidence/serato500-usb-audio-close.json).

## Separate the service from the audio notification

The preceding disconnect routine calls singleton getter `0x141960f80`. The getter's initialization/store chain reaches factory `0x141960a60`, which selects one of two constructors according to a global flag. Exact constructor stores and RTTI identify `serato::authorization::RLMAuthorization` and `serato::authorization::JWTAuthorization`.

The selected factory branch and live instance are not observed. This investigation assigns no further meaning to their virtual slot +0x90, does not implement the identity transformation and does not call or change either service. The separate 0x2ca notification supplies the audio route below.

## Notification reaches engine disconnect

| Stage | Checked original-image link |
| --- | --- |
| Producer | The earlier `CUSBAudioManager` matching-removal branch constructs `UserIO_VoidPtrMessageData`, message 0x2ca, scalar payload zero, and publishes it. Its earlier identity/component guards remain. |
| Subscriber | `serato::dj::engine::Engine` constructor `0x141370760` installs vtable `0x142f29b28` and subscribes to 0x2ca at `0x1413718c3`. RTTI and vtable slot +0x18 bind handler `0x141373a40`. |
| Dispatch | The handler routes 0x2ca to `0x141373bce`, which calls message virtual slot +0x10. For the producer's `UserIO_VoidPtrMessageData` table, this slot is the exact three-byte constant-false getter at `0x1404a4550`. This is a type-specific virtual getter, not a generic test that every pointer payload is null. |
| State guard | It compares that false result with the engine byte at +0x2b0. An unchanged value returns. A change stores the value; false calls `0x141373130`. |
| Disconnect | That routine obtains the engine member at +0x1b8 and calls `0x141377800`. This checks its active-descriptor pointer and contains both `Audio connection, disconnecting aborted - already disconnected` and `Audio connection, disconnecting from '` diagnostics. |
| Owner closure | The active branch calls `0x14137a830`. If its connection at +0xc0 is non-null, it invokes virtual slot +0x10, clears that field and invokes the deleting destructor through slot zero. |

The same +0xc0 owner is populated from the audio selector `0x1421b8b80` in setup `0x141379a70`. The [existing audio-route investigation](serato-audio-routing.md) defines when an explicit legacy route or another backend can supply it. The unchanged SL3 stub does not establish a usable explicit route.

## Conditional legacy ASIO dispatch

For the legacy object type `serato::device::audio::PortAudioConnection`, validated vtable `0x1431d7248` maps close slot +0x10 to the exact tail thunk `0x1421e6120` → `0x1421e7ba0`.

That close function checks its active-state flag and passes the same raw-stream global to `0x1422155d0`, then, on its successful branch, `0x142215620`. These generic routines validate the stream and obtain its stream-interface table from raw stream +0x10. They check the stopped state and dispatch abort at table +0x18 and close at table zero, with explicit error/skip branches. Not every close invocation must execute every later operation.

The ASIO host initializer `0x1422187d0` initializes both callback and blocking stream tables at host +0x48/+0xa8. Its concrete close target is `0x142216c80` and abort target is `0x142216940`. The table-construction helper's exact stores and the ASIO-open interface-selection/store chain are checked; these are plain function tables, distinct from the C++ connection vtables.

| Operation | Checked ASIO target |
| --- | --- |
| Abort | `0x142216940` calls wrapper `0x142222180`; its dispatch is IASIO Stop at slot +0x40. |
| Stream close | `0x142216c80` calls `0x142221e60`, whose dispatch is IASIO disposeBuffers at slot +0xa0. |
| Interface unload | The close then calls `0x142221e80` → manager removal → `0x1422222d0`; its checked IUnknown Release call is at `0x1422222f9`, followed by clearing the stored interface pointer. |

The [prior lifetime verifier](serato-asio-object-lifetime.md) checks the official local ASIO/IUnknown method order and those concrete dispose/release wrappers. A software driver's Stop, buffer disposal and final object lifetime must therefore remain distinct. Retaining the USB redirect across stops in one COM object does not preserve it across final Release.

## Implication and remaining evidence

A discovery-removal input can reach actual backend teardown along this guarded legacy path. This gives a concrete reason to correlate USB identity changes with application callbacks and driver-object lifetimes. It is not evidence that every disappearance closes audio, nor that our current SL3 has reached the path.

The engine state must change, an active descriptor/connection must exist, the connection must select the legacy backend, and the raw stream must use the ASIO table for the final dispatch described here. Delivery, scheduling, current instance/backend, statuses and successful retirement have not been captured. The corresponding JUCE close chain is outside this result.

The next runtime evidence needs an admitted device and a correlated identity/message/ASIO lifecycle trace. First the prepared normal-token ownership/control test and safe repeated redirection still need hardware validation. No identity substitution, authorization/account change, application/resource patch, firmware request or Windows security change is introduced.

## Revalidation

```powershell
.venv/Scripts/python.exe scripts/export-serato-usb-audio-removal.py
.venv/Scripts/python.exe scripts/export-serato-asio-lifetime.py
.venv/Scripts/python.exe scripts/export-serato-usb-audio-close.py
```

These commands read saved original-image/source/SDK/build records only. Explicit leaf extents and individual unwind fragments are checked without pretending a single unwind record covers every logical C++ method. Native source/runtime inputs remain unchanged; the preceding 39/39 Release, 39/39 Debug, 125/125 Python and 25/25 SDK-free results were not rerun for this static-only change. No Serato/device/UAC operation ran.
