# WinUSB development test

Prepared on 26 October 2026. This is a local development experiment, separate from the normal-security release-signing route. Preparation does not trust the certificate or install the driver.

**Follow-up:** the subsequent traced binding at 22:50 UTC succeeded with the same package, all active alternates at zero and read-only queries passing. The original 22:18 failure below remains a historical result, not the result of every binding. [Traced test and current next gate](windows-traced-test.md).

## Actual result and recovery

The owner explicitly approved this certificate's machine trust import and the SL3 binding test. At 22:18 UTC Windows accepted the signed package and installed it as `oem152.inf`, selecting `WINUSB`. Secure Boot was true before and after. This establishes development-package signature acceptance; it does not establish that the device started.

Kernel-PnP event 411 then reported **code 10**, status **0xC000009E (`STATUS_DEVICE_POWER_FAILURE`)**. The SL3 disappeared as VID 1CC5 / PID 0001 and the port showed “Unknown USB Device (Device Descriptor Request Failed)”. The owner's blue-light-then-off observation agreed with that failure. The probe found no project interface and never opened WinUSB, queried its endpoints or sent device I/O. This is a startup failure before the planned user-mode experiment, not an audio or DVS result. The status name alone does not distinguish electrical power from configuration/driver/firmware behaviour.

One USB reconnect did not recover it. The experiment was then fully rolled back: `oem152.inf` was removed, both machine trust entries removed, and the original `oem136.inf` preserved. The owner disconnected USB and external power, waited, and reconnected. At 22:22 UTC the unit returned as **Rane SL3 / MEDIA / strmdrv / code 39**, with both descriptors byte-for-byte identical to the initial capture. A final elevated snapshot confirms Secure Boot true. The development signing identity and its non-exportable private key were subsequently removed from CurrentUser/My as well.

Evidence: [installation record](evidence/winusb-development-installation.json), [PnP events](evidence/winusb-development-pnp-events.json), [failed probe](evidence/winusb-development-probe.json), [cleanup](evidence/winusb-development-cleanup.json), [verified final state](evidence/winusb-development-final-state.json). The original script's `problem: null` reflected an unavailable device property during disappearance; it did not mean code 0. The script now records explicit presence/status and start success separately.

The experimental `DeviceInterfaceGUIDs` registry value remained after driver-store removal. A final targeted cleanup removed only the project GUID and verified it absent, preserving other values. The cleanup script now handles this setting and avoids rebinding a device that already uses the original package.

Do not repeat this package unchanged. The next experiment must address an identified startup difference and capture the failing request/state transition.

## Prepared identity and package

- Subject: `CN=SL3 WinUSB Local Development Only`.
- Certificate thumbprint: `11538DF7C55A5BB2DBFE7160C45ECC804F3BB077`.
- Certificate SHA-256: `ee80d5551969f4a1b2007d13c847d431d438c434d09b0df173fa1b88d4640f50`.
- Valid until 2 November 2026, 22:14:32 UTC.
- EKU: code signing only; the non-exportable RSA key was created in CurrentUser/My and removed after the completed test. No private key was exported or committed.
- Files: `artifacts/build/sl3winusb-development/`. The INF is unchanged from the Inf2Cat-checked source; only the copied catalogue was signed. There is no replacement SYS in this package.

The catalogue's cryptographic signature verifies through `SignedCms.CheckSignature(true)`. Before approval, Authenticode reported an untrusted root and presence checks confirmed the certificate was absent from machine and user Root/TrustedPublisher stores. During the approved test, Authenticode became Valid. After cleanup it is no longer trusted. [Preparation evidence](evidence/winusb-development-preparation.json).

## Approval boundary

The approved test imported this exact certificate into **LocalMachine/Root** and **LocalMachine/TrustedPublisher**. That trusted other code signed with the same key, not only this INF. Certificate validity is time limited, but store entries are not automatically deleted when it expires. Explicit owner approval was obtained before the import; both entries have now been removed.

No Secure Boot, HVCI, CI-policy or BCD change is part of this experiment. Microsoft WinUSB remains the kernel binary. Whether this host accepts the development package without further changes is a test result, not an assumption. If it rejects the package, capture the failure; do not disable protections to make it pass.

## Reproducible commands

Preparation and preflight, already executed:

```powershell
./scripts/prepare-winusb-test.ps1 -Prepare
./scripts/test-winusb-development.ps1
```

Only following explicit approval, run elevated:

```powershell
./scripts/test-winusb-development.ps1 -Install -DevelopmentTrustApproved
```

The script checks hashes, signer, validity, the original Rane INF and exactly one connected SL3. It logs the exact trust stores added, stages the signed INF and captures the binding. If needed it uses the documented UpdateDriverForPlugAndPlayDevices API to select the exact SL3 hardware ID. The original Rane package stays in the driver store. No reboot is automatic.

Then run:

```powershell
python scripts/probe-winusb.py tests/results/local/winusb-development-probe.json
```

The probe opens only the project interface, initializes WinUSB, obtains associated interface handles and queries alternate descriptors/pipe metadata. It never selects an audio alternate, submits audio data, issues vendor control requests or updates firmware. Expected success: WinUSB service, PnP problem 0 and four interfaces matching the fixture. A successful probe would establish transport enumeration, not audio or current Serato/DVS support.

## Restore the baseline

Review the targeted restoration plan, then run elevated:

```powershell
./scripts/cleanup-winusb-development.ps1
./scripts/cleanup-winusb-development.ps1 -Restore
```

It verifies the original Rane INF hash, restores that binding if the unit is connected, removes only the matching development package and removes the certificate only from stores the test added. The original Rane driver was blocked before this experiment; restoring it restores code 39. The script leaves the untrusted My-store signing identity for optional re-signing. In this completed experiment that identity and its private key were separately removed after checking the exact certificate SHA-256.

Before an installation attempt exists, cleanup correctly refuses to invent an installation record. If the device/package identities differ from the saved test record, inspect the state rather than deleting unrelated drivers or certificates.
