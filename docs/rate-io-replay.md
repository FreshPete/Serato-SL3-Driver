# Replay rate recordings before accepting current native evidence

`validate-rate-io.py` now parses and replays complete bounded rate recordings against the accepted diagnostic summary. Current native host probes require this replay, matching worker PID and a canonical recording reference. The traced runner additionally binds the recording digest and checks its creation/submission/completion UTCs inside the probe lifetime. No positive native recording or physical test ran.

## Exact budget origin and recording v2

The first raw format did not include the transaction's start tick. Its first transfer tick cannot substitute for that origin, especially when acquisition or recording work consumed time. The native adapter now buffers exact transaction start, budget, finish and final diagnostic reason through nonblocking core callbacks. A `transaction` row is persisted after raw returns and before buffered decisions. The replayable format is `sl3.rate-io.v2`, with at most 47 rows: one header, thirty begin/end rows, one transaction row and fifteen decisions.

Raw v1 recordings are rejected by this replay path rather than upgraded or assumed to contain missing timing facts. Historical native summaries without a recording declaration retain their original result-consistency scope; the archived physical v1 44.1-to-48 kHz record still passes that original check. It gains no raw recording or current-worker physical claim.

## Parser and replay

The parser reads at most 47 × 2,048 bytes plus one overflow byte, rejects duplicate keys/nonfinite values, enforces exact fields, types, lowercase hex, lengths, sequence/order and native status relationships, and distinguishes input intent from returned bytes. The returned recording metadata exposes actual recorded UTCs and failed-transfer Win32/USBD facts. An API acceptance fact does not attest bus traffic.

Replay independently reconstructs the initial getter, optional single setter, opaque acknowledgement and verification getter. It checks exact request bytes, expected direction, wait limits/remaining budget, bounded notifications, reply tags, supported rates and acceptance/abort decisions. A valid but late frame remains unaccepted. A mismatching supported getter remains a failed operation with actual readback retained. Write counts and possible effects stay conservative even if native submission was rejected.

A complete recording must agree with all accepted rate/result/count/effect fields in its referenced summary. Current native records use the default three-second transaction budget. Cancellation reasons remain recorded software assertions, not independent proof of an external cancellation signal. No retry, device I/O, rate restoration, timeout extension or new production ASIO setter was added by validation.

`--allow-prefix` permits inspection of complete rows before a torn or unfinished suffix. It reports incomplete state with no replayed observation or verified operation and cannot qualify a completed summary. A complete failed operation can be consistent without becoming a successful experiment. The output uses `validRecordingConsistency`, not the broader test `valid` flag, and its scope excludes independent hardware, cleanup, security/recovery and audio attestation.

## Required host and trace gates

Native host validation requires raw v2, a complete replay, summary agreement and the same PID as its single acquisition journal. Missing references/files, incomplete decisions, wrong PID or contradictory data fail. The shared-trace runner preserves the recording hash even on failed attempts. Final qualification binds that file and refuses stale raw UTCs even if a current summary and recomputed file hashes otherwise agree. Windows recovery and device rate restoration remain separate facts; restoration stays unverified.

The rate trace dependency set now contains 24 scripts, including the independent replay module. Existing USB/WPP payload correlation, readiness/image-window qualification, analogue signal and current Serato/DVS claims have not expanded.

## Verification and remaining work

Nineteen focused recording/native-probe tests cover change/no-op/mismatch/short/late outcomes, prefixes, torn suffixes, corruption, native status, request/tag/decision/count/clock contradictions and required-file/PID gates. Eight role tests cover the complete synthetic envelope and stale-recording rejection. A synthetic fixture emitted by the actual C++ writer is independently replayed in both Release and Debug, including PID and no-overwrite checks; no helper or USB device is constructed by that test mode.

The first role-test invocation caught an indentation error introduced while updating fixtures; it was corrected before the successful run, and the failed log is preserved. Verification identities, test counts, synthetic emitter outputs and legacy validation are in [checkpoint evidence](evidence/rate-io-replay-20261101.json).

An attended current-build test is still needed to collect and interpret native rate/USB/WPP evidence. Old Scope/image and rate unit-test plans remain permanently disarmed. Production ASIO rate selection, reliable cross-host lifetime handling, measured physical audio/latency and current Serato integration remain unfinished. No UAC, physical acquisition/rate operation, firmware, trust/binding/registration or security-policy change ran for this checkpoint.
