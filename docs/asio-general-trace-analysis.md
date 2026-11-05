# Read-only ASIO log decoding and call analysis

The project can now decode a completed own-provider ETL and analyze a selected-call sequence that differs from the eight-call unavailable-state fixture. This is the missing reader for a future opted-in Serato session. The tool does not start a logger, load an ASIO DLL, run Serato or access the SL3. [Sanitized evidence](evidence/asio-general-trace-20261102.json).

The standalone Windows x64 decoder builds with the Windows SDK and our provider header; it does not use the private ASIO SDK. Release and Debug each decoded an archived production-DLL fixture into JSONL **byte-for-byte identical** to its original decoder output. Nine model tests cover arbitrary ordering and failure/incompleteness cases. Four actual native refusal checks preserve the input and an existing output. These are offline results, not a new Serato or hardware capture.

## Build and use

```powershell
pwsh -NoProfile -File scripts/build-asio-trace-decoder.ps1 -Configuration Release
python scripts/analyse-asio-call-log.py --configuration Release `
  --etl C:/path/to/completed/private.etl `
  --session C:/path/to/completed/session.json `
  --output tests/results/local/asio-decoded-trace-NEW
```

The session marker comes from the [opt-in DLL-owned logger](asio-owned-trace.md). Select a completed log and a fresh output directory; the analyzer never closes or flushes a running host's session. It validates the decoder's build/source/image pins, parses the marker, hashes inputs, runs its own read-only decoder child with a 20-second limit, confirms retirement and rechecks inputs/tool/sources. Timeout cleanup kills only that decoder child, never Serato. The standalone decoder defaults to an inert `--plan`; its explicit `--decode COMPLETED_ETL NEW_JSONL EXPECTED_PID` mode can also be used directly.

For the attended installer diagnostic, pass `--expected-pid` with the PID from that run's `selection-events.json`. The analyzer rejects a session marker for a different process before creating output and includes the matched PID in its report. Use the module-load event from the same observer alongside the resulting `class_object` and `init` calls. The PID check helps avoid mixing logs across runs. It does not authenticate the host or establish hardware streaming. The exact installer DLL's isolated capture passed this check with eight complete call pairs, including `init` returning false. An intentionally different PID was refused without writing output.

To view those results alongside Serato's installer timeline, pass the generated `analysis.json` to `scripts/summarize-serato-installer-trace.py selection-events.json --call-analysis analysis.json`. The optional report requires a decoded production log, a matching PID and an observed rebuilt-module load. When the observer provides creation and exit times from the actual process handle, the report also requires every decoded event to fall within that lifetime. Older traces without a process lifetime retain PID-only matching and are marked accordingly. The integration was checked with the actual decoded fixture and a synthetic module-load record. A workspace launch captured its process lifetime and the join rejected timestamps from the older fixture even when the test supplied the same PID. The attended Serato capture remains pending.

The native reader checks the provider GUID and stored event PID, string-only event type, terminated bounded UTF-16/ASCII JSON payload, ETL size up to 8 MB and at most 8,192 selected records. It holds a read-only file handle that excludes writes/deletion while reading and uses Windows OpenTrace/ProcessTrace to consume the file. File-reader losses or decode errors fail the command. Output files use create-new semantics; a failed attempt can leave partial output for review. Parent/path substitution is not an independently tested security boundary.

The wrapper preserves `events.jsonl`, decoder stdout/stderr, a source/image/input-hash journal and `analysis.json`. Paths, timestamps, PIDs/thread IDs and raw ETL headers can disclose host metadata; retain these privately. A marker with failed stop/loss counters is represented as incomplete evidence when its fields are internally consistent; contradictory fields are refused. Reader success never overrides those session counters.

## What the report means

The analyzer pairs by module-local call ordinal, checking thread, method, object, arguments and clock identity. Calls from different threads may interleave. It reports method/result counts, matched terminal records, orphan terminals, unterminated begins, abandoned calls, interior ordinal gaps and whether ordinal 4,096 was reached. A paired negative ASIO/HRESULT or false `init` is recorded as a returned error; version/void completion values keep their separate domains. A reported API error is a valid observation, not a parser failure.

`observedPairsComplete` describes pairing within the supplied records. `sessionMetadataComplete` separately describes the stop status and reported losses. Neither proves that every host call was logged: only selected methods are instrumented, the module budget can expire, recording may start after earlier calls, and logs cannot reveal a missing tail. `wholeHostSequenceVerified` remains false. Duplicate terminals/IDs, mixed production/fixture ordinals, malformed shapes, Boolean numbers, bounds violations and inconsistent paired identities are refused. One module ordinal stream is assumed; ambiguous multiple-module captures need separate handling.

QPC/frequency/elapsed fields describe host calls. Zero clock/frequency/elapsed is indeterminate; no field becomes physical audio or round-trip latency. Provider GUID, PID and payload build label are not authentication of a host or loaded module. The generic report therefore leaves source-host identity, actual Serato capture, current SL3 admission, physical audio and DVS unverified even after successful ETL decoding. A later real Serato test needs independent host/module provenance and its own functional observations.

## Verification scope

The nine model tests exercise interleaved threads and returned errors, orphan/missing/abandoned calls, empty/budget-limited logs, failed stop/loss metadata, duplicate/mixed/mismatched pairs, exact types/field bounds, zero timing, result-domain distinctions and marker claims. Models cannot set `actualEtwCaptureDecoded=true`; the wrapper requires the real retired decoder and source/image/raw-input provenance before doing so.

The actual native negative cases are wrong event PID, invalid PID syntax, corrupt ETL and attempted output overwrite. Each decoder process exited with an error; the archived ETL and preexisting output sentinel stayed unchanged. Both build configurations also pass their two plan/refusal CTests. Run the model checks with `python -m unittest discover -s tests -p test_asio_call_analysis.py`.

Production audio/native source, build manifests and DLL images are unchanged from the [DLL-owned logging checkpoint](asio-owned-trace.md); their earlier 65/65 Release, 65/65 Debug and 39/39 SDK-free results are not rerun or expanded by this independent decoder project. No current archive, ASIO deployment, binding/trust/security policy or firmware change ran. The next attended recovery/readiness test, measured audio, actual Serato execution and genuine two-deck DVS remain outstanding; Mac is deferred.
