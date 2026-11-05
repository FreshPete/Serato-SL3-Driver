# Prepared attended Serato archive test and rollback

A private review bundle now contains the SL3 archive hypothesis, a source-bound PowerShell wrapper, the original transaction library and provenance. Its default `Plan` action is read-only. No installed archive replacement, protected rollback, application session or device operation has run. This is preparation for an attended experiment, not an approved deployment or working Serato release.

## Package and read-only preflight

The original reviewed bundle was `analysis/sl3-archive-deployment-20261102-reviewed/`; it and the preliminary bundle are now historical snapshots. The current bundle is `analysis/sl3-archive-deployment-20261102-owned-trace/`, refreshed against the [new native build](asio-owned-trace.md). Older generated manifests are refused against current sources. Both contain vendor resource data and stay private. The public repository supplies original tool source, tests and sanitized evidence rather than generated resource archives.

The preparer independently reconstructs and validates the [additive archive](serato-sl3-archive.md), checks the exact saved bundle and all source bindings, verifies the installed original archive and queries the original executable's Windows Authenticode status. The observed executable status is **Valid**, signer thumbprint `A38279C93F7D1D669D0C367CAE3EC45ACF63F017`. Windows reports **UnknownError** with no signer for the original resource archive; that is not interpreted as proof that Serato performs no resource integrity checks. No executable signature, certificate store, security policy or authorization is changed.

Each bundle contains:

- `candidate-userio_resources.bin`, the exact private candidate.
- `serato-archive-file-transaction.ps1`, original file transaction code.
- `archive-test.ps1`, the generated attended wrapper.
- `deployment-plan.json`, original/candidate/app/source identities and limitations.
- `provenance.json`, exact package file hashes.

The wrapper embeds the fixed installed target and original/candidate/app/core/plan hashes; manifest fields cannot redirect its target. It checks its core and plan, imports the same core bytes whose hash it verifies, checks the original executable hash/signature/signer, and checks the candidate payload for `Plan`/`Install`. Default `Plan` was run with an ordinary token and reported original-to-original state with no file replacement. Read-only owner/DACL checks accepted the current app/archive directory paths; they do not establish future protected staging, replacement or rollback.

## File transaction behavior

The core library is inert when dot-sourced. Its file operations require an explicit quiescence callback. The wrapper supplies a guard that refuses a running process named `Serato DJ Pro`, checks trusted protected owners and refuses applicable untrusted write/ownership grants. It checks the live archive/directories and existing stage/backup/retired files. No ACL or owner is repaired or relaxed; unexpected ownership, including a future staging owner that fails the predicate, stops the action for review.

`Install` requires the exact original target or a verified candidate stage. It copies the independent candidate into a create-new same-directory stage, flushes it to disk, rechecks quiescence/state, then calls Windows file replacement with an atomic original backup. Metadata errors are not ignored. Original and replacement hashes are checked afterward. `Rollback` requires the exact installed candidate plus the exact original backup, stages the backup, then atomically restores it while retaining the displaced candidate. The original backup stays until explicit `Clean`. `Clean` requires the verified original live target and removes only matching derived witnesses; it can cancel a verified pre-install stage.

The implementation uses [.NET File.Replace / Windows ReplaceFile](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew). OS error cases can leave different file-name states. The engine accepts only its explicitly checked states; it preserves unknown, corrupt, missing-target or partially written artifacts for review rather than guessing a recovery action. Tests cover selected failure/interruption states, not every power-loss/OS/storage failure. Application closure checks and protected directories do not coordinate a concurrent privileged updater; the attended caller must exclude one.

A changing live target, unknown stage/backup, path tampering, reparse path or unavailable original backup prevents replacement/cleanup. A locked live file fails without losing the original in the tested Windows case. Unknown witnesses are not recursively removed. Package rollback does not require the candidate payload, but does require the reviewed wrapper/core/plan, original executable and exact protected backup/target identities. No automatic retry, UAC request, reboot or application launch exists.

## Review commands

From the repository root, prepare a **new** bundle or revalidate the reviewed one:

