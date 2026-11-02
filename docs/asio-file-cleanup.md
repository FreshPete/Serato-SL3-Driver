# Owned staged-file cleanup

The file-stage helper now provides a cleanup primitive for a completed, reviewed
stage. Its 26 actual Windows workspace tests pass. This is one part of the
unfinished protected installer/uninstaller, not an installed driver release.
No Program Files cleanup, live registration change or device operation was run.

## Validation and removal

`remove_stage` requires the exact completed stage-record SHA-256 and policy. It
first uses the full stage inspector, including the original bundle contract.
It then holds the parent chain and the original directory, opens **all fourteen
files** with exclusive read/delete handles, and rechecks the receipt, directory
identity, inventory, every file identity, size, hash and descriptor through
those handles. A changed or busy file refuses cleanup before deletion begins.

The caller's `validated` journal event contains the full recovery record before
mutation. Binary files are removed first; the stage intent and receipt are last.
Before each deletion, the directory inventory and that held file's policy are
checked again. Deletion uses
[SetFileInformationByHandle / FileDispositionInfo](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle)
on the checked handle, followed by handle closure and a separate path-absence
observation. The same approach removes the original directory only if empty.
There is no recursive deletion, wildcard, permission repair, process termination
or automatic retry.

Failure raises `CleanupFailure` with a structured report: files marked for
deletion, files separately observed absent, directory disposition/absence, error
and remaining receipt/intent observations. A partially removed tree is never
reported as a successful cleanup. A late foreign file is preserved. If it
appears after the receipt has been deleted, the caller's external journal is
necessary for recovery; this operation is not atomic.

The privileged `remove_production_stage` wrapper requires explicit x64 elevation,
a caller-provided recovery journal, a fully verified production stage, absent
project HKLM registration and no current-user COM overlay. It reads only the
project's planned registry locations. These production checks have **not** had
a positive elevated execution. The public CLI still provides plan, read-only
preflight and explicit staging; it exposes no cleanup or test-policy switch.
The future installer must serialize registration and file operations, persist
and flush its journal outside the stage, and handle interrupted operations.
Providing a callable alone does not establish journal durability.

The primitive trusts its installer caller and the normal administrator-controlled
Windows/kernel/NTFS environment. Held handles and rechecks limit ordinary file
races; they do not establish a boundary against malicious administrators, a
hostile filesystem driver or an already-authorized metadata writer.

## Evidence

`scripts/test-asio-file-cleanup.py` creates fresh stages under the workspace,
using an explicit current-user test descriptor. Production protection is never
inferred from those descriptors. The suite proves:

- Complete removal of fourteen reviewed files and their own directory, with
  distinct deletion and absence observations and a pre-mutation recovery event.
- Refusal for incorrect hashes, changed/missing/extra payloads, hard links,
  identical-byte file replacement, a receipt from another directory, unexpected
  write rights and production inspection of user-owned stages.
- Identity revalidation after preflight and denial of a concurrent writable
  open while the deletion handles are held.
- An active reader refuses cleanup before deletion; closing it allows cleanup.
- Journal failure before mutation preserves files; failure after the first
  deletion reports that exact partial outcome and keeps intent/receipt.
- Late foreign files are preserved both before receipt removal and before the
  final directory deletion, with truthful partial reports.
- A native image-section mapping blocks deletion of the first binary with
  access denied. Unmapping it permits cleanup. This uses
  [CreateFileMappingW](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw)
  and [MapViewOfFile](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile),
  with no `LoadLibrary`, entry-point invocation, COM activation or payload code
  execution. It is not a running ASIO-host test.

All 24 staging and 16 ancestor-review regressions also pass. Temporary fixture
ACLs are restored and checked; private junction tags are removed and rechecked.
The source bundle and planned installation/pointer locations remain unchanged.
The native C++ source pins still match the prior 59-test Release/Debug builds;
those unchanged builds were not rerun. See the
[verification record](evidence/file-cleanup-20261102.json).

[Installer exclusion and flushed journal primitives](asio-install-journal.md) now
have workspace process/file/cleanup coverage. Protected installation/removal,
full recovery integration, runtime dependency checks and ordinary-user
write-denial proof remain unfinished. Genuine native
audio/timing and physical analogue validation, current Serato admission and
two-deck DVS remain unproved. macOS remains deferred.
