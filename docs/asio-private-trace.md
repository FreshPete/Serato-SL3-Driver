# Real private ETW capture without an administrator prompt

This records the earlier external-controller checkpoint. The subsequent [DLL-owned opt-in checkpoint](asio-owned-trace.md) changes the native image and diagnostic sources; its new source-bound captures supersede this checkpoint for the current build. The earlier evidence remains preserved in its capsule.

The logging pipeline now has an actual Windows round trip: the Release and Debug production ASIO DLLs each emitted **16 ETW events**, decoded into **eight complete begin/end pairs**, under an ordinary user token. Both sessions stopped with zero reported losses and both child processes exited. These are first-party unavailable-state fixtures; no Serato session or physical audio/device operation ran. [Sanitized evidence](evidence/asio-private-trace-20261102.json).

Microsoft documents [low-privilege private sessions in processes the user started](https://learn.microsoft.com/en-us/windows/win32/etw/configuring-and-starting-a-private-logger-session). This diagnostic uses `PRIVATE_LOGGER_MODE | PRIVATE_IN_PROC`, enabling only our provider in its own process. That closes the original capture/decoding gap for this scope. It does not provide cross-process access to Serato or a kernel/UsbDk WPP trace, and no group membership, elevation, security policy or signing setting changes.

## Exact fixture scope

The runner verifies the current native build/source/image hashes and the independent diagnostic's build/source hashes, copies the exact production DLL into a fresh isolated folder and confirms that it contains no ASIO configuration. The native fixture refuses configuration beside that DLL, requires a non-elevated token and loads only the copied DLL. It makes these calls through the actual COM/ASIO interface:

| Method | Observed result |
| --- | --- |
| `DllGetClassObject` | S_OK |
| `getDriverName` | Expected project name; void completion |
| `getDriverVersion` | 1 |
| `init` | false, as required without configuration |
| `getChannels`, `getBufferSize`, `getSampleRate` | ASE_NotPresent (-1000), caller output sentinels unchanged |
| `getErrorMessage` | Void completion; text is not logged |

It performs no createBuffers/start, rate/control write or firmware operation. Objects release fully and `DllCanUnloadNow` reports S_OK. The DLL unregisters/unloads before the completed ETL is read. The logger has a 4 MB sequential-file limit; decoding bounds its file read to 8 MB and payload strings to 1,024 bytes. The parent bounds the entire child to 20 seconds, preserves failures and confirms retirement. No automatic UAC, application launch or retry is present.

The Windows reader checks the exact provider GUID, current child PID, string-only event flag, bounded terminated UTF-16 payload and ASCII JSON shape before writing records. `ProcessTrace` consumes the completed file, not an active real-time session. Both session and file-reader loss counters must be zero. The Python validator checks exact envelope/payload fields, PID/thread identity, eight expected operations, ordered begin/end IDs, return values, timing-field consistency and lifecycle/source/image/raw-ETL hashes.

The public summary omits raw host metadata. ETLs, copied DLLs and detailed run records remain under ignored local test paths; raw ETL headers can include machine/path information. No vendor resources or private SDK contents are published.

## Build and reproduce

This is an independent Windows x64 diagnostic project under `diagnostics/asio-trace`. It uses the already reviewed local ASIO interface headers and Windows SDK. It does not modify/rebuild the production audio targets or change their manifests. The earlier 65/65 Release, 65/65 Debug and 39/39 SDK-free results remain their original build evidence; their capture flag describes that original test scope. This separate report supplies the later actual private-capture result.

```powershell
pwsh -NoProfile -File scripts/build-asio-private-trace.ps1 -Configuration Release
pwsh -NoProfile -File scripts/build-asio-private-trace.ps1 -Configuration Debug

# Requires a fresh result directory; uses own isolated DLL and ordinary token.
.venv/Scripts/python.exe scripts/test-asio-private-trace.py --configuration Release `
  --output tests/results/local/asio-private-trace-NAME

# Saved-evidence validation only: no logger, application or device call.
.venv/Scripts/python.exe scripts/validate-asio-private-trace.py `
  tests/results/local/asio-private-trace-20261102-release-retired
```

The current verified results are `asio-private-trace-20261102-release-retired` and `asio-private-trace-20261102-debug-retired`, each with the raw ETL, decoded JSONL, child/source/image record and validation. Earlier development fixtures stay preserved. The native executable defaults to `--plan`; explicit `--capture` is required for the fixture. Its two plan/refusal checks pass in both build configurations.

Six synthetic validator tests reject incomplete/lost events, wrong scope/build/PID/thread/operation, missing or abandoned terminals, altered expected results, Boolean numbers, duplicate/nonfinite JSON, extra fields and clock/time inconsistencies. The pure row validator explicitly leaves actual capture/physical claims false. Only the complete saved run, current source/images, raw ETL pins and producer lifecycle can qualify the first-party capture scope.

Nine additional checks reject missing/changed ETL, changed isolated DLL, extra configuration, an unretired child, a false device scope, changed API results, native output reuse and native activation with a configuration present. The last native guard rejects before loading the DLL. These fault copies do not alter the real captured evidence; no unknown witness or existing capture is overwritten.

## Remaining gates

This confirms the [ASIO call event provider](asio-call-tracing.md) can emit and decode real Windows records. It does not establish Serato loading or selecting the driver, current admission/licensing/control behavior, protected installation, measured timing/profile, stable reopening, physical mapping/levels/latency or actual two-deck DVS. The current [reviewed resource bundle](serato-archive-deployment.md) stays undeployed and source-current. Windows security and installed Serato bytes remain unchanged; Mac remains deferred.
