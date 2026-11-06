# Return to SL3 testing — 6 November 2026

The unattended work is committed and pushed. The latest candidate is **prepared, not installed**. The remaining goal is still install once, launch the original Serato normally, and use the same driver for Phase RCA or timecode vinyl. That experience is not yet verified.

## Last observed host state

The final read-only setup check reported original Serato resources, no installed project native package, Serato stopped and no action steps. A separate process query found no Serato, `sl3_usbdk.exe` or `sl3_broker_controller.exe` process. Windows listed Rane SL3 under its original MEDIA binding with problem code 39. These are point-in-time observations, not USB readiness evidence.

No installation, administrator launch, certificate import, firmware operation or security-policy change ran during this final audit. The checked source and publication worktrees were clean before this report was added. The old idle setup-window artifact is distinct from the new candidate; do not assume it contains the refreshed native payload.

## Current local candidate

| Item | Local location / identity |
| --- | --- |
| Setup window | `artifacts/build/native-setup-window-activation-failure-20261106/build/Release/SL3_Compatibility_Setup.exe` |
| Window SHA-256 | `78525b5e909aef3a5939736cbf3393f48fa8fa5759ea4c9c6b7d5185109d22b4` |
| Setup-only kit | `artifacts/build/sl3-on-demand-kit-activation-failure-20261106` |
| Kit manifest SHA-256 | `7460d806d560b008c65ca2862bb716fcfd6a806930d07bfd8703fd2b30749bcd` |
| Kit-bound experiment SHA-256 | `0d28e2df5b723fa6342619c7839959bc535dec40429ddd277e50c64486f9b9eb` |
| Native build | `artifacts/build/native-activation-failure-report-20261106/native-build-Release.json` |
| Native build manifest SHA-256 | `2e747d51c5fe7f170793705da55c25208a616a2ef3becc3983a8ce405864f42d` |

These private artifacts require their bound local kit/experiment and original Serato installation. They are not a public download installer. The kit ships no Serato executable or derived resource archive. [Full candidate and source evidence](asio-activation-failure-report.md).

## Established results and limits

The earlier temporary Serato 5.0 session demonstrated owner-confirmed two-deck Phase REL tracking: A on LINE inputs 3/4 and B on LINE inputs 5/6, both remotes sharing one platter. That does not validate the new installed-use path, separate platters or timecode vinyl.

The earlier production ASIO build passed two control-only initializations without a power cycle. A subsequent three-second silent-duplex run completed 1,029 callbacks and normal owner retirement. The next acquisition failed inside USB redirect startup. The successful control-only reopen used a 16.922-second gap; the failed post-stream attempt used 9.406 seconds. Streaming was not isolated as the cause, and no safe delay was established. [Hardware result](native-asio-silent-stream-reopen.md) · [Timing confound](native-reopen-cadence.md).

The new build preserves failed-start controller cleanup and exposes more precise ASIO errors. All 73 native checks, 25 setup-entry checks and 18 window checks pass. A same-build fixture package also passes 21 contract and 261 isolated staging/recovery cases. The new native build has **not** acquired the physical SL3. Its software checks do not repair or verify USB recovery. The ten-minute unmeasured diagnostic limit remains.

## Next attended steps

1. Recover the device with the owner present. Disconnect all SL3 power, including USB and any external supply, for 30 seconds, then reconnect directly to the PC. Check normal descriptors and absence of a stalled worker; cached enumeration or Code 39 alone does not admit a new acquisition.
2. Start one reviewed USB/UsbDk lifecycle capture with administrator approval. Once the actual collector is verified recording, run one normal-user, bounded silent-duplex acquisition using the current hash-bound build. Observe release and the Windows stack through the remaining trace window. Do not immediately reopen, add a guessed delay, retry a stalled redirect or change binding as a presumed fix. Check actual event coverage, trace loss and source/binary identities before drawing a readiness conclusion.
3. After the native recovery boundary permits it, use the explicit one-time setup candidate and launch the original Serato normally. Initially leave playback stopped and record the actual status/ASIO selection. Do not use Download Driver or the temporary startup shim to count this comparison as normal-start success. Close Serato normally and verify restoration/removal separately.
4. Only after actual driver selection and stable startup, repeat Phase REL tracking and real output checks. Native reopen, longer playback, unplug/replug, interrupted-application recovery, another account/PC and vinyl remain acceptance work. Mac remains deferred by the owner.

The existing passive capture command's **non-capturing plan** was rechecked in this audit:

```powershell
& artifacts/build/portable-powershell-766-20261106/pwsh.exe -NoProfile `
  -File scripts/capture-usb-startup.ps1 -WithUsbDkLifecycle `
  -DurationSeconds 60 -OutputDirectory tests/results/local/native-activation-release-next
```

It verified the three USB providers at keywords `0x281` and the reviewed UsbDk lifecycle provider at flags `0x650`, level 4, with a 60-second/64 MiB bound. It did not start a collector, create the output directory or establish event emission. Actual capture requires the explicit `-Capture` option from an approved elevated process; the hardware probe stays in the normal user session. Use a fresh output directory and keep raw USB traces local. [Capture semantics and limits](usbdk-detachment.md).

## Why unattended work stops here

Physical recovery and an administrator-approved lifecycle capture have remained the prerequisite across the failed-reopen investigation, cadence review and refreshed-build work. The useful independent implementation, packaging and regression work is now complete for this checkpoint. Another untraced open, inferred recovery from cached enumeration, arbitrary timeout change or repeated software-only test cannot answer the remaining hardware question. The first protected installation/ordinary Serato launch also needs owner approval and observation.

The goal remains incomplete and is blocked on those attended observations, not marked achieved. The full acceptance scope is preserved in [the installed-use target](installed-use-target.md). Resume from this packet when the owner returns rather than repeating old launches or overriding stale source pins.
