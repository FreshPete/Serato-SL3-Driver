# Optional ASIO activation and control-call tracing

The rebuilt COM/ASIO DLL now has optional Windows ETW begin/end metadata for selected activation and control calls. A future attended current-Serato test can use this to distinguish a driver activation failure, an unavailable `init`, later metadata/buffer negotiation and a failed start. No actual Serato call sequence has been captured. The later [private fixture capture](asio-private-trace.md) now verifies a real ETW round trip for the own unavailable-state production DLL. This feature adds observability; it does not restore admission or prove physical audio.

## Provider and bounded behavior

The original project provider is `{953df2f7-5f98-4895-a57a-73c0188c4321}`, keyword 1, information level 4. It uses the existing Windows [ETW provider APIs](https://learn.microsoft.com/en-us/windows/win32/etw/writing-manifest-based-events), with a single JSON string payload through `EventWriteString`; no system-wide manifest is installed. Registration is lazy on the selected control paths. The provider is [unregistered before module unload](https://learn.microsoft.com/en-us/windows/win32/api/evntprov/nf-evntprov-eventunregister).

When the provider-enabled check returns false, the call wrapper emits nothing, reads no QPC for the call and consumes no event budget. Provider registration/enabled queries themselves remain ordinary Windows calls. When enabled, at most 4,096 calls per module lifetime are admitted, each with a begin and one end or abandoned record: at most 8,192 records. The atomic counter saturates rather than wrapping. Unloading/reloading a DLL resets its local counters. Enabled tracing has overhead; no real-time or latency claim follows from these host timings.

`getSamplePosition`, `outputReady`, reference-count methods and audio callback processing are not instrumented. `getChannelInfo` and `future` also remain outside this selected event set. The C++ payload formatter uses a fixed 512-wide-character buffer; no audio samples, buffers, callback pointers, error-message text, paths or account/licensing material are logged. Windows ETW internals and actual delivery overhead are not benchmarked.

A tracing error or dropped backend write does not change an API return value. Existing COM/ASIO forwarding, name/identity, unavailable-state output preservation and simulated lifecycle tests still pass. The provider is runtime diagnostics in our own user-mode DLL; no kernel driver, trust entry, signing policy, vendor executable or authorization path changes.

## Payload and interpretation

Each `sl3.asio-call.v1` JSON string contains `build` (`production` or `session_fixture`), `phase`, numeric `op`, module-local ASIO `object`/`call` ordinals, raw signed `result`, integer `a0`/`a1`, starting `qpc`, `frequency` and `elapsedQpc`. Windows event headers supply process/thread/time metadata. Object zero denotes the class-object entry point. Object ordinals are newly assigned internal diagnostics, not hardware identity or pointers.

Only `phase=end` carries a completed API return value. Begin/abandoned result zero is a placeholder, not success. An abandoned record means the wrapper did not complete through its `finish` path; it is not proof that a hardware operation failed or completed. Missing records can also result from filtering, loss, session timing, the budget or process termination. A no-event result does not prove Serato never called the DLL.

| Op | Method | Result / arguments |
| --- | --- | --- |
| 1 | `DllGetClassObject` | HRESULT; object zero |
| 2 | `init` | ASIO Boolean |
| 3 / 4 / 5 | `getDriverName` / `getDriverVersion` / `getErrorMessage` | Void-completion zero / raw version / void-completion zero; no returned strings |
| 6 / 7 | `start` / `stop` | ASIO error code |
| 8 / 9 / 10 | `getChannels` / `getLatencies` / `getBufferSize` | ASIO error code; output values are not captured |
| 11 / 12 / 13 | `canSampleRate` / `getSampleRate` / `setSampleRate` | ASIO error code; rate arguments for 11/13 are the original IEEE-754 bits in signed `a0` |
| 14 / 15 | `getClockSources` / `setClockSource` | ASIO error code; selected clock index in `a0` for 15 |
| 16 | `createBuffers` | ASIO error code; requested channel count / frames in `a0` / `a1` |
| 17 / 18 | `disposeBuffers` / `controlPanel` | ASIO error code |

The starting QPC remains in both records; end elapsed ticks span the begin-record write and method body, before the end-record write. Invalid frequency cannot establish duration. Regressing counters are clamped to zero elapsed ticks; zero elapsed must therefore be treated as indeterminate rather than proof of a zero-time call. These are host control-call timings, not SL3 clock samples, callback jitter, end-to-end latency or a measured ASIO profile. Ordinals provide pairing/uniqueness, not cross-thread chronological order. A decoder must retain process and module-lifetime boundaries so IDs from a later load or fixture cannot be stitched into another session.

A later attended collector must explicitly enable this provider before activation, bound the session/output, preserve process/image identities and ETW loss metadata, and decode the string events. It must keep production/fixture records separate and report unpaired or missing intervals. The original build checkpoint did not record a trace. The later [private fixture proof](asio-private-trace.md) separately verifies actual own-process capture/decoding; Serato/cross-process and physical behavior remain unverified.

## Build verification

Release **65/65**, Debug **65/65** and the separate build without the ASIO SDK **39/39** pass. The new native test checks real Windows provider registration/unregistration without starting a session; disabled/drop behavior; exact Boolean/HRESULT forwarding; begin/end/abandoned pairing; timing failure/regression; worst-case integer formatting/truncation; eight concurrent threads making 128 uniquely paired calls; and budget saturation with no further writes. Tests inject a local backend for event inspection; those inspected records are not an ETW capture.

Both SDK-facing manifests bind 148 native source inputs plus the existing trace/launcher scripts and selected images. The build without the SDK binds 145 inputs. The build manifest records `actualEtwCaptureTested=false`, `traceSessionStarted=false` and all physical/current-Serato claims false. [Sanitized source/build/refresh evidence](evidence/asio-call-trace-20261102.json) records the exact binary identities and checks.

## Refreshed private review artifacts

The changed native source/build invalidates the earlier generated manifests. Older bundles remain preserved; validators reject them against the current source/build. Fresh artifacts are:

- `analysis/sl3-descriptor-candidate-20261102-asio-trace-final/`
- `analysis/sl3-archive-candidate-20261102-asio-trace-final/`
- `analysis/sl3-archive-deployment-20261102-asio-trace-final/`

The descriptor XML and archive bytes remain identical to their original hypothesis. New manifests bind the new DLL/build/source identities. No descriptor field, control hypothesis, revision, hardware identity or authorization was changed for tracing. The private archives contain vendor resources and are not published.

The deployment preparer now accepts explicit descriptor/archive bundles, avoiding implicit reuse of an older manifest:

```powershell
.venv/Scripts/python.exe scripts/prepare-serato-archive-deployment.py `
  --descriptor analysis/sl3-descriptor-candidate-20261102-asio-trace-final `
  --archive analysis/sl3-archive-candidate-20261102-asio-trace-final `
  --validate analysis/sl3-archive-deployment-20261102-asio-trace-final

# Read-only default action; no UAC, application execution or replacement.
pwsh -NoProfile -File analysis/sl3-archive-deployment-20261102-asio-trace-final/archive-test.ps1
```

The seven actual refresh/preflight cases cover descriptor/archive/deployment validation, old descriptor/deployment refusal, the new read-only wrapper Plan and no-overwrite refusal. They preserve the original installed executable/archive. The refreshed package still does not install the ASIO driver or provide a measured native profile; the earlier ASIO deployment bundle remains a separate historical artifact. Protected install/rollback, actual current-Serato ETW capture, stable device reopening, measured physical timing/mapping/levels and real current Serato/two-deck DVS remain required. Mac is deferred.

The conditional selection exporter also accepts `--candidate` for a refreshed bundle and records its manifest hash. The current explicit candidate projection was revalidated without a new USB observation or application call; its static identity/default conclusions remain unchanged.
