# Action-6 notification object provenance

The previously opaque `+0x40` call in the [generic DriverAPI notification receiver](serato-driver-notification.md) is now bound to a notification dependency and checked notification implementations. This narrows the application contract; it supplies no admitted SL3 session or new transport/licensing predicate.

The original Windows 5.0.0.1278 executable and installed copy match SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. All addresses below are preferred image VAs. The application was read as data. No resource, executable, registration, device identity or account check was modified.

| Link | Original-byte evidence |
| --- | --- |
| Receiver type | Vtable `142f2b598`, slot `+0x18`, targets receiver `14137b790`. Its complete-object locator identifies `serato::dj::DeviceNotificationController`. |
| Stored dependency | Constructor `14137b140` saves incoming R8 into receiver `+0x48`. |
| Caller provenance | RTTI identifies constructor `141370760` as `serato::dj::engine::Engine`. At `141370faf` it passes the entry-stack `+0x60` argument through R15 to R8. The complete enclosing constructor type signature identifies explicit argument eleven as `NotificationCenter&`. The shortened decompiler prototype is not used to infer this ABI. |
| Keyed lookup | `14137b6e1` loads receiver `+0x48` for `140f1fa40`; the returned pointer, when nonzero, receives virtual `+0x40`. |
| Base notification target | `Notification` vtable `142eb2828` binds `+0x40` to `140f25fc0`. |
| Checked QML target | `QmlNotification`'s secondary vtable `142b828c0` binds the same slot to `1409c5f00`, an exact jump to the base implementation. RTTI independently places its `Notification` base at complete-object `+0x10`. |

The base method passes Boolean **false** into two conditional callbacks and dispatches numeric event **9** through virtual `+0x78`. Its contrasting base slot `+0x48` passes **true** and event **10**. These are checked argument values, not assigned names such as “driver accepted”, “audio ready”, “licensed”, or a demonstrated visible-dialog action. Callback consequences and actual runtime instantiation remain unobserved. The inspected QML thunk is one checked implementation, not an exhaustive subclass inventory.

For the genuine unchanged SL3 descriptor, support state 2 still selects the discontinued-device path. The action-6 projection remains conditional on entering a different support branch. Its notification-object handling must not be promoted into either a new hardware requirement or proof that the missing descriptor/handshake/audio contract is satisfied.

Two fresh focused Ghidra constructor results completed with automatic whole-program analysis disabled. The import was read-only, its temporary project was discarded, and its specific tool process exited zero. Other Java processes were left untouched. No native audio build or hardware test was needed for this static change.

`scripts/export-serato-notification-object.py` verifies five RTTI tables, the QML base hierarchy, twenty-five exact instructions, the small no-unwind thunk, the complete enclosing type signature and both PE unwind ranges. It binds the original-image focused reports and checks installed-image equality, then writes [compact evidence](evidence/serato500-notification-object.json). Actual export and byte-identical regeneration pass. Vendor binaries, complete reports and metadata remain in ignored local artifacts/analysis.

The next application requirement remains a legitimate genuine-SL3 descriptor/connection entry and its real driver-timer exchange through a compatible current interface. The historical `DRIVER_API` kind is absent from the recovered current map; an unmatched `NONE` fallback or another device's kind is not adopted as that interface. Unique ASIO selection, measured transport/latency, product/account requirements and physical DVS remain separate gates. The ordinary-user readiness experiment also remains deferred until an attended launch is available.

Source review also confirms a concrete implementation gap: `control_frames.hpp` constructs the original eight-byte `0x37` challenge request, but the native worker has no explicit driver-timer diagnostic mode. Its native audio-control adapter's default write whitelist is `0x32`, with `0x33` available only under its separate selection grant. The existing rate query is not a timer query. The next bounded implementation can expose the real timer exchange through an explicit isolated diagnostic, preserving the fixed opcode, four-frame reply budget, retirement/containment rules and real device response. It must not insert a generated reply, embedded key, automatic startup exchange or current-Serato handshake fallback. A physical reply would validate that protocol operation, not establish current application admission.
