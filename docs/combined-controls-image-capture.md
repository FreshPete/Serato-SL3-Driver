# Combined controls and image capture

This workflow uses one administrator approval for a bounded image logger and a twenty-second sequential USB/WPP collector. The separate controls probe inherits the launcher's normal user token. No elevated broker, task or service remains available for later commands.

`collect-controls-with-images.py --prepare analysis/logging-batch-<fresh-name>` prepares a sixty-second image-source job and a frozen `controls-image.json`. Preparation starts no trace and launches no probe. The plan pins the launcher, collector, image inspector, window validator, existing logging runtime, eighteen controls dependencies, native manifest and both native executable hashes.

`start-controls-image-capture.ps1 -Plan <absolute-controls-image.json>` validates only. Adding `-Run` starts the normal-user role, then requests one administrator launch. A create-new parent attempt record prevents a cancelled prompt from leaving two normal probes waiting for the same future trace. A cancelled or failed attempt needs a new plan and context. There is no automatic retry. The normal role's existing ninety-second admission wait remains bounded.

The elevated collector starts the existing image-only controller. It requires an accepted fresh strict native query and the owned, hash-bound committed configuration before an independent second strict query. Only then may it start the USB collector. It never launches a device probe itself. The normal role independently checks the collector's process identity, fresh trace, baseline and duration before its one acquisition/getters/release. There are no audio starts, control setters, rate changes or firmware operations.

After the offline admission verifier returns, the normal role now independently reobserves the collector process and recording trace. This hash-bound `launch-admission.json` must preserve the original collector identity and still fall within the duration's launch window. The two-second final freshness guard uses this new observation. Cold verifier startup does not replace a live observation or extend that guard. Final validation checks both observations and their ordering; historical records without the second observation retain their original guard.

Both collectors own their cleanup. The supervisor waits for their results and records exact child PIDs and exit codes. A timeout does not kill a collector that could still own source cleanup; the error requires inspecting that process before another test. The result's `collectionCompleted` describes USB collection only. It does not imply a passing probe, image overlap, physical identity or safe reopening.

After both roles retire, run `validate-controls-image-window.py --plan <plan> --output <fresh-local-output.json>`. It revalidates the normal-user controls result, USB trace, observer and selected recovery; verifies source artifact/result bindings; and independently decodes the image ETL against the current USBHUB3 disk image. The consistent DCStart/DCEnd pair must bracket the entire USB window, including at least twelve seconds after probe retirement. Integer FILETIME comparisons preserve 100 ns boundaries. Decode warnings remain in the result.

Matching metadata across a window does not prove a loaded-memory hash, identify which physical USB port an opaque state event belongs to, admit another acquisition or establish audio/Serato compatibility. Those conclusions remain separate requirements.

Twenty targeted checks passed before a live combined run: collector success/failure composition, source/query/runtime refusal paths, cleanup-owner preservation, exact window boundaries, metadata/lifetime rejection, actual plan-only and denied-child PowerShell executions, and two read-only checks against saved real records. All native sources and binaries remain unchanged. The tests do not establish a physical combined-capture pass.

## First live attempt

The 1 November 14:25:52Z launch used one administrator launch, but the normal role stopped before creating a native probe: its cold verifier took the original admission past the two-second launch guard. The guard age was already at least 2.0590907 seconds when the run record was created. No acquisition, getter or audio operation ran.

The image controller passed its sixty-second job and retired. The sequential USB ETL contains 5,502 events and 24,117,248 bytes with zero reported loss. The live observer processed 5,500 events and zero state rows; the file likewise contains zero USBHUB3 state rows. The strict state check correctly failed with `No actual live state rows`. The run remains failed. The image metadata brackets this USB-only window, without establishing device/probe coverage.

The USB header reports sequential mode zero and native maximum file size zero. A native hard file cap is not proven. The image ETL reached 64,159,744 bytes, below the existing 64 MiB inspection bound; this provides no guaranteed margin for a later, noisier capture. Both collectors' cleanup completed, all six recorded owner PIDs were later absent, no native device process remained, and selected before/after recovery including enabled Secure Boot matched.

Regenerate the [compact failure evidence](evidence/combined-controls-first-20261101.json) with `scripts/export-combined-controls-first.py`. The local capsule at `artifacts/build/checkpoints/combined-controls-first-20261101` preserves thirty exact runtime files, the actual manifest, raw traces and records. The launch-reobservation correction passed sixteen normal-user tests; the twenty combined-workflow checks, eleven capture-evidence checks and three live-consumer checks also pass. Native inputs and binaries are unchanged. No corrected physical pass is claimed here.

## Corrected live attempt passed

The fresh 14:32:25Z attempt passed the complete controls capture under one administrator launch. Parent, native probe and worker were independently queried as normal user tokens. The probe ran from 14:33:13.0372475Z to 14:33:14.5141188Z, acquired once, read 44.1 kHz and the full twenty-two control bytes, released once and retired. There were no audio starts. The bytes match the earlier acquisition:

`[0,1,1,5,96,0,96,0,1,5,96,0,96,0,0,5,96,0,96,0,0,1]`

The sequential USB file retained 6,536 events in 32,112,640 bytes, with zero reported event/buffer loss. All 493 live state rows match all 493 source-file state rows. The image ETL retained 64,582 events in 53,149,696 bytes. Its consistent USBHUB3 rundown pair matches the disk image metadata and brackets the entire USB window, including 15.9134111 seconds after probe retirement. This is same-window version metadata, not a loaded-memory hash. Tracerpt's schema warning is preserved; complete decoding of every event is not claimed.

Both collectors exited zero and cleaned up. Selected security/device recovery matched, including enabled Secure Boot. The nine recorded owner PIDs were subsequently absent, and no native device process remained. The [compact pass evidence](evidence/combined-controls-pass-20261101.json) is independently regenerated by `scripts/export-combined-controls-pass.py`; the actual image overlap was established by a fresh offline decode through `validate-controls-image-window.py`.

Raw data, the exact thirty runtime files, native manifest and reports are preserved in `artifacts/build/checkpoints/combined-controls-pass-20261101`. The original failed attempt remains failed and unchanged.

The default native build was refreshed after this physical result. The original source inputs, manifest and complete Release directory now also reside in `artifacts/build/checkpoints/native-controls-build-20261101`. The historical exporter verifies that exact archive and reuses the unchanged saved-evidence validators against its manifest/binaries; it does not execute them. Live admission retains its current-build checks. Regenerating this result therefore cannot turn the earlier physical pass into validation of a newer worker.

The complete XML now retains two events carrying SL3 VID/PID, which were unavailable in the old overwritten trace. Their relationship to the post-release DSM context and physical port still needs examination. A candidate startup-timeout sequence is again present; no further acquisition has been admitted from it. Safe successive acquisition, current-worker physical audio, analogue routing/latency, current Serato admission and two-deck DVS remain incomplete. macOS remains deferred.
