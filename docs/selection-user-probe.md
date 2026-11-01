# Supervised normal-token setting test

The single-target runner is prepared for an attended test on this Windows host. No physical run of this wrapper has occurred. It requires a successful **current-build normal-token read-only control run**; the earlier administrator audio tests and normal-token descriptor listing do not satisfy that requirement. Repeated native redirection remains unresolved, so an owner must be available for recovery. Windows security and the installed driver binding are left unchanged.

## Separate roles

`scripts/test-selection-user-probe.ps1` runs from an ordinary PowerShell terminal. It never elevates itself. `scripts/capture-controls-user-context.ps1` runs separately in an administrator terminal and owns the 60-second USB/WPP trace and Windows before/after snapshots. Despite its historical filename and context schema, that collector launches no device probe and changes no audio setting. It is reused unchanged. The normal-role runner never stops or kills that collector.

The setting runner accepts one explicit canonical target: `sensitivity:GROUP:VALUE` (group 0–2, value 0–15) or `through:GROUP:VALUE` (group 0–2, value 0–1). Logical groups and physical jack mappings are not yet verified. No target is chosen automatically. The read-only baseline's full 22-byte table and cached rate are bound to the run.

## Before a probe may launch

The runner validates the completed read-only run with the existing normal-token validator, including its native journal, actual parent/probe/worker token queries, complete shared USB trace, selected recovery state, script identities and current build manifest. It checks the current binaries, native inputs, build script and all 22 setting-runner dependencies. Descriptor-only evidence, simulated evidence, failed cleanup and old-build evidence are refused.

The validated prerequisite and target are saved as `intent.json` using create-new semantics after the collector creates the fresh context directory. The prior run, control sample and Windows snapshots are bound by hash. The collector's new resting state must match the prior recovered state. Admission queries the actual collector process identity, requires a still-recording trace no more than ten seconds old, and allows at most two seconds from that observation to probe launch.

The native probe receives both `--target` and `--baseline-controls`. Its [version-2 prepublication gate](selection-host-probe.md) compares the freshly read full table before any selection command. The worker separately requires its fresh same-owner, single-use baseline at setter submission. A mismatch never causes retry or rollback.

## Attended sequence

First obtain the [current normal-token read-only baseline](controls-user-probe.md), using its separate collector and ordinary-terminal roles. Inspect its complete result and recovered state. An old silent-stream pass proves neither current control access nor successful reopening. Stop and investigate any stalled redirect, remaining worker or descriptor failure before another device operation.

For the setting test, choose a new local context directory and one exact target from the reviewed baseline. Start the ordinary role first, supplying all three values:

```powershell
# Set these to the reviewed baseline, fresh context and exact intended target.
./scripts/test-selection-user-probe.ps1 -Run `
    -BaselineDirectory $baselineDirectory -ContextDirectory $newContextDirectory -Target $reviewedTarget
```

Then start the unchanged collector in the separate administrator terminal with that same new context:

```powershell
./scripts/capture-controls-user-context.ps1 -Run -ContextDirectory $newContextDirectory
```

Omitting `-Run` returns a plan without creating output or accessing the device. Missing baseline/target and malformed targets reject before launch. The collector retains its own admission checks. Do not reuse a saved context or relaunch automatically after failure.

## Outcome, containment and acceptance

There is one retained acquisition, one baseline read and one selection attempt. A verified no-op is allowed; at most one setter can occur. No stream, rate change, firmware operation, registration or security change is requested. The probe's 45-second watchdog sits inside the runner's 50-second deadline. A deadline failure requests containment of that runner's child tree, remains a failure and does not establish kernel-operation retirement. Raw request/result files are retained and hashed even when operation or cleanup fails. An unreadable result file records an evidence-preservation error without skipping the collector/recovery wait. Secondary evidence and recovery errors remain separate from the original probe error.

The runner waits for the collector, decodes the recorded USB trace and checks loss counters and selected Windows recovery. The final read-only validator revalidates the original prerequisite, binds immutable intent to the actual native request/result, requires the reviewed rate and table, checks the complete selection journal, actual non-elevated process tokens, trace window/session/ETL bindings, zero trace loss, and independently retired owners. A verified operation with failed cleanup remains unsuccessful while retaining its operation evidence.

`recoveryConfirmed` records the selected Windows/device comparison. Final validation failure does not erase that independent observation or turn the whole run into a pass. `run-validation.json` is required for accepted completion. A failed run must be inspected rather than retried from the same context.

WPP provider configuration and prepared decoder identities are checked. **Live WPP emission and decoded WPP messages are not proved by this wrapper's preparation or by zero ETW loss.** Continuous physical USB identity during redirection is also not verified. A successful result would establish one bounded setting operation and selected recovery under the recorded permissions; it would not establish physical gain/routing, analogue audio, sustained operation, reopening reliability, application admission or Serato/DVS readiness.

## Offline validation scope

Six new Python tests exercise real plan-only PowerShell invocations, canonical target rejection, current-build/dependency checks, prerequisite composition, changed-table/state admission and full synthetic final envelopes. The trusted PowerShell evidence-preservation function is also executed in isolation against temporary files, including a deliberately locked result: it preserves the original error and returns without throwing. The final-envelope tests run the real selection/journal/token/trace/recovery checks; their prior validation and build-contract dependencies are isolated with test doubles. Their ETL/XML and native journal are synthetic. They do not execute a native positive USB call, establish administrator collector runtime behaviour or prove physical packet contents. Existing native process suites continue to test the actual probe executables with simulated positives and safe absent-helper negatives.

The actual prerequisite CLI also rejects the archived normal-token descriptor-only run with `Completed split-role read-only controls run required`; this check launches no native probe. The [build-bound setting evidence](evidence/selection-probe-build.json) records that rejection, the default plan, prepared runner sources and test identities. The next physical gate is the attended current-build normal-token read-only run; no current qualifying baseline exists yet.

The collector now has an [optional live-state reader](live-state-capture.md). Its preparation is checked offline and does not authorize a second open.
