# Current generic DriverAPI notification path

The generic DriverAPI result previously predicted for an SL3 support-1 counterfactual now has a checked notification receiver. Conditional action **6** dispatches through DeviceManager observer slot `+0x38`, emits UserIO message **0x52**, and reaches keyed object/state handling in the notification receiver. This is neither evidence of an ASIO open nor a newly established blocking hardware requirement. The actual unchanged SL3 stub still selects the discontinued support branch.

The [reproducible evidence](evidence/serato500-driver-notification.json) verifies the original 5.0.0.1278 executable SHA `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`, 41 instruction facts, nine PE unwind ranges, two switch-table mappings, DeviceManager observer RTTI and four newly focused function reports. The original application was read as data, never executed or modified by this analysis.

| Link | Checked evidence |
| --- | --- |
| Conditional action | `1421dad00` preserves DriverAPI `+0x90`'s Boolean in R13B. Its false branch tests BL and writes action 6 when BL is nonzero. The [earlier contract](serato-supported-contract.md) identifies the generic implementation and its empty-key readiness prediction; this does not change the descriptor's actual support state. |
| Deferred switch | Action index 6 in the table at `1421debe4` targets `1421dea78`, loading observer slot `+0x38`. |
| Concrete observer | RTTI binds table `1431c3f28` to DeviceManager's `+0x88` subobject. Slot `+0x38` points to `14213f740`. Runtime instantiation remains unobserved. |
| Notification emission | The observer passes message ID `0x52` into constructor `14185ee90` and publishes through a separate receiver slot `+0x58`. |
| Message receiver | `14137b790` reads the ID at message `+0x0c`. Its two-level lookup uses byte index 9 for `0x52`, selecting `14137bdd9`. The case extracts the payload through `141380440` and handles a keyed collection at receiver `+0xb0`. |
| Payload type | The extractor uses RTTI for `UserIO_VoidPtrMessageData` from base `UserIO_MessageData`. The payload remains an opaque pointer at that cast boundary. |
| Keyed helper | Conditional helper `14137b670` obtains a keyed value through `14137b450`, looks up an associated object through `140f1fa40`, optionally calls its virtual `+0x40`, then invokes further collection-update helpers. The full meaning and dynamic target of `+0x40` are not established. |

The newly focused `140f1fa40` is a keyed pointer lookup: it returns a stored value on a match and zero otherwise. The focused helper output supports that local interpretation; it does not supply the associated object's class or prove that the virtual call closes a dialog. Those names are deliberately not assigned without evidence.

The subsequent [object-provenance analysis](serato-notification-object.md) identifies the receiver as `DeviceNotificationController` and traces its stored dependency from the engine's `NotificationCenter` argument. Base/QML notification tables now supply checked slot-0x40 targets and Boolean callback values. This resolves more of the static object contract without assigning a licensing/audio result or claiming a live SL3 connection; the original report above retains its earlier scope.

This separates a notification route from USB trust, native transport, audio opening and DVS. It supplies no supported external descriptor registration route and selects no patch. Genuine SL3 descriptor provision, component aggregation, current handshake/control integration, unique ASIO selection, measured timing and legitimate account/product behavior remain required. No registry entry, support value, archive, executable, account state or device identity was changed.

Run `.venv/Scripts/python.exe scripts/export-serato-driver-notification.py` from the repository root. It checks exact original bytes and saved focused reports, then writes the compact evidence. Regeneration is byte-identical. The focused analysis used a fresh read-only Ghidra import with automatic analysis disabled; the process completed successfully and its temporary project was discarded. No native production input changed, so native/audio tests were not repeated or reassigned.
