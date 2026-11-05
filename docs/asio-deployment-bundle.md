# Verified local deployment review bundle

`scripts/prepare-asio-deployment.py` now prepares and independently verifies a
local package from the reviewed Windows x64 Release build. The package contains
exact executable bytes, a stable locator for a proposed installation, licences,
PE dependency metadata and an x64 registry plan. It does not install, register,
apply ACLs, start a process or open the SL3.

This is a review artifact, not a working-driver release. The later [registry-engine checkpoint](asio-registry-engine.md) implements and tests
the registry core in a private namespace. Protected staging and the complete
privileged install/uninstall wrapper remain unfinished. The later
[file-staging checkpoint](asio-file-staging.md) adds captured-byte verification
and actual workspace ACL checks, while recording the current production
ancestor-policy refusal.
The native broker, real timing/audio and current Serato/DVS gates remain open.

## Commands

No arguments or `--plan` produces JSON only, with no file writes or PE loads.
Preparation requires explicit paths and the reviewed build-record hash:

```powershell
$record = (Resolve-Path 'artifacts/build/native/native-build-Release.json').Path
$recordHash = (Get-FileHash -LiteralPath $record -Algorithm SHA256).Hash.ToLowerInvariant()
$helper = (Resolve-Path 'artifacts/extracted/usbdk-msi/UsbDkHelper.dll10').Path
$output = Join-Path $PWD 'artifacts/build/deployment-bundles/review-unique'
$installation = Join-Path $env:ProgramFiles 'SL3 Rebuild\review-unique'
$pointer = Join-Path $env:LOCALAPPDATA 'SL3Rebuild\current-session.txt'
.venv/Scripts/python.exe scripts/prepare-asio-deployment.py --prepare --manifest $record --expected-build-sha256 $recordHash --helper $helper --output $output --install-directory $installation --pointer $pointer
```

The output directory must be new and below this workspace's
`artifacts/build/deployment-bundles`. The command reads all source payloads and
validates them before creating output. Existing bundles are preserved. On an I/O
failure, a partial directory is retained for diagnosis; the complete manifest is
written last and verification must pass before preparation reports success.

The result supplies `bundleManifestSha256`. Preserve that reviewed hash and use
it for verification:

```powershell
.venv/Scripts/python.exe scripts/prepare-asio-deployment.py --verify --bundle $output --expected-bundle-sha256 <reviewed-lowercase-bundle-manifest-sha256>
```

For the bounded Phase diagnostic, pass `--unmeasured-diagnostic` during preparation and use the Release build record from `-WithUnmeasuredAsioDiagnostic`. The builder selects the separate diagnostic DLL and native broker, validates their distinct image hashes and required tests, and binds the timing mode into the manifest, package identity and install plan. Use a dedicated install directory and session pointer. The package uses the existing SL3 ASIO registration name and cannot be staged alongside another package using that name. The prepared 44.1 kHz review bundle passed file verification and the read-only System32 import check. It remains uninstalled.

Both operations need the existing analysis environment's `pefile` dependency,
already pinned in `scripts/requirements-analysis.txt`. PE inspection parses data;
it never loads or executes the packaged Windows DLLs/executables. Default plan
mode does not import that optional dependency.

## Provenance and contents

Preparation requires a tested x64 Release build with the ASIO component. It
checks every build source pin, the build/controller-test script hashes, the
exact successful CTest log hash/count and required COM/configuration/controller
coverage. Each executable must match its native build-manifest hash. The
controller digest must differ from the recorded simulated-controller digest.
The actual simulated-provider ASIO DLL is refused by its exports.

Every PE must be AMD64/PE32+ and match its DLL/executable role. The production
ASIO DLL must export exactly `DllGetClassObject` and `DllCanUnloadNow`; test
configuration exports are forbidden. The helper is restricted to the already
reviewed UsbDk 1.0.22 SHA256. Its bytes are unchanged, with Apache-2.0 text and a
third-party notice included in the local bundle. No kernel SYS, firmware,
Serato/Rane installer/application or ASIO SDK is copied. The public repository
continues to contain source and documentation, not these binary bundles.

