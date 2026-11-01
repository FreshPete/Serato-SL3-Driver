# UsbDk access under a non-elevated token

The existing native worker successfully listed the actual SL3 and verified its device/configuration descriptor fixtures under a **non-elevated limited token**. The parent and child tokens were both queried directly. This establishes ordinary-session descriptor access on this host; it does not establish redirection or streaming permission.

Local record: `tests/results/local/usbdk-user-list-20261030-01`. [Verified token, native result, archived binary/source and reviewed access-source bindings](evidence/usbdk-user-access-20261030.json).

| Observation | Actual result |
| --- | --- |
| Parent / child token | `TokenIsElevated=false`, `TokenElevationType=3` for both; neither token query failed |
| Native mode | Existing `sl3_usbdk.exe --list --helper` with the pinned helper |
| Descriptor result | Exactly one matching SL3, recorded device/configuration fixtures match, high speed |
| Redirection | False; list mode returns before `Device` construction and redirection |
| Exit | 0, no stderr, normal child exit, no forced termination |
| Process elapsed | About 41 ms, including process startup and dependency/service verification |
| Post state | Original `strmdrv` / `oem136.inf`, problem 39; no SL3 test process remains |

Microsoft defines elevation type 3 as a limited token; it is distinct from a full elevated token. This test used the current account's limited token, not a separately created standard-user account. [Microsoft token enumeration](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-token_elevation_type).

The native executable matches the archived control-selection-I/O build. Its list path checks the already-running driver's image and helper identities, loads the reviewed helper, enumerates and checks descriptors, then returns. It does not install/start the driver, call `StartRedirect`, send SL3 clock/control-pipe commands, activate audio endpoints, set a rate or modify firmware. This was one descriptor-only execution; no ownership experiment or UAC prompt ran.

## Source interpretation

Reviewed UsbDk commit `84752c30037956149d53b498005b5368616f9257` calls `WdfControlDeviceInitAllocate` with `SDDL_DEVOBJ_SYS_ALL_ADM_RWX_WORLD_RWX_RES_RWX`. Its helper's `UsbDk_GetDevicesList` path constructs control-driver access and requests the device list. The separate add-redirect caller-context path captures a handle to the requesting process using `UsbDkCreateCurrentProcessHandle`. The exact previously pinned source hashes are rechecked by the exporter.

Microsoft documents the allocation argument as the control-device security descriptor and notes that a later assignment can overwrite it. Its SDDL documentation defines the generic read/write rights and World/Restricted SIDs. Those documents explain the mechanism; the actual non-elevated descriptor test supplies the runtime access evidence. The live device-object ACL was not dumped or changed. [Control-device allocation](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdfcontrol/nf-wdfcontrol-wdfcontroldeviceinitallocate), [device-object SDDL](https://learn.microsoft.com/en-us/windows-hardware/drivers/kernel/sddl-for-device-objects).

The reviewed source and observed result are consistent with an ordinary-user control endpoint. They are not proof that every request, caller, policy override or redirection handle will succeed. In particular, no unprivileged `StartRedirect`, system-handle/pipe I/O, COM/ASIO deployment or sustained audio result is established.

## Architectural consequence

An elevated broker is not justified merely because the current **trace runner** requires administration. Driver installation, ETW/Secure Boot inspection, descriptor access, USB ownership and audio streaming have separate privilege requirements. Keep the existing normal-security target; do not change device ACLs or introduce an elevated service to solve an unmeasured access failure.

The next privilege-specific physical gate is a bounded non-elevated control/ownership test with independently collected trace/security evidence and confirmed release. The [split-role procedure](controls-user-probe.md) is now prepared and software-tested, requiring actual parent/probe/worker token evidence. No ownership run has occurred through this new path. The known repeated-redirection stall remains an ownership/readiness problem to investigate separately. The existing admin trace wrapper currently creates elevated probe children; its success alone would not establish non-elevated streaming. Current Serato admission, measured analogue/timing behaviour and two-deck DVS remain incomplete.

## Revalidation of saved evidence

```powershell
.venv/Scripts/python.exe scripts/export-usbdk-user-access.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_usbdk_user_access.py -v
```

These commands read saved records and test synthetic mutations; they do not load the USB helper or repeat the physical check. The exporter binds the archived native executable/build manifest, preserved worker source, stdout/stderr hashes, actual token/retirement fields, reviewed source and post-state. Five targeted tests reject elevated/missing/incorrectly typed token data, failure/forced retirement, descriptor flag mutations and invalid timing.

The post-state is not a full before/after recovery attestation, and Secure Boot was not freshly queried. No trust, signing-policy, ACL, binding, ASIO registration, application/account or resource change ran. Native runtime binaries are unchanged.

The full Python suite passes 114/114. The local `usbdk-user-list-20261030` checkpoint preserves the exact native binary/manifest/source, raw result/post-state, reviewed source files, validator/tests and log. Native 39/39 Release, 39/39 Debug and 25/25 SDK-free remain preceding evidence for unchanged native inputs.
