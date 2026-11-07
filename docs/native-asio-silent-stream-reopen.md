# Native on-demand streaming passes; post-stream reopening fails

The [application-bound follow-up](#application-bound-physical-rehearsal) prepares two opens on one connection. The earlier test below released the connection between opens.

6 November 2026: the exact production ASIO DLL completed a three-second physical silent-duplex stream through its new lazy activation path. A subsequent control-only reopen failed at `redirect_start.enter`, before any clock read. Hardware testing stopped there. This is **not** a reliable-reopen or ready-to-install result.

**Timing follow-up:** the successful control-only reopen used a 16.922-second gap; the failed post-stream acquisition used 9.406 seconds. The [journal comparison](native-reopen-cadence.md) preserves this confound. Streaming is not isolated as the cause, and neither interval is a validated readiness delay.

## Observations

| Probe | Observed result |
| --- | --- |
| Earlier two control-only initializations | Both passed, with no power cycle between them. [Separate checkpoint](native-asio-control-reopen.md) |
| New silent-duplex host | Six input and six output channels, 44.1 kHz, packed 24-bit little-endian, 128-frame buffers; 1,029 completed callbacks over three seconds. |
| Input peaks, channels 1–6 | 25,464; 28,887; 2,829,290; 2,668,337; 2,619,994; 2,803,165, on the signed 24-bit magnitude scale. This establishes input activity, not Phase decoding or calibration. |
| Silent output | Both output buffer banks were zeroed before start and every callback cleared all six output channels. No tone, music or captured input was copied to output. Physical DAC silence was not independently measured. |
| Stream shutdown | Stop, buffer disposal and object release returned successfully. Exact retained controller and worker handles signaled; the native retirement report was successful with I/O retired, helper ownership released and job empty, without forced termination. |
| Follow-up control-only reopen | ASIO init returned false. The worker journal ended at `redirect_start.enter`; no return, system handle, clock getter or published ready record followed. |
| Failed acquisition cleanup | Controller result: `worker_control_channel`, phase 4, `terminationRequested=true`, `snapshotValid=false`, `processExited=false`, `jobEmpty=true`. I/O retirement and device release were **not verified** for this attempt. |
| Later read-only observation | Neither recorded PID was present. This is a later point-in-time observation, not proof of when those exact processes exited or that USB is ready. Windows still enumerated Rane SL3 under its original MEDIA error binding. |

The successful stream report retained `lastNativeError=1168` alongside no stream/device/owner failure. That raw value is preserved; it is not attributed as the cause of the later redirect stall. The successful stream report's `usbReadyForNextAcquire` and `rateRestorationVerified` remained false.

## What changed in the diagnostic

`diagnostics/asio-native-silent-duplex` is a separate, hash-bound production COM host. Default/plan and unknown-option build checks are inert. Only its explicit silent-duplex operation calls the physical driver. The observer retains exact controller/worker identities after init and before allowing the host to create buffers/start. The stream is bounded to three seconds, then stops, disposes and releases. No fixture-provider export, registry installation, Serato, elevated action, sample-rate write or firmware operation is involved.

The shared runner now supports this explicit separate host/profile while keeping its control-only CLI control-only. Failure leaves raw stdout/stderr and native journal identities intact. `inspect-native-activation-failure.py` adds a read-only, exact-result/bundle-bound view of the completed probe's native records and process metadata. It rejects altered result or journal bytes and makes no device call or termination request. A PID without a retained creation identity is explicitly weaker evidence; an absent PID is not relabelled as a verified historical exit.

Two silent-host build checks, three inert wrapper plans, an actual altered-result refusal and the real failure observation passed. The observer's live-process branch is not claimed covered by that later observation; both recorded PIDs were absent by then. The old control-only evidence keeps its historical shared-runner source hash rather than being rewritten to claim execution of the newer version.

## Interpretation and next test

This reproduces the boundary already described in [UsbDk detachment](usbdk-detachment.md): accepted helper close and process retirement do not attest Windows re-enumeration or the next StartRedirect. The new journal establishes the external call boundary, not the exact internal wait. The [historical USB state timeline](reopen-state-context.md) provides a hypothesis to test, not a diagnosis of this run, which had no kernel trace. The two earlier control-only successes remain valid but cannot support a general post-stream reopen claim.

Do not add a guessed delay, retry the failed redirect, restart a service, change binding/security or reset firmware as a supposed repair. The next physical test needs owner-attended recovery and a reviewed USB/UsbDk lifecycle trace covering stream release and the original stack's subsequent state. Establish recovery first; use one controlled acquisition and observe release without immediately issuing another redirect. The existing signed driver and trace decoder remain unchanged.

The one-time package is still **uninstalled**. Original Serato resources, absent project native installation and stopped Serato were confirmed by the source-current read-only native setup entry after the failure. The latest setup window remains idle behind the locked desktop. No action was started there. Native hardware reliability and normal Serato selection remain separate open requirements; a public install-once release is premature.

[Machine-readable evidence](evidence/native-asio-silent-stream-reopen-20261106.json) preserves both results, exact build/source identities and the later failure observation. Raw private activation records/journals remain local; no vendor binary, derived Serato archive or serial is published.

## Application-bound physical rehearsal

The new ordinary-user diagnostic can exercise the exact application-bound package before involving Serato. One registration-free host creates two successive ASIO objects. It runs each for three seconds at 44.1 kHz with silent output, then stops, disposes and releases it. The observer retains Windows handles to the controller and worker before allowing audio callbacks. It checks both handles after each release, checks that the same readiness publication remains in place and counts a single successful USB redirection. After the host exits, the observer requires both processes to exit and the controller to report successful retirement. The diagnostic does not treat this as proof of the next USB acquisition.

`scripts/test-native-activation-silent.py --prepare-application-reopen` checks the build and bundle identities, generates private workspace records and runs the passive native parser. It stops before starting the host. It takes the same `--host-build`, `--host-build-sha256`, `--bundle`, `--bundle-sha256` and `--native-build` arguments as the existing single-stream diagnostic. The application-bound mode requires the version 2 package and does not accept the earlier per-session configuration.

The Release host passed three inert and invalid-invocation checks. Five additional checks verified the default plan, passive preparation of the exact version 2 package, refusal of the earlier package in version 2 mode, refusal of a version 1 configuration in the host itself and ASIO initialization rejection with an incomplete version 2 record. The incomplete record reached the real driver and returned an init failure before readiness, with no activation owner created. The physical two-open sequence remains unrun. [Preparation and checks](evidence/native-application-reopen-preflight-20261107.json).

After a fresh attended SL3 recovery, `--run-native-application-reopen` selects the physical rehearsal. It uses the current user's token and requires Serato closed and the rebuilt driver uninstalled. The original Serato configuration is preserved. A failure retains the startup journal and any completed stream report, and cancels the remaining host steps. Normal Serato selection, audible output and Phase still need separate live confirmation.
