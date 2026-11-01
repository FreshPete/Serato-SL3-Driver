# Both logging durations pass, 1 November

The explicit observed/rechecked identity diagnostic passed real five- and ten-second logging jobs under **one administrator launch**. Both retained the first GUID-mismatch query as rejected evidence, independently rechecked the observed native GUID, and kept that GUID in every accepted live sample. Each source disappeared before cleanup needed to request a stop. Both persisted collectors were deleted and independent after-queries reported absence. No SL3/audio operation ran.

| Result | Five-second job | Ten-second job |
| --- | --- | --- |
| Native GUID | `a7fee275-7ec3-4a51-8783-2d2399466015` | `d8286ed2-c9b2-47a9-8630-9bb9324aed12` |
| Accepted live samples | 5 | 10 |
| Saved ETL window | 5.3512566 s | 10.3379520 s |
| ETL bytes | 14,876,672 | 17,104,896 |
| Decoded events | 48,858 | 50,332 |
| Consistent kernel rundown pairs | 259 | 259 |
| USBHUB3 metadata agrees with disk | Yes | Yes |
| Supervisor stop requested | No | No |
| After-query absent / collector deleted | Yes / Yes | Yes / Yes |

Each live query falls inside its own saved image-trace window. USBHUB3 metadata agrees with disk SHA `f93fa3a32037c597fd19ca9d65f59e53a1e337123582ed2479d5c16a4848df16`: image size 733184, timestamp 180548141 and checksum 781464. This is metadata agreement in these two windows, not a loaded-memory hash, PDB-memory identity or qualification of an earlier/future USB test.

Reported loss counters were zero. Tracerpt also warned that some events did not match a schema. The strict image inspector accepted the known image payloads and checked all kernel rundown pairs; it does not prove every event decoded. The complete inspector reports and ETLs remain local.

Observed disappearance is consistent with the requested durations, but the Windows timer's causal path was not traced. `independentTimedExpiryCauseVerified` remains false. The native maximum file size was zero, so no hard cap is claimed. No retry/reset policy or USB-readiness admission follows from these results.

The elevated child exited with code zero. A later inventory found no matching recorded runtime instance: one PID had been reused by an unrelated process, distinguished by its later creation time. That unrelated process was left untouched. No persistent elevated broker, service or scheduled task was created.

The [compact evidence](evidence/native-guid-live-20261101.json) validates anchored plan/run hashes, frozen scripts, committed owner, rejected/strict-query separation, GUID stability, name/output/properties, source disappearance, cleanup, ETL/decoder/image provenance and exact query/window times. Regenerate with `.venv/Scripts/python.exe scripts/export-native-guid-live-20261101.py`. The local snapshot at `artifacts/build/checkpoints/observed-native-guid-live-20261101` preserves the actual runtime, both job records/ETLs, inspector reports and comparison inputs. The [earlier configured-GUID failure](attended-logging-20261101.md) remains failed and unchanged.

This establishes a useful logging foundation. The next hardware work still needs a trace encompassing the actual SL3 operation, the corrected sequential USB trace, independently matched physical-device identity and recovery evidence. Safe successive acquisition, physical audio/timing, current Serato admission and two-deck DVS remain incomplete.
