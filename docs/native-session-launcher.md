# Native reusable launcher candidate

**Current entry:** the newer launcher can verify and prepare a copied kit directly, with complete pre-execution source/runtime checks. Its combined live Start mode is untested. [Native kit entry](native-kit-entry.md)

**6 November follow-up:** a newer native candidate includes a complete-session entry bound to application-local PowerShell as well as Python. Its read-only entry passed with two sessions; the earlier build described below is preserved as historical evidence. [Portable runtime, launch contract and remaining live test](portable-powershell-session-entry.md)

The reusable launcher now has a native Windows implementation that does not require an installed .NET runtime. The same 352,256-byte x64 executable passed Plans for two separate sessions and relocated without recompilation. It retains the private Python runtime and existing installation/broker policy. No protected installation, Serato process or device operation ran during these checks. [Image, source and test evidence](evidence/native-launcher-preparation-20261106.json)

## Behaviour retained

`src/installer/NativeSessionLauncher.cpp` accepts the same explicit read-only Plan arguments as the C# prototype. No arguments requests the installer action only when the supervisor supplies the complete selected capsule context; missing context refuses. It pins the capsule, eighteen release sources, interpreter, all 130 runtime/manifest entries and original Serato executable under retained read-only handles before helper dispatch.

The implementation uses Windows' JSON API, BCrypt SHA-256, CreateProcessW for ordinary helpers and the existing explicit RunAs elevation for installation. Child arguments are quoted for Windows process parsing, never sent through a command shell. Ordinary helpers inherit only their designated standard handles. Output is drained independently with bounds. The launcher never terminates an elevated transaction with an unknown commit outcome. Its manifest requests normal `asInvoker` privilege; only the installation action requests elevation.

The build statically links the MSVC runtime. PE inspection finds no CLR directory, .NET startup import or external MSVC runtime import. Other imports are Windows system libraries/API contracts. This removes the separate .NET installation prerequisite for this launcher; it does not make the whole development workflow dependency-free.

## Preparation and checks

Run `scripts/prepare-native-session-launcher.py` under the selected private Python interpreter, supplying its explicit directory and reviewed runtime-manifest hash. Without `--prepare` it is read-only. A fresh `artifacts/build/native-session-launcher-NAME` receives release metadata, a generated binding header and a CMake project. Build with the existing x64 MSVC toolchain and Windows SDK. The candidate was built against SDK 10.0.19041.0. Build tools are developer prerequisites, not proposed end-user requirements.

The native argument test passed eight Windows round trips including empty strings, spaces, quotes, trailing backslashes and Unicode. Eleven actual launcher Plan/refusal cases passed, including a real capsule directory containing spaces, shell metacharacters and Unicode. Five copied-runtime/changed-module checks passed: the complete private runtime relocates, and changed module/standard-library bytes are rejected before Python executes. Two complete wrapper Plans passed using one native executable and one private Qt installer resource. The resource round-trip bound the exact selected executable.

The earlier C# prototype remains available, but the native candidate is the preferred next packaging experiment. Its actual Serato installer-child launch, UAC, broker startup, ASIO Start and rollback still require an attended live test. PowerShell remains an external prerequisite; release-kit relocation, removing repeated Download Driver clicks, clean second-PC installation and the outstanding physical audio/reliability checks remain unfinished. The native audio DLL and USB worker are unchanged.
