# Assembled temporary session wrapper

The public components are now assembled by `scripts/serato-session.ps1`. Its default **Plan** verifies the complete prepared set and current resting state without elevation, Serato execution, broker startup or registry writes. **Run** requests the attended protected workflow. On 6 November 2026 this temporary route passed an attended startup, full tracer detach, manual application close and complete rollback. It remains diagnostic integration, not a permanent installation.

The earlier attended two-deck test used the preserved private route. Its results do not prove this new wrapper works end to end. [Attended result](evidence/phase-two-deck-session-20261105.json)

## Assemble a reviewable set

Use the [source-bound capsule](serato-session-capsule.md), its compiled launcher and private installer resource, the [prepared startup-only shim](serato-startup-only-shim.md), and the reviewed Phase archive. `prepare-serato-session-plan.py` accepts their explicit paths/hashes plus an existing reviewed Frida dependency directory. Without `--prepare`, it only inspects them. `--prepare CAPSULE_DIRECTORY/session-plan-NAME.json` writes a new plan; existing files are never replaced.

The preparer verifies the capsule and exact application, checks the Phase archive hash, and decodes the installer resource in memory to prove it contains the exact selected launcher. Resource-codec material and decoded payload are not emitted. It revalidates the prepared shim and deployment package, records the complete runtime source inventory and hashes the Frida Python/native dependency files without importing Frida. Outputs and generated/vendor-containing artifacts remain private.

The current audited set has fifteen installer/broker source pins, including the installer-base helper. The full wrapper binds twenty-five project sources plus its Frida runtime files. Earlier fourteen-pin prototypes and their evidence are preserved; they refuse changed source and are superseded by this set. Early installer exceptions without a valid typed outcome are now normalized into failure receipts while preserving their cause reports. An exception cannot claim successful installation.

The wrapper is invoked with the prepared file and its reviewed hash:

```powershell
# Read-only. Use the exact generated plan and hash from preparation.
pwsh -NoProfile -File scripts/serato-session.ps1 `
  -Mode Plan -SessionPlan 'ABSOLUTE_SESSION_PLAN_PATH' `
  -ExpectedPlanSha256 'REVIEWED_SESSION_PLAN_SHA256'
```

An explicit `-Mode Run` is the attended action. It must start from ordinary x64 PowerShell and still needs normal Windows consent for protected staging and the local installer. No signing, Secure Boot, code-integrity or trust-store settings are changed. This source is not a permanent installation or a downloadable finished driver release.

## Session and cleanup

1. Verify the exact plan, sources, dependencies, original signed executable, original archive, empty registration/native stage, unused broker state and unused launcher cache. Hold read-only leases on the plan, sources, runtime files, capsule, shim, launcher, resource inputs, application and native package throughout the invocation.
2. Claim a fresh per-capsule run file before elevation. It prevents overlapping parent runners and records process creation fingerprints. The protected stage observes a retained handle for its original desktop runner; it does not treat a recycled PID as that owner.
3. Elevate the protected stage, temporarily install the reviewed archive and resource through the existing transaction, issue the exclusive five-minute permit, and publish readiness. The stage is bounded to fifteen minutes with a monotonic clock and also notices parent exit.
4. Run the public application supervisor under the ordinary token. The user clicks Download Driver and accepts its installer prompt. The exact launcher installs through the permit-bound journaled helper and starts the bounded broker. The startup shim detaches fully after verified ASIO start, before manual interaction.
5. Prefer closing Serato manually and answering any application dialogs. The host also recognizes its `stop.txt` request and has its existing bounded viewing/containment policy. Forced termination is recorded and cannot count as successful supervision.
6. Confirm Serato is stopped, close the ordinary broker handoff, verify independent retirement, then release the protected stage for permit revocation and owned native rollback. The protected stage repeats quiescence and retirement checks. Restore original resources and retire only the exact cached rebuilt launcher.

Broker/session failure and safe retirement remain separate outcomes. Failed or missing release facts preserve native files and recovery records. Original-resource restoration is reported independently. A completed cleanup does not overwrite an `owner_failure` result. Run records are one-shot and retained; a new run requires a fresh prepared state, not an automatic reacquisition loop.

`Stage` is an internal elevated mode for that runner. `Recover` is an explicit elevated recovery action after ordinary-user broker retirement. Recovery refuses while an original runner or stage process with the recorded creation fingerprint remains active, refuses unknown resource/witness identities, requires native retirement before uninstall, and removes only the hash-matching cached launcher. It is not a generic delete or force-recovery option.

## Actual validation

The full read-only Plan passed on the original Windows installation, including native x64 view, original executable signature, empty stage/registration, cache absence, exact installer payload and all twenty-five source bindings. A stale plan was refused before elevation or application launch. The refreshed fifteen-pin launcher compiled, passed its real Plan and passed resource round-trip packaging.

Sixteen Python tests cover source/dependency/capsule bindings, installer receipt and permit behavior, broker retirement, plan tampering/payload binding and actual Windows cache-file handling. Cache tests preserve wrong-hash, hardlinked and busy files, while removing only the matching owned read-only fixture.

