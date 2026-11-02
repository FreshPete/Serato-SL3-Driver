# Conditional USB-only arrival: deferred action, version gate and state messages

The current USB-only connection route has a checked upstream bridge: a selected nonzero predicate result constructs deferred action zero, whose observer binding reaches a `DeviceManager` callback. That callback's checked final branch emits message 0x2d4 when neither HID nor MIDI components are present. The downstream USB helper returns the OR of two stored state bytes, rather than simply returning a service call's Boolean. These are application-memory/control contracts, not observed SL3 eligibility, backend selection or audio success.

Target: unchanged original/installed Windows Serato DJ Pro 5.0.0.1278, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. Addresses are preferred VAs. No application/resource, firmware/version policy, state message, account or physical device was modified or exercised.

## Selected action-zero bridge

The existing [supported-device contract](serato-supported-contract.md) separates application support, expected components and DriverAPI readiness. This extension follows one later local branch in aggregation worker `1421db390`; it does not replace those earlier requirements or prove every path to this branch.

At `1421dcbf0` the worker calls predicate `140c00af0` and tests AL. Its nonzero path constructs an action using a preserved zero ordinal; the zero path selects ordinal 8 instead. The exporter verifies the zero register has no intervening write on the checked interval. Constructor `1421de6b0` copies that ordinal through its fourth argument to action +0x28. Its table is RTTI-bound to `DispatchDeviceDeferredAction`.

| Boundary | Checked route |
| --- | --- |
| Deferred queue | The selected action-zero path queues its constructed action through `1421de0a0`. |
| Action switch | `1421de890`'s ordinal-zero entry selects case `1421de955`, loading observer virtual slot +0x08. |
| Concrete observer | `DeviceManager` table `1431c3f28`, complete-object offset +0x88, binds that slot to `14213dd20`. |
| Callback binding | The observer stores target `14213ddc0`, adjusts its receiver by -0x88 and passes the callback/shared argument to `14213ae20`. Actual scheduler delivery was not observed. |
| Selected emission branch | Callback `14213ddc0` invokes HID/MIDI presence helpers `140c00ad0`/`140c00ab0`; either present result leaves this final USB-only emission branch. |
| Arrival message | With both absent, the checked branch composes a scalar payload, constructs message 0x2d4 and publishes through the existing sink's virtual +0x58. |

The presence helpers operate on composite members at +0 and +0x10. Their complete checked bodies call the QWORD-null primitive and invert its result. These are component-pointer presence checks, not audio readiness or authentication predicates.

The [previous primary-pointer proof](serato-primary-pointer.md) follows the matching 0x2d4 consumer through numeric descriptor lookup, kind-zero/helper-result conditions and message 0x2ca toward the registered-instance setter. Together these checks identify a longer conditional handoff. They are not a captured call chain. All packed-payload word provenance and every other producer branch remain unexhausted; the emitted third word is not promoted into a verified physical USB revision.

## The action predicate checks a declared minimum version

Predicate `140c00af0` obtains the composite descriptor and, on its checked connection branches, invokes descriptor slot +0x60. For the RTTI-verified `ControllerDescriptor` interface at complete-object +16, that complete getter reads DWORD +0xc8, i.e. complete-object +0xd8.

The parser initializes that field and binds it to the `minimum_version_number` attribute under the optional `firmware_check` element. The predicate compares a connection-derived DWORD against the required DWORD with an unsigned greater-or-equal result. It checks one available MIDI/HID connection branch before the other; the branch with neither connection present sets its local result byte to one. This does not establish an actual device's firmware version, enforce all component-count rules or make this a complete admission predicate. Other descriptor/error paths and actual connection contents must remain separate claims.

Machine code loads the local result into EAX before return, and the caller tests AL; inferred decompiler prototypes are not used as the return contract. No minimum value, firmware, descriptor, version response or comparison was changed. This is a read-only identification of an existing gate, not an instruction to bypass a firmware requirement or to update firmware.

## The USB helper's result comes from state messages

The [previous USB-only publisher](serato-primary-pointer.md) requires helper `14070ff10` to return true. Its method receives the complete `CUSBAudioManager` object. After service/notification work, it tests bytes +0x71 and +0x70 and returns true if either is nonzero, false if both are zero. Constructor `14070fd70` initializes their combined word to zero.

The manager's handler receiver is its +0x10 interface. The checked arithmetic message dispatch updates those bytes through the exact address/byte-load helper leaves:

| Message ID | Interface-relative destination | Complete-object destination | Value stored |
| --- | --- | --- | --- |
| 0x692 | +0x60 | +0x70 | Low byte returned through message virtual slot +0x10 |
| 0x693 | +0x61 | +0x71 | Low byte returned through message virtual slot +0x10 |

The service path queries virtual +0xa0 and conditionally calls +0x90. Its result is published in message 0x693 through sink +0x50, after which the helper reads its two stored bytes. Delivery may affect that result, but synchronous/asynchronous dispatch and complete service semantics are not established. The helper therefore does not simply forward the +0x90 Boolean, and a local true return is not independently proven physical audio readiness. The source of all 0x692 updates and the underlying service/backend selection still need investigation.

## Consequence for the SL3 work

This identifies an existing route for a qualifying USB-only composite without assuming a fabricated MIDI or HID component. It does **not** establish that a new SL3 description can legitimately omit its control contract or pass the whole application pipeline. The unchanged SL3 still follows the already verified support-2/discontinued route; its current stub also lacks a complete supported audio/DVS configuration. Earlier eligibility, real component acquisition, the service/state messages, genuine descriptor provision, current ASIO/control selection and actual DVS remain unfinished.

The next application-side questions are the upstream eligibility of a genuine SL3 description and the service/state contract that drives these two bytes. Current native transport and the prepared attended recording experiment retain their separate scopes. No test was armed, retry requested, application event injected or primary descriptor inserted.

## Verification and reproduction

Run `.venv/Scripts/python.exe scripts/export-serato-usb-arrival.py` with the pinned original and private focused reports available. [Evidence](evidence/serato500-usb-arrival.json) verifies 208 selected instruction facts, 105 prior instruction-byte checks, four RTTI tables, four complete helper leaves, the action-zero switch mapping and zero-register preservation. Five fresh focused functions complete; two unchanged earlier focused functions supply the worker/helper context. Export regenerates byte-identically.

Fresh focused ranges are `14213dd20:14213ddbb`, `14213ddc0:14213eeca`, `1421de890:1421dec20`, `1421de6b0:1421de7a5` and `140c00af0:140c012c7`. Each matches its full PE unwind extent. The isolated unchanged PE import disabled library loading and whole-program analysis, used read-only mode and an empty library-search directory, and logged zero additional files and discarded import. Its temporary project is empty. Whole-program and indirect-call completeness are not claimed.

Both native builds' input, trace/launcher and selected binary hashes remain unchanged; native tests were not rerun for this static-only checkpoint. No Serato/Phase/hardware execution, USB acquisition, audio, approval prompt, protected installation, driver/binding/trust/security or account operation ran. Physical levels/mapping/timing, stable reopening, protected Windows deployment, genuine current SL3 admission/control/audio and real two-deck DVS remain unverified. Mac is deferred.
