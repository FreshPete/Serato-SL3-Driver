# Relocatable development-kit assembly

**Current package binding:** the newer kit [creates a separate current-account deployment package during preparation](deployment-account-rebinding.md), preserving the immutable origin and native binaries. It no longer uses the original account's destination paths for the prepared session. Actual different-account/PC and live startup tests remain outstanding; the earlier host-bound checkpoint below is preserved.

**Follow-up:** the newer kit adds a [native preparation/start entry](native-kit-entry.md), removing the need for a direct Python preparation command. Its Plan and Prepare modes passed actual relocated-kit tests; live Start is still untested. The original kit and evidence below are preserved.

A copied kit now prepares and verifies a complete temporary Serato session using its own Python, PowerShell, source helpers, native launcher and native deployment package. The actual relocation check used a folder with spaces and Unicode and an empty process `PATH`. It generated the tested Phase archive, prepared the startup shim and session, and passed the native full-session Plan from the copied folder. No Serato, broker, administrator prompt, registry write or USB operation ran. [Assembly and ten actual checks](evidence/portable-kit-assembly-20261106.json)

## Scope

This is a development kit for the reviewed Windows host and account. The native package still contains the reviewed protected installation directory and user-owned session-pointer destination. Moving the kit folder is supported by the offline evidence; using another account or PC is not. The signed UsbDk filter is an external prerequisite and is not installed by these helpers. Actual live startup and cleanup through a copied kit remain untested.

The initial kit has 842 selected files totaling 464,158,371 bytes, plus its two small inventory/manifest files. Most of the size is the complete Python and PowerShell runtimes. It includes original project helpers, license notices, the reviewed native ASIO/worker/controller/helper package, the native launcher and a resource containing that same launcher. It contains no Serato executable, derived Serato descriptor archive, historical installers, signing key, firmware or kernel driver. Serato-derived resources are generated locally from the owner's pinned original installation after copying.

## Assembly and integrity

`scripts/assemble-portable-serato-kit.py` takes an explicitly hash-reviewed complete session plan, native launcher release record and selected portable PowerShell directory. It rechecks the existing session inputs and the release source/runtime hashes, then selects only the required files. Default mode is read-only. Explicit `--prepare` requires a fresh `artifacts/build/portable-serato-kit-*` directory without a semicolon. Each copied file is hash-checked; partial output is retained on failure. The inventory and compact kit manifest are published last.

`scripts/prepare-portable-serato-kit.py` verifies an externally supplied kit-manifest hash, the bound inventory, every static file and component binding, and refuses unexpected static files or reparse entries. The `analysis` directory is reserved for mutable generated/session state; it cannot be included as an immutable payload. The complete private runtime inventories are checked again before preparation. No security policy or global tool installation is changed.

The preparer must run under the copied kit's Python interpreter. With an explicit original application selection, default mode checks the kit and capsule inputs without creating state. Explicit preparation generates the Phase archive and guarded startup shim, creates a new session capsule, binds the copied native launcher/resource, and verifies the complete plan. Its completion record supplies a fixed argument vector for the native read-only Plan. No Start command is issued automatically.

The capsule preparer retains its legacy C# project/source outputs in the session state directory; these are not compiled or executed. This kit uses the already compiled reusable native launcher. The source helpers run from the copied root and all new capsule, interpreter, shim, package, archive, resource, launcher, Frida and supervisor-output paths bind there. The installed Serato path and native package's Windows destinations remain intentional external bindings.

## Developer entry

From the copied kit, using its `runtime/python/python.exe`:

```text
runtime/python/python.exe -I -B scripts/prepare-portable-serato-kit.py --kit-manifest ABSOLUTE_KIT_DIRECTORY/kit-manifest.json --expected-kit-manifest-sha256 REVIEWED_KIT_MANIFEST_SHA256 --app "ABSOLUTE_SERATO_DIRECTORY/Serato DJ Pro.exe"
```

Add `--prepare` to generate a session. Omitting `--app` performs inventory verification only. These are developer interfaces; a simple native setup/launch/recovery interface remains to be built. A prepared session is bound to its current folder. After moving the kit, prepare a new session rather than attempting to reuse old absolute session paths.

## Evidence and remaining work

Ten actual checks passed: copied inventory verification under the private interpreter with an empty `PATH`; read-only application Plan; complete offline preparation; native complete-session Plan; static inventory verification after preparation; incorrect kit hash; changed helper refusal by both the preparer and native entry; changed PowerShell runtime refusal; and unexpected static-file refusal. Negative cases created no further session state. There was no run lock or installation receipt. The generated archive matched the tested Phase hash exactly.

The isolated relocation test's temporary copy was removed after verification. The original assembled kit remains private under ignored build artifacts, uninstalled and with no session state. No binary kit was published. The public repository contains assembly/preparation/test source and sanitized evidence.

Remaining release work includes rebinding the deployment package for another Windows account, an application-facing native bootstrap, simple recovery, signed-filter prerequisite handling, second-PC testing and a reviewed distribution package. The repeated Download Driver interaction, diagnostic lifetime, measured latency, reliable post-playback shutdown and physical output still need their own work. Earlier Phase tracking evidence does not establish that this new kit is ready for public use or live DJ performance.
