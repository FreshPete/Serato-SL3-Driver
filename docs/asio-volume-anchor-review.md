# Volume-anchor policy correction

The earlier production refusal came from treating a drive root's Modify rights
as if they granted replacement of protected descendants. The software policy
now distinguishes a verified OS volume anchor from ordinary ancestor
directories. Read-only production preflight passes on this host without any
host ACL change. Elevated staging and installed audio remain unproved.

## Evidence used

The new read-only inspector obtains security descriptors from held handles and
uses Windows `AccessCheck` with a duplicate of the current process token. The
duplicate is never impersonated and no privileges are enabled or removed.
The observed non-elevated token lacks `SeCreateSymbolicLinkPrivilege`; only
`SeChangeNotifyPrivilege` is enabled among its recorded privileges.

| Object | Current token's object-ACL result |
| --- | --- |
| `C:\` | Add-file/subdirectory, write EA/attributes and delete-this-object allowed; delete-child, write-DACL and write-owner denied |
| Program Files | All eight tested mutation rights denied |

These are object security-descriptor results, not successful filesystem writes
or permission to remove a volume root. Microsoft distinguishes specific
directory rights in [File Access Rights Constants](https://learn.microsoft.com/en-us/windows/win32/fileio/file-access-rights-constants)
and describes [AccessCheck](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-accesscheck).

A fresh workspace fixture then uses the same effective `0x1301bf` Modify mask
on an ordinary parent and a protected child. Actual child opens for data-write
and DELETE fail with error 5. Adding `FILE_DELETE_CHILD` (`0x40`) to the parent
allows a DELETE-access handle to that child, while child data-write still fails.
No delete disposition is set and the child bytes remain intact. The fixture
owner is the current user, so this experiment does not prove production
ownership or denial of that owner's ability to change a DACL. Fixture ACLs are
restored afterward.

This supports treating add-file/write rights separately from child replacement.
Microsoft states that a parent's descriptor does not generally control access
to a child in [File Security and Access Rights](https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights).

## Corrected gate

Every ancestor still requires a trusted owner and a non-null DACL. Reparse
points and unexpected resolved paths remain refused. The ordinary-directory
predicate continues to reject untrusted effective data/attribute writes,
generic writes, deletion, delete-child and ACL/owner changes.

The narrow anchor treatment applies only when a held handle's resolved path is
the drive root itself. Windows must return a native volume GUID and identify an
NTFS filesystem with persistent ACL support. The GUID path returned for the
held root handle and its volume serial must match the native mount/volume
queries. An ordinary directory or mounted
folder does not receive this treatment. See Microsoft's
[GetVolumeNameForVolumeMountPointW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getvolumenameforvolumemountpointw)
and [GetVolumeInformationW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getvolumeinformationw).

For that OS anchor, untrusted `WRITE_DAC`, `WRITE_OWNER`, `FILE_DELETE_CHILD`
and generic-all grants remain forbidden. Its own Modify rights are no longer
equated with rights on the protected Program Files object. Program Files and
the project's protected base retain the ordinary strict checks, and production
files still require administrator ownership and the exact protected descriptor.
There is no CLI override for declaring a path an anchor; the classification is
derived from the actual handle and native volume APIs.

This is an explicit platform trust assumption: the existing administrator-owned
Windows volume/mount namespace and filesystem implementation are trusted. It is
not a certificate against arbitrary privileged code or every filesystem-filter
reparse mechanism. No privilege or host permission is changed to establish that
assumption. User-owned workspace stages still fail production inspection.

## Reparse experiment and limits

The suite also calibrates the mount-point tag `0xA0000003` in fresh workspace
directories. Setting it on an empty source succeeds with the observed token;
setting the same tag/buffer on a nonempty source fails with error 145. The tag
is removed in `finally` through the original handle, and the original directory
identity, source data and target sentinel remain intact.

This is evidence about that directory-junction case on this host. It is **not**
a volume-root reparse test or coverage of symbolic-link, cloud or other reparse
tags. No mutation is attempted on `C:\`, Program Files or other existing host
ancestors. The native-volume trust decision is not derived solely from the
empty/nonempty junction result.

## Commands and verification

```powershell
.venv/Scripts/python.exe scripts/inspect-asio-ancestor-rights.py --plan
.venv/Scripts/python.exe scripts/inspect-asio-ancestor-rights.py --inspect
.venv/Scripts/python.exe scripts/test-asio-ancestor-rights.py
```

The inspector's public CLI is plan/read-only only. The 16-case suite includes
actual Windows access checks and private filesystem operations, four synthetic
ACL-model refusals for dangerous anchor rights, and an actual ordinary-directory
Modify refusal. Host descriptor/access snapshots match before and after the
suite; private ACLs are restored and private junction tags removed.

The 24 file-staging regressions also pass, including the now-successful
read-only production check and continued rejection of a user test descriptor.
Package/registry source and native C++ did not change; their prior 26/26 and
59-test Release/Debug results retain their previous scope and were not rerun.
See [the verification record](evidence/volume-anchor-review-20261102.json).

No administrator-owned staging, ordinary-user write-denial proof, live COM/ASIO
registration, privileged install/uninstall or native/physical audio occurred.
Those, genuine measured timing and current Serato/DVS admission remain pending.
