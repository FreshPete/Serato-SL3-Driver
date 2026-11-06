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

## Consequence for the simpler launcher

Widening the shim's click token to the generic helper address is not a justified automatic-start change. It could mistake unrelated helper traffic for the user's install action and does not provide the missing descriptor lifetime or successful-install evidence.

The next candidate should preserve the real installer and completion path: after an explicit Start action, deliver the original install action on its owning UI thread once the genuine SL3 arrival and panel readiness are established. That still requires identifying and validating the original action receiver; a scalar VID/PID is not a substitute for it. If the existing installer is run ahead of application launch, a separate genuine connection handoff remains necessary.

Before any live candidate, retain the current application/hash guards, verify the package and actual broker attachment, scope the attempt to one session, and leave account/DVS authorization and firmware untouched. A candidate must report actual ASIO start and detach startup instrumentation before manual Phase playback. This work has not yet removed a click or reduced the number of Windows approvals. The prepared attended shutdown test should remain on the proven click route so startup and shutdown changes are not conflated.

Reproduce without launching vendor code:

```powershell
artifacts/build/embedded-python-3152-20261106/python.exe -I -B scripts/inspect-serato-installer-handoff.py --application 'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe'
```
