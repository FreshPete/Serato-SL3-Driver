# Checked setting-selection evidence format

`src/core/audio_control_selection_wire.hpp` defines a bounded message format for the setting-selection engine. It preserves the requested target, initial/latest/verified observations, opaque receipt, failure details and possible-write uncertainty. The format is now used by the [idle-only protocol-v3 worker/host command](control-selection-ipc.md). The native USB adapter remains getter-only and refuses selection; no native setting write or control-panel connection is added.

The [selection engine and I/O policy](audio-control-selection.md) already produce distinct observations across success, no-op, failed/short transfer, cancellation, deadline, protocol failure and read-back mismatch. Those distinctions must survive serialization before a host can safely report a setting result. [Source/build evidence](evidence/audio-control-selection.json).

## Format

All integers are explicit little-endian 32-bit words. C++ object layout, padding, pointers and `std::optional` representation never cross the boundary. The format has its own magic `0x53334c53` and version 1; this does not advertise a command in the retained-device protocol.

| Record | Fixed size | Content |
| --- | --- | --- |
| Request | 24 bytes | Magic, version, setting enum, logical group, requested byte value, reserved zero word |
| Reply header | 64 bytes | Magic/version/exact target; I/O, selection and exchange errors; terminal phase; write/read/setter counts; presence/uncertainty flags; two reserved zero words; native error |
| Reply observations | 68 bytes | Three 22-byte slots for initial/observed/verified tables, then two opaque receipt bytes |
| Complete reply | 132 bytes | Header and observation area; no variable length or allocation from a sender-supplied size |

Only sensitivity codes 0–15 and through values 0/1 for logical groups 0–2 are admitted. Phono and other table bytes are not setter targets. Unknown bytes in valid observations and both receipt bytes are preserved unchanged. Absent optional fields have zero-filled storage; nonzero absent storage or reserved bits/words rejects the record.

The decoder requires the exact expected target, including setting kind, group and value. It rejects another target even when that target is otherwise valid. This is correlation, not freshness: a repeated same-target request still needs the enclosing mailbox's request sequencing, exclusive ownership and timing contract. There is no new USB transaction nonce.

## Consistency checks

The codec accepts terminal complete/failed results only. Counts cannot exceed three writes, twelve reads and one setter. Possible-write state must agree with the setter-attempt count. Initial and latest observations appear together; an accepted receipt requires a setter and enough prior transfers; a third write requires that receipt.

Success requires complete phase, no errors and a verified table equal to the latest observation, with the targeted byte matching exactly. A read-only no-op has one write, no receipt/setter uncertainty, and identical initial/latest/verified tables. A changed setting requires three writes and the initial target byte must have differed. Failures cannot carry a verified table, invent a completed state or suppress possible-write uncertainty. Read-back mismatch retains the actual observed table and receipt while remaining a failure.

The native error code remains a separate uninterpreted field; it does not replace the selection outcome or prove cleanup. Invalid targets reject at the request boundary rather than becoming fabricated physical-operation results. The decoder validates sizes, enums and flags before using them and checks canonical re-encoding.

This is recorded-data consistency, not authentication of a sender or proof that the device was accessed. The format contains no device-owner, transfer-retirement, callback, worker-exit, redirect-release or security attestation. The protocol-v3 command carries a separate owner snapshot and the host retains independent cleanup state. A lost reply after an attempted command must preserve host-side uncertainty; this codec cannot reconstruct a missing worker result.

## Tests and next connection

The existing native control test now checks all 54 offered targets in both changed and already-selected cases, complete observation/receipt/native-error preservation, valid-but-wrong target rejection, exact lengths/null input, enum/count/phase/flag/reserved mutations, absent-field canonical bytes and contradictory success/uncertainty. Every existing valid-target injected I/O failure, short transfer, cancellation and deadline result also passes through the codec with all fields compared to the original result. No USB helper or driver is loaded by these tests.

The serialization-only checkpoint passed 39/39 Release, 39/39 Debug, 25/25 SDK-free and 125/125 Python with unchanged runtime binaries. The subsequent [IPC checkpoint](control-selection-ipc.md) sets `workerCommandConnected=true` for the new explicit command and changes retained protocol/runtime hashes, while the native adapter and physical-settings flags remain false. The exporter checks the three expected production codec callers and retains the native getter-only guard. See the current [evidence](evidence/audio-control-selection.json) for exact hashes and suite records.

The distinct idle-only worker command and host API now preserve accepted results through later failed cleanup, using separate 7.5-second worker and eight-second host policies tested with simulated processes. Native transfer/drain timing and independently measured hardware retirement remain unverified. The prepared physical read-only table query remains the gate before any native setting experiment; physical jack mapping, routing/level behaviour and current Serato/DVS remain unverified.
