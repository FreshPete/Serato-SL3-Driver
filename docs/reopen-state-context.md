# Failed reopen: the stopped-enumerated interval

The saved second-open trace contains more useful startup evidence than the earlier numeric-only timeline showed. Using the **currently installed USBHUB3 image and its matching public symbols**, the dropped event decodes as a **client cycle request while StoppedEnumerated**. About ten seconds later, the same child follows the driver-not-found/start-timeout path, disables its port and reaches Stopped. The inspected driver's Stopped state accepts a cycle request; its StoppedEnumerated top-level table does not.

This is a concrete candidate mechanism for the failed rapid reopen: the original Rane stack has reappeared in enumeration but is still completing an unsuccessful startup. A unique cached SL3 descriptor is therefore insufficient evidence that the hub can process another cycle. It explains why the existing two-second descriptor-readiness gate may admit too early. **This remains a version-qualified interpretation, not a verified repair:** the old capture did not record the identity of its loaded USBHUB3 image. The current image matches its downloaded PDB, but that does not prove which image was loaded during the historical run.

## What was recovered

[Reproducible context report](evidence/reopen-state-context-20261030.json), [symbol inspector](../scripts/export-usbhub3-state-symbols.py), [saved-trace correlator](../scripts/export-reopen-state-context.py).

The copied current image hashes to `f93fa3a32037c597fd19ca9d65f59e53a1e337123582ed2479d5c16a4848df16`. Its observed file version is `10.0.26100.1`, and Windows reports a valid Microsoft Windows signature. Its RSDS identity is `179F1445-B718-DC85-4314-4991DC161F09`, image age 1. The PDB was retrieved from [Microsoft's public symbol service](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/microsoft-public-symbols) using that exact identity. All subsequent inspection uses cached local files and a local-only DbgHelp symbol path; it opens no USB device and loads no driver into the kernel.

The PDB's info-stream age is 4, while its DBI age is 1. These are deliberately recorded separately. The inspector checks the GUID, requires info age at least the image age, and requires matching nonzero DBI/image ages, following [Microsoft's PDB validation implementation](https://github.com/microsoft/microsoft-pdb/blob/1bdc5900390b6edec02e7b6a1b6e7bdef6e76df1/PDB/dbi/pdb.cpp#L808). Merely comparing the info age with the image age would incorrectly reject this pair. Exact image/PDB hashes are also pinned.

The actual [DbgHelp type APIs](https://learn.microsoft.com/en-us/windows/win32/api/dbghelp/nf-dbghelp-symgettypeinfo) expose 882 types, including separate internal and ETW DSM state enums. The inspector also verifies the image's `HUBSM_LogUnhandledEvent` instructions and event-111 descriptor. The logger reads the state entry's `EtwName` field; it does not write the raw internal state number into `fid_State`.

| Meaning in the inspected image | Internal state value | ETW state value |
| --- | --- | --- |
| StoppedEnumerated | 4243 (`0x1093`) | 4224 (`0x1080`) |
| Stopped | 4241 (`0x1091`) | 4222 (`0x107E`) |

Looking up `0x1080` directly in the internal enum would incorrectly label the trace as a pipe-reset state. The separate DSM event enum identifies `0xFAB` as `DsmEventClientRequestCycle`.

The compiled state table independently maps StoppedEnumerated to ETW value `0x1080`. Its bounded, null-terminated top-level transition list has no client-cycle transition. Stopped instead routes that event to `DsmStateRequestPortCycle`. These checks do not purport to exhaust every possible nested-state path.

## Saved sequence, with conditional current-image labels

The correlator first revalidates the original [failed-reopen timeline](reopen-usb-timeline.md): run/journal prefixes, ETL/XML hashes, loss counters and all 14,368 recorded events. It then labels 246 target-child DSM state events. Six other target-child state events belong to another state-machine namespace and are excluded from the DSM lookup.

| UTC on 30 October 2026 | Observation and label for the inspected image |
| --- | --- |
| 17:23:21.2370835 | After release re-enumeration, original child enters StoppedEnumerated. |
| 17:23:21.2401803 | Last top-level return to StoppedEnumerated before the second cycle, following PDO pre-start handling. |
| 17:23:21.2436070 | PID 32156's client cycle request is reported unhandled in StoppedEnumerated. |
| 17:23:31.2401878 | TimerFired enters CheckIfDeviceCanBeDisabledOnDriverNotFound, about **10.000007 seconds** after the preceding top-level return. |
| 17:23:31.2401889 | DisablingDeviceInControllerOnStartTimeout. |
| 17:23:31.2402403 | DisablingPortOnStartTimeout. |
| 17:23:31.2402591 | Stopped, following PortDisabled. |

The original Windows snapshot reports Rane SL3 problem code 39. That is consistent with unsuccessful original-driver startup; it does not establish every causal step. The existing trace still contains no later target-port enumeration and no second redirect return in the bound journal prefix. Successful dispatch of the cycle IOCTL remains distinct from the state machine handling its event and UsbDk completing attachment.

## Consequence for the next test and implementation

The next attended investigation should bind the hub-driver image/symbol identity, record release through the original stack's settled state, and correlate a subsequent single redirect with the shared USB/UsbDk trace. It should distinguish **enumerated**, **startup still pending**, and **able to accept a cycle**. The normal-token read-only test remains the next physical prerequisite. Its full trace window can also expose the post-release timeout sequence without immediately asking for another redirect.

The subsequent [native passive state reader](usb-state-observer.md) now replays every saved state observation directly from ETL in both builds, preserving namespace and timestamp fields. Live delivery is not yet verified or connected to reopen admission. A standard cached connection-status query is also examined there and is not promoted to a readiness predicate.

A production readiness policy needs a supported observable condition that works under the application's actual permissions. Neither cached enumeration nor the helper close Boolean supplies this condition. The observed ten-second timeout is evidence to investigate, not a universal sleep to insert. Changing the two-second limit to an assumed longer delay, retrying an already dropped cycle, issuing another reset type or changing the original binding is not established as a repair by this analysis. The exact outstanding UsbDk wait also remains unobserved.

The retained single-acquisition audio results remain valid for their archived builds. Reliable cross-object reacquisition, current-worker normal-token access and current Serato/DVS operation remain unverified. No native code, test package, driver, security setting or firmware was changed here.

The subsequent [kernel image rundown investigation](kernel-image-rundown.md) adds an offline checker exercised against Microsoft's actual public test ETL. It confirms that the saved reopen trace has no image events and cannot retrospectively identify its loaded hub driver. A fresh image source and USB-window correlation remain outstanding; the first normal-token read-only control test can still proceed with numeric state observations.

## Verification

The actual offline export and byte-identical regeneration pass. Four actual negative CLI checks reject a changed GUID, changed image age, changed image bytes and malformed PDB before creating derived output. Python syntax checks pass. Full native/Python production suites were not repeated: their inputs are unchanged from the frozen setting-runner checkpoint. The symbol files, copied image, full enum/layout/disassembly evidence, decoded saved rows and negative-check record remain local; the compact report pins their identities.
