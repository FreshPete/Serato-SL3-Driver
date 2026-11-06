# Shutdown grace and marker-free ASIO inspection

The supervisor's exit grace is now 20 seconds, replacing eight seconds. It records `process.closeGraceSeconds` and the actual `closeWaitSeconds` when it requests a close. The five-second termination wait, viewing limit, protected-stage limit and hard process watchdog are unchanged. A viewing-limit exit still does not count as deliberate clean session completion. [Checkpoint evidence](evidence/asio-shutdown-evidence-20261106.json)

## Why extend the grace

`BrokerSession::stop()` and `close()` each cap their own operation at five seconds. A host may call ASIO stop and then release its driver/session. Eight seconds was shorter than the sum of those independent budgets. This is a code-based candidate mismatch, not a measurement of Serato's shutdown or proof of its root cause. Logging finalization and host confirmation dialogs introduce further uncertainty; 20 seconds is still a bounded diagnostic choice, not a universal shutdown guarantee.

The real owned-process regression now includes a child that deliberately exits about twelve seconds after its exit signal. The default grace allows that exit without forced termination and records a wait above eight but below twenty seconds. The test uses a headless Python child and synthetic startup events, not Serato or an audio driver. Separate one-second fixture overrides still exercise forced termination and failed window enumeration. Production startup uses the 20-second default; the constructor refuses non-integer or out-of-range values.

## Inspecting a log without a completion marker

`scripts/inspect-incomplete-asio-call-log.py` adds a separate read-only path:

```text
python scripts/inspect-incomplete-asio-call-log.py --etl CLOSED_ETL --expected-pid OBSERVED_PID --output NEW_OUTPUT_DIRECTORY
```

It uses the existing source/image-bound native decoder and the same strict record/pair validator as completed-log analysis. It never starts or flushes a logger, controls the host, edits an ETL or writes a session marker. The decoder refuses a writer-held input. Source/input hashes and decoder outcomes are preserved; failed decoding leaves no final analysis report.

The report has a distinct `sl3.asio-incomplete-call-analysis.v1` schema. Logger stop status and event/buffer losses are unknown (`null`); `sessionMetadataComplete`, `shutdownVerified`, host identity and physical validation remain false. Reader-reported zero losses are kept separate from unknown logger counters. Even fully paired observed calls cannot become a completed session. Missing terminal records identify an observation gap, not a proven blocked method or deadlock.

Microsoft describes [buffer flushing at fullness, timer expiry or session stop](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/nf-evntrace-controltracea). The presence of an ETL therefore does not by itself establish that all relevant events reached disk. This tool does not repair truncated files or relax native decoding failures.

## Actual saved-data results

The exact packaged-DLL completed fixture still yields sixteen events/eight pairs; completed and marker-free analysis produce identical method/pair observations. The marker-free view keeps session state unknown even for that valid completed fixture.

One older markerless 16 KB ETL was readable but contained zero recoverable provider records. It cannot identify a shutdown failure, prove that ASIO was unused or establish why its marker is absent. Its supplied PID does not independently prove the host identity. Original evidence hashes stayed unchanged.

Five new model cases and nine existing completed-analysis cases passed. Six actual native-reader cases cover the completed fixture, markerless input, wrong PID, a write-access-held input, output preservation and corrupt input. Sixteen supervisor cases passed, including the delayed exit above. Fresh launcher/session/kit bindings were regenerated for the changed supervisor. No audio binaries changed, and no Serato launch, device access or administrator prompt occurred.

With current status/result/window/plan checks and actual kit, Stop and fresh-preparation regressions, this checkpoint passed 95 targeted cases. The post-fixture read-only status check found the original setup clean. Live startup and real Serato post-playback close with the new grace remain untested.

The next attended run should use a fresh trace-enabled session, stop playback and close Serato before the viewing limit. Correlate the actual driver calls, close observations and broker retirement. The real Serato shutdown result remains unverified.
