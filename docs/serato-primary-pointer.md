# Current primary descriptor pointer: registration identity and USB-only publication

`PrimaryDeviceManager` accepts a stored descriptor pointer only when that exact pointer occurs in its registered descriptor vector. Its message-0x2ca handler can select or clear the pointer. One checked `CUSBAudioManager` path publishes the same descriptor returned by numeric lookup, conditionally on handshake kind zero and another helper returning true. These are local registration/connection contracts, not a demonstrated SL3 admission, ASIO open or current DVS session.

Target: unchanged original/installed Windows Serato DJ Pro 5.0.0.1278, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. All addresses are preferred VAs. No vendor program, device, message injection, descriptor insertion or application modification ran.

## Registered-instance identity

Constructor `1405033d0` installs the RTTI-bound `PrimaryDeviceManager` vtable `142808488`. It initializes the descriptor vector at +0xd8/+0xe0/+0xe8 and the selected pointer at +0xf0 to zero. The [prior precedence proof](serato-descriptor-precedence.md) establishes resource registration before identity-only stubs and the numeric lookup's exact/older-revision rules; this extension binds and rechecks that report.

Setter `140505900` takes the requested pointer in RDX, preserves it in RDI and walks the vector in 16-byte entries. It compares each entry's first QWORD with the requested pointer. An exact match stores that same pointer at manager +0xf0. Exhausting the vector enters a diagnostic path and clears +0xf0. The complete getter at `140505500`, vtable slot +0x30, simply returns +0xf0.

An independently allocated object with matching VID/PID/name/fields would not satisfy this **pointer identity** test. This setter contains no general external descriptor registration interface; it selects an already-registered instance. The successful local store block is a pointer write, not a USB or audio operation. Vector ownership, all mutation paths and runtime object lifetimes remain outside this bounded proof.

## Selection message and independent state update

The constructor subscribes to message 0x2ca through `14154cd50`. Its vtable slot +0x18 points to handler `1405056b0`. The handler has three adjacent PE unwind fragments; the complete logical body is their exact union, ending at `1405057ae`.

| Handler input/condition | Local behavior |
| --- | --- |
| Message ID other than 0x2ca | Return without this selection path. |
| Payload getter slot +0x38 returns null | Clear +0xf0, call state-update helper `14154c060` with zero, publish message 0x2d3 with an empty string. |
| Non-null payload and the separate global object's byte +0x319 is nonzero | Leave the handler before these pointer/state updates. The flag's product meaning is unidentified. |
| Other non-null payload | Clear +0xf0, call the identity-checked setter, call the state-update helper with one, then publish 0x2d3 using a string from payload +0x28. |

The exclusion getter `1404d10d0` is a complete byte-load leaf; it is not identified as an account, entitlement or authentication check. No flag was changed.

The non-null branch does **not** independently test the setter's result before requesting its state update and notification. Thus that state update or notification alone cannot prove a pointer was accepted. Even a non-null +0xf0 proves only this local selection; support state, component eligibility, audio selection and real DVS remain independent requirements. No message/pointer forging mechanism is implemented or proposed here.

## One concrete USB-only producer

The checked `CUSBAudioManager` interface has complete-object offset +16 and vtable slot +0x18 pointing to `1407108e0`. For incoming message 0x2d4, its case `1407109a1` obtains the packed scalar through payload getter +0x38 and passes its three 16-bit VID/PID/revision fields to callback `1407100b0`, adjusting the receiver back by 16. This extends the existing [USB-audio removal proof](serato-usb-audio-removal.md) with the other checked message branch.

The callback preserves those identity arguments and calls `PrimaryDeviceManager` numeric lookup `140505360`. It saves the returned descriptor pointer in RBX and compares descriptor field +0x154 with zero. The [existing handshake map](serato-clock-handshake.md) names zero `NONE`; this producer proof checks the numeric branch and does not execute a handshake.

