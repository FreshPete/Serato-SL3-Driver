# Offline ASIO restart exercise

The standalone host passed 64 start/stop cycles across 16 recreated ASIO objects using the existing unregistered test DLL and simulated retained worker. It observed 144,280 callbacks. Callback bank alternation and sample positions matched throughout; callbacks stopped before buffer disposal, and repeated Stop succeeded. The complete worker audit exactly matched one acquire/release per object and four balanced begin/end pairs per object. Process handles sampled before and after were 136 and 123, within the four-handle warm-up allowance. [Hashed evidence](evidence/asio-restart-endurance-20261105.json)

This exercises the actual COM/ASIO implementation with a test provider, not a Python model of its state machine. The fixture streams as quickly as it can; callback count is not elapsed audio time. Its 48 kHz metadata and synthetic latency are not physical SL3 measurements. The test does not establish sustained real-time operation, physical reopen reliability, Serato behaviour, or the cause of the attended session's shutdown failure.

The [host source](../tests/native/asio_restart_endurance.cpp) admits the test DLL and simulated worker filenames and requires the test-only provider export, with the registration export absent. It loads no registered driver. Six input/output channels use packed 24-bit banks with 64, 128 and 256-frame sizes. Every cycle requires callback progress within three seconds and checks callback quiescence after Stop. The worker binary is hash-bound through the test provider. The saved evidence pins the exact binaries, linked library, host source and full audit used in this run.

Build separately against an existing Release native build and the locally acquired ASIO SDK; the production build and prepared session sources are unchanged:

```powershell
cmake -S tests/asio-endurance -B artifacts/build/asio-endurance `
  -G 'Visual Studio 16 2019' -A x64 -DCMAKE_SYSTEM_VERSION=10.0.19041.0 `
  '-DSL3_EXISTING_BUILD=ABSOLUTE_EXISTING_NATIVE_BUILD_DIRECTORY' `
  '-DSL3_ASIO_COMMON=ABSOLUTE_LOCAL_ASIO_SDK_COMMON_DIRECTORY'
cmake --build artifacts/build/asio-endurance --config Release
```

Run `sl3_asio_restart_endurance.exe` with the absolute paths to that native build's `sl3_asio_session_fixture.dll`, `sl3_device_session_fixture.exe`, and a fresh audit-file destination. Preserve the audit and exit status. No administrator prompt, Serato launch, device acquisition, firmware command, registry registration or security-policy change is needed.

The next attended test remains the prepared temporary Serato startup followed by a manual application close, with the startup tracer fully detached. The restart exercise does not replace it.
