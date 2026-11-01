# UsbDk detachment and the next reopen diagnostic

**1 November offline update:** [the saved 16:40Z experiment now has decoded lifecycle evidence](attended-port-lifecycle-20261101.md). UsbDk reports successful exact-SL3 detachment/removal, followed by the original stack's startup timeout on the same physical port. All 21 UsbDk records decode without unknown formats. This advances the earlier source-only limits below but establishes no successive-open readiness condition.

The [native retained test](retained-physical-test.md) passes within one acquired connection. Current Serato can [release and recreate ASIO objects](serato-asio-object-lifetime.md), so separate acquisitions still need a defensible startup/recovery path. The earlier second-redirect stall is not resolved by the retained test.

The [saved USB-stack timeline](reopen-usb-timeline.md) now establishes that the failed second open reached the port-cycle handler, which reported success, with an unhandled child-state event and no later target-port enumeration recorded. This narrows the failure beyond the preceding startup power wait, but does not establish full-cycle return or locate UsbDk's outstanding wait. No new hardware test was needed.

## What the cleanup result means

Review of UsbDk commit `84752c30037956149d53b498005b5368616f9257` traces the following path:

| Layer | Reviewed behavior | Limit |
| --- | --- | --- |
| Helper StopRedirect | Destroys its redirector owner, then returns true unless an exception is caught | Does not receive kernel removal status |
| Helper handle owner | Calls CloseHandle in its destructor | Does not inspect that return value |
| WDF file close | Registered callback calls redirector OnClose | Callback has no return status |
| Redirector OnClose | Calls control-device RemoveRedirect and logs a failure | Does not propagate that status to the helper |
| Control removal | Marks removal, resets, waits for detachment, then deletes redirection entry | Reset/detachment can fail; deletion failure is logged but the enclosing successful branch still returns success |
| Detachment event | Set when a removed child is absent from a hub relations snapshot while removal is in progress | Does not attest normal-device restart, successful descriptors or future redirect readiness |

The relevant sources are [helper](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDkHelper/UsbDkHelper.cpp), [handle owner](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDkHelper/DriverFile.h), [WDF registration and hub removal](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDk/FilterDevice.cpp), [redirector](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDk/RedirectorStrategy.cpp) and [control lifecycle](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDk/ControlDevice.cpp).

Microsoft documents that [EvtFileClose](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdfdevice/nc-wdfdevice-evt_wdf_file_close) runs after the last file handle/reference is released and outstanding I/O finishes or is canceled. That framework callback is synchronous in an arbitrary thread context. This does not make the application helper's Boolean a device-readiness attestation.

The reviewed startup sequence adds a redirection entry, cycles the device's USB port, waits for attachment and then opens a user handle. Both attachment and detachment waits can reach 120 seconds; handle readiness polling has a separate approximately ten-second allowance. **Those limits do not bound the whole StartRedirect call:** the power and port-cycle stages below have no timeout. The existing short watchdog remains necessary containment, and cannot guarantee immediate cancellation of those kernel operations. Cached device enumeration is not an adequate readiness barrier, as the earlier hardware failure demonstrated.

Our `device_released` evidence describes retirement of the caller's redirect/helper ownership. Actual Windows recovery is checked separately. The latest native retained test passed both ownership and selected recovery gates; this source finding does not overturn that bounded result. It does prevent treating a helper close alone as proof of safe rapid reacquisition.

## Power and port-cycle waits

The exact-commit [DeviceAccess.cpp](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDk/DeviceAccess.cpp) establishes an earlier startup stage. AddRedirect asks the reset helper to force D0; RemoveRedirect does not. When the queried power state differs from D0 and the power request is accepted, the helper waits for its completion event before issuing the port-cycle request. The callback signals the event but discards completion status. Failed power-state queries instead skip that conditional path. These are potential stall locations, not identification of the observed hardware stall.

[UsbDkUtil.h](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDk/UsbDkUtil.h) defaults this event wait to no timeout; [UsbDkUtil.cpp](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDk/UsbDkUtil.cpp) forwards a null timeout. Separately, [Irp.cpp](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDk/Irp.cpp) waits with a null timeout if the synchronous cycle request returns pending. Microsoft documents that a [null KeWaitForSingleObject timeout waits indefinitely](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-kewaitforsingleobject).

The operation is `IOCTL_INTERNAL_USB_CYCLE_PORT`, which Microsoft describes as [simulated unplug/replug](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usbioctl/ni-usbioctl-ioctl_internal_usb_cycle_port). It is distinct from an audio alternate change or pipe reset. Thus an accepted helper close and stable cached descriptors cannot attest completion of the underlying Windows handoff.

