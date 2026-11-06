# Production ASIO initialization and reopen — 6 November 2026

The exact packaged production DLL now initializes the physical SL3 through its lazy ASIO entry, without an administrator prompt or prestarted broker. Two successive fresh COM hosts each report six inputs, six outputs and a 44.1 kHz clock. Between them the SL3 remained connected and was not power-cycled.

Both hosts released the ASIO object normally. The observer retained and validated the exact controller and worker process objects before release, then observed both exit. Each controller reported successful native acquisition, I/O retirement, device release and an empty process job, with no forced termination, lifetime expiry or device/stream failure. Worker journals contain clock reads and normal redirect close/helper unload. No audio buffers or streams were created. This is a control-only result; connected Phase remotes were not sampled.

## What this establishes

Automatic broker startup from the production IASIO `init` path works on this Windows host. Ordinary-user access to the reviewed signed UsbDk dependency works. A second real acquisition after normal release works without a cable/power cycle. These are stronger results than the earlier passive production COM enumeration or simulated transport tests.

The host uses a private registration-free COM manifest and a copied production DLL with fresh adjacent records. It does not install a package, register a class, replace Serato resources, launch Serato or exercise the installed registry path. Serato's ordinary primary-device selection is still unverified. This does not prove streaming through the new on-demand path, physical output, Phase tracking under that path, vinyl, unplug recovery or long playback. Earlier temporary-session Phase tracking remains separate evidence.

Two successful acquisitions are the extent of this reopen evidence, not a general claim that future acquisitions cannot fail. The controller conservatively retains `usbReadyForNextAcquire: false` and `rateRestorationVerified: false`; this report does not override either field.

## Diagnostic and bounds

`diagnostics/asio-native-control` is a separate x64 host built against the hash-checked official ASIO ABI. Default/`--plan` is inert; unknown arguments fail. Only the explicit native-control mode constructs the production COM object and calls `init` once. It reads channel count and sample rate, publishes a readiness marker, waits at most 15 seconds for the observer and releases once. It has no `createBuffers`, `start`, sample-rate write or firmware call. The build runs only two inert/refusal checks.

`scripts/test-native-activation-control.py` defaults to an inert plan. Its explicit run requires the reviewed host/build/bundle identities, unchanged native sources and full native Release test evidence, an ordinary x64 token, reviewed UsbDk disk image/running service, original Serato resources, no project registration, stopped Serato and no live previous activation owner. The disk check is not loaded-image attestation.

Fresh configuration records are checked by the actual passive native parser before the DLL is initialized. They bind the same reviewed controller/worker/helper and 44.1 kHz/128-frame diagnostic profile, with a shorter 60-second lifetime for this control-only probe. Existing bundle and installation records are not modified. The observer enforces deadlines, preserves raw output/journal hashes and uses only its retained child handle for last-resort host termination. A failed or unproved retirement is a stop condition for further device tests, not permission to reopen repeatedly.

## Evidence and host state

[Machine-readable checkpoint](evidence/native-asio-control-reopen-20261106.json) binds the source/build identities, two raw result hashes, readiness and retirement records. Raw reports, private manifest/configuration and native journals remain local under the recorded analysis/session identities. No vendor binaries or device serials are added to the public checkpoint.

After both tests Windows still enumerated Rane SL3 under its original MEDIA binding with an error status; this is not a claim that the old Rane driver started. Original Serato resources and absent project ASIO registration were checked. The idle setup window remains open behind the locked desktop; no privileged setup action was started. Security policy and firmware were unchanged.

Next attended step: review the latest setup-window result display, explicitly install the prepared one-time candidate, then launch the original Serato normally and observe actual driver selection. A successful install label alone cannot establish that result. The candidate remains a ten-minute audio diagnostic and is not ready for a public installer release.
