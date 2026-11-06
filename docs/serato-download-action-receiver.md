# Original Download Driver action receiver

**Follow-up:** [opt-in supervised integration](session-action-observation.md) now shares the arrival hook, verifies both guard groups before attachment and retains the diagnostic fields. Its offline checks passed; no live probe or automatic action has run. The standalone checkpoint below remains historical.

The original Serato 5.0.0.1278 executable identifies the click action more precisely than a scalar message ID. Its RTTI names a `std::_Func_impl_no_alloc` lambda from `DeviceNotificationController::ShowDriverPopup`. The action vtable's invoke slot (`+16`) points to `141380170`, the previously checked genuine `0x4ff` publisher. [Offline inspection and preparation source](../scripts/inspect-serato-download-action.py) · [Evidence](evidence/serato-download-action-20261106.json)

## What the original bytes establish

`ShowDriverPopup` saves its incoming receiver, builds the callback with vtable RVA `2f2bdb8`, and stores that receiver at callback offset `+8`. It passes the callable to the downstream helper at `140f25270` while constructing the popup. A checked controller message-handler branch passes the same receiver into `ShowDriverPopup`.

The callback invoke body reads its capture at `+8`, obtains the object's message bus at `+0x40`, constructs the fixed `0x4ff` message and publishes it through the original virtual method. Its small copy/move leaf copies the vtable and captured pointer only. That shallow copy does not establish an extra controller lifetime lease.

The inspector checks the original whole-file hash, exact complete-object locator and full callback RTTI name, copy/move/invoke table slots, the unwind-free copy leaf and selected instruction/data flow. It decodes the checked code extents fully and hashes each complete PE function extent. The controller handler's extent includes 136 bytes of jump-table data after its code; those bytes are retained in the range hash and not claimed as instructions. It also verifies all four entry signatures used by the passive probe before preparing any output.

These facts identify a concrete action receiver. They do not establish when the popup is ready relative to the SL3 arrival, whether the creator thread is the UI owner in the live session, or whether a receiver retained past that call remains valid. They do not justify constructing an arbitrary callback or calling a stale pointer.

## Prepared passive probe

`serato-sl3-action-observer.js` observes four startup paths: popup construction, the helper receiving its callback, the controller's message handler and genuine SL3 arrival publication. Before attaching any hook it checks all four entry signatures.

Within a popup call on the same thread, it requires the exact callback vtable, invoke method and captured popup receiver. It reports a small controller ordinal and thread ID, then reports when that popup call returns. Later message-handler observations correlate only already-seen receiver addresses. Those ordinals are address correlations, not lifetime identities; address reuse or object destruction remains a limitation.

The probe keeps no callable for later use, invokes no vendor function, copies no callback, changes no return value and writes no application data. It reads no audio buffers and installs no ASIO callback hooks. Raw controller addresses are not emitted. Output is capped at 128 numbered events and eight controller correlations. An observed scalar arrival is labelled publication, not delivery to a ready panel or an available audio device.

This diagnostic is separate from the working startup shim and is not wired into the session wrapper. It has not been attached to Serato. Its entry guards require original instructions: it cannot simply be layered after another script has already hooked the shared arrival entry. A combined host would need to verify entries before either attachment and share that observation. A future attended observer run must use the normal hash-bound launch/recovery lifecycle and unload/detach all startup probes before manual audio use. This checkpoint provides no automatic install action and reduces no approval prompts.

## Verification

Nine Node cases mock the Frida boundary: reject a changed entry before any attachment, ignore unrelated construction, match the exact capture, reject a wrong capture/table/method/thread, contain an unreadable callback, correlate known controller messages and enforce the event cap. The positive fixture is an observer simulation, not a Serato action invocation.

Actual offline preparation against the pinned installed executable passed the RTTI, table, instruction and entry checks. A wrong executable was refused before output creation, and existing prepared output was preserved. Private prepared files are in `analysis/sl3-action-observer-20261106-checked`. The preparation records the observer, inspector and image-reader source hashes. No process was attached, vendor code executed, UAC requested or device opened; driver binaries and the working shim are unchanged.

```powershell
artifacts/build/embedded-python-3152-20261106/python.exe -I -B scripts/inspect-serato-download-action.py --application 'C:\Program Files\Serato\Serato DJ Pro\Serato DJ Pro.exe'
node tests/test_serato_action_observer.cjs
```
