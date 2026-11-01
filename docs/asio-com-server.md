# Windows ASIO COM interface: unavailable-state build

An original x64 DLL now implements the complete official `IASIO` vtable and Windows class-factory/unload exports. It is built locally as `artifacts/build/native/{Release,Debug}/sl3_asio.dll`. **It is unregistered, cannot initialize an audio session, and does not restore SL3 or Serato audio yet.**

The optional SDK build produces this DLL alongside the tested buffer component. The two components are not connected by a live session. The DLL links neither USB transport nor buffer implementation at this stage. Loading it performs no device enumeration, helper loading, rate/control request, audio transfer, registration or trust change.

## Identity and host behaviour

The project has its own CLSID `{5A551CD0-F83E-48EB-8B9D-8614E07852FE}` and driver name `SL3 Rebuild Development`. It preserves the original Rane identity/registration. The official SDK's Windows loader (`host/pc/asiolist.cpp`) requests a driver's CLSID as the interface ID; the device supports that ID and `IUnknown`, with a canonical object identity.

`init` always returns false with an explicit unavailable-session error. Every audio/control method returns `ASE_NotPresent` and leaves caller outputs untouched. It does not report invented channels, clock position, latency or sample-rate availability. Name/version/error methods work before initialization. The real session must replace this state before any host registration or successful initialization is appropriate.

`DllGetClassObject` supports the project CLSID and returns an `IClassFactory`. Factories/devices have atomic reference counts and contribute independent module leases. Balanced `LockServer` calls hold the module even after the factory is released. Underflow/overflow is rejected; unknown interfaces/classes and unsupported aggregation fail with cleared result pointers. `DllCanUnloadNow` permits unloading only when both object and server-lock counts are zero. This follows Microsoft's [unload contract](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-dllcanunloadnow) and [server-lock contract](https://learn.microsoft.com/en-us/windows/win32/api/unknwn/nf-unknwn-iclassfactory-lockserver).

Only those two COM functions are exported. There are no registration/unregistration entrypoints or installer. No production registration layout or threading model is claimed yet. A module definition file provides the exports using the SDK's existing `STDAPI` declarations.

## Validation performed

Eleven native CTest entries pass in Release and Debug. The new test loads the actual local DLL with restricted dependency search and calls every ASIO method through the pinned official SDK interface. It covers failed init, unchanged caller outputs, unknown class/interface handling, null result pointers, aggregation rejection, canonical identities, object lifetimes, locks surviving factory release, counted unlocks, unload readiness and 1,600 concurrent device-creation/refcount/lock cycles across eight threads. It unloads the module afterward. No registry entry or hardware operation is involved.

A separate SDK-free build still passes nine tests with a deliberately nonexistent SDK directory. A changed private copy of `iasiodrv.h` is rejected during configuration. The original downloaded SDK is unchanged; its implementation is not copied into this project. The build manifest now pins `iasiodrv.h`, the export definition, DLL and test executable in addition to prior inputs. [Build evidence](evidence/asio-com-build.json).

## Remaining work

The DLL needs an isolated, validated device/session owner connected to the existing [buffer component](asio-buffer-component.md). That owner must handle real continuous input/output, serialize controls, establish rate/position/latency provenance and retire USB/callback leases safely. A stuck USB operation cannot be handled by terminating Serato's process. A subsequent [worker-process supervisor](worker-process.md) implements and tests the process/job lifetime boundary; IPC, continuous USB operation and buffer/callback ownership are still missing.

After that integration, test with a controlled ASIO host before making a distinct registration available. Current Serato's initial buffer/start/stop probe and its descriptor/backend/DVS routing remain independent requirements. This build supplies a tested host ABI and object lifecycle; it establishes neither a working stream nor Serato admission. [Recovered Serato contract](serato-supported-contract.md).
