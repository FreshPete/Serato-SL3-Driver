# Ordinary-user port observation during release

`observe-sl3-hub-port.py` prepares and supervises one fixed observation job. It waits at most ninety seconds for a fresh twenty-second USB/state capture, verifies the collector's PID, creation time and image, then samples for eighteen seconds. It opens only the selected root hub for the already tested cached connection-information query. It also reads the original SL3 devnode's presence, status flags and problem number through Config Manager. The problem number is meaningful only when `DN_HAS_PROBLEM` is set.

The latter APIs are read-only [CM_Locate_DevNodeW](https://learn.microsoft.com/en-us/windows/win32/api/cfgmgr32/nf-cfgmgr32-cm_locate_devnodew), using only `CM_LOCATE_DEVNODE_NORMAL`, and [CM_Get_DevNode_Status](https://learn.microsoft.com/en-us/windows/win32/api/cfgmgr32/nf-cfgmgr32-cm_get_devnode_status). There is no cancel-remove flag, node modification or child-device handle. Ordinary missing-node results are recorded during redirection; unknown query errors fail the observation.

The worker is launched using the pinned **base interpreter**, not the venv executable. The supervisor requires the actual query producer PID to equal its direct child PID. It waits for this process and records any timeout, termination or unconfirmed retirement as failure. The worker code starts no children. It does not start a trace, launch the control probe, retry a failed query, change security or admit another acquisition.

The 250 ms interval is a requested sleep after each complete snapshot. Actual query intervals and UTC bounds are saved; the interval is not an achieved polling period. A query crossing the eighteen-second sampling deadline fails. Partial or failed output does not qualify the ordinary-user fields as a readiness signal.

Usage:

1. Prepare the existing combined controls/image plan in a fresh `analysis/logging-batch-*` directory. Obtain its future controls context path.
2. Prepare an observer with `--prepare analysis/hub-port-observer-<fresh-name> --context <that-context> --hub-instance <freshly-mapped-root-hub> --port <port>`.
3. `--job <observer-directory>` validates only. Add `--run` to start its normal-user supervisor before launching the one-approval combined capture.
4. After both retire, independently revalidate the controls/image capture and compare complete snapshot intervals with the exact-port DSM timeline. Never classify a snapshot that crosses a phase boundary.

Twelve software cases cover process identity, source/time admission, timing and cadence, failed/slow queries, meaningful problem-code bits, direct producer matching, single use and timeout failure. An actual software-only worker run against a synthetic terminal trace refused admission, produced no hub-query sample, matched the base worker PID to the direct child and retired normally with a failure result. This proves the refusal/process path, not live sampling. A separate read-only Config Manager call returned the expected present, failed original SL3 node under the normal session.

Live phase discrimination remains unverified. `DeviceConnected`, a matching descriptor, devnode presence and problem code 39 are observations, not a selected reopen policy.

## Comparison and first attempted run

`analyse-hub-port-phases.py` revalidates the successful observer lifecycle, direct normal producer, exact collector identity, control result, topology, full state retention and matching image/PDB version evidence. It maps the actual SL3 port context, then classifies only whole snapshot intervals within the native USB header bounds and unambiguous startup-pending or port-stopped phases. At least four complete snapshots spanning 750 ms are required in each phase. A complete fingerprint repeated in both phases demonstrates ambiguity for that stateless distinction in this capture; a disjoint field is only a candidate. Host query duration is excluded as a device-state feature. Six synthetic cases pass and do not supply live evidence.

The 14:59Z attempt produced no live samples. The normal observer's ninety-second admission wait expired while Windows awaited administrator consent. Windows returned a cancelled-launch error; its status record is `launch_failed`, with no administrator wrapper PID. The waiting normal controls role also expired without starting the native device probe. Its earlier plan-only executable check does not access the device. Neither controls, image context nor source capture root was created.

The collector's existing single-use marker was consumed with an explicit `aborted-before-start` record: start time null, source/device access false and the observer failure hash. The normal validation path independently rejected late execution as `Collector plan already attempted`. Both normal PIDs were later absent, no consent prompt/native device worker remained, and the phase analyser rejected the failed observer before inspecting any supposed window. The attempt must never be reused; a future attended test needs fresh plans. No automatic relaunch was requested.

The [compact aborted-attempt evidence](evidence/hub-port-observer-aborted-20261101.json) is reproduced by `scripts/export-hub-observer-aborted.py`. The preparation, refusal/timeout tests and comparison implementation remain useful, but neither a readiness discriminator nor a new physical acquisition follows from this cancelled attempt.