The eleven payload files are:

- `sl3_asio.dll`, `sl3_broker_controller.exe`, `sl3_usbdk.exe`, `UsbDkHelper.dll`;
- `sl3-asio.conf`, pointing to the proposed protected broker location and a
  separate user session pointer, with broker/worker hashes;
- `PROJECT-LICENSE.txt`, `USBDK-LICENSE.txt`, `THIRD-PARTY-NOTICES.txt`;
- `deployment-plan.json`, `provenance.json`, `README.txt`.

`bundle-manifest.json` binds every payload's size and hash and reports that
installation, registry writes, PE execution and hardware validation did not
occur. The package identity binds the source builder/build-record hashes,
original binary/licence hashes and planned installation/pointer locations.
Verification checks that identity, exact inventory, payload hashes, PE metadata,
locator contents and registry/ACL plan. Extra, missing, changed or reparse
payloads and duplicate JSON fields are refused.

This checks consistency against explicit reviewed hashes. It is not a signing
service, proof against arbitrary same-user code, a certificate of measurement
quality or an independently attested build. An installer must validate the
reviewed artifact again at the privilege boundary.

## Installation plan and dependencies

The proposed installation is below `ProgramFiles\SL3 Rebuild`, with a separate
pointer below the current profile's `LocalAppData\SL3Rebuild`. Verification is
profile-specific as well. These locations are planning data only: neither operation creates the
installation or reads/writes session-pointer contents. Path-resolution metadata
queries can occur. A privileged
installer must derive trusted known folders, check the resolved paths and
current permissions, and refuse conflicts at execution time; environment-derived
planning paths are insufficient authorization for privileged writes.

The proposed protected DACL assigns ownership/control to Administrators and
SYSTEM, with Users receiving read/execute access. The x64 HKLM plan uses only
the project's own CLSID `{5A551CD0-F83E-48EB-8B9D-8614E07852FE}` and ASIO name
`SL3 Rebuild Development`, never Rane's identity. It records string-valued
`InprocServer32`, `ThreadingModel=Both`, `CLSID`, `Description` and package
ownership markers. `Both` has same-apartment STA/MTA activation coverage; it does
not establish arbitrary cross-apartment marshaling or concurrent IASIO control.

No registry API is called, and the ACL is not applied. **Do not register the DLL
in this writable review directory.** The plan requires new-destination checks,
conflict preservation and owned-entry uninstall; those operations still need
implementation. There is no elevated helper, service, automatic start, UAC
launch or security-policy change in the builder.

Import tables for the current first-party Release artifacts include
`MSVCP140.dll`, `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll` and Windows/UCRT API sets.
The helper's current import table uses Windows libraries. Full ordinary and
delay-import inventories are retained per image in `provenance.json`. Runtime
availability must be checked before installation. No runtime installer is
downloaded or executed, and the separately installed signed UsbDk filter remains
a prerequisite. No timing/profile file is included or fabricated.

## Verification scope

Run `.venv/Scripts/python.exe scripts/test-asio-deployment.py`. The current
26-case suite prepares a real positive bundle from the existing 59-test native
Release checkpoint, verifies exact byte copies, preserves an existing output,
and checks source/helper/build/log/coverage/kind refusals. It also checks the
actual fixture DLL, payload/inventory/JSON tampering, unsafe ACLs, and internally
rehash-consistent registry/locator/install-scope retargeting. No registry write or
binary payload execution occurs. Proposed installation/pointer locations remain
absent throughout the suite.

The native C++ build did not change at this checkpoint; its preceding Release
and Debug runs each passed 59 tests. No physical or installed-ASIO proof follows
from packaging. Retained hashes and cases are in
[the verification record](evidence/deployment-preparation-20261102.json).

## Later runtime and installation coordination

[Runtime/import admission and the install coordinator](asio-runtime-install.md)
now have 17 runtime and 20 isolated installer checks, including a composed
install/remove round trip. The original bundle remains byte-identical and its
README retains the scope of its preparation checkpoint. No protected production
installation or package-code activation has run; bootstrap, complete recovery
and native/physical/current-Serato validation remain unfinished.
