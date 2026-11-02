# Recovering journalled incomplete installation copies

The staging writer now journals each new directory/file identity, and each file's
verified completion. `scripts/asio-recover-copy.py` can abort an interrupted copy
using those witnesses, the original reviewed journal and the verified source
bundle. It removes no registry keys, executes no package images and opens no USB
device. The default/`--plan` CLI is inert; mutation requires a trusted API caller.

The full Windows/current-Serato goal remains incomplete. This closes a deployment
recovery case, not audio or DVS validation. Actual protected installation and
ordinary-user write denial still need attended evidence. macOS remains deferred.

## Evidence recorded while staging

The existing coordinator still admits the runtime/bundle, verifies registration
and overlay absence and serializes the transaction before staging. The shared
writer retains its create-new, protected-policy, source-byte snapshot and readback
requirements. Its completed stage receipt schema and payload bytes are unchanged.

New journal steps are:

1. `stage_root_created`: original directory metadata/identity, package/bundle pins
   and policy, before the first intent-file write.
2. `stage_file_created`: name, original identity and intended byte count/hash,
   after create-new inspection but before writing. This includes intent, every
   payload and the final receipt.
3. `stage_file_completed`: identical metadata only after the complete write,
   flush, exact readback and identity/policy recheck.

Payload `before_file` steps remain in the sequence. The full copy has 41 staging
steps: one root witness, fourteen create/complete pairs and twelve payload
before-file steps. Failure of a callback stops subsequent writes. Files and
intent are preserved on failure; no completion is fabricated.

There is necessarily a gap between kernel creation and durable recording of the
new identity. This implementation **does not recover an unwitnessed object**.
Unknown data in that gap is preserved, even if its name or bytes look familiar.
The first protected-base creation gap likewise remains outside this recovery.

## Recovery admission and operations

The API captures the original bundle through held read handles, verifies its
reviewed manifest SHA and captures the old journal without write/delete sharing.
The journal reader checks base/file identities, protected policy, canonical
sequence/hash chain and reviewed whole-file SHA. A bounded incomplete tail is
reported without replay. The journal must have the original `install` header,
matching package/bundle pins, one ordered absent-registration admission and
before-stage pair, and no durable `stage_completed` or `install_completed` event.
Journalled complete stages use [install-abort recovery](asio-install-recovery.md).

Recovery reconstructs the canonical intent and, when possible, the completed
receipt from the original metadata and verified bundle. Staging steps must be an
exact known prefix, with the expected names, intended bytes and matching
create/complete identities. Merely matching a filename is insufficient.

Under a fresh serialized recovery transaction, live project registration and
current-user overlay must both be absent. An existing directory must have its
original identity, resolved path and exact policy. Its inventory must be a subset
of the witnessed created files. Every surviving file is held for exclusive
read/delete and must have its original identity, single-link regular-file form,
policy and expected bytes. A file with a durable completion witness requires its
full exact bytes. Only the last witnessed created-but-uncompleted file may contain
an empty or shorter exact prefix of its intended data. Nonprefix data, changed
completed bytes, unknown names, replacement objects, busy handles, hard links and
reparse points are preserved.

All survivor leases are acquired before the first deletion. The new journal is
flushed before each operation, followed by fresh registration/overlay and inventory
checks. Deletion uses the held handles, not recursive or wildcard removal. Missing
files and an already-absent directory are current observations; they do not prove
which previous process deleted them. An explicit retry pins the same original
journal/bundle and examines current survivors again. The original journal is never
rewritten, and absent files are never recreated.

This is a trusted installer/OS boundary. A reviewed hash is a content pin, not a
signature or a defense against another trusted administrator falsifying history.
There is no power-loss durability or arbitrary concurrent-administrator proof.

## Verification

Run `.venv/Scripts/python.exe scripts/test-asio-recover-copy.py` with an ordinary
Windows token. Tests use actual runtime-gated coordinator/staging operations,
workspace NTFS directories and a fresh UUID-marked private HKCU model. Injected
interruptions bypass ordinary exception rollback but release Python contexts;
they are not real process termination or power-loss tests.

Coverage includes every staging-event boundary, a real short prefix write that is
flushed/read back, the stage-completion journal gap, preservation of unwitnessed
creation gaps, completed-stage refusal, foreign/changed/replaced/hardlinked/busy
survivors, current registration/overlays, wrong review hashes, interrupted recovery,
explicit retry, already-absent reconciliation and late unknown data. Original
journals, source bundle and live machine/current-user registrations are compared,
planned production/profile location presence remains unchanged, and the private
registry namespace is observed absent after cleanup. No package image is loaded
or executed; runtime admission may initialize native System32 dependencies.

The shared staging change also requires affected installer/staging/cleanup/recovery
regressions. Logs and detailed test artifacts remain private; the public
verification record binds actual results and current source hashes.

All **65 new checks** and **269 affected regression checks** pass. See the
[verification record](evidence/copy-recovery-20261102.json) for current source
pins, suite/case scope and private checkpoint hashes.

The verification record distinguishes exact local source-byte hashes from
published Git LF-byte hashes. Three unchanged analysis/test helpers use CRLF
locally; their published bytes differ only by that line-ending normalization.
Suite-reported source pins remain bound to the actual local files tested.
