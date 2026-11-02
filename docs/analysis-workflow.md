# Reproducible analysis workflow

Run from the repository root. Vendor programs are not executed by these extraction steps.

## Tools

Observed host tools: PowerShell 7, Python 3.13.11, Node 22.21.1, Git 2.52.0, Java 17 (and an older Java 8), 7-Zip 25.01, CMake, .NET and Visual Studio 2019 Enterprise. A Windows SDK including SignTool 10.0.19041 is present. `cl`, `dumpbin`, Ninja and WDK build tooling were not found through the initial command/path checks; do not treat this as a configured native-driver build machine.

Project-local toolchain: Node 24.22.1, Temurin JDK 21.0.9+10, Ghidra 12.1.4, REA 6.8.0 and innoextract 1.9. Downloads/hashes are in the provenance ledger. Node's SHA-256 matched the official SHASUMS256 entry. No global tool upgrade or Codex MCP registration was performed.

To restore the analysis Python environment:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r scripts/requirements-analysis.txt
```

Tools were downloaded with `scripts/fetch.py` and extracted under `tools/`. REA installation used the isolated Node directory on PATH and:

```powershell
$env:PATH = (Resolve-Path tools/node-v24.22.1-win-x64).Path + ';' + $env:PATH
npm install --prefix tools/rea rea-agents@6.8.0 --ignore-scripts --no-audit --no-fund
./scripts/rea.ps1 doctor --provider ghidra --json
```

`--ignore-scripts` was used; successful real provider operations, not just npm completion, verified that the distributed native bundle works here. Doctor's global summary also lists missing unrelated providers/client registrations. Inspect the selected Ghidra checks separately.

## Rane packages

Source links were recovered from the archived official page listed in artifacts.md. Use the exact case-sensitive filenames:

```powershell
python scripts/fetch.py https://cdn.inmusicbrands.com/rane/legacy-product-downloads/RaneAsioSl3Ver1.3.5f2.zip artifacts/downloads/RaneAsioSl3Ver1.3.5f2.zip
python scripts/fetch.py https://cdn.inmusicbrands.com/rane/legacy-product-downloads/Sl3-2.0.1f2.zip artifacts/downloads/Sl3-2.0.1f2.zip
& 'C:/Program Files/7-Zip/7z.exe' x artifacts/downloads/RaneAsioSl3Ver1.3.5f2.zip -oartifacts/extracted/rane-windows -y
tools/innoextract/innoextract.exe --extract --collisions rename --output-dir artifacts/extracted/rane-windows/all-variants artifacts/extracted/rane-windows/RaneAsioSl3Setup.exe
```

Keep collision variants. `$0` files in this installer are x64; unsuffixed final variants are x86. Verify PE machine and INF decorations, rather than inferring architecture from extraction order. Normalized copies in `rane-windows/x64` retain the original file bytes. Always use `-LiteralPath` or single quotes around filenames containing `$`.

Mac extraction is ZIP → XAR (`Sl3.pkg`) → gzip (`Payload`) → CPIO (`Payload~`). Use 7-Zip at each layer, then `python scripts/macho-report.py artifacts/extracted/rane-mac/tree docs/evidence/rane-mac-macho.json`. Package install/uninstall scripts were inspected as text, not executed. Signature verification needs a Mac with `pkgutil`/`codesign`.

## Serato Burn/MSI packages

```powershell
python scripts/carve-cabs.py 'DJPro/Serato DJ Pro 2.5.5/Serato DJ Pro 2.5.5.83_64bit_Installer.exe' 'artifacts/extracted/Serato DJ Pro 2.5.5'
```

7-Zip verifies/extracts each carved CAB. The bootstrap CAB's `0` file is the Burn XML manifest, mapping `SourcePath` values to real payload names. For 2.5.5 and 2.5.6, the attached container's `a0` is the main MSI. Read it with `scripts/read-msi.ps1`, which opens the Windows Installer database read-only; it does not call `msiexec`. Extract its `product.cab`, then restore names:

```powershell
./scripts/read-msi.ps1 -Path 'artifacts/extracted/Serato DJ Pro 2.5.5/payloads/a0' -Output analysis/msi255.json
python scripts/restore-msi-files.py analysis/msi255.json 'artifacts/extracted/Serato DJ Pro 2.5.5/files' 'artifacts/extracted/Serato DJ Pro 2.5.5/tree'
```

Use the same sequence for 2.5.6. In 5.0.0, Burn splits models/drivers/main app into separate containers: `a1` is drivers MSI and `a5` is main MSI. Main app files were restored to `tree/PFiles64/Serato/Serato DJ Pro`; driver resources to `drivers-tree/PFiles64/Serato/Serato DJ Pro/bundles`. Driver bundles have opaque `.bin` contents; they have not been falsely inventoried as extracted SYS/INF packages.

## PE and REA work

```powershell
.venv/Scripts/python.exe scripts/pe-report.py 'artifacts/extracted/Serato DJ Pro 2.5.5/tree/Serato/Serato DJ Pro/Serato DJ Pro.exe' analysis/pe255.json
./scripts/rea.ps1 decompile 'C:/absolute/path/to/Serato DJ Pro.exe' 0x14069afd0 --provider ghidra --snapshot 'C:/absolute/path/to/analysis/serato255.snapshot.json' --format json
```

For the large 2.5.5 import, REA explicitly recommended increasing `REA_GHIDRA_STARTUP_TIMEOUT_MS` after the default 330000 ms timeout. Setting it to 1200000 for a new CLI process completed the loader decompilation. Preserve the timeout diagnostic separately from successful Evidence. The CLI closes its live provider after each invocation; snapshots retain returned evidence, not a permanently running Ghidra session.

The standalone `scripts/ghidra/FocusedDecompile.java` is a fallback for selected PE unwind ranges without whole-program auto-analysis. Its output must retain its reduced-coverage label. Neither its pseudocode nor REA output is recovered buildable source.

The continued current-release work retains `analysis/ghidra-focused/SL3Work500`. It was imported with `-noanalysis -loader-loadLibraries false -loader-ordinalLookup false -loader-libraryLoadDepth 0`. Additional selected functions can be processed without another full import:

```powershell
$env:JAVA_HOME = (Resolve-Path tools/jdk-21.0.9+10).Path
& tools/ghidra_12.1.4_PUBLIC/support/analyzeHeadless.bat analysis/ghidra-focused SL3Work500 -process 'Serato DJ Pro.exe' -noanalysis -scriptPath scripts/ghidra -postScript FocusedDecompile.java analysis/new-focused-report.json 0x14213f330:0x14213f676
```

`pe-navigate.py` boundary-checks direct-call and selected RIP-reference candidates and reports qword data pointers. `pe-field-refs.py` finds selected member-displacement candidates; matching displacement does not establish object type. `pe-rtti.py` validates selected x64 MSVC complete-object locator structures and recovers capped vtable candidates. Their headers state coverage limits. Example:

```powershell
.venv/Scripts/python.exe scripts/pe-rtti.py 'C:/Program Files/Serato/Serato DJ Pro/Serato DJ Pro.exe' analysis/device-manager-vtables.json '^\.\?AVDeviceManager@@'
```

`scripts/export-serato-evidence.py` projects the retained named analysis reports into the compact discontinued-path evidence, verifying that all input reports refer to the exact current executable hash. Its `sources` list records each intermediate report and function address. The large selector and notification handler excerpts are labeled, and the full local reports remain available. Selected start addresses must be checked against enclosing unwind-entry disassembly; a byte search can start inside an instruction.

## Isolated Windows package tools

The original installed Windows Kits tree did not contain Inf2Cat/InfVerif. We acquired Microsoft's official WDK NuGet 10.0.28000.2526 without installing a system-wide WDK or upgrading Visual Studio:

```powershell
python scripts/fetch.py https://api.nuget.org/v3-flatcontainer/microsoft.windows.wdk.x64/10.0.28000.2526/microsoft.windows.wdk.x64.10.0.28000.2526.nupkg artifacts/downloads/microsoft.windows.wdk.x64.10.0.28000.2526.nupkg
dotnet nuget verify artifacts/downloads/microsoft.windows.wdk.x64.10.0.28000.2526.nupkg --all
& 'C:/Program Files/7-Zip/7z.exe' x artifacts/downloads/microsoft.windows.wdk.x64.10.0.28000.2526.nupkg -otools/wdk-10.0.28000.2526 -y
./scripts/build-winusb-package.ps1
```

NuGet verification passes for the Microsoft author and NuGet repository signatures. The Inf2Cat executable separately reports Authenticode `UnknownError` with signer `Windows Internal Build Tools CodeSign`; do not label that individual check Valid. The pinned package and executable hashes are checked by the build script. Inf2Cat executes here and generates the unsigned catalogue with zero errors/warnings. This proves tool/package signability execution, not certification or runtime loading. Standalone InfVerif was not included in this extraction, and a full current driver C++ build toolchain is not established.

## Real diagnostics and tests

`collect-windows-state.ps1` queries only SL3-specific PnP/ASIO records and relevant Code Integrity events. `usb-descriptors.py` enumerates hub interfaces and issues only hub metadata/standard descriptor GET requests. It never sets USB configurations or alternate settings, sends vendor requests, resets the device or starts audio.

Run `python -m unittest discover -s tests -v`. The tests replay the captured physical descriptor fixture and reject malformed descriptor boundaries. Passing these parser tests does not validate streaming or DVS.

`test-original-driver.ps1` defaults to preflight only. `-Install -RiskAccepted` explicitly runs the authentic vendor installer from an elevated terminal, verifies archive/setup hashes and signature, captures before/after state, requests normal visible UI and suppresses automatic reboot. No silent EULA acceptance is automated. The owner completed the interactive installation in the first session. Read next-tests.md before using it again.


## Isolated focused PE input

The [generic DriverAPI checkpoint](serato-generic-driver-fallback.md) used a fresh byte-identical PE copy in an otherwise empty private analysis directory, plus `-librarySearchPaths` pointing to a separate empty directory. Keep `-loader-loadLibraries false`, `-noanalysis` and `-readOnly`, verify the copied SHA against the original, and retain the successful log/project cleanup evidence. The explicit search path avoids unrelated application/system library paths during this focused import. It does not increase analysis coverage or validate runtime behavior. Do not publish the isolated vendor image or whole pseudocode.
