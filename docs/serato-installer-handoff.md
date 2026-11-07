# Removing the repeated Download Driver action

**Follow-up:** the [original action receiver is now statically identified](serato-download-action-receiver.md), with a passive probe prepared and mocked-boundary checks passing. Runtime readiness, thread and lifetime observations remain outstanding; the candidate below is still not an automatic-start implementation.

The working temporary route still needs the user to click Download Driver and approve the local installer. This investigation checks what an automatic launcher would have to preserve. No automatic action was implemented and Serato was not executed.

The new [offline inspector](../scripts/inspect-serato-installer-handoff.py) verifies the exact original Serato 5.0.0.1278 image, complete PE function boundaries and selected instructions in three functions. [Reproducible findings](evidence/serato-installer-handoff-20261106.json)

## A helper address is not a startup trigger

The genuine click publisher at `141380170` constructs a fixed `0x4ff` message with argument 1. Its message-constructor return address is `1413801ba`, the address used by the current startup shim to bind a genuine user action.

The other observed constructor return address, `14154b5b5`, is inside a generic message helper at `14154b4b0`. That helper preserves the incoming message ID from `edx` and forwards it to the constructor. It has both a single-message path and an indexed loop. Its return address identifies a helper-generated message; it does not identify the helper's upstream caller or prove a startup request.

The trace summarizer now labels this `installer_helper_message`, replacing `installer_startup_message`. The observed message ID and caller remain in the timeline. Seven summarizer tests pass. Reanalysis of the saved successful startup trace `serato-installer-live-097e52fb0c34496a96b0b65795f08166` changed exactly one origin label while preserving all 41 timeline events and their other fields; the capture had no trace errors. The corrected summary is retained locally in `analysis/installer-handoff-corrected-summary-20261106.json`. Existing saved reports retain their original labels; interpreting those reports must apply this correction. The startup shim source is unchanged and still accepts only the checked click caller, thread, identity and delivery interval.

## The successful installer handoff is conditional

The completion function at `1405b0a40` does more than announce an installer exit:

1. It clears the panel's in-progress byte and casts the supplied object. A null result takes the exit path.
2. It obtains the driver provider and calls virtual slot `+0x48`. A false result skips connection publication. Earlier analysis identifies the generic implementation as a registration-key detection predicate.
3. It reads two descriptor identity slots. The pair `ffff:ffff` takes a separate `0x68b` publication path.
4. For the non-sentinel descriptor it publishes `0x51`, then checks descriptor byte `+0x522`.
5. Only a nonzero byte reaches the `0x2ca` publication, passing that live descriptor in `r8` and stack argument 7.

The static facts establish these local guards, not runtime object identity, lifetime, delivery or successful audio selection. They do not prove that an arbitrary synthetic event would be accepted. Registration by itself was already shown insufficient in the separate [installed-driver startup branch](serato-installed-startup-boundary.md).

### What installed-driver detection shares with installer completion

The original 5.0.0.1278 notice receiver uses the same message switch for installer completion's `0x51` and installed-driver action 6's `0x52`. Both extract a key through `141380440`. `0x51` calls the keyed notice helper `14137b670` directly and then exits the switch. `0x52` looks up the key in the receiver's collection at `+0xb0` first. Its matching branch can skip the helper when the entry's byte at `+8` is nonzero. The helper has its own entry checks and conditionally calls a stored object's virtual slot `+0x40` before updating the collection. The byte and virtual slot's full semantics remain open. [Checked switch entries and instructions](evidence/serato-installer-handoff-20261106.json)

