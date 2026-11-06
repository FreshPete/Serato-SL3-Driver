# Portable PowerShell and native session entry

**Follow-up:** automatic fresh-session preparation now reuses the same release executable and installer resource across new sessions. Its preparation and Plan routes passed offline; live fresh startup is still untested. [Contract and evidence](fresh-session-preparation.md)

The native launcher can now start the complete session wrapper using a private, application-local PowerShell runtime. The read-only route passed with two separately prepared sessions, without a separate PowerShell command. This is a packaging candidate, not a published end-user installer or new hardware validation. [Recorded checks](evidence/portable-powershell-session-entry-20261106.json)

## Runtime preparation

The selected distribution is Microsoft's self-contained Windows x64 PowerShell 7.6.6 ZIP. Its SHA-256 matched the [official release hash](https://github.com/PowerShell/PowerShell/releases/tag/v7.6.6). Microsoft documents ZIP deployment as a [side-by-side installation option](https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-windows?view=powershell-7.6#install-the-zip-package). The runtime stays under the ignored development artifacts directory; no MSI, PATH, registry, trust-store or execution-policy change was made.

`scripts/prepare-portable-powershell.py` verifies an explicitly supplied archive hash before extraction. It bounds the inventory and expansion, refuses traversal, Windows path aliases, streams, links, encryption and file/directory collisions, and preserves the full runtime and notices. Without `--prepare` it only inspects. Preparation requires a fresh `artifacts/build/portable-powershell-*` directory. The separate `--verify` action checks an externally supplied manifest hash, each file's hash/size and the exact file inventory without executing PowerShell.

The official ZIP expands to 658 files, 256,625,143 bytes, plus the generated inventory manifest. Windows reported valid Microsoft signatures on `pwsh.exe` and `System.Management.Automation.dll`. The full wrapper's Plan succeeded under that runtime using the private embedded Python interpreter. The self-contained PowerShell distribution includes its .NET runtime; the claim is that a separate .NET installation is unnecessary, not that no .NET code runs.

## Native entry

`scripts/prepare-native-session-launcher.py` optionally accepts `--portable-powershell` and its expected manifest hash. The resulting release embeds 29 project source hashes, 130 Python runtime/manifest hashes and 659 PowerShell runtime/manifest hashes. These bindings are release-wide, not tied to one session directory. The same executable retains its capsule installer entry.

The new developer read-only entry is:

```text
SL3_Rebuild_Development_x64.exe --plan-session --session-plan ABSOLUTE_PLAN_PATH --expected-session-plan-sha256 REVIEWED_PLAN_SHA256 --powershell-directory ABSOLUTE_RUNTIME_DIRECTORY
```

The launcher pins the selected complete-plan hash, original Serato executable, interpreter, complete release source closure and both runtime inventories under read-only file handles before launching PowerShell. It invokes a fixed `-NoProfile -NonInteractive -File` argument list, with the existing wrapper's `Plan` mode. The wrapper then verifies the complete selected capsule, archive, installer resource, native package and session bindings. No shell command text is constructed.

The corresponding explicit `--start-session` entry selects the existing wrapper's `Run` mode. Its protected staging, approvals, supervisor, broker retirement and recovery contract are retained. **That entry has not been exercised live.** No new installation, Serato process, audio stream or USB acquisition was started during this work. No-argument invocation still means the supervisor-selected installer action and refuses without its context; it does not automatically start a session.

PowerShell's bundled CoreCLR failed with HRESULT `0x80070057` when the runtime directory contained a semicolon. The native entry now refuses that location explicitly before child creation. Spaces, Unicode and literal dollar/parenthesis characters passed actual relocated runtime tests.

## Checks and remaining work

Five focused preparation/verifier tests passed. Thirteen actual native full-session Plan/refusal cases passed: both sessions, wrong plan hash, executable relocation, relocated PowerShell, semicolon refusal, changed PowerShell executable/runtime configuration/automation DLL, foreign interpreter/application, unsupported schema and changed wrapper source. Eleven existing actual capsule-launcher cases and eight Windows argument round trips also passed. Both positive session Plans explicitly report no application, broker, elevation, registry write or device access.

The first attended use must verify the full new path: native entry, protected stage, actual installer child context, Serato/ASIO startup, owner interaction, manual close before the viewing limit and rollback. Previous physical results belong to their recorded builds; they do not validate this launcher. The old native executable is preserved but its source hashes precede this change and it refuses the updated source tree.

Automatic fresh-session preparation, whole-release-kit relocation, removing the repeated Download Driver action, crash recovery through a simple user interface and second-PC installation remain unfinished. Current prepared plans still refer to this development checkout and private Serato-derived resources. The public repository contains original source, documentation and sanitized evidence, not the private resources, runtimes, signed third-party driver package or recorded music. Playback shutdown, physical SL3 output and longer two-deck reliability still need their separate hardware checks.

Later work added [fresh-session preparation](fresh-session-preparation.md) and a [recipe that generates the exact Phase archive from the original installed Serato files](installed-phase-archive-preparation.md). These remove two manual preparation dependencies; whole-kit assembly and attended validation remain unfinished.
