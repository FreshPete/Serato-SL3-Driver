# One launcher build for multiple temporary sessions

The reusable-launcher prototype removes the need to compile and repackage an executable for every new session. One release-bound executable passed Plan for two different fresh session configurations, and two complete wrapper Plans passed using the same executable and private installer-resource bytes. No installer ran and no SL3 was opened for these checks. [Preparation and validation evidence](evidence/reusable-launcher-preparation-20261106.json)

## Binding and dispatch

`src/installer/PortableSessionLauncher.cs` embeds the release's seventeen source hashes, interpreter executable hash and exact Serato executable hash. It does not embed a username, checkout path or individual session hash. The supervisor passes the reviewed session path and hash through `SL3_SESSION_CAPSULE` and `SL3_SESSION_CAPSULE_SHA256`. Before starting its application, it verifies that this configuration belongs to the same application and native package being supervised. Its child environment explicitly clears inherited session values when no context was selected.

The launcher accepts either no arguments for the actual installer action, or the explicit read-only developer form:

```powershell
SL3_Rebuild_Development_x64.exe --plan `
  --capsule 'ABSOLUTE_SESSION_CAPSULE_PATH' `
  --expected-capsule-sha256 'REVIEWED_CAPSULE_SHA256'
```

No arguments with missing context refuses before dispatch; it does not mean Plan. With a valid selected context, no arguments invokes the existing elevated installer and then ordinary-user broker start. All executable/source files and the selected capsule are hash-checked under retained read-only leases. Helper arguments use `ProcessStartInfo.ArgumentList`, not shell command text. Complete capsule/package/permit checks remain in the existing helpers. Authorization, USB identity, firmware and Windows security policy are unchanged.

## Build and actual checks

`scripts/prepare-portable-session-launcher.py` defaults to read-only inspection. Its explicit `--prepare artifacts/build/portable-session-launcher-NAME` emits a release configuration and .NET project in a fresh directory. Publish that project once, then package the resulting executable once through the existing local installer-resource packager. The release currently targets framework-dependent .NET 10 x64; this prototype does not bundle that runtime or a portable Python distribution.

Ten compiled-executable checks passed: two distinct actual session Plans, relocation of the same executable without rebuilding, missing context, unsupported action, wrong capsule hash, untrusted interpreter binding, foreign helper root, changed package binding and a moved session. Every invocation used Plan or a refusal path. Thirteen supervisor checks, twenty-two session checks and four actual temporary-file transaction checks also pass.

Two additional tests used the real local Frida runtime with owned Python child processes, not Serato. They observed the selected environment exactly, checked that unselected inherited context was cleared, detached instrumentation and verified normal child exit and empty jobs without forced termination. This validates environment propagation for that backend; it does not establish that Serato's actual installer child receives it or that the reusable launcher installs successfully during a real session.

## Limits and next step

The existing session-specific launcher and earlier live evidence are preserved. The shared wrapper now supplies the verified context for either launcher; the older executable simply ignores those new variables. All source-bound full plans prepared before the supervisor/wrapper change are stale and must be regenerated before another run.

The two candidate sessions have fresh state and share the same native diagnostic package and installer payload. Their next check is an attended real Serato startup and explicit close before the viewing limit, with complete rollback. Runtime bundling, removing the repeated Download Driver action, installation on a second PC, physical output, long-session reliability and a permanent installation remain unfinished. Moving the launcher executable is supported by the tested path; moving an already-prepared session or copying the development checkout to another user is not a finished deployment solution.
