# One approval for a reviewed logging batch

The logging batch launcher reduces prompts by running one to three predeclared source-only diagnostics beneath one elevated process. It uses the existing query/collector/cleanup controller for each job. It does not retain an elevated command server, create a task/service, save credentials, change UAC/security policies or open the SL3. It cannot power-cycle hardware or run audio tests.

Preparation and default validation are unelevated and start no trace:

```powershell
.venv/Scripts/python.exe scripts/logging-batch.py --prepare analysis/logging-batch-new-session --durations 5
pwsh -NoProfile -File scripts/start-logging-batch.ps1 -Plan analysis/logging-batch-new-session/batch.json
# After reviewing that plan, one Windows approval launches the complete batch:
pwsh -NoProfile -File scripts/start-logging-batch.ps1 -Plan analysis/logging-batch-new-session/batch.json -Run
```

The new batch directory must be a direct child of `analysis` named `logging-batch-*`. Preparation creates uncommitted PLA configuration records and fixed private result paths. Each duration is 1–60 seconds, with at most three jobs; the default is one five-second diagnostic. Multiple durations must be reviewed in advance, for example `--durations 5 10`. This is a sequence of experiments, not automatic retries.

The plan pins the fixed scripts and Python/PowerShell executable hashes, preparation bytes and exact source-run arguments. The elevated child requires the launch-time plan hash and independently checks its token. Changes to code or plans require a newly prepared batch. Before each job the runtime and source plan are checked again. A failed result, cleanup error, changed runtime or exception stops the batch; later jobs are skipped. Existing source-controller cleanup and its uncertainty reporting remain authoritative. Child wait bounds do not prove cancellation of service work, timer cause, hard file-size enforcement or service quiescence.

There is one administrator launch for the whole batch. The parent records the actual PID only if Windows returns a process. Cancellation is a failed launch, not a successful test, and never triggers a retry. A successfully launched process has unknown source-start status until the independent query observes it. Cancelling before execution leaves no source context; after any execution marker is created, the batch is single-use. Results remain in `batch-result.json` and the individual source contexts. Once the sequence ends, the elevated process exits.

Each launch has a random attempt ID. The parent names its corresponding `child-<id>.log` and `child-<id>-exit.json`, and the child saves console output and exit status even if Python rejects the plan or token before `batch-result.json` can exist. Changed-plan failures are also recorded. These files use create-new semantics, so an attempt ID cannot overwrite prior evidence. The internal child requires the fixed workspace batch location and refuses reparse points before creating output. Invalid paths/roles are rejected without writing there. A launch record or zero process exit must still be distinguished from source/run evidence; exit metadata never admits USB readiness.

The first 1 November launch attempt using the previous ad-hoc wrapper was cancelled before its child started. Its source context and capture root were not created. The new launcher fixes that wrapper's false-success handling, which had allowed a null PID to be written after a nonterminating Start-Process error. A subsequent [actual elevated batch](attended-logging-20261101.md) completed and preserved a failed native GUID query, successful cleanup and independent absence. The launcher worked; the source diagnostic still failed and no passing timer/identity result is inferred.

Verification: fourteen Python cases exercise simulated batch sequencing, single-use behavior, no default execution, limited-token refusal, hash/runtime/location/argument checks and stop-on-failure behavior. Three cases execute the extracted production PowerShell launch handler with a mocked Start-Process, covering successful launch, cancellation and another launch error without UAC. Actual local preparation/default-plan validation starts nothing; an actual normal-token execution attempt rejects before creating its execution marker. These are software/admission results, not live logging or device evidence.

Five further actual ordinary-token CLI checks exercise the internal child: token refusal with saved output/exit status, changed-plan failure with saved output/exit status, refusal to overwrite a completed attempt, refusal of a foreign output location and refusal of a malformed attempt ID. The test script itself refuses elevation before running these checks. No execution marker or source context is created by these software checks, and no UAC is requested. The later attended elevated attempt remains separately identified above.

An explicit `--native-identity-policy observed-rechecked` preparation option now binds the [separate observed-native-GUID recheck diagnostic](native-session-guid-recheck.md) into each job. The default remains `configured`. The batch refuses unknown policies and fixes the same reviewed policy for every job.

The [actual opt-in sequence](native-guid-live-20261101.md) has now run both five-/ten-second jobs successfully under one administrator launch, with source disappearance before supervisor stop and complete owned-collector cleanup. This is logging evidence only; hardware operations remain outside this batch's scope.
