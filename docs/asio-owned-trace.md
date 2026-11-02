# Opt-in logging owned by the ASIO DLL

The production ASIO DLL can now start its own private in-process ETW session when the host process explicitly sets `SL3_ASIO_PRIVATE_TRACE=1`. It remains off by default. Release and Debug each captured 16 real events/eight complete call pairs under an ordinary user token, with no reported loss. These isolated tests used an unavailable, unconfigured copy of our DLL; they opened neither Serato nor the SL3. [Checkpoint evidence](evidence/asio-owned-trace-20261102.json).

This removes the separate administrator logger from the proposed ASIO-metadata capture path. It does not remove approval requirements for protected installation or kernel/USB tracing. Current Serato loading this DLL and producing these logs remains an attended test, as do archive acceptance, working audio and DVS.

## Ownership and limits

A successful session belongs to shared factory/device leases. Releasing a factory before its device does not stop it. The last lease stops and flushes the session before the COM object lease permits module unload. A temporary activation lease also covers unsuccessful class-object requests. No controller is started or stopped by our `DllMain`; audio callbacks do not acquire sessions. The static manager owns only a weak pointer. Final object release can perform logging cleanup and is not a real-time operation.

The controller requires a non-elevated token and an existing absolute local fixed-drive `LOCALAPPDATA`. Existing path ancestors must be directories without reparse points. It creates a unique run directory below `SL3Rebuild/AsioTraces`, with a protected user/System DACL. Existing parent ACLs are not rewritten. ETL headers can contain host metadata; keep these logs private. The log payload contains selected ASIO method metadata, not audio or account data.

Each sequential session has a 4 MB file limit and at most four session-creation attempts per loaded module. The existing 4,096-call/8,192-record module budget also remains. Reloading a module resets its budgets; no retention policy or total-disk limit across launches is implemented. Creating a logger can fail without changing ASIO results. The marker uses create-new semantics and records the stop status and loss counters, with `hardwareStateAssessed=false`; an absent marker or nonzero status/loss means incomplete evidence. Abrupt host termination can leave an incomplete log. The fixture bounds its child to 20 seconds; that is not a timeout guarantee for ETW calls inside an arbitrary host.

The controller follows Microsoft's [private-session guidance](https://learn.microsoft.com/en-us/windows/win32/etw/configuring-and-starting-a-private-logger-session). It does not install an ETW manifest, change security policy or create a persistent service.

## Verification and reproduction

Build the native ASIO target and independent diagnostic with their existing build scripts, using Release or Debug consistently. With the reviewed local SDK already available:

```powershell
pwsh -NoProfile -File scripts/build-native.ps1 -Configuration Release -WithAsioComponent
pwsh -NoProfile -File scripts/build-asio-private-trace.ps1 -Configuration Release
python scripts/test-asio-private-trace.py --driver-owned --configuration Release --output tests/results/local/asio-private-trace-NEW-owned
python scripts/test-asio-owned-fallback.py --configuration Release --output tests/results/local/asio-private-trace-NEW-fallback
```

Outputs must be fresh direct children of the local results directory. The runner changes only its child environment. It copies the exact source-pinned production DLL into a directory containing no configuration, checks unavailable-state ASIO results and output sentinels, releases the factory before device calls, then checks final release, `DllCanUnloadNow` and actual DLL unmapping. It decodes the stopped ETL, validates the exact eight API results and binds the raw files, executable/DLL, build manifests and producer sources. Neither configuration can start a hardware worker in this fixture.

Both configurations passed default-off and missing-log-directory fallback tests, preserving ordinary results and full unload without creating a trace directory. The external-controller Release capture still passes. Seven validator model tests pass, and five altered real-run stop markers are rejected even after updating their file digests. Native Release/Debug tests pass 65/65 each; SDK-free tests pass 39/39. These checks cover ordinary object retirement and one missing-directory failure; elevated-host refusal, concurrent real host activation, four-attempt exhaustion and abrupt host termination have not been exercised end to end.

The earlier [external private-capture checkpoint](asio-private-trace.md) remains historical evidence in its capsule. Current source changes require new build/capture manifests; old source-bound results do not validate against this image. The refreshed descriptor/archive/deployment bundles use the `20261102-owned-trace` suffix. Their XML/archive hypothesis bytes are unchanged and remain private and undeployed.

Next attended work remains safe recovery/reacquisition verification, then the reviewed read-only control/port trace. A later approved current-Serato session can opt in to these logs to establish which ASIO methods it actually calls. No claim of host admission, measured latency, analogue channel mapping or two-deck DVS follows from this checkpoint.

The later [general read-only decoder and analyzer](asio-general-trace-analysis.md) can inspect completed logs without requiring the fixed eight-call fixture sequence. It reports incomplete pairs and raw method outcomes while keeping source-host identity, Serato admission and physical audio/DVS unverified.
