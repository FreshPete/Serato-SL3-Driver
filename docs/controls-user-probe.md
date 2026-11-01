# Normal-token controls test with a separate trace collector

31 October 2026. This prepares one SL3 acquire, clock getter, audio-control-table getter and final release under a normal Windows token. The administrator collects USB/WPP events and security/device snapshots separately. It has **not run on the SL3**. The earlier actual non-elevated descriptor listing passed; ownership, control-pipe access and streaming remain separate physical gates. [Actual descriptor evidence](usbdk-user-access.md).

The workflow does not self-elevate, install a broker/service, change device permissions, send audio, change rate/settings, register ASIO or retry a failed acquisition. The known `StartRedirect` stall can still require an owner power cycle. Use it with the owner present and a recovered resting SL3.

## Procedure for a future supervised run

Use two terminals in the repository and the same fresh context path. First start the normal terminal role; it waits up to 90 seconds for the collector:

```powershell
pwsh -NoProfile -File scripts/test-controls-user-probe.ps1 -Run -ContextDirectory tests/results/local/user-controls-01
```

Then, from an already elevated terminal, start the collector:

```powershell
pwsh -NoProfile -File scripts/capture-controls-user-context.ps1 -Run -ContextDirectory tests/results/local/user-controls-01
```

Omit `-Run` from either command to review its plan. Plans create no directories and perform no USB or trace action. The normal role rejects an elevated token; the collector rejects a normal token. The collector owns its unique, bounded 60-second trace and before/after snapshots; it never launches the probe. The normal role never stops or kills the elevated collector. Existing run records are not overwritten.

## Admission and evidence

Before launching the probe, the normal role checks tested native images and seventeen pinned script dependencies. It saves the recording trace/context prefix and queries the collector process's PID, creation time, executable path and liveness. A reused PID, stale record, trace older than ten seconds, missing enabled-security SL3 baseline or missing successful WPP-provider configuration rejects admission. Native launch must follow admission within two seconds. Collector liveness is a process observation; it is not an independent normal-token ETW-session query or proof of emitted WPP messages.

The read-only process inspector uses limited process-query and token-query rights. Parent, probe and journal-identified worker each require a directly queried non-elevated token, exact image and distinct PID. Child creation/query times must fit the probe window. A short-lived process whose token cannot be captured cannot pass this privilege test, even if its native sample is valid. Valid samples are retained separately from failed token/trace/recovery evidence.

The probe has a 40-second outer bound and five-second forced-retirement observation; containment never counts as success. The live journal reader shares access with the writer and reads only a bounded prefix. No extra shell process is spawned per poll. The normal role waits for collector completion, decodes its ETL and validates the native sample/journal, complete probe trace window, loss counters, selected before/after state, source/build/hash bindings and all three tokens. The collector independently records whether device-test processes remain. Raw traces stay local.

The existing controls validator supplies native one-acquire/getter/release and trace/recovery checks; the new validator adds split-role bindings. No USB-identity observer is enabled here. A successful result would establish a bounded normal-token control/ownership operation on this host, not repeated reacquisition, a separate standard account, sustained audio, deployment, current Serato admission or DVS.

## Software verification

Eleven targeted checks cover stale/reused/dead collector evidence, trace timing/configuration, baseline/security roles, missing/elevated/wrong tokens, child identity/time bounds, saved-record mutation and composition with the existing native trace validator. They include a harmless actual self-process token query and plan-only invocations of both scripts. They do not load the USB helper or acquire the SL3. [Current build/test metadata](evidence/held-controls-build.json).

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_controls_user_probe.py -v
```

`run-validation.json` is the final result of a future physical run. `probe-validation.json` alone does not establish normal-token access, complete tracing or recovery. Failed/incomplete records require investigation before another device attempt.

The current worker now uses retained protocol v3. Its explicit setting IPC has simulated process tests, but native capability remains false and this diagnostic still sends only getters. Use the current tested worker/probe and a fresh context; version-2 records or earlier worker hashes are not current prerequisites. [Protocol change and native refusal](control-selection-ipc.md).
