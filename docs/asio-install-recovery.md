# Interrupted installation: reviewed abort after completed staging

`scripts/asio-recover-install.py` adds an explicit abort operation for an
interrupted original install with a journalled, intact completed stage. It removes
only witnessed own partial registration, then the verified stage. It does not
finish registration, start a session or activate an ASIO component.

This is one recovery phase in the full installer. Interrupted copies, failures
before the stage-completion journal record and the initial base-creation gap
remain unfinished. Existing state in those cases is preserved. Windows audio,
protected production deployment, current Serato admission and two-deck DVS remain
separate unverified requirements.

## Admission and mutation boundaries

The trusted caller supplies the original journal and reviewed whole-file SHA-256,
the completed stage receipt SHA-256, base/destination, policy and explicit registry
root handles. The public command line offers only an inert plan. Production uses
native fixed Program Files scope and an already elevated process; it never starts
UAC automatically. Tests use an ordinary token, workspace directories and a fresh
UUID-marked private HKCU subtree.

The original journal is held immutable, with its directory/file identity and
policy checked by the existing journal reader. Recovery requires an original
`install` header, one validated absent-registration/container/overlay snapshot,
one completed-stage record, exact package/bundle/stage pins and no durable
`install_completed` event. A completed install is preserved for normal removal.
A bounded incomplete journal tail is reported, never treated as an executed step.

Registration callback events after stage completion must be an exact prefix of
the known three-key create/write sequence. A surviving key requires its original
`created` witness. Its current values must be a subset of the exact project names,
REG_SZ types and bytes; its children must be precisely the currently present
known children. Unknown values, wrong types, extra children, unwitnessed keys and
current-user overlays block deletion. Missing values/keys are fresh observations,
not assertions about what the interrupted process finished or rolled back.

The whole stage is verified and its fourteen files held through registry removal.
The retained plan and receipt must match the original journal exactly. A new
serialized recovery journal is flushed before mutation. State is rechecked across
each before-delete journal append and immediately through the registry handle;
deletion is nonrecursive. The ASIO/COM entries are removed child-first. No missing
key is recreated. This assumes the existing trusted OS/administrator boundary;
journal hashes are reviewed content pins, not signatures or protection against
another trusted administrator replacing indistinguishable state.

File cleanup requires fresh absent registration/overlay observations, then the
existing exclusive-handle, identity/bytes/policy-checked deletion primitive. The
callback checks registration absence at every cleanup journal boundary. A busy
file can leave registration removed and the intact stage retained; the failure
report distinguishes that from success. Explicit retry checks the original
journal and all current state again. It does not repeat assumed prior operations.

Before file deletion, recovery also flushes an `uninstall_validated` snapshot
with the original stage record and the now-observed absent registry/overlay.
If cleanup subsequently stops, the existing
[file-recovery API](asio-file-recovery.md) can consume this **new recovery
journal**, its newly reviewed whole-file hash and the original verified bundle.
That path handles partial survivors and already-absent stages. Retrying this
install-recovery API itself still requires an intact stage; it does not silently
choose or perform the separate operation. The original install journal remains
unchanged.

## Validation scope

Run `.venv/Scripts/python.exe scripts/test-asio-recover-install.py` on Windows
with an ordinary token. The suite performs actual isolated stage/registry
operations, injects interruptions after durable original create/write events,
and verifies completion or exact preservation/partial outcomes. Its injected
`BaseException` bypasses ordinary exception rollback while releasing contexts;
it is not a real process termination or power-loss test.

The suite checks all eleven registration boundaries (completed stage, then three
creations and seven value writes), completed-install and partial-copy refusal,
foreign values/types/children and unwitnessed keys, overlays, changed/unknown/
missing/hardlinked files, review-hash errors, installer exclusion, poisoned
journals, late changes and explicit retries. It snapshots live machine/current
user registrations, planned production/profile location presence, the reviewed
source bundle and original journals, and observes its private registry namespace
absent after cleanup. Test registration points to the planned production path,
not the workspace stage, and package code is never loaded or executed.

All **41 new checks pass**. The private test index and logs retain detailed evidence. A public verification
record binds the passing case names, source hashes and reviewed private index.
No result is a protected production install, physical audio or Serato/DVS test.

See the [verification record](evidence/install-recovery-20261102.json) for source
pins, regression scope and checkpoint hashes.
