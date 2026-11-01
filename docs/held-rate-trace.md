# Single-use shared trace for a held-rate diagnostic

**Later checkpoint:** [raw per-transfer rate recording](rate-io-recording.md) is now emitted by the native adapter. Replay and a required recording gate are still pending, so the trace qualification below does not claim to validate that new file. Native inputs changed; prepared test plans stay disarmed.

The rate experiment now has a dedicated normal-user runner, an administrator trace/state collector, a frozen plan and a single-use launcher. This is source and offline validation work: no elevated launch, USB acquisition or physical rate selection ran for this checkpoint.

## Plan and roles

`prepare-rate-trace.py --prepare analysis/rate-trace-NAME --target HZ --expected-initial HZ` creates `rate-trace.json`. Both clocks must be canonical 44,100 or 48,000 values. The plan freezes the intended target and reviewed initial clock, current native build/source hashes, probe/worker images, PowerShell image, 23 trace dependencies and both planner/launcher sources. It requests one acquisition, at most one rate setter, no audio, a 30-second probe deadline and a 60-second shared USB/WPP trace with the existing state-observer attempt.

`start-rate-trace.ps1 -Plan ABSOLUTE_PLAN_PATH` validates and prints that plan without launching the probe or collector. Only an explicit `-Run` claims it, creates the normal waiting role and requests one administrator launch for the collector. Create-new attempt/normal/collector markers bind one plan hash and launch ID. The collector rechecks the plan and the exact live normal process. Refusal, cancellation or consumption never rearms a plan or retries a device operation. Test-created plans are disarmed without execution.

The collector uses the existing bounded `capture-controls-user-context.ps1` implementation, which starts tracing and captures Windows state; it never launches the device probe. The separate `test-rate-user-probe.ps1` runner requires an ordinary token, current tested images and all rate dependencies. It saves a create-new intent, checks the live collector and reobserves its PID/creation time/image/session immediately before launch. An expired or changed observation refuses the rate test.

## Outcome and recovery

The normal role runs the bounded [held-rate host probe](held-rate-probe.md), records parent/probe/worker token evidence and preserves whatever request, probe and native rate records exist even on failure. It never stops or kills the independent administrator collector. A missing or failed rate result cannot become a successful traced experiment.

Final qualification checks the immutable intent, native observation and journal, source/image bindings, ordinary process tokens, fixed trace duration, capture session/statistics/loss, trace cleanup and selected before/after Windows/security state. A fresh launch observation must be within two seconds of probe launch. The full collector window must enclose the probe and retain at least twelve seconds after its retirement. The native rate observation timestamp must lie inside that probe lifetime.

The operation record remains `redirect_closed: false`; final owner evidence establishes later cleanup independently. The final target in the host report is its **last accepted clock observation**, not a new getter after releasing the device. Windows state recovery does not restore or prove persistence of the device's prior sample rate. `rateRestorationVerified` remains false; no restoration write runs.

The validator reports collected, loss-checked shared trace evidence. It does not prove USB payload correlation, decoded WPP causal startup behavior, continuous identity/readiness, a qualified kernel-image window, oscillator accuracy, analogue audio, production ASIO or Serato/DVS admission. The state-observer attempt remains separately validated and cannot supply a readiness claim.

## Checks and next attended work

Seven focused tests cover actual inert normal-role/default-launcher commands, invalid requests before device launch, frozen target/runtime/role arguments, source changes, consumed plans, synthetic complete trace composition, stale/insufficient windows, clock/cleanup/file-binding failures and native observation timing. Composition uses synthetic ETL/statistics/journal/native records and a mocked build-contract boundary; these are not physical SL3 evidence. Actual current-build checks and default launcher inspection run without elevation, tracing or context creation.

The first focused run accidentally included imported fixture test classes, causing an older contract test to reject the stale build manifest after the build-runner change. Fixture imports were corrected; the initial failed log is retained, and all intended focused checks pass. Verification and saved test-plan identities are in [checkpoint evidence](evidence/held-rate-trace-20261101.json).

An attended test still needs a freshly reviewed intended/initial clock pair and fresh plan for its current build. The old Scope/image plan and all unit-test rate plans remain permanently disarmed. Positive elevated launcher execution, physical held-rate validation, native USB/WPP interpretation, production ASIO rate selection and measured profiles remain unfinished. No UAC, firmware, binding/trust/registration or security-policy change ran for this update.
