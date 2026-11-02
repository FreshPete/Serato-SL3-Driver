# Current HID verifier task and state flow

The current HID kind-6 path creates a `HidDeviceVerifierTask` whose update dispatch reaches a descriptor-dependent verification state machine. Its initialization reads the previously identified `secret_key` storage and passes a generated message through the retained connection. This extends the [earlier HID construction proof](serato-hid-verifier.md); it does not expose a generic-ASIO registration hook or demonstrate an admitted SL3.

Target: unchanged original/installed Windows Serato DJ Pro 5.0.0.1278, SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. Addresses below are preferred VAs. No vendor program or device operation ran. The exporter reads the executable and prior sanitized evidence, not key-bearing XML. Keys, generated buffers, transformation details and the reply-comparison algorithm are omitted.

## Concrete task and dispatch

Start method `140628c30` clears the second retained object's verification state through `140627b60(..., false)`, sets its own started byte +0x1c, allocates 0x50 bytes and constructs the task through `1406282f0`. That constructor installs vtable `142825af0`, RTTI-bound to `HidDeviceVerifierTask` at complete-object offset zero. It retains the supplied shared pointer at task +0x40/+0x48. The start method stores the task at verifier +0x48 and invokes its virtual slot +0x20.

| Task slot | Target | Checked boundary |
| --- | --- | --- |
| +0x08 | `140628940` | Another task method; its full scheduler meaning is not assigned here. |
| +0x10 | `140628910` | Complete 14-byte leaf loads task +0x40 and tail-dispatches a non-null value to `140628850`. |
| +0x20 | `1405b2ff0` | Checks task byte +0x3c; when clear, passes the task to `1404db050` and sets the byte. The downstream scheduler is not exhaustively traced. |

Method `140628850` checks verifier byte +0x10 and otherwise calls poll method `140628500`. Its machine code tests AL after that call. Although the fresh decompiler labels the poll method `void`, the poll's complete-success fast path sets AL and its common path loads byte +0x10 into EAX before return. The status-byte interpretation is supported by these instructions, not the inferred pseudocode prototype.

## Descriptor and connection dependency

Initialization method `140628960` obtains the descriptor stored at verifier +0x40. It reads begin/end pointers from descriptor +0x160/+0x168 and passes that range to a copy helper. The [prior field proof](serato-midi-field-sources.md) identifies this vector as `secret_key`, distinct from the +0x178 `secret_serato_key` vector that gates one MIDI processor. The new exporter binds that prior report and rechecks its instruction bytes; it publishes no field values.

Later initialization loads the retained connection from verifier +0x20 and calls message helper `14069b930`. The helper's full transport/indirect callees are not established here, so this is a connection-backed call boundary rather than proof of a particular physical HID transaction. The method records `timeGetTime()` at verifier +0x14, increments attempt field +0x18 and calls `140627c60` on the second retained object. No actual message, response, attempt count or timing was observed.

This dependency is separate from the incoming descriptor's root HID-section and capability/kind checks. The earlier primary numeric lookup and legitimate descriptor contents are still necessary boundaries; changing a kind integer or registering an audio device does not supply this path's connection, data and result contract.

## Poll, timeout branch and notification

Poll `140628500` first returns the existing success byte when it is nonzero. Otherwise it queries the second retained object's byte +0x8d through `140627140`. On the response-available branch it calls predicate `1406287f0`. A successful predicate writes verifier byte +0x10 and returns success; the poll then calls `140627b60(..., true)` and requests task cleanup through `140628ce0`. The rejected-response branch goes back to the common return without executing the no-response retry branch in that invocation. Other writers and later callbacks remain unexhausted.

The no-response branch subtracts the saved timestamp from `timeGetTime()` and uses an **unsigned elapsed comparison strictly greater than 5000 ms**. It invokes initialization again when the signed attempt count is below 12. At or above that threshold it requests task cleanup and calls the second retained object's virtual slot +0x10. These are branch constants, not a measured end-to-end timeout or a safe USB reopening policy; callback scheduling, response state and other mutation can affect behaviour.

`140628ce0` checks the started byte and task pointer, calls task virtual slot +0x28 with true, then clears the task pointer. This does not independently prove thread retirement, cancellation completion or kernel quiescence.

Setter `140627b60` exchanges the supplied Boolean into the second object's byte +0x8e. When the resulting byte is nonzero, it performs another existing VID/PID/revision descriptor lookup and conditionally builds an object with constructor argument 0x2e3 and field +8 equal to 5, then passes it to a sink's virtual slot +0x58. Two complete helper leaves establish the Boolean load and address identity used by that exchange. [Later subscriber/handler tracing](serato-wireless-notification.md) identifies wireless-deck handling and an additional primary-manager/state condition. Actual event delivery and successful primary-device admission remain unverified. A local success byte, this notification and actual audio/DVS success must remain separate claims.

## Reproduction and scope

Run `.venv/Scripts/python.exe scripts/export-serato-hid-task.py` with the pinned original and private focused reports available. [The evidence](evidence/serato500-hid-task.json) verifies 106 new instructions, 201 prior instruction-byte checks, the task RTTI and three slots, one complete dispatch leaf, two complete setter helper leaves, nine unwind extents, two actual `WINMM.dll!timeGetTime` import sites and six fresh complete focused functions. Export regenerates byte-identically.

Fresh focused ranges are `1406282f0:14062838b`, `1405b2ff0:1405b3020`, `140628500:1406287ed`, `1406287f0:14062884e`, `140628850:140628904` and `140628960:140628c29`. The import used an isolated unchanged PE copy, an empty library-search directory, no whole-program analysis, read-only mode and disabled library loading. Its log reports zero additional files, discarded import and success; the temporary project is empty. Private pseudocode remains analysis evidence, not a verified ABI or published vendor source.

Native build inputs, trace dependencies and binaries remain unchanged by this static-only checkpoint. No application/resource/account, driver, registry, trust, security, firmware or physical device change ran. No other product identity or key was adopted and no response fabricated. The findings identify more of this HID contract; they do not show it is an appropriate SL3 implementation route. A defensible genuine SL3 provider/control/audio integration and actual current Serato/two-deck DVS remain unfinished, alongside physical mapping/levels/timing, reliable reopening and protected Windows deployment. Mac remains deferred.