The verifier now pins six additional source files and checks power/cycle ordering, event defaults, pending-IOCTL wait and discarded power completion status. The signed driver itself is unchanged. Source review is not a complete equivalence proof for every instruction in that binary.

## Prepared passive diagnostic

The reviewed MSI contains a bundled TMF decoder. Its relevant message GUIDs occur in the actual pinned x64 driver. The preparer checks exact driver/TMF hashes, normalized source hashes, call ordering, WPP flag order and now **32 lifecycle message definitions**, extending the earlier 27 with power-query failure, power request/completion and cycle-IRP creation/send errors. These selected definitions are invariant across the bundled architecture/OS repetitions; unrelated records include differing formats and are deliberately omitted. The generated TMF stays local. [Checked source and message inventory](evidence/usbdk-lifecycle-source.json).

Plan only, without creating a result directory, loading the helper or enabling tracing:

```powershell
pwsh -NoProfile -File scripts/capture-usbdk-lifecycle.ps1
```

Future operator-attended passive capture from an already elevated terminal:

```powershell
pwsh -NoProfile -File scripts/capture-usbdk-lifecycle.ps1 -Capture -DurationSeconds 60 -OutputDirectory tests/results/local/usbdk-lifecycle-01
```

This standalone command records only the UsbDk WPP provider, now flags `0x650` including `TRACE_DEVACCESS`, level 4, in a uniquely owned, bounded 64 MiB session. It checks the installed running-service image hash and Secure Boot, refuses an existing output directory and records its script hashes. Stop/delete cleanup also recognizes successful operations recorded before a manifest-write error. A separately reviewed USB scenario must occur inside the window; this command does not start one or justify repeating the known failing rapid-reopen test.

The subsequent [controls-runner option](controls-probe.md#optional-shared-usbdk-lifecycle-trace) captures this provider and the USB stack in one session/ETL, using `-WithUsbDkLifecycle`. It prepares the same checked decoder and verifies provider configuration before the one-acquisition, no-audio probe. This removes manual trace-window alignment for that supervised scenario. The 1 November update above supplies actual WPP evidence from this shared route; the separate sidecar remains available.

Decode a resulting ETL offline with the installed SDK's Tracefmt, using that capture's generated `lifecycle.tmf`:

```powershell
& 'C:/Program Files (x86)/Windows Kits/10/bin/10.0.19041.0/x64/tracefmt.exe' 'PATH-TO-CAPTURE.etl' -tmf 'PATH-TO-CAPTURE/lifecycle.tmf' -o 'PATH-TO-FRESH-OUTPUT.txt' -utc -hires -sortableTime -cp utf8
```

[Tracefmt documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/tracefmt) describes ETL/TMF decoding. Match device identity and process/thread/time to the native journal and simultaneous USB-stack trace. Record trace loss, unformatted messages and actual event coverage. Missing selected messages do not prove a stage never ran. Decoding is not an acceptance validator or recovery barrier.

## Verification and next decision

The expanded 32-message source/TMF verifier passes. Actual fresh decoder preparation produces the checked bytes; a second preparation rejects without changing any files. The actual passive wrapper's plan reports `0x650`, no helper/device access and creates no output directory. An earlier live invocation from the ordinary terminal rejected before directory creation. At the preceding 27-message checkpoint, offline Tracefmt ran against the failed-reopen USB-stack ETL: 14,368 events, no reported format errors or unknown formats. Its WPP summary was empty; that result neither exercises the expanded formats nor proves live WPP emission/decoding.

Future interpretation must preserve absent evidence: a power-request message without its matching completion is a candidate power wait; no such request may mean the D0 path was unnecessary or its query failed. There is no selected positive cycle-completion message. Correlate USB-stack events, selected error messages, attachment messages and the native journal. Missing WPP messages alone cannot locate a stall or prove successful port cycling. The passive sidecar remains separate from the native test wrapper and has not captured live events.

Next capture the kernel lifecycle around a reviewed scenario, then distinguish reset failure, attachment timeout, handle-open failure and incomplete removal. Do not add an arbitrary delay or independent CloseHandle, change the signed kernel driver, or infer a need for an elevated broker from these findings. Cross-object transport lifetime design remains open until that evidence supports a change. No new hardware operation, administrator prompt, driver/trust/security change or firmware operation occurred in this investigation.