A nonzero kind follows another branch and skips this primary-pointer publication. A zero kind calls helper `14070ff10`; a false return also skips publication. The helper has additional service/notification behavior, so its Boolean is not assigned an unproved audio-open or authorization meaning. If the checked branch continues, the callback passes its preserved lookup result to publisher `1404db170`, with message ID 0x2ca. The publisher passes that same pointer to `UserIO_VoidPtrMessageData` construction and publishes through the sink's virtual +0x58. Its complete getter returns the payload QWORD unchanged. No extra USB claim or protocol was added to the replacement driver.

The selected path therefore carries a registered lookup result toward the identity-checked setter. **It does not prove the unchanged SL3 stub reaches this path.** Upstream support/component gates may prevent the 0x2d4 message, the helper may reject, and no actual callback or selected pointer was observed. The already established discontinued support route and empty audio/DVS configuration remain unresolved for current SL3 operation. Zero kind alone is not a compatibility recipe or a reason to change a device's legitimate control contract.

## Consequence for integration

A defensible current-Serato component must preserve genuine SL3 description, registration/instance lifetime, eligibility and connection/control/audio behavior. An ASIO registry entry or an equal descriptor allocation does not by itself supply the existing primary manager's registered object and message path. This proof identifies a concrete handoff to investigate; it selects no resource patch, message injector, foreign identity, key or account change.

The [wireless notification helper](serato-wireless-notification.md) separately reads this +0xf0 getter. That connection reinforces why Phase accessory handling cannot be treated as primary SL3 admission. It also prevents treating a local pointer as evidence that Phase/DVS, licensing, native audio, clocking or output routing worked.

## Reproduction and verification

Run `.venv/Scripts/python.exe scripts/export-serato-primary-pointer.py` with the pinned original and private focused reports available. [Evidence](evidence/serato500-primary-pointer.json) verifies 105 new instruction facts, 169 prior instruction checks, three RTTI tables, three complete getter leaves, the descriptor-register preservation on the publishing branch and six fresh complete focused functions. Regeneration is byte-identical.

Focused ranges are `1405033d0:1405035cd`, `1405056b0:1405057ae`, `140505900:140505ad4`, `1407100b0:1407103a8`, `14070ff10:1407100a4` and `1404db170:1404db209`. The handler's logical range is explicitly verified as the exact union of unwind fragments `1405056b0:1405056cc`, `1405056cc:1405057a8` and `1405057a8:1405057ae`; it is not mislabeled a single unwind record. Other ranges match individual unwind records. The isolated unchanged PE import disabled whole-program analysis/library loading and used read-only mode plus an empty library search path. Its log records zero additional files and discarded import; the temporary project is empty.

Native build input, shared trace/launcher and selected binary hashes remain unchanged. Native tests were not rerun for static-only analysis. No app/account/resource, driver/binding/trust/security, firmware, protected deployment, device or audio operation ran. Physical levels/mapping/timing, reliable reopening, protected Windows deployment, genuine current Serato SL3 integration and actual two-deck DVS remain required; Mac is deferred.


The later [USB-arrival bridge proof](serato-usb-arrival.md) identifies the selected action-zero observer and the no-MIDI/no-HID emission branch upstream of 0x2d4. It also resolves the helper's returned Boolean to two stored state bytes and identifies an optional minimum-version comparison. These static links do not show that the discontinued SL3 reaches the branch or that the service/state contract produces working audio.

## Installer-assisted selection observed in Serato 5.0

Three saved captures start with default audio, the Engine receiving integer zero on `0x2ca`, and construction of an arrival message carrying the SL3 VID/PID. The workspace capture ends without a primary request or named audio selection. Both successful temporary installer runs record the operator's click and the diagnostic supplying the SL3 identity to the installer panel. The completion callback then publishes the descriptor pointer. The primary setter runs, the manager creates integer one on `0x2ca`, and the Engine receives it with prior state false. Serato requests the rebuilt ASIO driver by name, loads its DLL, initializes it successfully and receives a connection. The same ASIO instance declines 192 frames, accepts 128, and returns success from `start` 913 and 924 ms after installer completion, respectively. [Compact comparison](evidence/serato-startup-routes-20261107.json)