The installer callback publishes `0x2ca` separately from `0x51`, through the same message system and with the live controller descriptor. The `connect_on_finish_install` check is in that callback, after the notice publication. The two successful traces observed this separate primary request before ASIO opened. For the ordinary launch test, a cleared notice or activity in the shared notice helper still needs to be paired with an actual selection event or ASIO load. [Installed-driver notification](serato-driver-notification.md) · [Captured installer selection](serato-primary-pointer.md#installer-assisted-selection-observed-in-serato-50)

### The installed notice carries the common descriptor interface

Deferred action 6 takes the shared descriptor from the device composite, moves ownership into a local shared pointer to its common virtual base, and calls the DeviceManager observer at slot `+0x38`. That observer supplies the common interface pointer as the payload of the route-zero `0x52` notice. On the checked `ControllerDescriptor` object, the virtual-base table places this interface at complete object `+0x738`. Its slot `+0x10` reads the key string at complete object `+0x28`. Installer completion adjusts its own input to this same common interface when publishing the `0x51` notice.

The installer completion entry takes the `driver::Descriptor` base at complete object offset zero. Its separate primary-selection request uses the complete `ControllerDescriptor` pointer on route 7. Those two addresses differ from the common interface address in `0x52`. The installed notification therefore gives a concrete place to observe whether the genuine SL3 descriptor is already present on the ordinary installed route. A live comparison must check the actual type and primary-vector membership while the application still owns the object. The notice's raw payload alone establishes neither membership nor lifetime. [Descriptor conversion and RTTI evidence](evidence/serato-installer-handoff-20261106.json)

The inspector verifies 91 instructions, eight code extents, both descriptor base adjustments and the action-6 observer table. Two reports matched byte for byte, and an existing report was preserved on a repeat output request. This was offline inspection. The earlier `0x52` trace did not record its payload identity, and an installed reconnect bridge remains unimplemented.

The private Windows probe now has a read-only `--notice` mode. At the checked `0x52` constructor it verifies both descriptor tables, the SL3 identity and the exact rebuilt ASIO name. While the application's shared reference is still live, it checks the complete pointer against the primary manager's bounded descriptor vector. It reports present, absent or unavailable. It then correlates the same message at the publish call and notice receiver using the checked route, payload and message table. Publication and receiver entry are separate observations. Raw pointers and descriptor strings stay out of the log.

The installed image matched all three breakpoint pins and the primary-manager global reference. Windows fixtures checked exact membership, rejection of a wrong subobject or revision, refusal of an invalid vector, and publication-to-receiver correlation. The notice fixture also rejected a different publishing thread and route. Both debugger start fixtures continued to pass and exited normally after detach. The private executable SHA-256 is `39be2a73b859d12866221d04544ec98bf5191af3f8ab33723c498b8abf7030ac`.

The attended Serato 5.0.0.1278 trace on 7 November captured two calls to the installed-driver notice constructor. One matched the genuine SL3 and rebuilt ASIO name. Its complete descriptor pointer was present in the primary manager's registered vector at construction. The trace then matched the same notice at publication and at receiver entry. The debugger detached with six breakpoint hits and zero memory read errors. The installed-driver notice is a candidate point for a selection handoff. Automatic selection remains unresolved, and the run produced no ASIO activation receipt. The traced process remained after its window closed and was stopped before restoration. The private trace SHA-256 is `ce9612d358093a823ca149e6c3b8b6f32a59ac449f2ca1c4e71d78e938ce4388`.

After the owner ran Restore original setup, a separate check matched the original Serato archive hash and confirmed that the trial package and its ASIO and COM registrations were gone. No Serato, probe or SL3 audio worker process remained.

### Selection from the regular Windows shortcut

One trial installation was used for the shortcut tests. A private debugger attached to the process opened by the original Serato desktop shortcut. It retained the descriptor identity from the genuine installed-driver notice. When a later application callback ran, it rechecked the SL3 identity, rebuilt ASIO name, membership in the primary descriptor vector, empty primary selection and the engine guard. It then used Serato's original publisher to send one primary selection request and restored the interrupted thread context. The earlier attempt at the notice itself encountered an unavailable engine guard.

On the successful launch, Serato left offline audio, selected Rane SL3, loaded `sl3_asio.dll` and reported starting at 44.1 kHz with a 192-frame application buffer. The native broker recorded acquisition, one stream-start reply and retirement on application exit. The process exited normally. Playback stayed stopped. The private trace SHA-256 is `f99e5ceeaf7494243653fdfef46b2ebc958d2b71bf412806d41d37c62134d626`. The native broker result SHA-256 is `303fc52ef1d938da7a176ba542af2b732a3906136a5fa3ffbc1c3c6c9a691a5b`.

On the repeat launch without reinstalling, the probe saw the matching notice but sampled neither of its two later callback points. It made no selection request, and Serato stayed on offline audio. The repeat probe also had a change that detaches immediately after the publisher returns. The debugger supplied the selection request on the successful run. The trial installer currently installs the profile and driver. A repeatable startup trigger and a way for the installed package to supply it are still open.

The original archive and removal of the trial files and registrations were verified after both runs ended.

### Two shortcut launches with the Windows helper

The Windows trial helper moved notice capture ahead of Serato's UI message loop. The first implementation loaded through a thread message hook and missed the notice. The tested implementation used the Windows loader early in the fresh shortcut process, verified the pinned Serato image and observed the original DeviceManager notice callback. A timer on Serato's UI thread waited until the notice matched the rebuilt SL3 descriptor, the primary manager owned that exact descriptor and the engine allowed selection. The helper restored the original callback slot before it sent one selection request through Serato's publisher. Both application processes ran without a debugger. [Native helper](../scripts/native/serato-notice-startup/notice-startup.cpp) · [Trial watcher](../scripts/native/serato-notice-startup/watch-notice-startup.ps1)

The same trial install and the same armed watcher covered both launches from the original desktop shortcut. Both logs show the matching notice, one selection request and successful return from the publisher. Serato loaded the rebuilt ASIO DLL and reported that Rane SL3 audio started at 44.1 kHz with a 192-frame application buffer on both launches. Each native broker reported USB acquisition, one stream-start reply and application-exit retirement. Both Serato processes exited normally. This was a startup test with playback stopped.

The tested DLL SHA-256 is `a370ab23c5c1ed80a35b8b49046c92ec270f2bb5cb43d058f72c5ea67a3b8306`. Both helper logs have SHA-256 `5ed360ed01f009fbd2f7aa646c1c63fbb7049a83f774d767a80a2f623322b974`. The broker result SHA-256 values are `323c97ece92f0277358f42b3572e2ca1847ba858ca3f6f280c5b859cdaf3fa93` and `f0d25ea155624d5a2a3091e4e7484aed0d3d546eaeb11390b9dd0be7911698b5`. Cleanup verified the original archive, no trial driver files or registrations and no remaining audio worker.

The watcher was armed separately as part of the trial and exited after observing two launches. The next packaging step is for the installer to set up and start the watcher so it can handle subsequent launches and Windows sign-ins.

For source review, copy the helper files to a scratch directory. From an x64 Visual Studio Native Tools command prompt in that directory, build the DLL:

```cmd
cl /nologo /std:c++17 /O2 /EHsc /W4 /WX /MT /guard:cf /LD notice-startup.cpp user32.lib /link /guard:cf /OUT:sl3-notice-startup-early.dll
```

The watcher pins both the Serato executable and the tested helper DLL. A local build may produce a different DLL hash. Review the build, update only the helper pin in the scratch copy, then run the watcher with `-CheckOnly` to verify its exports without attaching to Serato. This source snapshot is not a ready-to-run installer.

## Consequence for the simpler launcher

Widening the shim's click token to the generic helper address is not a justified automatic-start change. It could mistake unrelated helper traffic for the user's install action and does not provide the missing descriptor lifetime or successful-install evidence.

The next candidate should preserve the real installer and completion path: after an explicit Start action, deliver the original install action on its owning UI thread once the genuine SL3 arrival and panel readiness are established. That still requires identifying and validating the original action receiver; a scalar VID/PID is not a substitute for it. If the existing installer is run ahead of application launch, a separate genuine connection handoff remains necessary.

Before any live candidate, retain the current application/hash guards, verify the package and actual broker attachment, scope the attempt to one session, and leave account/DVS authorization and firmware untouched. A candidate must report actual ASIO start and detach startup instrumentation before manual Phase playback. This work has not yet removed a click or reduced the number of Windows approvals. The prepared attended shutdown test should remain on the proven click route so startup and shutdown changes are not conflated.

Reproduce without launching vendor code:

```powershell
artifacts/build/embedded-python-3152-20261106/python.exe -I -B scripts/inspect-serato-installer-handoff.py --application 'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe'
```