```powershell
.venv/Scripts/python.exe scripts/prepare-serato-archive-deployment.py `
  --descriptor analysis/sl3-descriptor-candidate-20261102-owned-trace `
  --archive analysis/sl3-archive-candidate-20261102-owned-trace `
  --prepare analysis/sl3-archive-deployment-NAME
.venv/Scripts/python.exe scripts/prepare-serato-archive-deployment.py `
  --descriptor analysis/sl3-descriptor-candidate-20261102-owned-trace `
  --archive analysis/sl3-archive-candidate-20261102-owned-trace `
  --validate analysis/sl3-archive-deployment-20261102-owned-trace

# Read-only inspection; this is the only wrapper action exercised on Serato paths.
pwsh -NoProfile -File analysis/sl3-archive-deployment-20261102-owned-trace/archive-test.ps1
```

For a later attended, reviewed test, the wrapper's explicit actions are `-Action Install`, `-Action Rollback` and `-Action Clean`. They require an already elevated launch; the wrapper never requests UAC. No such action is selected or approved by preparation. ASIO deployment/profile and the actual application/device test scope are separate prerequisites. The archive is not evidence of an accepted current descriptor, legitimate service result, implemented NONE control semantics, physical audio or DVS.

## Verification

On 4 November the current private bundle passed full validation again. The read-only wrapper found the original archive, no staging or rollback files, and a valid signature on the installed executable. All 22 Windows transaction fixtures passed again. These results verify bundle and rollback preparation. Application acceptance still requires a later protected test after the Windows audio prerequisites are met.

Twenty-two transaction checks use original synthetic data in bounded owned temporary folders on this Windows host, with real file replacement calls. They cover install/rollback/cleanup, exact backup/retired bytes, stage resume/cancellation, first/second quiescence refusal, unknown/corrupt/missing backups, partial staging, independent source and path identity, changed-target/create races, held-file failure, destination ACL preservation, junction rejection and untrusted owner rejection. Temporary ACL changes and all writes stay inside those disposable fixture folders. No installed app file is used as a transaction test target.

Six actual package CLI scenarios check full validation, repeat preparation, no-overwrite refusal and wrapper refusal of changed core, candidate or plan. The repeated five-file bundle is byte-identical. The actual default wrapper `Plan` passes and leaves the original installed identities unchanged. [Sanitized evidence](evidence/serato-archive-deployment-20261102.json) binds source files, package hashes, fixture/CLI results and the read-only preflight. No new native audio tests are claimed, and no protected install/rollback, current admission or physical audio/DVS result is inferred.

Run fixture checks with `pwsh -NoProfile -File tests/test-serato-archive-file-transaction.ps1`. They require a Windows user session with permission to create ordinary owned temporary files/junctions. The goal remains Windows-first; Mac is deferred.

## First attended Serato 5.0 recognition test

On 4 November 2026, the original signed Serato DJ Pro 5.0.0.1278 executable ran under the ordinary desktop user with the temporary additive archive. The application log reported the genuine USB VID/PID `1CC5:0001`, identified the device as Rane SL3, reported its minimum firmware as installed, and recorded the SL3 being added. Serato showed **Rane SL3 Driver Not Installed** in place of the earlier **Rane SL3 Discontinued** notification. The operator confirmed the new message with a screenshot.

The log separately enumerated the historical Rane ASIO entry and kept playback on its offline device. The test did not register the rebuild or establish that Serato opened it. The next application-side question is which driver check produces the new notification and whether the rebuilt ASIO registration satisfies it.

The single elevated helper restored the original archive after Serato exited and removed the temporary transaction files. The restored SHA-256 matched the original preflight and the post-clean state was `original`. The full application log and candidate archive remain local.

## Attended ASIO registration test

With the same temporary SL3 definition and the reviewed startup-fix ASIO bundle registered, Serato 5.0.0.1278 listed `SL3 Rebuild Development [ASIO]` and added the genuine Rane SL3. The previous **Driver Not Installed** notification did not appear during the test. Serato showed **Sign In to Serato DJ Pro**, and its audio log showed a successful start only for the offline device.

