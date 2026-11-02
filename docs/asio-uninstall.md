# Serialized owned registration and file removal

An original removal coordinator now composes the reviewed stage inspector,
installer lock/journal, constrained registry removal and retained-handle file
cleanup. Its 20 workspace/isolated-registry cases pass. This is not a completed
installer release or an elevated production removal test.

`scripts/asio-uninstall.py` exposes only inert default/`--plan` CLI behaviour.
Its trusted-caller API accepts an explicit stage receipt hash, policy and registry
roots. The production wrapper selects native HKLM and current-user roots itself
and requires an explicit administrator token. The transaction additionally
enforces x64, the fixed native Program Files base and protected ancestor/base
policy. No automatic UAC, device access, payload execution, broker termination
or session-pointer change is performed.

## Ordering and evidence

The stage must be a direct child of the serialized installer base. Full stage
validation and the exact receipt SHA precede transaction creation. The journal
header binds the actual package ID, bundle-manifest SHA and reviewed stage SHA.
Once the fixed-base lock is held, every stage file is opened without write/delete
sharing and the full inspector runs again. The deployment plan is read through
its retained file handle. These leases remain through the registration phase.

The coordinator refuses a current-user COM overlay, foreign registry values or
partially present registration. Either all three own entries must be exactly
owned, or all must be absent. It flushes the full stage recovery record and
registry/overlay snapshots before attempting deletion. Exactly owned entries
are removed through the registry engine; already-absent entries are skipped.

After releasing the stage read leases, the coordinator rechecks registration
absence and no overlay. The file-cleanup primitive then obtains its own exclusive
deletion handles and repeats validation. It removes only the reviewed files and
original empty directory. Final registration absence, no overlay and directory
absence are checked independently, then a completion observation is flushed.
Only that full sequence returns success.

An exception retains the registry/file phase receipts and attempts a flushed
failure record. Failure-journal persistence is reported separately: a poisoned
writer cannot supply a false confirmation. Mutations are not silently reversed.
The following distinct states are deliberately observable:

| Trigger | Result |
| --- | --- |
| Bad stage/hash, outside base or busy installer lock | No registration/file removal |
| Foreign/partial registry or user overlay | State preserved, failure journal where available |
| Journal failure before unregister | Registration and all stage files retained |
| Interruption after first registry deletion | Exact deleted-key list, all stage files retained |
| Busy file after unregister | Registration absent, all stage files retained; explicit retry after reader closes can finish |
| Foreign file appears after unregister | Registration absent, stage/unknown data preserved |
| Completion-journal write fails after removal | Both absence observations retained, overall success remains false |

The base lock coordinates participating installers, not unrelated registry
writers or privileged hostile code. Rechecks are observations, not a global
registry/filesystem transaction. The coordinator does not certify that a running
ASIO client stopped or that the native USB session is released.

## Verification scope

`scripts/test-asio-uninstall.py` creates actual protected test-policy stages under
a fresh workspace UUID and real registry entries under a marked private HKCU
UUID namespace. It verifies complete removal and the failure states above,
including a retained external journal and correct package/stage bindings. Foreign
registration siblings are checked unchanged. The entire private registry
namespace is removed only after checking its exact owner marker and boundary,
then independently observed absent. Live planned HKLM entries/current-user
overlay, the reviewed bundle and planned installation/profile locations remain
unchanged. No payload binary is loaded or executed.

These are **coordination tests**, not installed ASIO activation. The isolated
registry contains the reviewed plan's Program Files strings; the disposable
stage lives under the workspace with an explicit current-user policy. Production
inspection would refuse that stage. This separation is recorded in the evidence
and cannot support a claim that a workspace DLL was installed or activated.
See the [verification record](evidence/uninstall-20261102.json).

Automatic reconciliation of partially removed registry keys, stage absence with
an uncommitted completion record and other interrupted states remains unfinished.
The complete install path, runtime dependency admission, protected production
tests and ordinary-user write-denial proof also remain unfinished. Native/physical
audio, measured timing, current Serato admission and two-deck DVS remain unproved;
macOS is deferred. No firmware or security-policy change is required by this work.
