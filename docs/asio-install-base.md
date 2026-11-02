# Protected installer base and directory read leases

The production install API can now prepare its fixed base before starting a
journaled installation. The new 17-case workspace suite and nine affected suites
pass: **228 distinct checks** in total. Read-only host preflight passes without
changing the actual Program Files base or ancestor descriptors. Elevated creation,
installation and ordinary-user write-denial proof remain unperformed.

## Preparation

`scripts/asio-install-base.py` has inert default/`--plan` behaviour and an explicit
read-only `--check-production` CLI. Mutation is exposed only to a trusted caller
through `prepared_base`. Production requires explicit x64 elevation, the native
Program Files `SL3 Rebuild` path, the reviewed ancestor predicate and exact
SYSTEM/Administrators-full, Users-read/execute protected base policy. The test
policy adds the current user and never certifies production protection.

The API holds ancestor handles and either creates **only the final directory**
with its descriptor already supplied, or opens and verifies the existing object.
It never creates missing parents, follows an accepted reparse point, repairs a
descriptor or replaces a file. Existing contents are preserved without being
certified as project-owned. A verified base and parents remain held throughout
the caller's context. Consumer errors keep their original exception/phase receipt.
The base is never automatically deleted on failure.

[CreateDirectoryW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectoryw)
supports creation-time descriptors on filesystems with persistent ACLs and does
not create intermediate directories. In the real synchronized first-create race,
one call succeeds and the other receives error 183. The losing caller does not
silently reopen or repair the winner's directory. A later explicit retry can
verify and reuse it.

The later [bootstrap journal](asio-base-bootstrap.md) now records an absent-base preparation header in a protected sibling file before creation, then the verified new directory identity before installation continues. Explicit recovery can remove that witnessed directory while it is empty. A crash between kernel creation and the persisted identity record remains unwitnessed and preserved. Existing contents are never claimed owned or removed; atomic bootstrap and power-loss durability remain unproved. The checks below describe the earlier preparation checkpoint, with current verification in the bootstrap report.

## Directory sharing correction

The first new rename test failed: an open directory with access `0x20080`
(`READ_CONTROL | FILE_READ_ATTRIBUTES`) and share mode 3 still allowed rename.
An explicit native calibration reproduces that behaviour, observes the same
object at the new path and restores the original path. That metadata-only open
was insufficient for the intended directory lease.

The shared Python `open_file(..., directory=True)` now also requests
`FILE_LIST_DIRECTORY` (`0x1`). With the same no-delete-sharing policy, the wrapper
refuses the real rename and the directory remains at its pinned path. This
strengthens all Python ancestor/base/stage directory opens, not only the new
preparation API. Microsoft describes access/sharing interactions and the special
handling of attribute requests in
[CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew);
the exact contrast above is also measured on this host.

The three C++ directory opens found in the controller already request
`GENERIC_READ`. No C++ source changed; prior native build/source pins still match
and the unchanged 59-test Release/Debug builds were not rerun. This inspection is
not a universal filesystem attack proof. Normal administrator-controlled Windows,
NTFS and namespace trust assumptions still apply.

## Installation connection

The production install entry now validates the reviewed bundle, performs runtime
admission and checks registry/container/overlay conflicts before preparing the
base. It retains the preparation context through `install_owned`, which repeats
fresh runtime/admission checks and holds its own installer lock/journal before
staging or registration. The resulting phase receipt includes base preparation
on success or an `InstallFailure`. No mutating CLI or automatic UAC is exposed.

This removes the API's old requirement for a manually prepared base. The positive
production branch remains untested: the isolated installer regression proves its
existing staging/registration logic, while the ordinary-token production gate
refuses before machine operations. No test policy or token bypass is used to
pretend a workspace result is a protected deployment.

## Verification

The 17 new cases exercise actual native preflight, creation and reuse, existing
foreign-data preservation, wrong descriptor/owner/type refusal, missing-parent
refusal, retained rename exclusion and its raw metadata-only control, consumer
failure/retry, the two-contender creation race and winning object identity.

Because the central directory-opening wrapper changed, the 24 staging, 26 cleanup,
16 ancestor, 17 runtime, 20 installer, 31 journal, 20 removal, 22 registry-recovery
and 35 file-recovery cases were rerun. They all pass. One initial staging run's
writable-open fixture collided with another suite's deliberate source read lease;
it was rerun alone after readers exited. Runtime was also repeated alone. Both
initial failure logs are retained privately; neither is presented as a passing
run. The native metadata calibration remains in the final passing suite.

Test registry namespaces are removed/observed absent, private junction tags are
removed/rechecked, original bundles/journals and live registration remain unchanged,
and host production-base/ancestor snapshots compare equal. See the
[verification record](evidence/install-base-20261102.json).

Interrupted install/copy recovery, attended protected installation/activation,
ordinary-user write denial, current native/physical audio and measured timing
remain unproved. Legitimate current Serato admission and two-deck DVS remain
unresolved; macOS is deferred. The full rebuild goal stays active and incomplete.
