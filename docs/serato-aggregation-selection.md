# Current Serato aggregation registration and revision selection

The USB-side connection path has its own descriptor collection and registration rules. It is not sufficient to apply `PrimaryDeviceManager`'s lookup rules directly to every connection. Static evidence now traces the transfer between those collections in unchanged Windows Serato DJ Pro 5.0.0.1278. No application, driver, account, firmware or USB identity was changed.

## The two collections

RTTI validates `serato::device::composite::DeviceAggregator` at vtable `1431d4560`. Constructor `1421ba6b0` initializes its descriptor vector at `+0x48`, end `+0x50`, capacity `+0x58`.

`DeviceManager` constructor `14213be40` constructs that aggregator and retains it at `+0x1b0`. It calls `140505470` on the primary manager, iterates the returned vector in order, converts each non-null complete descriptor to its `+0x10` interface and calls aggregator registration `1421bc060` at `14213c695`. Getter `140505470` is exactly an eight-byte leaf returning `this + 0xd8`, the previously recovered primary vector. This establishes the source and order of the registrations, not a live application's successful parsing or final selection.

Registration compares existing entries' shared identity getters at slots `+0x18`/`+0x20`/`+0x28` with the incoming VID/PID/revision. For an equal triple, it obtains the **existing** entry's interface-name string at slot `+0x30`. If that string is empty, it skips insertion of the new entry. A nonempty existing name does not take that suppression branch. If no suppressing entry is found, registration appends the new shared interface in a 16-byte vector element. This is different from the primary registration's null-pointer-only predicate.

The call occurs in construction. The analysis does not establish every possible later mutation, concurrent observer or runtime re-registration.

## USB-side lookup

Worker `1421bc440` calls enumerator `1421beec0`. That enumerator obtains USB-side identity fields through leaf getters:

| Getter | Record field |
| --- | --- |
| `140c01c50` | unsigned 16-bit value at `+0`, used as VID |
| `140c01c40` | unsigned 16-bit value at `+2`, used as PID |
| `140c01c30` | unsigned 16-bit value at `+4`, used as revision |

At `1421bf08f`, the revision is explicitly stored as the fifth stack argument to `1421bffa0`; the next instructions pass PID and VID in R9D/R8D, then call that selector at `1421bf0a4`. This call does not force revision zero.

Selector `1421bffa0` searches the aggregator vector at `+0x48`. It returns the first exact identity/revision match, otherwise the highest strictly older revision, with later entries winning equal older-revision ties. Its comparisons are unsigned 16-bit comparisons. This resembles the primary numeric rule, but its input collection may have had duplicates suppressed.

For another enumerated collection, `1421beec0` reconciles revision information across matching VID/PID records: zero is replaced by the USB-side revision; otherwise replacement occurs only when the composite value is greater. Setter `140b1a3c0` updates the `+0x10` integer in each non-null constituent identity record. These are application-memory writes. They do not change hardware descriptors, firmware or Windows device identity. The construction and provenance of every identity record, and values actually supplied by a connected SL3, remain unverified.

## Consequence for an integration experiment

Conditionally, if a fully parsed resource descriptor is registered before the identity-only stub, both have the same VID/PID/revision, and the earlier descriptor's interface name is empty, aggregation registration retains the earlier entry and suppresses the later stub. The primary vector can still contain both, so its separate later-fallback behavior must not be generalized to this collection.

This does not establish that a restored SL3 descriptor can currently be discovered, parsed or connected. The resource-provider boundary, current handshake/control requirements, admitted USB transport, ASIO timing, product/account requirements and real DVS tests remain independent gates. No loose XML, archive edit or support-value patch was installed. The MIDI connection callbacks at `140525710` and `14052d370` explicitly identify themselves as MIDI in their messages; they are excluded as proof of the SL3's USB-only route.

Reproduce the static checks with `.venv/Scripts/python.exe scripts/export-serato-aggregation-selection.py`. The [evidence](evidence/serato500-aggregation-selection.json) pins original and installed executable identity, RTTI, focused unwind ranges, exact leaf bytes and relevant call/branch instructions. It is not a runtime trace or physical success record.
