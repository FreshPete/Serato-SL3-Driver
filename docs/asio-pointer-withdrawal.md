# Explicit pointer withdrawal and republication

The controller can now withdraw one reviewed session pointer by its exact byte
hash. A separate explicit publication can then reuse the same pointer path.
This advances the stable-locator workflow without installing anything or
performing an automatic broker/device restart.

```powershell
sl3_broker_controller.exe --withdraw-pointer --pointer "C:\path\current-session.txt" --sha256 <exact-lowercase-pointer-sha256>
sl3_broker_controller.exe --publish-pointer --config "C:\path\reviewed-session\sl3-asio.conf" --pointer "C:\path\current-session.txt"
```

Review and preserve the pointer bytes before withdrawal. The SHA256 is for the
pointer file itself, not its target configuration. The two commands are explicit
operations; they do not run automatically together. The second still validates
a live broker configuration and refuses any existing pointer or pending file.

## Withdrawal contract

The withdrawal command requires a non-elevated user and a local fixed-drive
pointer path. It pins the parent directory, checks resolved locations, and opens
the pointer with read/delete access and zero sharing. It requires a disk file,
one link, no directory/reparse attribute, and 1..65,536 bytes. Its owner SID must
equal the current user's SID. A resolving reader or other conflicting file
handle causes refusal; there is no wait/retry or forced handle closure.

The opened file's bytes must parse as the same strict versioned pointer format
used by the production loader and publisher. The shared codec supports UTF-8
absolute target paths and lowercase SHA256 and bounds input size. Withdrawal
does not resolve or open the target, so an old pointer can be removed after its
broker and target files are gone.

SHA256 is calculated from the bytes read through that same exclusive handle.
Only an exact match to the caller's reviewed hash permits deletion. The command
then uses `SetFileInformationByHandle(FileDispositionInfo)` on that handle and
closes it. It never verifies one pathname and later calls a pathname deletion
function that could select another file. Wrong hashes, malformed records, open
readers, hard links, directories and oversize/empty files are refused without
modifying their bytes. It does not alter permissions or file attributes to force
success.

The receipt distinguishes `pointerDeletionMarked` from `pointerAbsentObserved`.
The latter is a subsequent directory observation, not a reservation against
another publisher. If absence is not observed, do not infer successful path
reuse. Publication independently uses create-new semantics and preserves any
competing file. There is an intentional unavailable interval between withdrawal
and explicit publication; this is not an atomic replace or a hidden fallback.

Microsoft documents the handle-based deletion operation and required DELETE
access in
[SetFileInformationByHandle](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle).

## Client and device lifetimes

A selected ASIO client retains its immutable records and exact broker process
reference. Removing the pointer does not detach that client, stop a broker,
release USB, change rate or modify firmware. A new object encountering the
missing pointer reports unavailable. Republishing only affects future
resolution; it does not redirect the existing attachment. All previous
broker/worker/measurement pins and native admission checks remain in force.

The command reports `deviceAccess: false`, `brokerStopped: false`, and
`automaticPublication: false`. Pointer absence provides no evidence of native
USB release or readiness for another acquisition. An explicit controller stop
and its independent retirement evidence remain separate requirements.

## Verification

The controller lifecycle suite adds an actual separate COM client with a
control-thread barrier after its first simulated SDK callback. While that
client's audio stream and its exact controller process are confirmed live, the
test invokes the native withdrawal executable, confirms pointer absence and
refusal of a fresh client, then invokes the native create-new publisher for the
same session. The existing client continues and completes three ordinary COM
objects/four SDK streams. Its worker audit still records one acquisition, eight
clock inspections, four starts/stops and one final release. No extra acquisition
or client clock request occurs due to pointer withdrawal/publication. This tests
the same simulated broker; it does not demonstrate handoff to a different native
broker or analogue continuity.

After that controller exits, the republished stale pointer can also be withdrawn
without target/process resolution. Additional guards exercise wrong/uppercase
hashes, unknown options, a live resolving reader, hard links, malformed/BOM/extra
records, empty/oversize files, a directory and a missing file. Refusals preserve
existing bytes. The current-user ownership acceptance path is exercised; a
different-owner rejection and a reparse-point rejection have not been exercised
as runtime negatives on this host.

The shared codec has UTF-8 round-trip, relative-path, hash and size checks in the
configuration tests. Both native configurations retain the existing production
COM rejection of simulated workers; positive callbacks still use the explicit
test-only provider. See [the verification record](evidence/pointer-withdrawal-20261102.json).

The complete Windows/Serato goal remains unfinished: protected deployment and
registration, genuine measured timing, positive native broker/audio operation,
physical audio and current Serato/DVS still require their own evidence. No live
SL3 pointer, installation or security policy was changed by these software tests.
