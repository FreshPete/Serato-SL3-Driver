# Bounded setting probe and offline evidence validator

The host probe now has an explicit `--select-control` mode with a canonical `--target`. It performs one retained acquisition, one read-only baseline query, one setting attempt and final release. It creates no audio buffers, starts no stream, changes no rate and never retries or rolls back. Normal ASIO configuration remains read-only. No native positive setting run has occurred.

The process-level probe and recorded-result validator now have a separate [supervised normal-token USB trace/security/recovery wrapper](selection-user-probe.md). Its preparation is tested offline; no physical setting run has occurred. The prepared [read-only physical baseline](controls-user-probe.md) remains the next attended hardware step.

## Request and result lifetime

The probe requires a new output directory. It writes `request.json` once with the exact target, worker hash, kind, reviewed baseline and empty initial owner state, before constructing a HostSession or contacting a worker. Later updates affect only `probe.json`; an interrupted progress-file write cannot overwrite the original request. Existing output directories reject before launch.

Native selection now requires `--baseline-controls` containing exactly 44 lowercase hexadecimal characters (the complete 22-byte reviewed settings table). Missing, malformed or repeated input rejects before directory creation or worker launch. After the fresh read, the probe compares all 22 bytes with this input **before publishing any selection command**. A difference records the actual observed table, attempts no selection and releases the retained owner. This gate applies even when the requested field might already equal the target.

The table is caller-supplied, not independently authenticated hardware evidence. The supervised launcher obtains it from a validated current-build, normal-token read-only run, binds that run and its recovery state, then passes it to this gate. Direct invocation with arbitrary bytes does not establish an approved physical baseline. The separate same-owner, single-use freshness check remains in the worker at setter submission.

Before calling selection it saves pending publication, an unknown command-publication state, unknown outcome and possible device change. After the API returns it records actual command-attempt and uncertainty flags. Local/pre-operation refusal, unavailable reply and a verified no-op remain distinct. Missing results never establish success.

An accepted result is stored as the canonical **132-byte version-1 selection reply** in lowercase hex. It preserves target, initial/latest/verified tables, opaque receipt, counters, phase/error/native error and possible-write state. Acquisition, after-baseline, after-selection and final owner reports remain separate. Failed final release makes the whole probe unsuccessful without erasing a verified or partial operation result.

Selection mode uses a 45-second probe watchdog. The existing eight-second selection reply and independent five-second final-close policies remain. They do not prove immediate retirement of a stuck kernel operation. An unretired result is saved before fail-stop; forced termination never establishes successful cleanup.

## Recorded consistency checks

`scripts/validate-selection-host-probe.py` is read-only. Version-2 request/result records include the reviewed table; version-1 records are rejected. The validator checks request/result identity, target and worker kind/hash, reviewed/actual table equality, empty initial owner state, one acquisition/baseline/selection, canonical wire/terminal evidence and independent final retirement. It checks full initial-table equality for a setter; a write-free fresh no-op may observe intervening changes during the operation. Native error is preserved. Recorded equality validates consistency; the actual prepublication gate runs in the probe.

Native success also needs one complete worker journal: exact target markers, acquire/clock/baseline, ordered getter/setter/verification stages, bounded reply/notification counts, result classification and final close/unload. Simulation must not contain a native journal. These checks establish recorded stage/count consistency, not USB packet contents or uninterrupted physical identity.

This probe-only validator's `valid` means **recorded consistency only**. The separate split-role validator adds reviewed-baseline/current-build/target binding, USB trace and selected Windows recovery checks. Live WPP emission, continuous physical identity, physical gain/routing, audio continuity and Serato/DVS acceptance remain separate.

The native probe sets the existing single-target grant and journal only in explicit selection mode. Only the simulated executable accepts fixture modes. Invalid targets reject before output creation or worker launch. No control panel or production configuration entry is added.

## Validation

Actual process tests cover change/no-op, reviewed-table match/mismatch, no overwrite, partial setter failure, mismatched read-back, malformed/thrown/stalled outcomes, complete/partial evidence surviving failed close, and refusal before selection. A reviewed mismatch preserves the actual baseline and known-no-selection result through final release. Native negatives use an absent helper or invalid arguments and send no setting. Six Python tests mutate wire fields, target/reserved/optional evidence, reviewed-table types/contents/schema, initial owner/types, publication uncertainty, cleanup and native journal order/counts.

[Build-bound evidence](evidence/selection-probe-build.json) pins executable/source/script/log identities. The native CTest inventory is now **40**; SDK-free remains 25. Historical hardware results stay attached to their original binaries. Local checkpoint: `artifacts/build/checkpoints/selection-probe-20261031`.

Fresh checks pass **40/40 Release, 40/40 Debug, 25/25 SDK-free and 131/131 Python**. Eight current exporters pass. The old physical prerequisites are explicitly rejected for the current worker. No physical setting, driver/binding/trust/security, registration, application/account or firmware operation ran.
