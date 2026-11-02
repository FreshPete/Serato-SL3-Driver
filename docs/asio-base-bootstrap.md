# Journal-witnessed empty-base recovery

Initial production-base creation now has a protected sibling bootstrap journal before its first directory write. A trusted caller can explicitly remove the same witnessed base while it is still empty. This adds recovery after the creation witness persists; it does not make creation/journaling atomic or authorize removal of installation data.

## Preparation and ownership

`prepared_base` first retains and checks the existing parent chain. For an absent base it creates a new protected sibling file named `<base>.bootstrap-<guid>.jsonl`, writes a flushed/read-back header, then attempts `CreateDirectoryW`. The header binds the target path, parent identity, journal identity/name and exact owner/ACL policy. After opening and verifying the new directory under a retained read lease, preparation appends its directory identity and returns the journal path/SHA in its phase receipt.

Production retains its fixed native Program Files `SL3 Rebuild` path, native x64/elevated-token and trusted-ancestor checks. The journal is created with the production file policy already supplied; workspace tests use a separate explicit current-user policy. The existing production installer calls this preparation API, so no separate unconnected prototype is required. No mutating CLI or automatic UAC is exposed.

An existing base is verified and reused without writing a bootstrap journal or claiming its contents. Competing first-create attempts keep separate journals: only a successful directory create followed by a persisted identity record supplies a creation witness. A losing or incomplete attempt cannot claim the winner's object. Bootstrap files remain protected siblings for review and recovery; they are not recursively cleaned up.

## Explicit empty-base cleanup

`recover_empty_base(base, original_journal, expected_journal_sha256, policy)` is a trusted-caller API. It requires the reviewed lowercase SHA, the original single-link protected journal, its exact header/file/parent identity binding, exactly two complete canonical records and the witnessed directory identity. Torn tails, missing witnesses, substituted journal files and changed hashes are refused. Production additionally requires the normal fixed-path/elevation/ancestor policy; no security setting is changed.

The current base must either be the same empty directory or already absent. A present directory is held with delete access and no delete sharing, while its exact policy, path, identity and empty inventory are checked. A separate protected recovery journal records validation and delete intent before the native directory delete. The API records observed absence afterward. It never removes children or changes registry state. A nonempty base, including an installer lock/journal, stage, payload or foreign file, is preserved.

Actual native deletion also refuses a directory that gains a file after the last empty-inventory check. Active base read leases prevent the delete-access open. If completion journaling fails after deletion, the operation reports failure with its observed phase; an explicit retry against the same original witness can record already-observed absence. No automatic retry, rollback or journal repair runs.

The reviewed hash comes from the trusted installer/reviewer; the hash chain is not a signature or proof against a malicious administrator. Normal trusted-administrator/NTFS assumptions remain. Existing file/registration recovery and uninstallation keep their separate contracts.

## Remaining creation gap

A crash after the kernel creates the directory but before the identity record persists still leaves no durable creation witness. Header-only, torn or otherwise incomplete source journals do not authorize deletion. The directory and journal remain preserved for explicit verification/reuse. A failure before the initial header persists prevents the directory create entirely, but can leave a new empty protected journal file. No atomic bootstrap or power-loss durability claim is made.

No production bootstrap or cleanup has run. Existing review bundles and physical/audio/Serato evidence retain their prior versions. This change does not establish a protected installation, native audio/timing, stable reopening or current Serato/two-deck DVS.

## Verification

Twenty actual ordinary-token Windows workspace cases cover durable creation/removal, original-journal and sibling preservation, explicit absence retry, existing-base reuse, foreign/installer contents, directory replacement, wrong hashes/paths, copied and hardlinked journals, active read leases, creation-witness failures before/torn/after persistence, initial-header failure, cleanup journal faults before/after deletion and a real late foreign-file arrival. The host production base and ancestor snapshot remains equal.

The 17 existing preparation, 20 installer and 31 journal cases also pass: 88 checks in total, recorded separately in the [verification record](evidence/base-bootstrap-20261102.json). No package binary, device, production ACL or live registration is exercised. Run `scripts/test-asio-base-bootstrap.py` from the ordinary project Python environment to reproduce the workspace checks.
