# Recovering partially removed stage files

An explicit reviewed-bundle/journal recovery path now completes interrupted file
removal, including an empty remaining directory or an already-absent stage with
an uncommitted original completion record. All 35 Windows workspace/private-HKCU
cases pass. No elevated production operation or installed ASIO activation ran.

`scripts/asio-recover-files.py` exposes an inert default/`--plan` CLI. Its trusted
API requires the original verified bundle and manifest SHA, original uninstall
journal and whole-file SHA, original stage SHA, policy and registry roots.
The production wrapper selects read-only real registry roots and requires explicit
elevation; the transaction enforces x64, fixed native Program Files base and
protected policy. It does not request UAC or modify registration, a session
pointer, native broker, firmware or security policy.

## Evidence binding

The bundle is captured through held handles and fully verified. The old journal
is held without write/delete sharing, must match the reviewed SHA and pass its
identity/policy/sequence/hash-chain checks. It must be an uninstall transaction
with one validated stage snapshot, matching package/bundle/stage pins, an exact
own or absent original registration snapshot and no original user overlay.
The original stage record's canonical bytes must reproduce the reviewed SHA.

Every original payload's size/hash is checked against the captured bundle.
The original intent is reconstructed from those bytes and original directory
metadata; its size/hash must match the receipt. The canonical receipt is also
reconstructed. This permits verification when the stage no longer contains its
manifest, plan, intent or receipt, without creating replacement files.

Current project registration and user COM overlay must both be absent before
file recovery, before each deletion and at completion. This path does not remove
remaining registry keys; the separate intact-stage registry recovery handles
that case. No old journal event is blindly replayed as a command or inferred
current state.

## Surviving objects and removal

Under the same fixed-base installer lock, an existing directory must retain the
original native identity, path and exact protected policy. Any unknown name
refuses removal. Each survivor is opened with exclusive read/delete access and
checked before the first mutation: regular non-reparse type, single link, policy
and exact expected bytes. Payload and intent IDs must match the originals.

**Legacy receipt limit:** the original stage record did not contain its own file
ID. A surviving `stage-record.json` is therefore checked by exact canonical
bytes/hash, protected policy, type and single-link status, without claiming its
original identity. This is reported explicitly. A same-byte replacement of a
payload or intent still fails its original-ID check.

Freshly observed missing files are listed separately from files marked and then
observed absent during this attempt. The new journal flushes the original source
reference, full stage record and current missing inventory before mutation.
Binaries are removed first and intent/receipt last, skipping absent names. Each
step rechecks inventory, policy and registry absence, uses the checked handle for
deletion, closes it and separately observes absence. The original directory is
removed only if empty and still correctly identified/protected. Unknown data is
never recursively removed, permissions are never repaired and processes are
never terminated.

If the directory is already absent, expected path absence and registration
absence are observed and a new reconciliation completion record is flushed.
No directory or file is recreated. This establishes current desired absence,
not who caused it or an historical successful commit. A recreated directory with
a different native ID is preserved even when empty.

Errors retain exact new deletion/absence observations and attempt a failure
record. A poisoned writer cannot claim persistence or success. An explicit retry
can use the unchanged original reviewed journal and freshly inspect remaining
objects. Base locking and rechecks coordinate trusted installers; they are not
a global filesystem/registry transaction or protection against malicious
administrators, filesystem drivers or an authorized metadata writer. Flush and
readback are not power-loss durability proof.

## Verification

The suite interrupts the real original removal before file deletion, after each
of fourteen file deletions, and after directory removal with a failed completion
record. Recovery checks exactly the observed missing/newly deleted counts and
flushes a new completion. A separate non-prefix missing-file case verifies fresh
inventory handling rather than inferred deletion history.

Other cases preserve unknown/changed files, identical-byte payload replacements,
hard-linked survivors, busy readers, remaining own registration, user overlays,
wrong bundle/journal/stage hashes, a recreated empty directory and late unknown
data. A failed journal after one new deletion reports exactly one additional
removal; retry observes two files already absent and removes only twelve more.

Original bundle and journals remain unchanged. Foreign registry siblings and
live planned HKLM/current-user registration remain unchanged. The marked UUID
registry namespace is removed after owner/boundary checks and independently
observed absent. As earlier tests, reviewed registry strings point at Program
Files while disposable stages use workspace/current-user policy; this proves
recovery coordination, not installed activation or production protection.
See the [verification record](evidence/file-recovery-20261102.json).

Interrupted install/copy recovery and protected-base bootstrap remain unfinished,
along with attended production installation/removal and ordinary-user write-denial
proof. Native/physical analogue audio, measured timing, legitimate current Serato
admission and two-deck DVS remain unproved; macOS is deferred. The full goal stays
active and incomplete.
