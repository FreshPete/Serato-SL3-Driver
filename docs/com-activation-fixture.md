# Windows COM activation fixture

Windows COM now resolves the explicitly simulated ASIO fixture, creates two successive IASIO objects, runs callbacks and retires both owners normally. This extends the previous tests that called `DllGetClassObject` directly. **Installed registry activation and normal Serato selection remain unverified.** [Pinned run and build evidence](evidence/com-activation-fixture-20261106.json)

## What actually ran

The standalone ordinary-user host in `diagnostics/asio-com-registration` starts with no fixture module loaded. Its successful case activates a private, registration-free Windows assembly manifest, calls `CoGetClassObject`, verifies the exact loaded file, configures the simulated provider through its existing test-only export, and obtains two successive objects through `CoCreateInstance`. There is no direct `LoadLibrary` or `DllGetClassObject` call in this host. Production ASIO code has no simulated-provider fallback.

Factory resolution creates no owner. Object construction remains idle until `init`. Each object initializes six input and six output channels, creates 128-frame buffers, starts real simulated callbacks, stops/disposes/releases and reports the module unloadable. Both controller results attest successful simulated I/O retirement, released device ownership, process exit and an empty job without requested termination. Callback counts from this accelerated fixture are not measured physical timing or audio quality.

The copied fixture resides in a path containing spaces and Unicode. Its bytes match the source-bound DLL from the existing native reference run. No production DLL, Serato binary or hardware backend is executed.

## Private registry alias limitation

The runner also generates the installer's three registration records, with their DLL destination redirected to the workspace fixture, and writes them only under a fresh private HKCU namespace. The owned host maps HKCR to that subtree and confirms an ordinary registry read resolves the expected `InprocServer32` file. On this Windows host, `CoGetClassObject` nevertheless returns `REGDB_E_CLASSNOTREG` with no DLL loaded. Before insertion and after removal it also returns that error.

This is a recorded limitation of the isolated test arrangement, **not evidence that the actual installed driver registration is broken**. The passing manifest case is separate and explicitly marked registration-free; it must not be reported as an installed-registry success or proposed as a replacement for the intended normal Serato launch. The genuine installed registration still needs the attended package test.

Microsoft documents [RegOverridePredefKey](https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-regoverridepredefkey) as a calling-process remapping mechanism intended for capturing installation writes. That does not establish that this arrangement exercises COM's installed activation path. [CoGetClassObject](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-cogetclassobject) documents class resolution and its class-not-registered result. The exact observation above is from our host, not an inferred guarantee for all Windows versions.

## Evidence and next step

Two inert build checks and four isolated runtime scenarios completed. The private namespace was removed and the live machine/user class and ASIO registration snapshots were unchanged. The current normal-start experiment manifest still verifies (`4ca890a6d5e7c2d232919374bc047f86387587b4c4bd7c50648549c964b57073`); its read-only Plan reports original archive, absent native package and Serato stopped. No UAC prompt, protected install, native USB acquisition or Serato launch ran.

Build with `scripts/build-com-registration-host.ps1`, then run `scripts/test-com-registration-activation.py` with the exact build-manifest and simulated-reference paths/hashes recorded in the evidence. This fixture is diagnostic code, not part of the production package. The next product-level observation remains [one-time setup followed by ordinary Serato startup](on-demand-normal-start-test.md).
