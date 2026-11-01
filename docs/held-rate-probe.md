# Bounded held-rate host probe and offline validator

`sl3_host_probe --select-rate` now runs a dedicated no-audio experiment through the retained host API and single-use native diagnostic adapter. It acquires once, checks the acquired clock against an explicitly reviewed initial rate, requests one target selection and performs final close. Native mode requires both `--target 44100|48000` and `--expected-initial 44100|48000`; a native fixture override is rejected. Default invocation remains plan-only.

A complete invocation also supplies the absolute worker/helper paths, reviewed worker SHA-256 and a fresh output directory using the existing `--worker`, `--worker-sha256`, `--helper` and `--output` options. This is the underlying diagnostic executable, not the future shared-trace launcher. No positive native invocation ran for this checkpoint.

## Intent, observation and cleanup

The probe writes immutable `request.json` and initial `probe.json` before launching the worker. Progress records mark possible effects before publication. An initial-rate mismatch stops before the selection command, with known-no-setter state. The rate transaction then performs its own fresh initial getter; if that differs from acquisition, the probe rejects the experiment while retaining any actual operation evidence. The acquisition check is not an atomic guard across both getters.

The report separates command attempts, publication pending, explicit pre-operation refusal, unknown outcome, possible effects, accepted wire observation, operation verification and final ownership. A matching opaque acknowledgement alone never verifies the rate. Actual mismatching supported readback survives failure. Worker loss invalidates the old host clock; failed final redirect close cannot erase a previously verified operation. No automatic retry or rate restoration runs.

Success requires exactly one acquisition and one selection, a verified target, no buffers/audio/alternate/control-setting/firmware activity, a retired idle owner after selection, and final device/process/private-job cleanup without forced termination. Unretired ownership is recorded and contains the probe process. A 45-second outer watchdog bounds the overall probe; the existing transaction, worker and reply budgets remain unchanged.

## Validation scope

`validate-rate-host-probe.py --probe DIR --worker-sha256 HASH` checks native recorded intent/result/ownership consistency. `--expect-simulated` explicitly selects simulated evidence. Neither option qualifies a shared USB trace, security/recovery state, analogue signal, oscillator measurement, production ASIO, Serato admission or DVS.

The decoder validates the 64-byte rate wire using the v2 observation consistency rules. Temporary envelope values needed to call that checker are removed from returned evidence; no fabricated timestamp or retirement/cleanup field is exported. Successful records must agree on requested target, reviewed/acquired/transaction initial clocks, selected/final clocks, native status and possible setter effect.

For native records, validation requires exactly one current-format startup journal and an agreeing `worker-1.tsv.rate/rate.json`. The journal must contain one redirect, one acquisition getter, the selected target, one rate transaction and final close/helper unload, without audio or another acquisition. Individual rate transfers are **not** journalled, so payload/count correlation still needs the future USB trace. The native operation record must show retired I/O and `redirect_closed: false`, because it was saved before release. Final owner evidence establishes cleanup separately; rewriting the operation record to claim release is rejected.

## Checks and remaining work

Actual isolated process tests cover a change and a getter-only no-op, immutable intent/no-overwrite, expected-initial refusal, unsupported adapters, partial/mismatching/missing outcomes, watchdog exit and later close failures. Malformed native targets, missing reviewed initial rate, duplicate/invalid options and native fixture overrides reject before output creation. A valid native command with a deliberately absent helper retires without acquiring hardware or selecting a rate.

Seven additional unit tests exercise decoder corruption, request/type/uncertainty guards, owner clock/audio/cleanup failures and synthetic native journal/observation correlation. Synthetic native records exercise validator branches; they are not recordings of this PC or SL3. Build manifests now pin the rate-probe test/validator dependency set and require its lifecycle test in ASIO component builds.

A shared traced launcher, trace/security/recovery validator and actual attended held-rate experiment remain unfinished. The old Scope/image plan stays permanently disarmed; these native inputs require fresh plans. Production ASIO rate selection and measured profiles remain unfinished. No UAC, physical acquisition/rate change/audio, firmware, trust/binding/registration or security change ran. See [checkpoint verification](evidence/held-rate-probe-20261101.json) and [host/native adapter contract](held-rate-host.md).
