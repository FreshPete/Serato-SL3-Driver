# Recovering interrupted registry removal with an intact stage

An explicit reviewed-journal recovery path now finishes interrupted own registry
removal when all fourteen stage files remain intact. All 22 Windows workspace /
private-registry tests pass. This is partial recovery coverage, not a general
installer recovery engine or an elevated production test.

`scripts/asio-recover-uninstall.py` exposes an inert default/`--plan` CLI only.
Its trusted-caller API requires the original journal path and reviewed whole-file
SHA-256, the original stage SHA, explicit policy and registry roots. The production
entry selects the real roots and requires explicit elevation; transaction checks
also enforce native x64, the fixed Program Files base and protected policy.
No automatic UAC, firmware/security change, device access or package execution
is performed.

## What authorizes recovery

The original journal is held without write/delete sharing throughout recovery.
Its bytes must match the reviewed SHA; its protected descriptor, native file/base
identities, filename, canonical record sequence and hash chain must pass normal
journal inspection. An active incompatible writer refuses the read lease.

The original action must be uninstall and contain exactly one validated uninstall
snapshot. Re-encoding its complete stage record must reproduce the reviewed
stage SHA. Header package, bundle and stage pins must match that record. The
full stage inspector must verify the same directory and all fourteen original
files, including receipt, native identities, bytes, descriptors and bundle
contract. Missing, changed or replaced objects refuse recovery.

After acquiring the same fixed-base installer lock, the coordinator pins every
stage file and revalidates them. It reads the plan through a retained handle and
requires the original journal's pre-removal snapshot to contain **all three
exact own registry entries** and no user overlay. A journal that began with
absent registration or came from an install transaction cannot substitute for
that evidence. A bounded torn final record can be preserved as an unknown tail;
only the verified complete prefix supplies evidence. The source journal is never
rewritten or truncated.

## What happens next

Current registration may contain any subset of those three own entries. Every
remaining value, type and child list must match the plan, accounting for child
entries already absent. Any foreign value, wrong type, extra child or current-user
COM overlay refuses all further removal.

A new transaction journal records the reviewed original journal reference, full
stage record and fresh registry state before mutation. Already-absent keys are
reported separately from keys deleted in this attempt. InprocServer32, its empty
CLSID parent and the own ASIO leaf are removed in that order, skipping absent
entries. The subset and overlay are rechecked, an intent is flushed, and each
opened key is checked again before deletion. No missing key is recreated.

After registration absence is observed, the existing file-cleanup primitive
takes its exclusive deletion handles and repeats full stage checks. Final
registration, overlay and directory absence are checked before a flushed recovery
completion record permits success. Errors retain exact phase receipts and attempt
a failure record; a poisoned writer cannot claim that record was persisted.

This remains a cooperating-installer lock with conservative rechecks, not an
atomic registry/filesystem transaction or a boundary against privileged hostile
code. Journal ownership and hash chaining are not a code signature. Recovery
does not infer why a key disappeared or who removed it; it checks current absence
and deletes only remaining exact owned entries within the reviewed scope.

## Verification

The suite creates actual stages and own registry entries in a marked private
HKCU UUID namespace, then interrupts the real removal coordinator after zero,
one, two or three registry deletions. Recovery removes exactly the remaining
keys and fourteen files, observes absence and leaves a new completion journal.

Negative cases preserve foreign values/children, wrong types, user overlays,
changed stage bytes, wrong journal/stage hashes, an identical-byte journal with a
new native identity, a journal from an install action and an active installer
lock. Failure before the recovery validation record prevents mutation. Failure
after one additional registry deletion reports that exact partial state; an
explicit retry with the unchanged original reviewed journal reads fresh state
and removes only the last key. A stage with one file already deleted is refused
without further registry/file changes.

Original journals remain byte-identical. Foreign siblings and live planned
HKLM/current-user registrations remain unchanged. The test namespace is removed
after exact owner-marker/boundary checks and independently observed absent.
Reviewed package and planned installation/profile paths remain unchanged.
As with the earlier coordinator tests, registry strings retain the planned
Program Files location while disposable stages use workspace/test policy. This
does not establish installed ASIO activation or production protection. See the
[verification record](evidence/registry-recovery-20261102.json).

Recovery of partially removed file trees, absent stages with missing completion
records, interrupted install/copy states and fixed-base bootstrap remains
unfinished. Production deployment/write-denial proof, positive current native
transport, physical analogue audio/measured timing and current Serato/two-deck
DVS remain unproved. The full goal stays active; macOS remains deferred.
