# Installer exclusion and recovery journal

The installer now has original lock/journal primitives with 31 passing actual
Windows workspace tests. They provide the next building blocks for protected
install/uninstall. A complete installer and automatic recovery are still
unfinished; no elevated deployment or live registration changed.

`scripts/asio-install-journal.py` exposes an inert default/`--plan` CLI only.
Its trusted-caller `transaction` context accepts an existing protected base,
an explicit policy, install/uninstall action and lowercase reviewed hash pins.
Production policy additionally requires explicit native x64 elevation, the
native Program Files `SL3 Rebuild` base and the existing ancestor checks.
There is no automatic UAC, base creation, privilege change or policy override.
Workspace tests use a current-user descriptor that is never certified as
production protection.

## Exclusion

The context retains parent/base handles and opens the fixed
`installer-lock.json` with no sharing. It validates its owner, exact protected
DACL, regular single-link identity and expected base-identity/policy record.
A missing lock is created new with its descriptor; an existing one is read and
never overwritten. Foreign, partial or damaged lock data is preserved and
refused. A competing transaction fails immediately, with no timeout/retry loop.
The fixed lock coordinates package operations across processes which use this
protocol. It does not stop unrelated registry editors or malicious privileged
code. Callers must use the same base for all project package operations.

Lock and journal files persist after exit. Exclusivity comes from the live
Windows handle, not the pathname: normal close or process death releases it.
The process test intentionally exits without Python cleanup, then confirms a
new transaction can acquire the unchanged persistent lock. This is not a
machine-crash test. The sharing contract follows
[CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).

## Journal

Each transaction creates a new protected `transaction-<uuid>.jsonl` alongside
its stage, not inside the directory that cleanup removes. Its header binds the
base identity, journal file identity/name, action, policy and caller's reviewed
hash pins. Hash pins remain caller assertions until the installer checks them
against the actual package/stage.

Records have canonical JSON, consecutive integer sequence numbers, the previous
record's SHA-256 and their own SHA-256. Each append checks policy and prior bytes,
writes the bounded record, calls
[FlushFileBuffers](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers),
and reads back the exact accumulated bytes before returning. An append error
poisons that writer: later calls fail rather than authorizing another mutation.
Records are limited to 64 KiB, 4096 records and 4 MiB total. Journal use is
synchronous under one trusted caller; concurrent calls on the same writer are
not supported.

The callback works with the existing file/registry primitives. File cleanup's
full `validated` recovery record is flushed before its first deletion, and
before/after events preserve the observed sequence. An interrupted caller can
leave an intent without an outcome. The journal does not invent the outcome,
certify installation success or automatically replay any operation.

Inspection validates the file/base identities and canonical sequence/hash chain.
Corrupt complete records refuse inspection. A bounded incomplete final record
is retained and reported by byte count/hash separately from the valid prefix;
it is not accepted as a completed event. An incomplete header refuses. Hash
chaining detects accidental changes; it is not a signature against an owner
who can replace and recompute the entire journal. Normal administrator-controlled
Windows/NTFS and the trusted installer remain assumptions. Flush/readback and
process-exit tests do not prove storage behaviour during sudden power loss,
directory-entry persistence under every failure or universal hardware durability.

## Verification and remaining integration

The suite covers default/CLI guards, same- and separate-process exclusion,
close/death release, retained records, foreign lock preservation and ordinary
token production refusal. It also exercises changed/reordered/duplicated or
malformed records, incomplete/oversized tails, identical-byte journal replacement,
closed/poisoned writers, simulated flush/partial-write failures and actual files.

Three cleanup integration cases use real workspace stage files: complete cleanup
with a surviving external journal; interruption after exactly one observed
deletion with a matching recovery prefix; and journal failure before the first
deletion with all fourteen stage files retained. No payload code executes.
The reviewed bundle and planned installation/profile locations remain unchanged.
See the [verification record](evidence/install-journal-20261102.json).

The complete wrapper still needs to bind reviewed package/stage pins, enforce
runtime dependencies, hold this context across all file/registry operations,
record final independently observed state and reconcile interrupted operations.
There is no automatic rollback/replay implementation yet. Elevated production
behaviour and ordinary-user write denial remain untested. Current native audio,
measured timing, physical analogue audio and current Serato/two-deck DVS remain
unproved; macOS is deferred.