The host's module samples did not observe the rebuilt DLL and its per-process ASIO trace was absent. These observations do not rule out a transient load. The test verifies discovery of the ASIO registration and SL3 recognition. ASIO activation, streaming and DVS remain unverified. The broker session pointer was absent and no timing profile was supplied. A signed-in repeat can test whether Serato proceeds to the driver open before configuring a streaming session.

After Serato exited, the helper verified restoration of the original archive, removal of the temporary x64 ASIO/COM registration and absence of the staged driver directory. No account sign-in was performed during this test.

The repeat after the operator signed in again enumerated the rebuilt driver and added the SL3, but still emitted the same sign-in notification and used offline audio. Rollback and removal passed again. The operator confirmed that the ordinary Serato UI shows a signed-in account. The notification therefore cannot be used on its own to diagnose account state or establish what blocks the ASIO open. A follow-up should capture image-load events for the exact Serato process and correlate them with the application's hardware and audio connection messages.

The follow-up captured Microsoft-Windows-Kernel-Process process and image events from before Serato started until after it exited. The trace decoded 2,809 events with zero event or buffer loss. Serato's process had one start, 285 image loads, 285 unloads and one exit. The executable image was present, but there was no load of the rebuilt DLL or the legacy Rane ASIO DLL. The application still enumerated the rebuilt ASIO registration, added the SL3 and started offline audio. This rules out a successful DLL load during the observed run. It does not distinguish an application decision to skip activation from an attempted activation that failed before image load. The trace stopped, and archive restoration, registration removal and staged-directory removal were verified.

A second trace added the Windows COMRuntime provider and ran a successful registration-free COM activation of a hash-matched copy of the rebuilt DLL as a positive control. The first launch failed before Serato started because the collector command repeated its provider option. Cleanup was verified, and the corrected invocation used a provider list. The completed trace contained 3,474 events with zero reported loss, one rebuilt DLL load in the control process and none in Serato. COMRuntime did not emit the target class for the positive control, so this provider configuration cannot establish whether Serato requested that class. No Code Integrity event named the rebuilt driver during the captured Serato window. Archive and temporary registration cleanup passed again.

## Registered ASIO host and Serato registry trace

The ordinary-user control host used Windows `CoCreateInstance` against the temporary x64 machine registration. It received success, resolved the returned ASIO object's vtable to the exact installed DLL, and read its expected driver name. ASIO initialization returned unavailable because the diagnostic installation had no active broker session or timing profile. The host released the object cleanly. This verifies machine registration and COM opening independently of Serato.

The same process and registry capture then recorded Serato opening the rebuilt ASIO name and successfully reading a value from the driver's `InprocServer32` key. The control host also queried `ThreadingModel` and loaded the DLL. Serato had no observed `ThreadingModel` query on the tracked key and no driver image load across 281 observed image loads. This pattern is consistent with discovery without selection for audio. It is insufficient to assign the exact branch or exclude every pre-load activation failure. The full-trace statistics decoder timed out on the larger registry capture, so the registry comparison carries no zero-loss claim. Serato's prior lossless image-only trace independently showed no DLL load.

The capture stopped and the helper verified restoration of the original archive and absence of the temporary machine registration and driver stage.

## Live device selection trace

