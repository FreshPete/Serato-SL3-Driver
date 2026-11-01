# Bounded native metadata scope diagnostic

`sl3_scope_probe.exe` is prepared for one native acquisition followed by three separate `DriverFacade` metadata lifetimes and one final release. It exercises the shared C++ owner and fresh clock path without requiring a measured audio timing profile. It does **not** load the ASIO COM DLL, run Serato or exercise audio buffers. Actual COM/module lifetime has separate simulated-worker coverage.

The probe defaults to a JSON plan. Native `--run` requires explicit absolute worker/helper/output paths, a lowercase worker SHA-256, a fresh output directory and an ordinary user token. It verifies the worker and the pinned reviewed UsbDk helper bytes before creating evidence or launching a worker. The isolated native worker independently checks its helper and signed driver as before. Native builds reject the simulated fixture option.

The first facade acquires and reads its clock. Each successor uses a fresh read-only getter on that held connection. All three inspect six input/six output channel declarations, packed-24 type and inactive-channel state. Latency queries must remain unavailable and preserve caller outputs; zero extra frames in the diagnostic constructor are never exported as measured latency. No buffer creation, Start, rate setter or firmware method is called. A clock change during this bounded experiment is retained in the completed metadata rows and fails the diagnostic rather than being hidden.

Progress is flushed before each object and final close. The final record distinguishes successful objects, attempted objects, failure phase, cleanup and forced termination. After filesystem/identity preflight, a process-wide 20-second watchdog covers the device phase through final destruction. The supervising runner must separately bound the whole child, including preflight. Timeout/process containment is a failed experiment; it is not evidence of immediate native I/O recovery. The parent must retain the last progress record and perform its normal trace/recovery checks.

`validate-scope-host-probe.py` checks the recorded no-audio/metadata/final-retirement contract. For a native result it additionally requires exactly one complete worker journal, one acquisition, three ordered clock getter pairs and one final release, with no audio stages. This is recorded consistency, not hardware attestation, calibration, COM integration or reopen readiness. A simulated result cannot contain a native journal.

The new actual-CLI test runs the separately compiled simulated probe, requiring audit `acquire, rate, rate, rate, release`. It checks failed acquisition and failed second getter, exact cleanup, output-reuse/identity/option guards and strict synthetic journal rejection. Native cases stop at plan or pre-device input/helper/token refusal. The complete Release build passes **50/50** checks, including the preceding 48 and the new plan/lifecycle entries. [Exact tested sources and binaries](evidence/facade-scope-build-20261101.json).

Plan only:

```powershell
./artifacts/build/native/Release/sl3_scope_probe.exe --plan
```

The physical branch has not run. The next attended launch still requires adapting the trace wrapper to this scenario, pinning fresh plans and current PnP hub/port state, and recording selected recovery/security before and after. It must preserve the release window and remain one acquisition. Existing controls-only wrapper validation must not be reused as a scope pass. No prompt, SL3 open, audio, installation, registration or security change was performed during preparation.

The full build, sources, test/validator and plan/preflight records are preserved under `artifacts/build/checkpoints/metadata-scope-probe-20261101`; the preceding clock-refresh build remains separately archived. Controlled analogue audio, measured latency, current Serato admission, real DVS and macOS remain incomplete.

## Trace integration in progress

The latest source adds `-Scenario Scope -TraceSeconds 60` to `test-controls-user-probe.ps1`, separate scope validation, current build/source pins, direct token evidence and a whole-child 30-second deadline. `prepare-scope-trace.py` prepares a fixed single-use plan; `start-scope-trace.ps1` defaults to inspection and reserves its explicit run path for one administrator collector launch. No persistent elevated broker is installed. These changes have not been exercised as an elevated or physical experiment. They collect USB/WPP/state evidence; they do not qualify the separate kernel-image capture window. Do not treat a controls-only or simulated result as a native scope pass.
