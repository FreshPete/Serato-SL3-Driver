# Recovering interrupted Serato resource staging

**Later update:** the protected wrapper now requires [session-specific ownership](protected-session-ownership.md) for interrupted protected state. Legacy dirty state without that record is preserved for manual review. The resource-only fixture cases below do not exercise that wrapper prerequisite.

Explicit session recovery now handles two previously missed, hash-verifiable states: a candidate archive staged before installation (`install-staged`), and a reviewed installer resource left at its `.sl3-pending` path. The existing recovery branch now preflights the resource set before permit revocation or native uninstall. [Checkpoint evidence](evidence/interrupted-resource-recovery-20261106.json)

## Implementation

`Get-Sl3InstallerResourceRecoveryPlan` in the existing resource-transaction library is read-only. It reconstructs archive witness identities through the existing transaction state reader, accepts the five known states (`original`, `install-staged`, `installed`, `rollback-staged`, `restored`), and checks both the published and pending installer copies against the selected plan's bundle hash. It requires quiescence and protected-path callbacks, including existing files and their parents. Unknown hashes, conflicting archive witnesses or reparse paths are refused before resource mutation.

`Restore-Sl3InstallerResourceState` repeats that preflight, restores an installed/rollback-staged archive, clears verified archive witnesses, and removes only matching copies at the two fixed installer filenames. It rechecks quiescence, path protection and content before deletion and verifies the final original/no-installer-copy state. An `install-staged` archive keeps the original live archive and removes its verified candidate stage through the existing witness-cleanup function.

The protected session wrapper supplies its existing real ACL and closed-Serato checks. It preflights these resources before changing the permit/native stage, then calls the recovery function after the existing native rollback. Existing original-owner checks, administrator requirement, broker-retirement proof for native rollback, launcher-cache retirement and refusal to overwrite unknown state remain in place.

Preflight is a point-in-time check, not a multi-file atomic transaction. If a protected file changes later, recovery can stop after completing earlier verified steps. Changed files are preserved; the function does not fabricate a successful result or roll forward unknown bytes.

## Verification

Twelve new cases use real Windows file operations and synthetic contents inside retained project-local fixtures. They cover clean no-op, all five known archive states, pending/published/both installer copies, unknown hashes, corrupt backup, active-owner/protection rejection, retargeted witness paths and an installer changed during rollback. The read-only plan leaves file contents unchanged. Unknown files are preserved, including a late change after earlier rollback steps.

The existing 22 archive-transaction cases also passed, including actual atomic replacement, destination ACL preservation, junction rejection and refusal of an ordinary-user-owned deployment path. The new fixture's protection callback deliberately substitutes for production ACL enforcement; it does not validate administrator recovery against the installed application. No protected Serato file, registration, driver binding or device was changed.

A separate read-only call on this host used the real protection checks and observed the original archive with neither installer copy present. It passed without elevation or file mutation. With five complete-plan, fifteen kit, eight Stop and eight fresh-preparation regressions, the checkpoint passed 70 targeted cases. The final session-status observation also found the original setup clean.

Fresh launcher/session/kit bindings include the corrected resource library and wrapper. Audio binaries are unchanged. Live protected recovery, a user-facing recovery entry, interrupted native-install journal recovery and end-to-end install/uninstall on another PC remain separate work. This checkpoint fixes known resource rollback gaps; it is not a complete automatic recovery feature or a validation of Serato shutdown.
