# Source-bound installer and broker session

The previous working launcher embedded this machine's project checkout path. Public source now prepares the installer and broker dispatch for a specific checkout without a fixed username or workspace path. A session configuration, called a capsule, binds the project, interpreter, exact Serato application, native package, permit path and session directory. Moving it or changing a bound source requires preparing a new capsule and rebuilding its launcher.

This is still temporary diagnostic integration. The parameterized helpers and launcher have passed offline and Plan checks, not a protected install or live Serato run. The existing attended two-deck package remains preserved.

## Components

- `prepare-serato-session-capsule.py` verifies the reviewed app/package and emits a fresh `session-capsule.json`, generated `Program.cs` and .NET project under `analysis/sl3-session-capsule-*`.
- `src/installer/SessionLauncher.cs` is the original launcher template. The generated executable accepts only `--plan` or no arguments. Plan is read-only; no arguments request the normal attended installer flow, including UAC.
- `serato-session-capsule.py` verifies the manifest, fourteen bound source files, exact interpreter/application, native package, fixed diagnostic policy and session location before helper dispatch.
- `serato-session-installer.py` exposes Plan and explicit elevated install/revoke/rollback operations using the existing protected permit, journaled installer and own-file uninstaller.
- `serato-session-broker.py` exposes Plan, bounded ordinary-user broker start and verified stop, delegating process ownership and pointer withdrawal to the existing diagnostic coordinator.

The launcher opens read-only leases over its expected manifest, interpreter, application and project sources before child dispatch, verifies their hashes and retains those leases across the installer and broker invocations. Arguments use `ProcessStartInfo.ArgumentList`; they are not assembled as shell command text. Source-file pins are not an attestation of all interpreter dependencies or loaded code.

## Preparation and Plan

Use the exact reviewed diagnostic package and installed Serato application. The preparer defaults to inspection without writing. Adding `--prepare` creates a fresh private directory; an existing directory is refused. `--capture-output` explicitly enables the existing manually armed five-second recorder for that session. Without it, inherited output-capture environment state is removed from the broker child.

```powershell
.venv/Scripts/python.exe scripts/prepare-serato-session-capsule.py `
  --app 'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe' `
  --bundle 'ABSOLUTE_REVIEWED_NATIVE_BUNDLE_DIRECTORY' `
  --expected-bundle-sha256 'REVIEWED_BUNDLE_MANIFEST_SHA256' `
  --prepare analysis/sl3-session-capsule-YOUR-NAME
```

The generated project targets .NET 10, Windows x64 and framework-dependent single-file publication, matching the installed development runtime. Build it with `dotnet publish` to a fresh private artifact directory, then invoke the resulting `SL3_Rebuild_Development_x64.exe --plan`. **Invoking it without `--plan` requests installation and is not an offline check.** This launcher is only for the complete reviewed protected-session caller.

The existing resource packager can package that executable into the private installer resource. It verifies the complete decode/Qt-index round trip. The resource filename remains the installer-name-derived value used by the reviewed descriptor; its contents and hash change with the generated launcher. The caller must use the new resource hash. Generated projects, binaries, session manifests and resource bundles remain ignored/private.

## Runtime ownership and recovery

Install still requires an administrator token and an exclusive protected permit whose native bundle hash matches and whose remaining lifetime is no more than five minutes. The receipt is created exclusively and flushed while that permit is held. A failed operation preserves its failure report. Normal installer UAC consent is retained; no security policy or driver-signing change is introduced.

The capsule's installer must run through the protected outer transaction. That caller remains responsible for application quiescence, issuing/revoking the permit, temporary resource staging and restoration, and coordinating ordinary-user broker stop before elevated rollback. The generated launcher does not kill an elevated installer with an unknown commit outcome.

Broker start requires a successful receipt and exact staged controller/worker/helper hashes. It publishes a fixed 44.1 kHz, 128-frame unmeasured diagnostic configuration and requests the existing ten-minute bound. This is not a measured production timing profile. Closed handoffs, existing config/capture files and conflicting pointers are preserved instead of reused.

Rollback additionally requires verified broker retirement and an absent pointer. An unused handoff must be explicitly closed with no partial startup artifacts. A started handoff requires controller exit, worker exit, empty job, retired I/O and device release, with the cleanup report matching its owned result. A session with `successful=false` can satisfy these independent release facts; the failure is preserved. Verified stop retries return the saved report without restarting a process or changing that result.

## Actual validation and remaining work

Ten tests cover capsule location/source/interpreter bindings, release-proof refusal, preserving a failed-but-retired session, permit/receipt ordering, elevation gating, receipt collision, rollback ordering, inert Plan/stop retry and child-scoped capture configuration. Mutating installation and broker creation are mocked in these tests; no actual registry or USB operations occur.

On this Windows host, a fresh generated launcher compiled successfully and its real `--plan` passed, as did both helper Plan modes. An earlier compiled launcher refused stale source before child dispatch. The fresh executable passed private installer-resource packaging and round-trip validation. Nothing was installed, no broker was started and Serato was not launched. [Sanitized evidence](evidence/session-capsule-20261105.json)

The public [process supervisor](serato-startup-supervisor.md), capsule and installer resource now exist as separate reviewable components. The remaining wrapper must assemble them with the protected archive/permit transaction, bounded stage supervisor, application-exit checks, broker stop and rollback. That full parameterized route still needs live validation. It is not a permanent installation or a finished end-user launcher.
