# Attended logging-only result, 1 November

The one-approval launcher executed successfully under an elevated token and retained the diagnostic's failed result. The source test rejected a real difference between the configured and native session GUIDs, then stopped/deleted its collector and independently observed the session absent. No SL3/audio operation ran. This is useful diagnostic evidence, not a passing source-identity or timer test.

| Observation | Actual result |
| --- | --- |
| Requested collector GUID | `0fd7db65-c030-4a1b-a8de-bd83243b72f0` |
| Fresh committed-service readback | Configuration matched; stopped status before Start; XML retained the requested GUID. |
| Native query GUID | `902aa381-e9ba-452f-b3b1-28929ff30b6f` |
| Native name and file | Matched the private requested session name and its exact `images.etl` path. |
| Native mode/clock | `0x02800000`, QPC clock type 1, flush timer 1. |
| Native maximum file size | 0 MiB, meaning no native hard cap was observed. |
| Sampled loss counters | All three were zero at the captured live query; final loss/completeness was not established. |
| Cleanup | Supervisor requested stop; collector deletion succeeded; independent query returned 4201/absent. |
| Saved ETL | 11,599,872 bytes, SHA `271f53b4f125656f280815ea40d136fd3e3cac2d042c40ae88a50d1100d12276`. |
| Process retirement | The recorded launcher, batch, action and query PIDs were absent in the later process inventory. |

The installed SDK names mode bit `0x00800000` as `EVENT_TRACE_PERSIST_ON_HYBRID_SHUTDOWN`; `0x02000000` is the system-logger bit. These observed session flags are not a change to Secure Boot or code-integrity policy. The logging code requested no USB, firmware, binding, driver, account or security change. A read-only inventory before the attempt still reported the original SL3 driver at code 39.

The GUID difference is now captured rather than lost. It is consistent with the [inspected PLA GUID-generation path](pla-source-properties.md), but the generating function was not traced. Only one native live GUID observation was taken before rejection and cleanup. It does not establish stable native identity over the session or recover the discarded GUID from 31 October.

The [compact evidence](evidence/attended-logging-20261101.json) verifies the exact plan/run/rejected-query hashes, frozen runtime, elevated batch admission, accepted committed readback, private name/output, cleanup and ETL. Original failed records remain unchanged under `tests/results/local/logging-batch-20261101-ready-1`. Actual runtime scripts and evidence are frozen locally under `artifacts/build/checkpoints/attended-logging-20261101`. Reproduce the read-only checks with `.venv/Scripts/python.exe scripts/export-attended-logging-20261101.py`.

The next diagnostic should separate configured collector identity from observed native session identity. It needs the prior absence and committed-owner checks, the exact private name/output, then a second independent query against the observed native GUID and stability checks thereafter. The rejected first query must remain diagnostic evidence. No such acceptance-policy change is selected by this report. Independent duration expiry, file-limit enforcement, same-window image qualification and safe SL3 reacquisition remain open.
