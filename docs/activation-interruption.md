# Actual ASIO host interruption containment

The existing on-demand activation containment now has an actual process-death test. An owned, unregistered **simulated ASIO host** was forcibly terminated while streaming and again while its callback was deliberately blocked. In both cases the exact controller and worker process objects exited within the ten-second observation bound. A separate normal-stop baseline produced its successful typed retirement records.

This is new verification, not a new production-driver change. It does not establish Serato crash recovery, physical USB cancellation/re-enumeration, clean SL3 release or successful reacquisition. The prepared normal-start candidate and driver binaries remain unchanged.

## Host and process ownership

`diagnostics/asio-interruption` is a separate diagnostic build. It loads only the explicit unregistered fixture DLL, requires its test-only configuration export and exercises the same configured COM/IASIO activation path. The trusted Python runner binds that DLL, simulated controller, simulated worker and unchanged helper file to the previous source/image-pinned fixture run. It also rechecks the full native build's current source pins and simulated output identities. No production provider fallback is attempted.

The host checks six input/six output channels and the actual packed 24-bit buffer format, initializes output buffers to silence and observes completed callbacks. Its blocked case waits until the callback has entered an anonymous diagnostic event and completed none before publishing readiness. These are simulated software planes; the helper is not used to open hardware. The host's normal hold is bounded, with no application, firmware or signing operation.

Before an action, the parent retains live query/synchronize process handles for the host, controller and worker. It verifies executable file identities and records creation times. The controller's creation time must also match its immutable published broker record. The kill operation is `Popen.kill()` on the parent's exact retained **host** handle. It neither terminates descendants by name/PID nor touches other hosts. Descendant observations use the already retained controller/worker handles, so they do not depend on later PID lookup.

The production `worker::Process` implementation configures private jobs with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and creates children with handle inheritance disabled. The abrupt-death results verify that both known descendants disappear under the existing containment design. They do not establish exhaustive system-wide child discovery or which internal cleanup/termination action wins a scheduling race.

## Results

| Scenario | Ready state | End observation | Normal-retirement evidence |
| --- | --- | --- | --- |
| Normal stop | Completed simulated callbacks | Host, controller and worker exit | Host result plus successful controller I/O/device/process/job retirement record |
| Abrupt host death during stream | Completed simulated callbacks; host still holding stream | Exact owned host terminated; controller and worker exit | Absent, as expected |
| Abrupt host death with blocked callback | One entered callback, zero completed | Exact owned host terminated; controller and worker exit | Absent, as expected |

The descendant numeric exit codes were **zero even in the forced cases**. The test therefore does not equate exit code zero with clean retirement. It requires the normal baseline's typed records and preserves their absence after abrupt death. No physical-device release flag is promoted from process exit.

Two separate build Plan/refusal checks and all three actual process scenarios passed. Private driver logging was cleared only in each diagnostic child's environment; no persistent environment setting changed. The [checkpoint evidence](evidence/activation-interruption-20261106.json) binds host/build/runner/reference identities, callback-ready states and exact process outcomes. Native code/package inputs remain source-current; no native audio component rebuild or protected installation was performed.

## Reproduction

```powershell
& scripts/build-activation-interruption-host.ps1
```

The build only runs its inert Plan and unknown-argument refusal. The separate `scripts/test-activation-interruption.py` runner requires explicit expected hashes for its diagnostic build manifest and the prior simulated-ASIO reference report. It constructs fresh inputs under `analysis/activation-interruption-*`, starts only its owned fixture host and preserves raw markers/stdout/stderr and outcomes. Do not use this test host as a normal ASIO client or release launcher.

Read-only postchecks found original Serato resources, no occupied session paths or temporary registration, and no matching first-party worker/controller or Serato process. Firmware, signing enforcement, Windows security settings and registry state were unchanged. The [prepared normal-start experiment](on-demand-normal-start-test.md) still matches its original source/asset pins.

## Startup-selection investigation

A bounded original-byte navigation pass also rechecked the USB-manager initializer `140710720`, its constructor `14070fd70` and Engine handler `141373a40`. It found the previously documented direct-call chain and handler table pointer, with no additional reference in the selected navigation classes. This covers boundary-checked direct E8 calls, selected RIP-relative mov/lea references and data QWORDs; it is not exhaustive indirect-flow recovery. It supplied no new justified startup patch. Normal Serato selection and actual native startup/shutdown still require the attended experiment.