Four additional PowerShell cases exercise actual temporary-file resource transactions: successful restoration, body-failure restoration, busy-application preservation, and preservation of a changed/unknown installer resource. No protected paths, native device, real installer transaction, Serato instance or UAC prompt was used. [Preparation evidence](evidence/complete-session-wrapper-20261105.json)

## First live check and remaining work

The packaged-pointer cleanup regression is now fixed and live-validated, including automatic rollback after a forced-close playback session. It does not convert that forced shutdown into a clean session. [Fix, checks and live evidence](pointer-redirection-cleanup-fix.md)

The subsequent attended reopening test also passed on 6 November. The owner was instructed to leave USB and power connected; no power-cycle was requested between the two successful sessions. Fresh generated session state installed the same native package, observed a genuine SL3 arrival, returned a successful ASIO Start and fully detached instrumentation. Serato again exited manually with code 0 before any observer close request. Broker stop, retirement, original-resource restoration, registration removal and exact cache absence all verified. This establishes one successful re-acquisition/reopening under that procedure, not ten-cycle reliability or independently measured electrical continuity. Two intervening automatic launch attempts had cancelled at Windows consent, before staging or device access; the successful retry was launched from the owner's ordinary desktop PowerShell. [Reopening evidence](evidence/serato-reopen-success-20261106.json)

After a full power-cycle restored the genuine SL3 USB identity, a fresh one-shot retry passed. Serato 5.0.0.1278 observed the SL3, used the generated installer, opened the hash-verified rebuilt ASIO DLL and returned a successful Start. The smaller tracer unloaded and detached completely. The owner then closed Serato normally; its retained process handle recorded exit code 0 without an observer close request or forced termination. The broker reported `successful=true`, `reason=stop_requested`, `ownerFailureCode=none`, verified I/O retirement, device release, worker exit, empty job and controller exit. Protected rollback restored the original resource hash and removed temporary registration/staged binaries; exact cached-launcher retirement passed. All saved-result inspection checks passed. [Successful retry evidence](evidence/assembled-session-success-20261106.json)

The broker retained `lastNativeError=1168` despite zero final device-failure and stream-fault fields. That value is preserved rather than described as an all-zero-error run. No next-acquisition readiness or rate-restoration proof was reported. Playback was deliberately left stopped, and no physical audio, Phase tracking, sustained operation or immediate reopening result is inferred from this startup/shutdown check. It does not establish the exact cause of the older forced-close ownership failure.

The first attended invocation on 6 November 2026 staged the reviewed resources and opened Serato, but Windows concurrently showed a USB descriptor-request failure rather than an SL3 identity. The owner saw no driver notice. The trace observed only readiness and timed out waiting for the installer action; ASIO never started, no installation receipt was created and the broker did not start. Application cleanup used forced termination after its close-request fallback. Protected cleanup restored the original resources and verified absent temporary registration, and the launcher cache was absent. This is a failed startup with successful independent rollback, not validation of the full route or clean application shutdown. The records are preserved, and a fresh one-shot retry has passed Plan pending device recovery. [Attempt evidence](evidence/assembled-session-attempt-20261106.json)

The next attended run must validate the assembled route, smaller shim, generated launcher, actual elevation boundaries, full detach, manual application close and complete rollback. Keep playback stopped for the initial startup/shutdown check. Capture the new broker first-failure cause and application termination record if shutdown is not clean. Preserve the known-working private route for comparison.

Physical audible output through the SL3, independently observed deck-mode labels, independent platter control, sustained operation and a permanent repeatable installation remain open. No live result, timing certification or Mac validation is inferred from these software and Plan checks.

## Toward a private Windows beta

The first packaging implementation now supplies a release-bound reusable launcher. One executable and one installer-resource package passed two separate complete read-only session Plans, eliminating the per-session compile/package step for that candidate. Real Frida child-environment checks also passed using owned Python children. Actual Serato installation through the reusable executable remains untested. [Implementation, checks and limits](reusable-session-launcher.md)

The next packaging deliverable should be a small private beta rather than asking other owners to reproduce the development checkout. It needs a relocatable, versioned release bundle; local prerequisites and exact Serato-version checks; one initial installer; one ordinary-user Start/Stop launcher; and a journaled uninstaller/recovery route. Current generated launchers remain source-bound to one checkout/session and cannot simply be copied to another owner as a finished driver. Removing repeated installer clicks requires a separately validated installed-driver reconnection handoff; the current successful installer-completion route does not solve it.

Before broader release, validate physical output and monitoring, independent deck control, graceful shutdown after playback, repeated start/reconnect/reboot recovery, longer sessions, and installation/removal on a clean second Windows PC. Bundle project-owned components and clearly identify external prerequisites; do not publish private Serato resources, complete vendor applications or raw commercial-music captures. Preserve normal Windows security and existing product authorization. A small beta can collect these hardware results while the portable installer/launcher is developed, but must retain the diagnostic limits and exact supported version until those limits are replaced by verified production behaviour.