Two bounded, ordinary-user observation runs used [Frida Interceptor](https://frida.re/docs/javascript-api/#interceptor) on the exact original Serato executable. The observers checked the entry bytes before attaching and recorded selected function entries and return values without replacing them. The installed candidate definition explicitly names the rebuilt ASIO device. In both runs the audio selector entered the default route at startup, before the SL3 was added. It never entered the named audio selector during the captured window.

The second run saw the SL3 composite with a USB record, a descriptor and neither HID nor MIDI. It observed construction of message `0x2d4` with the expected packed identity `1CC5:0001`, revision zero, at the time Serato logged **Device Added: Rane SL3**. No receipt of that message at the traced `CUSBAudioManager` handler, corresponding SL3 lookup, or subsequent primary-device selection was observed. This puts the observed gap before named ASIO selection. It does not prove whether the message was delivered to a different consumer, dropped or queued, or whether the manager was absent.

Original-byte inspection found a direct call to the USB manager constructor from its lazy initializer. The checked caller of that initializer is an Engine handler branch for message `0x5d4`. The manager constructor subscribes to `0x2d4`. Two checked branches in a LicenseController updater construct `0x5d4` after state and service checks. This supplies the next boundary to observe. It does not identify the live value of those checks or establish an account or entitlement cause. Both test runs restored the original archive and removed the temporary driver registration and files.

### USB audio manager lifecycle

A 38-second follow-up verified the observer entry bytes for the Engine handler, USB audio manager initializer and constructor, the message constructor and the subscription function. Serato subscribed its Engine to `0x5d4` and the observer captured delivery of `0x2ca` to that Engine, confirming that the handler trace was active. No `0x5d4` construction or delivery, USB audio manager initialization or construction, or subscription to `0x2d4` was observed. The SL3's `0x2d4` message was constructed again with `1CC5:0001`, revision zero, after startup on default audio. The traced USB manager handler did not receive it. There were no observer errors.

The observed run stopped before USB audio manager initialization, rather than at a rejected ASIO DLL load. The trace does not establish why the manager's initialization message was absent or which normal application state would cause it to be sent. The original archive, machine registration and driver stage were restored or removed as appropriate, and their final state was verified.

### Why the initialization message was absent

The upstream trace observed both `ApplicationAuthorization` and `LicenseController` construction. The LicenseController received `0x694` and passed a false Boolean to its second state setter. The previous value was already false. The original setter compares the two values and returns without calling the updater when they are equal. The other state setter was never called in this window. Consequently neither observed route ran the updater that can publish the USB audio manager initialization message `0x5d4`.

This identifies the immediate reason for the missing trigger in the tested startup. It does not identify what account, product or hardware condition the Boolean represents, or why the authorization component supplied false. The run read no credentials or tokens and changed no authorization state. The SL3 arrival message was still constructed, the named audio selector was not entered, and archive and driver rollback were verified.

### Driver-install completion experiment

Original-byte inspection found a separate primary-selection path in the driver installer completion callback. It requires a usable DriverAPI and a descriptor that enables `connect_on_finish_install`. The generic Windows DriverAPI checks that its configured machine registry key is readable. The prepared SL3 profile points to the exact x64 registration key in the rebuilt ASIO installer plan.

The first attended experiment showed the SL3 driver notice. Clicking **Download Driver** opened a Serato web page that returned 404. The trace caught one local installer entry and no package extraction, process launch, completion callback, named ASIO selection or rebuilt module load. Recovery verified the original archive and removed the temporary bundle and installer permit. No driver registration was created.

The browser action and local installer have separate dispatch paths. The local installer receives its device ID from the info panel, which stores that ID when it receives a device-specific notification. The earlier trace did not record the ID or the early return checks. A follow-up trace is ready to capture the notice route, stored device identity, selected filename, bundle lookup and post-install registry result. The probes attached in stock startup, which did not exercise the installer. A separate local Qt test extracted the exact prepared installer payload from its bundle and verified its hash.

### Workspace startup comparison

With the original archive, a workspace copy of Serato showed neither the driver notice nor the SL3 arrival message. With the candidate archive, it checked the exact rebuilt ASIO registry key three times. All three results were false. A DeviceManager worker then prepared the web-enabled notice before the UI recorded the SL3 arrival. The installer panel started with a zero device ID, and the trace observed no message that populated it. The ID used during the earlier click remains unverified.

Clearing only the candidate's x64 detection string suppressed the notice while preserving the real SL3 arrival. Serato still used default audio. Inspection of the generic DriverAPI explains the distinction. The successful detection branch sends a notice-management message, while the local installer reads its ID from a different message path. This experiment used no temporary ASIO registration and performed no installer action. The original installed application passed its read-only preflight afterward.
