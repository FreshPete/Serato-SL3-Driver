# Post-release state candidate in the attended live stream

The saved live consumer observed a candidate DSM context reaching `StoppedEnumerated` **49.8973 ms after the control probe had finished**, followed by a roughly ten-second startup-timeout sequence. Its association with the SL3 is incomplete. This supports investigating delayed Windows startup after release, but it neither identifies a safe reopen point nor establishes a repair.

The [offline exporter](../scripts/export-attended-release-state.py) rechecks native component/three-token evidence, the original failed run, source/stream hashes, fresh offline image/PDB enumeration and all 330 DSM rows. It selects the ETW state namespace rather than the different internal state enum. [Compact evidence](evidence/attended-release-state-20261031.json). Raw context/tracking addresses remain local.

The grouping uses one shared opaque value in namespace 3000 observed under the actual worker PID. One DSM context entered under that worker with the same value and subsequently changed its device-tracking value after UCX-device creation; 158 rows belong to that context, ending in `WaitingToBeDeleted` before probe completion. A separate 97-row context began with the shared value and later showed the timeout below. Sharing a hub-associated value does not prove the same physical port. The early VID/PID/port identity events were overwritten, so the second context is explicitly a **candidate**. Collector/system PIDs in its rows are execution contexts, not proof that those processes initiated a new device operation.

| Observed point | UTC, 31 October 2026 |
| --- | --- |
| Probe completion recorded by parent | 12:05:24.7978268 |
| Candidate first `StoppedEnumerated` success | 12:05:24.8477241 |
| Candidate last observed successful entry before timer | 12:05:24.8516539 |
| `CheckIfDeviceCanBeDisabledOnDriverNotFound`, `TimerFired` | 12:05:34.8520901 |
| `DisablingDeviceInControllerOnStartTimeout` | 12:05:34.8520912 |
| `DisablingPortOnStartTimeout` | 12:05:34.8521292 |
| `Stopped`, `PortDisabled` | 12:05:34.8521459 |

The observed entry-to-timer interval is 10.0004362 seconds. The final candidate state is 10.0543191 seconds after parent-recorded probe completion. These differences use exact 100-nanosecond timestamps; no conversion from the journal's boot-relative tick counter is assumed. The native probe had already completed its acquire/getters/release and retired its ownership before the recorded completion point.

All 97 candidate rows survive only in the pinned live output. None is in the retained source XML: the 64 MiB circular file overwrote them. The later 21 retained state rows match the live consumer but belong outside this candidate sequence. Completeness of the live stream is not proved. Its positive observations can be examined; missing events cannot establish that an operation never happened.

Labels are conditional on the inspected USBHUB3 image, SHA-256 `f93fa3a32037c597fd19ca9d65f59e53a1e337123582ed2479d5c16a4848df16`, and matching public PDB. The control window's disk snapshots agree; a later [image-source rundown](attended-hub-image.md) matches its metadata. That later window does not attest the loaded image during the control test, so these labels retain the version qualification. The original end-to-end control result stays failed and no readiness admission is generated.

Verification: actual export and byte-identical regeneration pass. The exporter rejects changed inputs, unknown DSM values, ambiguous grouping, a different timeout tail or unexpected retained-file corroboration. No runtime implementation, source lifecycle, USB/audio action, registration, firmware or security setting changed. The observed interval is not a production sleep policy. Before selecting a successive-open change, preserve complete target VID/PID/port and lifecycle evidence and identify an observation or ownership design usable under actual application permissions.
