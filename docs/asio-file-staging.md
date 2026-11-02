# File staging, ACL checks and the current production refusal

The file-staging primitive now copies the reviewed package into a new directory,
assigns explicit protected descriptors at creation, validates owner/DACL/ACEs,
and checks exact bytes and file identities. Its 24 actual Windows tests use a
current-user-owned descriptor in the workspace. That descriptor is explicitly
refused by production inspection; it is not proof of administrator-owned
installation protection.

The initial checkpoint **refused an ancestor ACL on this host**. The later
[volume-anchor review](asio-volume-anchor-review.md) corrects that software
predicate; read-only production preflight now passes.
No Program Files directory, live registration, trust setting or security policy
was changed. Protected installation and uninstall remain unfinished.

## Commands and scope

```powershell
.venv/Scripts/python.exe scripts/asio-file-stage.py --plan
.venv/Scripts/python.exe scripts/asio-file-stage.py --check-production --bundle "C:\path\review-bundle" --expected-bundle-sha256 <reviewed-lowercase-manifest-sha256>
```

Default/plan mode writes nothing. Production checking reads captured package
bytes, resolves Program Files and LocalAppData through `SHGetKnownFolderPath`,
checks the current profile and direct-child installation scope, and examines
existing ancestor permissions. It creates nothing and performs no registration,
PE payload execution or device access. Paths supplied through environment
variables are not sufficient for this native scope check.

The explicit `--stage-production` route requires an already elevated native x64
process; it does not launch UAC. It uses the fixed administrator-owned policy,
requires a new destination, and verifies the existing project base or creates it
with that policy. There is no test-policy/destination override on the CLI.
**The elevated positive path has not run.** The original ancestor-policy refusal is resolved by the later volume-anchor
review, without changing the host ACL. This is a file-copy component, not the complete
installer or an instruction to register the writable review bundle.

## Captured bytes and exact ownership

Package verification now has a shared `verify_payloads` operation for captured
bytes. The stager opens source files with write/delete sharing denied, reads
bounded bytes through those handles, checks the reviewed manifest hash and
inventory, and applies the same PE/locator/provenance/plan checks to those exact
bytes. It copies the captured data, never a pathname re-opened after verification.
The total payload is bounded to 64 MiB, with the existing 16 MiB per-file limit.

The intended production descriptor has Administrators as owner, SYSTEM and
Administrators with full control, and Users with read/execute access. Each
directory/file receives an explicit protected DACL at creation. Existing objects
are never overwritten or permission-repaired to force acceptance. The trusted
low-level helper also accepts a caller-supplied policy for tests; the CLI does
not expose that capability.

| Validation target | Owner/control used | Current evidence |
| --- | --- | --- |
| Workspace tests | Current-user owner and explicit full-control ACE, plus the production-style SYSTEM/Administrators and Users entries | Real file creation and descriptor readback pass |
| Production | Administrators owner; full control only for SYSTEM/Administrators; Users read/execute | Policy is implemented; elevated creation and ordinary-user write denial have not been demonstrated |

Directories are retained with deletion sharing denied. The code rejects reparse
points, unexpected resolved paths and file-type mismatches. Staged files must
have a single link. Owner, protected-DACL state and the exact supported ACE list
must match the policy. A file's bytes are read back and hashed through its
creation handle after flush.

A protected `stage-intent.json` precedes payload writes. It records the package,
directory identity, expected policy and planned hashes with `complete: false`.
Only complete copy/descriptor/readback checks permit `stage-record.json`, which
binds the directory and each file identity as well as their bytes. There are 14
files in a complete stage: the package's eleven payloads, its manifest, the
intent and the completed record. Partial output is retained with its intent,
never presented as a completed stage or automatically deleted.

`inspect_stage` checks the reviewed stage-record hash, directory identity,
inventory, each file's identity/hash/descriptor and the original package
contract. Production inspection additionally requires the planned installed
DLL location and protected base/ancestor checks. It refuses a current-user test
descriptor rather than treating a test result as production protection.

## Initial ancestor refusal (superseded)

The initial read-only check rejected an effective Authenticated Users ACE on
`C:\` with mask `0x1301bf`. The existing Program Files descriptor is separately
readable and has TrustedInstaller ownership. The conservative check examines
the full ancestor chain, and that result was a **policy refusal needing
review**, not a conclusion that Windows' current root ACL must be changed.
Neither the predicate nor the host ACL was relaxed to obtain a pass.

The original refusal remains visible in its historical verification record.
The later volume-anchor review records native access checks, private filesystem
experiments, the corrected policy and its explicit platform-trust assumptions.
No change to drive-root permissions was proposed or performed.

Microsoft documents creation-time descriptors in
[CreateDirectoryW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectoryw),
handle-based descriptor retrieval in
[GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo),
and native folder resolution in
[SHGetKnownFolderPath](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath).

## Verification and remaining work

The 24-case suite exercises real file/ACL creation/readback, current-user and
production-policy separation, held source sharing, exact byte copies, existing
destination preservation, bad hashes and missing parents. It also covers
interrupted copy with retained intent/no completion record, changed data, extra
files, hard links, same-byte file replacement, wrong receipt hashes and a receipt
copied to a different directory. A synthetic empty text file temporarily gets
an extra write ACE for a negative test; its DACL is restored in `finally` and
verified afterward. No machine/file-system security policy is changed.

Because byte verification was refactored, the 26 package and 26 real registry
cases were rerun and pass. The registry test namespace is removed and verified
absent; its live planned machine/current-user entries remain unchanged. Native
C++ source/builds did not change, so the prior 59-test Release/Debug checkpoints
retain their original scope and were not rerun.

See [the verification record](evidence/file-staging-20261102.json). Elevated production staging, ordinary-user write-denial proof, the
serialized privileged install/uninstall wrapper, runtime checks and owned file
cleanup remain unfinished. Genuine timing/native and physical audio, current
Serato/DVS admission and the later macOS work remain unproved. No firmware or
device operation ran in these tests.
