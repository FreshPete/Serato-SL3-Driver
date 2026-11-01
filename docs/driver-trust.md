# Driver trust decision — 26 October 2026

The unchanged Rane package remains installed as `oem136.inf`; Windows rejects `strmdrv.sys` before audio can be tested, including after reboot. Its bytes match the original package. Reinstalling or changing ASIO registration does not address this failure.

## What the current policy permits

Microsoft's current Windows Driver Policy documentation names our exact enforced policy GUID, `{8F9CB695-5D48-48D6-A329-7202B44607E3}`. It describes WHCP-signed drivers and an explicit legacy allow list as the default permitted cases, and says there is currently no individual-driver bypass. Therefore an ordinary local hash allow rule is not an established solution to this particular block. [Windows Driver Policy](https://support.microsoft.com/en-us/windows/hardware/drivers/the-windows-driver-policy).

The release route for an updated kernel package is WHCP/HLK certification through the hardware dashboard. Microsoft's separate signing-options page describes attestation as a testing offering; an attestation signature should not be promised as a certified release or assumed to satisfy this host's newer enforced policy. [Signing options](https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/driver-signing-offerings).

Custom kernel signers are a different deployment model: the App Control policy must be signed through the Secure Boot PK/KEK trust hierarchy. That is not an ordinary publisher-certificate import or an application setting. We have not provisioned firmware trust, changed CI policy, installed certificates, disabled Secure Boot or enabled test signing. [Custom kernel signers](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/design/custom-kernel-signers).

## Checks completed

| Check | Result | Evidence |
| --- | --- | --- |
| Export installed Rane package | All four files match extracted originals | `evidence/exported-driver.json` |
| Current catalogue verification | Membership verifies offline, with timestamp warning; runtime rejects | `evidence/exported-driver-kernel-signature.txt` |
| Reboot | ASIO registration completes; fresh enforced rejection remains | `evidence/after-reboot-summary.json` |
| Update Catalog, queries `Rane` and `VID_1CC5&PID_0001` | Both HTTP 200 pages contain the visible no-results message | `evidence/update-catalog-search.json`; original HTML under ignored `analysis/` |
| Inbox WinUSB | Microsoft signature validates; original `WINUSB` driver node exists | `evidence/inbox-winusb-preflight.json` |
| Manual Have Disk selection | Owner reports “doesn't contain a compatible software driver for your device” | `evidence/winusb-binding-assessment.json` |
| Final PnP | Still Rane/MEDIA, `strmdrv`, `oem136.inf`, code 39 | Same assessment; local current snapshot |

Search results establish what these queries returned, not that no signed revision exists elsewhere. No suitable current Microsoft-signed SL3 package has been acquired.

## WinUSB feasibility and implementation

WinUSB provides user-mode isochronous APIs, so it remains a candidate for avoiding a new kernel streaming driver. Descriptor access is insufficient to prove packet scheduling, clock feedback or usable latency. [Isochronous WinUSB API](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/getting-set-up-to-use-windows-devices-usb).

The installed generic INF matches `USB\MS_COMP_WINUSB`; that compatible ID is absent from the captured SL3 PnP identifiers. Microsoft's developer article documents a system-class selection procedure, but the owner's concrete attempt failed. We have not demonstrated manual binding on this device. An experimental direct SetupAPI selection also failed to establish binding; its diagnostic attempt returned invalid parameter. We retained only the working read-only driver-node enumerator in `scripts/inspect-inbox-winusb.ps1`.

`src/windows/sl3winusb.inf` is an original experimental INF matching only VID 1CC5 / PID 0001. It uses Microsoft's inbox WinUSB sections and a project device-interface GUID. After the initial tool check, we acquired isolated Microsoft WDK NuGet 10.0.28000.2526. NuGet author/repository signature verification passed. Its Inf2Cat signability check for `10_GE_X64` passes with no errors or warnings and generates the package under `artifacts/build/sl3winusb/`. Providing a custom INF still requires a signed catalogue. [WinUSB installation and packaging](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/winusb-installation).

The generated catalogue is **NotSigned**, so this remains **not an installable release package**. No certificate or trust-store change was made. Standalone InfVerif was not present in this NuGet extraction; Inf2Cat success is not a substitute for InfVerif/HLK, WHCP certification or hardware tests. The full current WDK build workflow also calls for a newer Visual Studio toolchain than the initially detected VS 2019. [Official WDK NuGet setup](https://learn.microsoft.com/en-us/windows-hardware/drivers/install-the-wdk-using-nuget). Build with `scripts/build-winusb-package.ps1`; see `evidence/winusb-package-build.json`, `winusb-inf2cat.txt` and `wdk-nuget-verification.txt`.

For this **INF-only WinUSB package**, distinguish PnP catalogue signing from replacing the kernel binary: Microsoft's x64 PnP documentation permits WHQL or a third-party commercial release certificate for package signing, subject to edition/policy restrictions. The included kernel service is Microsoft's existing WinUSB, not a newly cross-signed Rane SYS. **Inference, untested here:** a suitable commercially signed INF catalogue could be a smaller deployment route than certifying a new kernel binary. It cannot make `strmdrv.sys` trusted. No currently valid code-signing certificate with a private key was found in the current-user or local-machine personal stores; public metadata counts only were recorded. No certificate was used or imported. [PnP signing requirements](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/pnp-device-installation-signing-requirements--windows-vista-and-later-), [readiness counts](evidence/code-signing-readiness.json).

`scripts/probe-winusb.py` is prepared to open only that project interface, initialize WinUSB, enumerate all four interface handles and query alternate descriptors/pipes. It contains no vendor requests, alternate-setting selection or audio transfers. On this host it correctly reports zero matching project interfaces; its device-I/O path remains untested. No WinUSB streaming or audio success is claimed.

## Selected sequence

1. Preserve the original package and its user-mode interface evidence. A vendor-supported WHCP-signed revision would be the smallest loading change, but obtaining one depends on its publisher and Microsoft's signing process.
2. Use the experimental WinUSB INF/probe as the transport prototype once a valid binding package or a verified system-class binding is available. Test load/enumeration first, then recover safe control requests and clock behaviour. Do not assume the Rane DLL's private IOCTL contract works over WinUSB.
3. Decide whether user-mode transport and a control/ASIO component can supply the interface current Serato actually uses. Complete the Serato integration gate before spending on signing or developing a replacement kernel engine.

No certificate purchase, account registration, external submission, vendor contact or security-policy change has been performed. A normal-security load result cannot be manufactured locally from the expired Rane signing identity.

## Subsequent approved development trial

The owner reported no signing access, then explicitly approved a temporary local development-certificate trust import and the WinUSB test. The newly signed catalogue was accepted without a BCD, Secure Boot or CI-policy change, but WinUSB failed device startup with code 10 / `STATUS_DEVICE_POWER_FAILURE`. This answers the development-package acceptance question, not transport compatibility. The test package and trust entries were removed; a full power cycle recovered the original Rane identity and descriptors. The signing key was also removed. See [test, failure and verified recovery](windows-development-test.md), and the [original-driver startup comparison](usb-startup.md). Release signing is still unresolved.
