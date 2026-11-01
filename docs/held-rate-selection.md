# Rate selection on a retained device: wire and worker dispatch

The retained-device worker now accepts the optional `select_rate` command (`0x308`) on its existing version-three session channel. The request contains one explicit 44,100 or 48,000 target. It never acquires a device implicitly. Dispatch requires a completed handshake, a ready idle device, retired I/O, no active stream, and an adapter that independently opts in through `supports_rate_selection()`. Support for audio-control selection does not authorize a clock write. Older workers reject the unknown command; default and current physical adapters refuse it without a rate transfer.

The original rate transaction supplies the operation: initial getter, at most one setter, accepted opaque acknowledgement and independent verification getter. Its existing 3,000 ms transaction budget and request/read limits remain. The worker has a 5,500 ms operation watchdog, leaving room for the adapter's single 2,000 ms cancellation drain; the future host call has a 6,000 ms reply limit. These constants do not extend native I/O deadlines. An adapter that cannot retire requests must contain its isolated process and retain storage.

## Evidence and ownership

The new standalone rate wire codec uses a 16-byte request and a 64-byte reply, with distinct magic/version, fixed little-endian words, reserved zero fields and target correlation. Replies preserve initial, verified and actual readback rates, accepted acknowledgement, write/read/setter attempt counts, possible effects, failure category and Windows status. Serialization does not grant permission, prove ownership or execute I/O. Malformed sizes, flags, enum values, unsupported rates, inconsistent counts and impossible success/failure histories are refused.

A combined reply carries both the rate observation and the existing owning-device snapshot. A successful operation keeps the redirect and reports the verified target. A failed operation seals that session against retry/start and retains its accepted post-write readback, if any. A pre-write rate is never presented as the failed operation's current clock. Exceptions or malformed adapter results produce snapshot-only failure with unknown clock; a future host must preserve possible-write uncertainty when operation evidence is unavailable. Completed operation evidence is returned before a later redirect close, so a cleanup failure cannot erase it.

Every dispatched rate operation clears the prior stream's interval/statistics contract before entering the adapter. No old stream measurement is assigned to the newly selected rate. A later stream start still performs its independent fresh clock getter and requires configuration agreement. Stop/quit and existing cleanup ownership remain unchanged; the command adds no automatic retry, restoration, audio submission or alternate activation.

## Validation and remaining integration

The actual bounded diagnostic runner's success, no-op, deadline, cancellation, transfer, short-frame, malformed-ACK, notification-limit and mismatch results are roundtripped through the codec. Additional adversarial checks exercise truncated/oversized/null input, each request byte, reserved/unknown reply words, wrong targets and contradictory observation fields.

Process tests use an isolated simulated adapter. They exercise both rate directions, a repeated getter-only no-op, a fresh getter, streaming after selection, refusal during streaming, a subsequent rate change after stop, exactly one acquisition/release, no duplicate setter, default capability refusal, and failure/unknown-outcome sealing. They do not access the physical SL3.

**Remaining:** the native held-device adapter, explicit diagnostic grant/launcher, host outcome/uncertainty API, production ASIO rate handling and measured timing profiles per selected rate still need implementation and validation. This change does not enable rate writes in the production ASIO facade. No physical rate command, USB acquisition, UAC prompt, binding/trust modification, firmware or security-policy change ran for this checkpoint. Current Serato admission and physical audio/DVS remain unverified.

The first dispatch-suite run failed because the new streaming-refusal assertion was placed after a helper had already stopped the stream. The assertion was moved into the active-stream section; that failed log is preserved. Subsequent Release validation passed, including the stricter rejection of stale stream statistics. Debug and SDK-free outcomes belong to the separate records below.

Verification identities and counts are recorded in [checkpoint evidence](evidence/held-rate-dispatch-20261101.json). The previously prepared Scope/image plan stays permanently disarmed; changed native inputs require a new attended plan.
