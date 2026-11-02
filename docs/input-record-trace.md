# Traced three-second input recording

The `InputRecord` scenario prepares an attended native run of the [input recorder](input-record-probe.md). It combines the normal-user diagnostic with the existing administrator USB/WPP trace collector and state-observer attempt. It has not run against physical hardware. Secure Boot and code-integrity settings are unchanged.

The recorder opens the SL3 once, reads its clock rate, starts input collection with zero PCM on all output channels, retains the first whole-bank three-second prefix and releases the session. Its expected rate must be explicitly chosen from an established device observation. A mismatch fails without setting the rate or retrying. No preliminary inspection acquisition, second open, rate/control setter, firmware change, production ASIO configuration or registration is requested.

## Prepare and inspect

These are offline operations. Use a new name; earlier or test-generated plans are not the next attended plan. The example rate is illustrative, not a current hardware observation.

```powershell
.venv/Scripts/python.exe scripts/prepare-input-record-trace.py `
  --prepare analysis/input-record-trace-NAME --expected-rate 44100
pwsh -NoProfile -File scripts/start-input-record-trace.ps1 `
  -Plan <absolute-path-to-input-record-trace.json>
```

Preparation requires the current tested Release manifest, build runner, all native input hashes, recorder/worker image hashes, nineteen shared/component dependency hashes and both new launcher hashes. The saved plan is reconstructed on inspection. Duplicate/nonfinite JSON, modified plans, changed runtime, an existing output context or an already-attempted launch are refused. Preparation and default inspection launch no child or device test.

An explicit `-Run` on the second command requests the attended experiment. It starts an ordinary-user waiting role, verifies that role's live process/image/token identity, then requests one Windows approval for the separate trace collector. The collector never launches the device probe. Before the normal role launches the recorder, it validates the resting SL3/security baseline, WPP configuration and the same live collector process; it reobserves that process after validation and requires a fresh launch observation. The state observer records an attempt; it is not a readiness oracle.

The native recorder has a twenty-second watchdog and a six-second collection limit for a nominal three-second prefix. The wrapper gives it thirty seconds inside a sixty-second trace and requires at least twelve seconds of trace after retirement. These bounds contain user-mode work; they do not prove kernel quiescence. The collector checks for leftover recorder, simulated recorder, worker, host/scope/broker probes and broker controller before and after tracing, refusing leftovers rather than killing them. The normal role does not terminate the elevated collector.

## Evidence and qualification

The plan schema is `sl3.input-record-trace.plan.v1`; the run schema is `sl3.input-record.traced-run.v1`. Controls, facade scope and broker scope cannot qualify this recording. The distinct scenario binds the requested expected rate to the recorder's observed rate, the native `probe/result.json` and `probe/input.pcm`, complete `probe/worker-1.tsv`, probe-validation hash and all shared trace/recovery evidence. Native journal grammar permits exactly one acquisition and one clock getter before release/unload, without setters or another acquisition.

Final qualification includes observed non-elevated parent/probe/worker identities, the exact native journal worker PID, source/build/image pins, matching before/after selected security/device/application/ASIO state, successful trace cleanup, bound ETL/statistics and zero event/buffer loss. Normal stop and retirement must succeed. A timeout, containment request, missing token evidence or failed recovery prevents a qualified run even if some PCM was saved. No automatic retry or plan rearming is available; a cancelled approval also consumes the attempt.

Saved native-shaped records are consistency evidence rather than independent physical attestation. The three-second recording preserves startup samples and cannot prove physical jack mapping, analogue levels, clock accuracy, packet continuity, measured latency, safe reopening or Serato/DVS admission. A successful trace must be reviewed before another acquisition. The existing [recovery/port-observer queue](next-tests.md) remains ahead of choosing an attended audio experiment. A known source with documented wiring/control state is still needed for useful physical [tone analysis](known-input-tone-analysis.md#three-second-recorded-prefix-input); Phase is not assumed to be a calibrated sine source. This workflow sends only zero output payload, so actual output mapping/levels and nonsilent loopback require a separate reviewed experiment.

## Offline verification

Seventeen new plan/launcher/component checks cover both expected rates, missing/wrong rate refusal before run, strict plan JSON, fixed operations, runtime drift, single-use binding, default inspection, ordinary-token collector denial and no-overwrite behaviour. The component composition uses actual synthetic recorder/one-getter journal grammar with mocked trace statistics; it is not a physical trace. Eighty-three shared-runner, controls, scope, broker and image-collection checks pass, including an added synthetic normal-token recorder dispatch test. Release and Debug each pass all 64 native checks; selected native recorder/worker/ASIO/broker image bytes remain unchanged. The SDK-free build's prior 39-check result retains its earlier scope and was not rerun for these script-only changes. [Verification](evidence/input-record-trace-20261102.json) binds exact versions and logs.

No UAC prompt, device open, native recording, nonzero audio, binding/trust change, protected installation or Serato operation ran for this checkpoint. All older trace plans retain their source versions and need fresh preparation. The full Windows/current-Serato/two-deck-DVS objective remains active; macOS is deferred.
