# ASIO object recreation software validation

**1 November extension:** the [explicit facade owner scope](facade-owner-scope.md) adds a separate actual-COM scenario in which all three objects share one acquisition until scope close. The original three-acquisition scenario below remains tested. The production provider is not yet switched to the shared scope; both scenarios use simulated transport.

The actual unregistered COM/IASIO DLL now passes an explicitly audited enumeration-release and recreated-object sequence with isolated simulated workers. This closes a software coverage gap exposed by the [current Serato lifetime](serato-asio-object-lifetime.md) and [reset-chain](serato-asio-reset.md) findings. It does not resolve the physical second-redirect stall. [Verified build evidence](evidence/asio-recreation-build.json).

## Added scenario

The existing retained ASIO test first initializes an enumeration object, reads channel/rate metadata and releases its last interface without audio. It then creates two successive fresh objects. Each initializes, runs setup I/O with an 80 ms hold, stops/disposes those buffers, runs another stream with freshly created buffers, then stops/disposes and releases its last interface. The hold mirrors the observed application call shape; it is not a USB-readiness delay or measured timing result.

Every stream uses 128-frame callback banks. The real vtable reaches the existing callback checks for alternating banks, logical positions, current rate and rejected callback reentry. The existing simulated copy callback remains in use. No physical audio is submitted.

A new test-DLL-only provider export selects the existing simulated worker's audit mode. After enumeration release and every subsequent initialization, stream retirement and final release, the test compares the entire audit to the expected sequence. Across these three objects it requires exactly:

- Three acquisitions and three final releases.
- Seven clock reads: one for each initialization and each audio start.
- Four ordered audio begin/end pairs.
- No implicit extra acquisition, final release at Stop, or missing release before the next object's acquisition.

The surviving factory reference prevents COM unload between objects. The pre-existing final test still releases COM/caller references during a blocked callback and checks that the independent audio module/plane lease survives until the callback returns. This is original implementation testing; Serato is not run and its timer callback is not invoked.

## Verification and preservation

Fresh full builds pass **39/39 Release and 39/39 Debug** checks, including the extended retained COM test. Test counts stay unchanged because the new scenario extends that existing test. The SDK-free 25/25 and Python 71/71 results remain preceding checkpoint evidence; those suites were not rerun for this test-only change.

The exporter checks every manifest source hash, full-suite logs, tested executables/DLLs and actual PE exports. The audit export exists in the fixture DLL and no `sl3_test_` export exists in the production DLL. At the original recreation checkpoint, all production `src/` inputs and ASIO DLL/worker/probe bytes matched the preceding controls-probe checkpoint. Later offline control selection extends two core headers; the current exporter records those exact source differences and per-binary equality instead of assuming unchanged identities. The recreation scenario is still actual unregistered-DLL testing with simulated transport, not new physical evidence.

The earlier controls and retained-probe metadata have been refreshed to the new build manifests. Original physical results remain independently pinned and are not replaced by this software audit. Transient audit files are checked inside the tests and removed afterward. New binaries, manifests and suite logs are preserved locally at `artifacts/build/checkpoints/asio-recreation-20261030`.

Reproduce:

```powershell
pwsh -NoProfile -File scripts/build-native.ps1 -Configuration Release -WithAsioComponent
pwsh -NoProfile -File scripts/build-native.ps1 -Configuration Debug -WithAsioComponent
.venv/Scripts/python.exe scripts/export-asio-recreation-build.py
```

## Remaining application gate

This proves software object ownership with simulated transport. It does not establish native USB reacquisition, dummy I/O on recreated physical objects, active SL3 backend selection, reset timing, measured latency, production deployment or current Serato/DVS. The [power/port-cycle/detachment diagnostic](usbdk-detachment.md) still needs a supervised, reviewed physical scenario before choosing a readiness change or shared transport lifetime. No device operation, UAC prompt, registration, driver/trust/policy or firmware change ran in this checkpoint.
