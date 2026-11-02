# Windows COM activation checkpoint

The ASIO component now has tests that call Windows `CoCreateInstance`, rather
than only calling the DLL's `DllGetClassObject` export directly. This advances
the host-loading boundary; it does not install an ASIO driver or establish
Serato support.

## What runs

`sl3_asio_activation_tests` creates three production objects in each of two
separate processes: one initialized as STA, the other as MTA. Each process
creates and activates a registration-free manifest for the project's own CLSID
`{5A551CD0-F83E-48EB-8B9D-8614E07852FE}`. The manifest specifies `Both` and is
created beside the intended DLL under a unique create-new filename. It is
deactivated and removed on normal test completion. No registry keys are written.

The test requests the driver's CLSID as its interface ID, as the ASIO Windows
loader does. It verifies canonical IUnknown identity and resolves the actual
implementation's vtable address back to the exact intended production DLL file.
An adjacent `sl3-asio.conf` must be absent before this test runs. Initialization
must report unavailable and unavailable metadata must preserve caller outputs.
There is no worker/helper/device operation in this test.

The controller lifecycle test adds separate `ordinary-sta` and `ordinary-mta`
clients. Each binds the controller's published, hash-pinned records through the
production configuration loader, explicitly configures the separately built
**simulated-provider test DLL**, and creates three objects using
`CoCreateInstance`. These exercise enumeration followed by four actual SDK
buffer/callback streams. Each controller audit must show exactly one acquisition,
eight clock inspections, four stream starts/stops and one final release. This is
synthetic audio and timing, not a positive native production DLL test.

The old direct-factory and blocked-callback destruction tests remain. The latter
does not use the COM runtime's DLL cache, so its assertion about caller unload
and independent callback/module retirement retains its original scope.

The manifest experiment first used a system-temp root manifest with
`lpAssemblyDirectory` pointing at the DLL directory. Creation/activation succeeded,
but `CoCreateInstance` returned `0x8007007e` (module not found). Placing the root
manifest beside its file entries resolved that failure on this host. The final
tests retain HRESULT diagnostics for future failures.

The later [session-locator checkpoint](asio-session-locator.md) implements the stable locator and first-session pointer publication described below. The later [withdrawal checkpoint](asio-pointer-withdrawal.md) adds explicit checked withdrawal and republication; installation is still pending.

The later [deployment-bundle checkpoint](asio-deployment-bundle.md) prepares verified payloads and the proposed locator/registry/ACL records. It does not apply them; protected staging and registration/uninstall are still pending.

## Deployment still to implement

The official locally reviewed ASIO 2.3.4 sources use an x64
`HKLM\SOFTWARE\ASIO\<driver-name>` entry with `CLSID` and `Description` strings,
plus the COM CLSID's `InprocServer32` DLL path and threading-model string.
Reference files are `common/register.cpp` and `host/pc/asiolist.cpp` in the local
SDK; SDK source is not redistributed here. Our own development name and CLSID
must remain distinct from Rane's registration.

The registration-free tests do not make an unmodified host discover the driver.
A deployment implementation still needs to do the following:

1. Stage a reviewed production DLL and matching worker/helper binaries in a
   stable local directory, verify hashes, and keep mutable configuration separate
   from administrator-owned executable files. Do not deploy the simulated DLL.
2. Resolve the current adjacent-configuration contract. The controller currently
   publishes to a new per-session directory, while the production DLL reads
   `sl3-asio.conf` beside itself. Registering a transient controller directory is
   not yet a reviewed deployment design. The stable, validated session-pointer mechanism is now implemented and
   tested; explicit withdrawal/republication is also implemented. Protected staging remains to implement before
   installation.
3. Add explicit x64 registration and uninstall operations with conflict detection
   and ownership checks. Preserve pre-existing entries; never overwrite another
   driver's registration or blindly remove a key. No persistent service, startup
   task, account or host modifications are required by the current design.
4. Verify enumeration and activation through an ordinary ASIO host, then obtain
   a genuine measured timing profile and perform attended input/silent-output
   and physical audio validation. The synthetic profile cannot be installed as
   a measurement.
5. Address [current Serato admission](current-serato-integration-decision.md)
   separately. Generic ASIO discovery does not supply the missing SL3 device API
   or demonstrate primary two-deck DVS integration.

The STA/MTA results support same-apartment object creation with this tested
manifest. They do not establish arbitrary cross-apartment interface marshaling,
concurrent control calls on one IASIO object, registry-based enumeration, native
USB startup, repeated USB acquisition, analogue audio or current Serato/DVS.
Control operations retain their existing single-owner contract; audio callbacks
remain on the separate bounded audio thread.

Microsoft documents the activation-context lookup used here in
[Creating Registration-Free COM Objects](https://learn.microsoft.com/en-us/windows/win32/sbscs/creating-registration-free-com-objects)
and the manifest fields in
[Assembly Manifests](https://learn.microsoft.com/en-us/windows/win32/sbscs/assembly-manifests).
Verification hashes and retained case inventories are recorded in
[`evidence/com-activation-20261102.json`](evidence/com-activation-20261102.json).
