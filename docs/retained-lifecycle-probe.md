# Retained-device physical test preparation

The bounded retained probe and traced sequence are implemented and tested in simulation. **The first native sequence passed on 30 October 2026: fresh capture, silent duplex and both retained streams, with trace/recovery checks.** See [actual result and limits](retained-physical-test.md). The preparation below describes the original test contract. The next hardware run must obtain fresh prerequisites from the current worker; the earlier F297 physical results are not substituted. No driver change or registration was made.

The latest worker adds [protocol-v2 idle control inspection](held-controls.md). This audio probe does not invoke that new getter; its physical inspection still needs a dedicated diagnostic record/trace entry.

## What the probe does

The native `sl3_host_probe.exe` now accepts `--retained-44100` or `--retained-48000` with the same pinned worker/helper and fresh output-path arguments as its other explicit modes. Retained modes fix eight USB intervals, 128-frame SDK banks and two one-second zero-output sessions; optional interval overrides are rejected before creating output. Default/`--plan` still performs no device access. The separately compiled simulated executable remains truthfully identified as simulated.

The probe acquires once through the retained ASIO host, verifies the actual acquired rate against the explicit expectation, creates buffers and starts the first session. After stopping, it requires retired audio I/O/callbacks while the device/process stay held. It disposes/recreates buffers, starts the second session on fresh queues, stops/disposes again, then performs final device/process release. A failure stops the sequence; there is no retry, reacquisition, rate setter or firmware operation. The reviewed redirect operation itself may reset/re-enumerate the device internally.

Each stream has a separate `stream-1.json` / `stream-2.json`, including actual counters, software callback timing, stopped-but-held state and buffer disposal. Root `probe.json` has schema `sl3.retained-host-probe.v1`, recording acquisition, two completed sessions, one buffer recreation and final independent ownership retirement. A failed startup persists its observed state before aborting. The root's final release does not overwrite the earlier per-stream retirement results. Unproved cleanup fails the private probe rather than allowing callback-owned storage to disappear.

Worker-published input, host-consumed input, published output and native submitted/completed output counts are separate. Shutdown can leave queue tails and canceled requests; validators check their ordering without requiring equal counts or promoting all submissions into successful completions. Callback frame positions must restart at zero for each new stream. Timing observations do not approve a latency profile or establish physical clock/sample continuity.

## Native journal and prerequisite gates

`validate-retained-host-probe.py` checks both stream records and the root result. A native positive result additionally requires exactly one complete `worker-1.tsv`, one PID and a matching operation sequence: helper load, complete enumeration/configuration, one redirect/system-handle acquisition, **three** clock getter pairs, one redirect close and helper unload. Enumeration may poll before the single redirect. Extra redirects/getters, another worker file/PID, missing returns or a partial final line fail verification. A simulated result is accepted only with the explicit simulated option and no native journal.

The prerequisite mode independently validates same-worker capture followed by silent duplex, their source/trace/security/recovery bindings, every submitted terminal packet/status, the fresh actual IN-to-OUT layouts and all four saved zero output buffers. It rejects the old F297 records when the current worker hash is requested. Replaying them with their actual historical hash verifies the validator only; it creates no new current-build hardware result.

`test-retained-host-traced.ps1` defaults to plan mode and does not elevate itself. Live execution requires an already elevated terminal, enabled Secure Boot, the reviewed running transport, explicit expected rate, same-worker prerequisites and no existing device-test process. It pins the tested probe, worker, validator, runner and imported script dependencies. It records the bounded USB trace, hashes records/ETL, checks loss/window coverage and selected before/after recovery. Failed runs retain journal prefixes and progress. No install, trust, policy, automatic reboot or ASIO registration occurs.

## One operator-attended sequence

`test-retained-sequence.ps1` runs fresh bounded capture, silent duplex and the retained probe in order under one already elevated terminal. Each step has its own trace and recovery gate, and the sequence stops on the first failure. The expected rate comes from that fresh capture; it is not assumed to persist through a power cycle. The finite prerequisite tests acquire separately; the **final two-stream probe** is the operation constrained to one redirect.

Inspect the plan without hardware access:

```powershell
pwsh -NoProfile -File C:\Users\peter\source\repos\Serato-SL3\scripts\test-retained-sequence.ps1 -ResultDirectory tests/results/local/retained-sequence-20261030-01
```

When the owner is present and the normal SL3 identity/no-test-process baseline is confirmed, run from an already elevated PowerShell terminal:

```powershell
pwsh -NoProfile -File C:\Users\peter\source\repos\Serato-SL3\scripts\test-retained-sequence.ps1 -Run -ResultDirectory tests/results/local/retained-sequence-20261030-01
```

Use a fresh result directory; evidence is never overwritten. Three separate trace windows make the sequence approximately three minutes even though the final audio workload totals two seconds. Raw USB/audio stays in the ignored local results tree. A failed device recovery requires inspection before another attempt; this script does not power-cycle, reset or rebind the SL3 automatically.

## Software validation and remaining scope

`sl3_retained_probe_lifecycle` exercises the actual probe executables: two positive simulated sessions, buffer recreation/final release, malformed-mode rejection, observed-clock mismatch without audio, truthful-kind rejection and a real-native asserted absent-helper negative. The Python evidence tests mutate ownership/failure/counter/identity fields, incomplete/extra journal operations, packet statuses/layouts and saved zero buffers; plan checks confirm no directory/device actions and missing live prerequisites fail before elevation/security/device queries. [Build/source/log bindings](evidence/retained-lifecycle-probe-build.json).

Full verification also exposed an older temporary-session shutdown race. An already executing callback could return after ordinary queue closure and be marked as an audio fault. The audio owner now treats only a closed queue behind an already sealed callback gate as ordinary stop; real callback, format, rate and other transport faults remain failures. The deterministic blocked-callback test now asserts no spurious fault. Temporary startup also invalidates its earlier inspection's I/O/device retirement flags before publishing Start, as the retained path already does.

After the native retained lifecycle passes, sustained timing, controlled analogue/channel measurements, a defensible timing profile, production deployment/application behavior and current Serato/actual two-deck DVS remain required. Retention is still scoped to one IASIO object: complete application scan/object-recreation behavior needs verification. No persistent/elevated service is inferred from this test, and macOS remains deferred by the owner.
