# Native entry for kit preparation and startup

**Current readiness entry:** the newer launcher pins forty source/license/evidence files and adds [read-only host checks before approvals](session-readiness-check.md). The host passed these prerequisite checks; actual kit Start/audio/shutdown remain untested. Older source-pin counts below describe their dated candidates.

**Follow-up:** kit preparation now [rebinds native package metadata to current-account Windows known folders](deployment-account-rebinding.md). The newer launcher pins 39 sources. The original 38-pin candidate and its evidence below remain historical; actual different-account/PC and live startup testing are still outstanding.

The kit's native executable can now verify and prepare a complete session directly. The user no longer needs to select and invoke Python for that preparation step. Thirteen actual native-entry checks passed in a moved kit with an empty `PATH`, including complete preparation and the resulting native session Plan. The combined live-start entry is implemented but remains untested. [Image and test evidence](evidence/native-kit-entry-20261106.json)

## Entry modes

The developer interface has three explicit modes, with the same argument shape:

```text
SL3_Rebuild_Development_x64.exe --plan-kit --kit-manifest ABSOLUTE_KIT_DIRECTORY/kit-manifest.json --expected-kit-manifest-sha256 REVIEWED_KIT_MANIFEST_SHA256 --app "ABSOLUTE_SERATO_DIRECTORY/Serato DJ Pro.exe"
```

`--plan-kit` checks the kit and selected original application without writing session state. `--prepare-kit` performs the existing offline kit preparation and returns the generated session's Plan and Start argument vectors. Neither starts Serato or requests elevation. `--start-kit` prepares a new session and then invokes the generated native `--start-session` entry. **No live `--start-kit` invocation has run.** Its actual installer context, approval sequence, ASIO startup, manual close and rollback require an attended test.

No-argument invocation retains the existing supervisor-selected installer action and refuses without its capsule context. Existing `--plan`, full-session and fresh-session modes remain available. An incomplete `--start-kit` command is refused without child creation.

## Before helper execution

The native builder now pins 38 release source/license/evidence files. That includes the complete kit preparer and its archive-generation dependency closure, alongside the existing session helpers. A kit entry opens and hashes the selected compact manifest and inventory, all release sources, all 130 Python runtime/manifest entries, all 659 PowerShell runtime/manifest entries, the selected original Serato executable, its own running image and the kit's launcher image. Read-only handles remain open through child completion. A semicolon in the kit path is refused before helper dispatch because of the previously observed CoreCLR path limitation.

Only after those checks does it invoke the kit's fixed Python path and fixed preparer with an isolated interpreter and argument vector. It never executes a path or command selected from arbitrary kit JSON. The Python helper verifies the exact full static inventory and native/resource bindings, then performs the existing local archive, shim, capsule and plan preparation. Start, if explicitly selected, uses the generated fixed native entry vector and the session wrapper's existing protected staging, approvals, lifetime bounds, retirement and recovery contract.

The launcher remains a normal `asInvoker` native x64 executable with no CLR startup or external MSVC runtime import. PowerShell's bundled runtime is still .NET; no separate .NET installation is required for the launcher. No automatic privilege change, firmware operation or security-policy change was added.

## Verification and limits

The thirteen native kit cases cover read-only verification, preparation, complete generated-session Plan, verification after preparation, incorrect manifest hash, changed preparer, changed historical specification evidence, changed Python standard library, changed PowerShell runtime, mismatched launcher release, unreviewed application, unsupported path and incomplete start context. The changed-code/runtime cases returned native hash refusals with no Python output or further session state. All ran from a copied kit with spaces/Unicode in its path and an empty process `PATH`.

Ten earlier direct-preparer relocation cases also passed on this new kit, along with eleven existing actual capsule entry cases and eight Windows argument round trips: 42 targeted checks in total. The native audio DLL, worker, controller and diagnostic deployment package were unchanged. No Serato, broker, UAC, registration or USB operation occurred. The copied test kits were removed afterward; the newly assembled private kit remains uninstalled with no session state.

The compact manifest still needs an externally reviewed hash and an explicit application path. A simple graphical launch/recovery interface is unfinished. The deployment package remains bound to the reviewed Windows host/account; another account/PC, signed-filter prerequisite handling and an installable public release remain unverified. The repeated Download Driver action, diagnostic lifetime, physical output, timing and reliable post-playback shutdown retain their separate limitations. Older source-bound launcher releases are preserved but refuse the updated source tree; new kit inputs bind this executable and its freshly packed installer resource.
