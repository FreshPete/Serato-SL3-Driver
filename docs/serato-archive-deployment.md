# Prepared attended Serato archive test and rollback

A private review bundle now contains the SL3 archive hypothesis, a source-bound PowerShell wrapper, the original transaction library and provenance. Its default `Plan` action is read-only. No installed archive replacement, protected rollback, application session or device operation has run. This is preparation for an attended experiment, not an approved deployment or working Serato release.

## Package and read-only preflight

The original reviewed bundle was `analysis/sl3-archive-deployment-20261102-reviewed/`; it and the preliminary bundle are now historical snapshots. The current bundle is `analysis/sl3-archive-deployment-20261102-owned-trace/`, refreshed against the [new native build](asio-owned-trace.md). Older generated manifests are refused against current sources. Both contain vendor resource data and stay private. The public repository supplies original tool source, tests and sanitized evidence rather than generated resource archives.

The preparer independently reconstructs and validates the [additive archive](serato-sl3-archive.md), checks the exact saved bundle and all source bindings, verifies the installed original archive and queries the original executable's Windows Authenticode status. The observed executable status is **Valid**, signer thumbprint `A38279C93F7D1D669D0C367CAE3EC45ACF63F017`. Windows reports **UnknownError** with no signer for the original resource archive; that is not interpreted as proof that Serato performs no resource integrity checks. No executable signature, certificate store, security policy or authorization is changed.

Each bundle contains:

- `candidate-userio_resources.bin`, the exact private candidate.
- `serato-archive-file-transaction.ps1`, original file transaction code.
- `archive-test.ps1`, the generated attended wrapper.
- `deployment-plan.json`, original/candidate/app/source identities and limitations.
- `provenance.json`, exact package file hashes.

The wrapper embeds the fixed installed target and original/candidate/app/core/plan hashes; manifest fields cannot redirect its target. It checks its core and plan, imports the same core bytes whose hash it verifies, checks the original executable hash/signature/signer, and checks the candidate payload for `Plan`/`Install`. Default `Plan` was run with an ordinary token and reported original-to-original state with no file replacement. Read-only owner/DACL checks accepted the current app/archive directory paths; they do not establish future protected staging, replacement or rollback.

## File transaction behavior

The core library is inert when dot-sourced. Its file operations require an explicit quiescence callback. The wrapper supplies a guard that refuses a running process named `Serato DJ Pro`, checks trusted protected owners and refuses applicable untrusted write/ownership grants. It checks the live archive/directories and existing stage/backup/retired files. No ACL or owner is repaired or relaxed; unexpected ownership, including a future staging owner that fails the predicate, stops the action for review.

`Install` requires the exact original target or a verified candidate stage. It copies the independent candidate into a create-new same-directory stage, flushes it to disk, rechecks quiescence/state, then calls Windows file replacement with an atomic original backup. Metadata errors are not ignored. Original and replacement hashes are checked afterward. `Rollback` requires the exact installed candidate plus the exact original backup, stages the backup, then atomically restores it while retaining the displaced candidate. The original backup stays until explicit `Clean`. `Clean` requires the verified original live target and removes only matching derived witnesses; it can cancel a verified pre-install stage.

The implementation uses [.NET File.Replace / Windows ReplaceFile](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew). OS error cases can leave different file-name states. The engine accepts only its explicitly checked states; it preserves unknown, corrupt, missing-target or partially written artifacts for review rather than guessing a recovery action. Tests cover selected failure/interruption states, not every power-loss/OS/storage failure. Application closure checks and protected directories do not coordinate a concurrent privileged updater; the attended caller must exclude one.

A changing live target, unknown stage/backup, path tampering, reparse path or unavailable original backup prevents replacement/cleanup. A locked live file fails without losing the original in the tested Windows case. Unknown witnesses are not recursively removed. Package rollback does not require the candidate payload, but does require the reviewed wrapper/core/plan, original executable and exact protected backup/target identities. No automatic retry, UAC request, reboot or application launch exists.

## Review commands

From the repository root, prepare a **new** bundle or revalidate the reviewed one:

```powershell
.venv/Scripts/python.exe scripts/prepare-serato-archive-deployment.py `
  --descriptor analysis/sl3-descriptor-candidate-20261102-owned-trace `
  --archive analysis/sl3-archive-candidate-20261102-owned-trace `
  --prepare analysis/sl3-archive-deployment-NAME
.venv/Scripts/python.exe scripts/prepare-serato-archive-deployment.py `
  --descriptor analysis/sl3-descriptor-candidate-20261102-owned-trace `
  --archive analysis/sl3-archive-candidate-20261102-owned-trace `
  --validate analysis/sl3-archive-deployment-20261102-owned-trace

# Read-only inspection; this is the only wrapper action exercised on Serato paths.
pwsh -NoProfile -File analysis/sl3-archive-deployment-20261102-owned-trace/archive-test.ps1
```

For a later attended, reviewed test, the wrapper's explicit actions are `-Action Install`, `-Action Rollback` and `-Action Clean`. They require an already elevated launch; the wrapper never requests UAC. No such action is selected or approved by preparation. ASIO deployment/profile and the actual application/device test scope are separate prerequisites. The archive is not evidence of an accepted current descriptor, legitimate service result, implemented NONE control semantics, physical audio or DVS.

## Verification

On 4 November the current private bundle passed full validation again. The read-only wrapper found the original archive, no staging or rollback files, and a valid signature on the installed executable. All 22 Windows transaction fixtures passed again. These results verify bundle and rollback preparation. Application acceptance still requires a later protected test after the Windows audio prerequisites are met.

Twenty-two transaction checks use original synthetic data in bounded owned temporary folders on this Windows host, with real file replacement calls. They cover install/rollback/cleanup, exact backup/retired bytes, stage resume/cancellation, first/second quiescence refusal, unknown/corrupt/missing backups, partial staging, independent source and path identity, changed-target/create races, held-file failure, destination ACL preservation, junction rejection and untrusted owner rejection. Temporary ACL changes and all writes stay inside those disposable fixture folders. No installed app file is used as a transaction test target.

Six actual package CLI scenarios check full validation, repeat preparation, no-overwrite refusal and wrapper refusal of changed core, candidate or plan. The repeated five-file bundle is byte-identical. The actual default wrapper `Plan` passes and leaves the original installed identities unchanged. [Sanitized evidence](evidence/serato-archive-deployment-20261102.json) binds source files, package hashes, fixture/CLI results and the read-only preflight. No new native audio tests are claimed, and no protected install/rollback, current admission or physical audio/DVS result is inferred.

Run fixture checks with `pwsh -NoProfile -File tests/test-serato-archive-file-transaction.ps1`. They require a Windows user session with permission to create ordinary owned temporary files/junctions. The goal remains Windows-first; Mac is deferred.
