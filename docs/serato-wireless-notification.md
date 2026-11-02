# HID verification notification and wireless-deck handling

The current HID verifier's successful-state notification has a checked matching subscriber in `CUserIOConnectionControl`. That handler uses `is_wireless_device` and `num_wireless_decks`, which the unchanged Phase accessory profile sets to true and two. Its subsequent update helper checks a separate stored pointer from `PrimaryDeviceManager` and additional state. This is evidence of wireless-deck handling, not primary SL3 admission or a completed DVS session.

Target: unchanged original/installed Windows Serato DJ Pro 5.0.0.1278, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. Addresses are preferred VAs. No application, device, account or resource change ran. Only two allowlisted Phase values, class/field names and structural metadata are published; keys, HID messages and response material are omitted.

## Message identity and subscriber

The [previous task proof](serato-hid-task.md) stops at setter `140627b60`. This extension checks that the setter passes 0x2e3 to base message constructor `14185ec90`, which stores the ID at +0x0c. The separately written value 5 at +8 is a different type field. The descriptor payload at +0x38 comes from the existing numeric lookup result adjusted by +16; null stays null.

The emitter's installed vtable `142825a40` is RTTI-bound to `UserIO_TemplateMessageData<const serato::device::composite::DeviceDescriptor *>`. Its sink global is `143eac9c8`. Constructor `1405db1e0` passes that same sink to its base constructor, installs `CUserIOConnectionControl` vtable `14281ff60`, and calls subscription helper `14154cd50` with ID 0x2e3. Vtable slot +0x18 points to handler `1405df470`. This establishes the matching subscription and handler in original disk bytes; actual bus delivery and live receiver instances were not observed.

The handler reads the message ID at +0x0c. Its two-level switch subtracts 0x224, uses index byte 20 for 0x2e3 and selects case `1405e0bc6`. That case performs an RTTI cast to the same descriptor-pointer message type, reads +0x38 and leaves on a null cast or null descriptor. A failed cast takes a diagnostic branch; no descriptor or successful connection is invented.

## Conditional concrete descriptor semantics

The non-null payload is queried through virtual slots +0x40 and +0x50. For the separately RTTI-bound `ControllerDescriptor` interface at complete-object +16, the complete getter leaves are:

| Slot | Target | Interface-relative read | Complete-object field | Parser property |
| --- | --- | --- | --- | --- |
| +0x40 | `1405c7f80` | byte +0x118 | byte +0x128 | `is_wireless_device` |
| +0x50 | `1405c6ff0` | DWORD +0x46c | DWORD +0x47c | `num_wireless_decks` |

The parser's literal/property-use and destination instructions bind these names; the interface adjustment matters. The second getter is not the complete object's separate `num_decks` field at +0x46c. Other concrete implementations and runtime mutation remain unexhausted, so the getter meanings are conditional on this checked class.

The unchanged archive's `hid/hid_mwm_phase.xml` has one recognized `osa_device` node, a root HID section, `is_wireless_device=true` and `num_wireless_decks=2`. The archive matches the installed/original hash, its 229-entry index is checked, and the selected member's CRC/hash is verified. This is a declaration projection rather than a connected or verified Phase device. No other device's identity, profile or key is adopted for SL3.

## Local case actions and the separate primary-manager condition

The case continues only when slot +0x40 is nonzero. It queries service/property ID 0x637; a zero integer selects starting index zero and a nonzero integer selects two. The loop uses slot +0x50 as its count, reevaluating it at the loop edge. It emits message 0x580 with integer payload one and the current loop index. Constructor `14185ec00` binds that integer to +0x38 and moves the incoming index into the base message's +0x10 parameter. The message's full consumers and deck/audio effects remain untraced; it is not labelled an observed DVS-enable operation.

The branch then writes connection-controller byte +0x171 and calls helper `1405e2af0`. The helper obtains a pointer through global `143eac1d0`'s virtual slot +0x30. In the checked construction branch that global is assigned the returned `PrimaryDeviceManager` object; its RTTI-bound slot +0x30 is complete getter `140505500`, returning the stored pointer at +0xf0.

For the helper's local update, all of these must hold:

- The primary-manager getter returns non-null.
- Connection-controller bytes +0x171 and +0x94 are nonzero.
- The returned object's DWORD +0x464 is nonzero.

If a gate fails, the helper writes zero to controller state +0x174. Otherwise its returned-object DWORD +0x46c is compared with four: below four writes one and emits message 0x637; exactly four writes two; above four writes zero. The [earlier DVS field proof](serato-dvs-contract.md) names complete descriptor +0x464 as `dvs_device` and +0x46c as `num_decks`. This update's raw field tests do not execute that manager's full DVS predicate or establish account/product entitlement. The actual stored descriptor, byte +0x94 source and live state were not observed.

**Inference:** this path adds wireless control around additional primary-manager/state conditions. It supplies no demonstrated substitute for admitting the genuine SL3 as primary hardware. Connecting Phase can remain part of the future DVS experiment, but its accessory declaration and this notification cannot establish the missing primary descriptor, current ASIO/control selection or working two-deck DVS.

## Verification and remaining work

Run `.venv/Scripts/python.exe scripts/export-serato-wireless-notification.py` with the pinned originals and private focused reports present. [Evidence](evidence/serato500-wireless-notification.json) checks 126 new instructions, 106 prior instruction bytes, five RTTI tables, three complete getters, one switch mapping, five complete fresh focused functions and the selected Phase metadata. Regeneration is byte-identical.

Focused ranges are `1405db1e0:1405dcebf`, `1405df470:1405e17c1`, `1405e2af0:1405e2b8b`, `14185ec00:14185ec52` and `14185ec90:14185ecdf`. The handler's unwind extent includes switch-table data after its last decoded instruction. The first truncated range was rejected by the metadata check and is preserved privately; the successful rerun uses the full unwind range. The fresh import used the unchanged isolated PE, no whole-program analysis, read-only mode and an empty library search path. Its log records zero additional files, successful discarded import and an empty temporary project. Whole-program and indirect-call completeness are not claimed.

Native build inputs, trace dependencies and selected image hashes remain unchanged; native tests were not rerun for this static-only work. No Serato/Phase/device execution, approval prompt, USB acquisition, audio, binding/trust/security, firmware, protected deployment or account operation ran. Physical audio/timing and reliable reopening, legitimate current SL3 admission/control/audio integration and actual two-deck DVS remain required. Mac remains deferred.


The later [primary-pointer handoff proof](serato-primary-pointer.md) identifies an identity-checked writer for the +0xf0 pointer, its selection message and one conditional USB-only publisher. This adds local pointer provenance, without proving the live primary descriptor, admission or audio/DVS operation.
