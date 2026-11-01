# Windows resumption — 30 October 2026

The owner resumed the goal and explicitly deferred Mac work. Normal Windows signing enforcement remains a requirement. Phase may later provide an analogue control signal; neither Phase nor turntables are required for descriptor-only USB and bounded silent transport tests.

The fresh read-only preflight found one connected SL3 with the original failing Rane binding, no UsbDk service, unchanged reviewed artifacts and matching source/build identities. Microsoft's nested kernel signature passed verification. Unelevated Secure Boot querying remained unavailable; the elevated installation workflow requires it enabled before proceeding.

`scripts/test-usbdk-install.ps1` defaults to plan mode. Its explicit `-Run` mode requires an already elevated PowerShell 7.5+, one connected SL3, absent UsbDk service, valid unchanged MSI and enabled Secure Boot. It records before/after state, starts the existing passive 60-second USB trace before invoking Windows Installer, saves the verbose installer log and records the returned restart requirement. Automatic restart is suppressed. It neither redirects a device nor submits audio. If installation takes longer than the trace, the record explicitly marks it outside the trace window. Windows Installer is allowed to finish its transaction; it is not killed on a timer.

UsbDk is a system USB filter. Recovery is removal of this unchanged MSI using Windows Installer (`msiexec /x` with the reviewed package path, verbose logging and restart suppression), followed by fresh device/security checks. The original Rane package is preserved. A restart may still be required; no automatic restart or security-policy change is part of this workflow.

The installation launch requested Windows elevation, but the launch subsequently returned **the operation was cancelled by the user**. The launch process is terminal, no installation evidence directory was created, and a fresh service query still found no UsbDk service. No installer was started. Do not relaunch that request automatically. Local evidence for a future reviewed attempt would be under `tests/results/local/usbdk-install-20261030-01`; it must not be treated as complete merely because a directory or progress record exists.

After admission is established, use the existing traced List mode first. Capture and silent duplex are separate gated steps. A running service alone does not prove packet transport or ASIO operation.

Independent static analysis subsequently recovered [name normalization](serato-name-matching.md) and the [aggregation registration/USB revision selection boundary](serato-aggregation-selection.md). The latter has different duplicate-registration behavior from the primary collection. These findings narrow a future integration experiment; no Serato descriptor, archive or executable was modified and no working application connection is claimed.

The [current resource archive was then decoded independently](serato-resource-container.md): all 229 member CRCs pass and 228 XML files parse. No scalar SL3 identity was found in recognized descriptor nodes. The Phase HID resource is present. Six new targeted parser tests pass; this is separate from the earlier 36-test Python checkpoint and does not add physical audio evidence.

The [original timer-response comparison](timer-verification.md) is now implemented offline with a caller-supplied key, strict parsed-event checks and no response-emission/runtime hook. Following that source change, the complete suites passed 29/29 Release, 29/29 Debug, 21/21 SDK-free and 42/42 Python. No key was embedded and no physical timer exchange ran. Signed-driver admission, real capture/playback and current Serato/DVS remain unverified.