The second positive trace also confirms the selected pointer is an SL3 descriptor when the primary manager returns. It records another arrival message with the same SL3 VID/PID and packed revision word 7.567 seconds after ASIO start. This establishes a later message construction. The capture does not establish a physical re-enumeration, continuous USB ownership or the destination of that message. The first positive capture is the same one independently joined to the [two-deck Phase session](evidence/phase-two-deck-session-20261105.json), with a recorded tracer detach immediately after start.

The manager initializer and constructor probes were armed and recorded no calls in the saved windows. The installer path still provides a directly observed route from primary selection to audio. The old handler probe cannot establish whether an arrival reached the USB manager. It read the third argument, while the handler reads the message ID at offset `0x0c` of the message passed as the second argument. A future delivery trace needs to read that field and distinguish queue admission, listener lookup and handler entry. [Handler instructions](evidence/serato500-usb-audio-removal.json) · [Dispatch boundaries](serato-usb-subscription.md)

Run `scripts/export-serato-startup-routes.py --workspace <workspace-trace> --two-deck <phase-trace> --selection <selection-trace>` with the three private trace files and their adjacent saved observer sources identified by the hashes in the report. Two regenerations matched byte for byte, and substituting the wrong capture was refused. These captures establish the earlier assisted route. The prepared launch from the usual shortcut with the retained broker still needs a live test.

## Other callers of the primary pointer message

The original 5.0.0.1278 image has five checked direct paths that construct pointer message `0x2ca` with a descriptor. MIDI selection, installer completion and the USB audio manager call the generic publisher. Two HID paths construct the message directly, so a probe on the generic publisher alone misses both. Five other checked calls use a null payload, which clears selection. The installed-driver notice uses its own message ID. [Caller and instruction inventory](evidence/serato-primary-publishers-20261107.json)

| Descriptor source | Call site | Boundary for the SL3 |
| --- | --- | --- |
| MIDI selection | `1405294b2` | The observed MIDI path requires readiness and a matching primary candidate. |
| Installer completion | `1405b0c48` | The attended captures used this route. |
| USB audio manager | `140710280` | This route still needs a live arrival and selection trace. |
| Existing HID connection | `140545b53` | The retained HID descriptor passes slot `+0x90` and the manager's state checks. |
| New HID connection | `140546aa6` | The incoming descriptor passes HID section, slot `+0x90` and manager state checks. |

The actual prepared SL3 archive contains a `native_pro_device` with `has_hid=false` and no HID or MIDI sections. For the concrete [ControllerDescriptor getter](serato-hid-verifier.md#the-preceding-virtual-check-is-now-identified-conditionally), slot `+0x90` requires `has_hid` and kind `native_intro_device`. The HID paths therefore provide no selection route for that prepared descriptor through this implementation. The historical SL3 definition also lacked those sections and used its separate DriverAPI handshake. Phase's own HID connection remains distinct from SL3 primary selection. [Historical descriptor comparison](serato-legacy-sl3-descriptor.md)

The [inspector](../scripts/inspect-serato-primary-publishers.py) checks 99 direct call sites across the generic publisher, the pointer constructor and two forwarding helpers. It verifies each candidate at a decoded instruction boundary in the pinned executable and checks the exact prepared archive. It does not infer runtime call order from the local instruction windows or exhaust indirect calls.

The two nonliteral calls to the second publisher come from `CGUIEditBox` slot `+0x98`. Both checked constructors initialize the message fields at `+0x2c0` and `+0x2d0` to `−1`. That value selects the default notifications `0x5e6` and `0x5e7` in the checked handler. On the configured path, the publisher forwards the live edit-box receiver unchanged into the message's pointer field. Even if a later assignment gave either field the selection ID, the payload would still be the edit box, which cannot match the registered descriptor pointer. Later ID assignments remain outside this check. [Verified edit-box contract](evidence/serato-primary-publishers-20261107.json)

If the ordinary launch stays offline, the next private selection trace can watch the pointer constructor for `0x2ca` and record its caller and whether the payload is null. The constructor probe passed four software cases for both HID call sites, a null selection and an unrelated message. The passive module observation remains the first live check, and the constructor probe has yet to run in Serato.
