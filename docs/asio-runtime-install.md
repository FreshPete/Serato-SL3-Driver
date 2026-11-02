# Runtime-gated staging and registration

The new runtime checker resolves the reviewed package's direct imports on this
Windows 11 host. The install coordinator uses that result before staging or
registration. All 17 runtime checks and 20 isolated installer cases pass,
including a real workspace/private-registry install/remove round trip.
No Program Files installation, machine registration or installed ASIO activation
has been performed.

## Runtime admission

`scripts/asio-runtime-check.py` is inert by default. Its explicit `--check`
requires a bundle and reviewed manifest SHA. It captures and validates all
package bytes through retained handles before parsing the four AMD64 images'
normal and delay import tables. It rejects unsafe import names and unsupported
local imported dependencies; it does not execute or load a package image,
including the bundled UsbDk helper.

The checker uses the native
[GetSystemDirectoryW](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getsystemdirectoryw),
holds and checks its ancestor chain, and reads native DLL bytes through handles
that deny write/delete sharing. System files require trusted owners, no untrusted
mutation grants, local non-reparse paths and AMD64 DLL headers. System DLL hard
links are permitted; they are not assigned the staging area's exact descriptor.

Direct DLL paths are restricted to native System32. API-set names are passed to
the normal loader with `LOAD_LIBRARY_SEARCH_SYSTEM32`, then their resolved host
path and file are checked there. An
[API set](https://learn.microsoft.com/en-us/windows/win32/apiindex/windows-apisets)
is a loader contract and need not exist as a file with its import-table name.
The diagnostic calls
[LoadLibraryExW](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-loadlibraryexw)
with that search flag only, and uses
[GetProcAddress](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-getprocaddress)
for every required symbol. Ordinals must also exist in the checked export table,
avoiding a non-null sparse-ordinal result being accepted by itself. Own module
references are released after the check.

This **allows system DLL initialization in the diagnostic process**, including
the VC runtime. It does not call the resolved import functions or package entry
points. It does not attest loaded memory, inspect every transitive delay import,
prove future host search state or establish runtime/audio behaviour.
Normal Windows/system-directory/administrator trust remains an assumption; no
AppLocker/authorization-bypass flags or policy changes are used.

On this host the current reviewed bundle resolves **330 direct symbol references
across 15 dependency names to nine System32 files**, including `MSVCP140.dll`,
`VCRUNTIME140.dll`, `VCRUNTIME140_1.dll` and UCRT API-set hosts. This is a snapshot,
not a promise about another PC or a later runtime update. Admission runs again
on each installation attempt; the install coordinator does not use a cached
passing result.

## Installation ordering

`scripts/asio-install.py` has an inert/plan-only CLI. Its trusted-caller API:

1. Requires a new destination directly below its installer base and runs runtime
   admission against the reviewed package hash.
2. Captures the source again, retaining its handles, and binds runtime/package
   identity. Production policy also requires the exact native planned location.
3. Holds the fixed-base installer lock, requires absent own registration, existing
   shared registry containers and no current-user COM overlay, and flushes the
   reviewed plan, runtime snapshot digest/dependency hashes and preflight state.
4. Journals stage intent, creates exact protected files through the stager, pins
   all stage objects and fully inspects them. It flushes the completed stage
   receipt and full file identities before registration.
5. Rechecks registry admission, creates only the own new entries through the
   registry engine, independently verifies files/registration/overlay again and
   flushes a completion observation before returning success.

Source and stage leases deny concurrent writers through registration. A failure
retains the stage/intent and phase receipts rather than guessing which files to
remove. The registry engine still rolls back only invocation-created keys whose
values remain exactly owned. A foreign key appearing after staging is preserved
along with the stage. A journal error poisons the writer and prevents the next
mutation. If completion recording fails after state was observed, overall success
remains false and those observations are reported separately.

The production wrapper selects real HKLM/current-user roots and requires explicit
elevation. It currently requires the protected fixed base to already exist;
first-install base bootstrap remains unfinished. It does not create shared
registry containers, alter an existing destination/descriptor, install a runtime,
start a native session, write a session pointer, create a service or activate COM.

## Verification scope and remaining work

The 17 runtime cases include actual library/symbol resolution and CLI execution,
audited loader flags/paths, source leases, absent package modules before/after,
bad hashes and changed bundles, absent DLLs/contracts/exports/ordinals, a present
ordinal, unsafe paths and unsupported local dependencies. Only a first-party PE
byte string is changed in memory for the unsafe-import parser fixture; the
reviewed bundle and bundled vendor bytes remain unchanged.

The 20 installer cases include actual staging and real registry writes in a
marked private HKCU UUID namespace, a composed install/remove round trip, live
source/stage sharing probes and a retained completion journal. They also cover
runtime/hash failures, existing/foreign/container/overlay/lock conflicts,
interrupted copy, stage-completion journal failure, registry write rollback,
post-stage foreign registration and failed final completion recording.
The namespace is removed after owner/boundary checks and independently observed
absent. Live planned HKLM/current-user registration, planned installation/profile
paths and source bundle remain unchanged.

The isolated registration keeps the reviewed Program Files strings while stages
use workspace locations and explicit current-user policy. This tests ordering
and ownership handling, **not installed ASIO discovery or activation**. Production
inspection refuses a test stage. The prior native source/build pins remain
unchanged; no C++ rebuild was needed. See the
[verification record](evidence/runtime-install-20261102.json).

[Reviewed registry-removal recovery](asio-registry-recovery.md) now covers exact
remaining own entries with an intact stage. [Separate file recovery](asio-file-recovery.md)
now covers partial file removal and absent-stage reconciliation. Protected-base
bootstrap, interrupted install/copy recovery, attended production deployment and
ordinary-user write-denial proof remain unfinished.
Runtime resolution does not establish the signed UsbDk filter's device readiness,
a positive current native session, measured latency, analogue audio, legitimate
current Serato admission or two-deck DVS. Those remain separate unproved parts of
the active goal; macOS remains deferred.
