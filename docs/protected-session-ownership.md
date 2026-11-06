# Protected ownership of the shared staging slot

Protected staging now claims one session-specific record before copying resources or issuing an installer permit. This prevents a recovery plan from treating another session's identical resource bytes as its own. The record lives beside the fixed installer resource as `8c7758f23375cee18a9cf3be4a3acc15.bin.sl3-session`. [Checkpoint evidence](evidence/protected-session-ownership-20261106.json)

## Protocol

The new library creates the record with exclusive create-new semantics. It records the selected capsule SHA-256, native bundle SHA-256, staging PID and canonical creation FILETIME. After writing and flushing, it retains a read handle that excludes write/delete sharing for the stage's lifetime. The wrapper supplies its existing protected-path and closed-Serato guards. No signing trust, binding or security policy is changed.

Another session cannot claim the same existing slot. Fresh-run, readiness and current-status checks now treat the record as residue even if the original archive is already restored. Recovery requires the exact recorded capsule/native bundle and a retired staging process. It holds a read lease while restoring state, preventing another recovery from removing/replacing ownership mid-operation. The creating live stage can release only its exact own record, after original resources and absent native registration are reported with no cleanup error. Failed cleanup retains ownership for review.

Recovery rechecks record identity before removal. Foreign, malformed, reparse or changed records are preserved. If interrupted protected state predates this protocol and lacks an ownership record, recovery now refuses it for manual review rather than guessing ownership from shared filenames or hashes. This is a deliberate restriction on the explicit recovery path; it does not silently convert legacy interrupted state.

Without a record, an already clean state exits without cleanup mutations. An unowned cached launcher is preserved for review too. This keeps an old clean-state recovery from proceeding into cleanup while a new session claims the slot.

Native files already absent are handled without repeating native uninstall. If a receipt or broker artifacts remain, the existing typed broker-retirement proof is still required; absence of files is not treated as proof that I/O retired.

The read-only recovery inspector now checks the protected record too. Its stage identity covers an interruption before the ordinary wrapper finished publishing its stage PID. Conflicting ownership or missing ownership in dirty state cannot authorise recovery. Snapshot checks remain observations rather than permission to mutate later.

## Verification and limits

Ten new fixture cases passed with real Windows file operations and an owned hidden child. They cover claim/read/self-release, duplicate scope claims, write/delete blocking, foreign-scope refusal, live-stage refusal, retired-stage removal, a concurrent recovery reader, malformed/changed records, failed guards and junction rejection. The fixture substitutes the ACL callback and writes only project-local test data; it does not validate protected marker creation against the installed application.

Recovery classification, current-status, readiness, saved-result and plan regressions passed. Fresh source-bound launcher/session/kit data includes the new library: 45 release sources and 33 complete-plan sources. The four audio binaries are unchanged.

Including actual native recovery-check, copied-kit, fresh-preparation and Stop regressions, this checkpoint passed 86 targeted cases. The final read-only host check reported original state clean and no protected ownership record present. The fixture ownership files remain in project-local test directories for review.

The production staging/recovery wiring has not run live with this protocol. No administrator prompt, Serato startup or SL3 operation occurred. The protocol coordinates trusted project callers at one protected application slot; it is not a boundary against a malicious administrator and is not a multi-file atomic rollback. An automatic recovery command remains unfinished. The next attended startup/normal-close test must validate ownership creation, cleanup and removal together with audio shutdown.
