# Saved second-open USB timeline

Offline analysis of `inspect-reopen-staged-20261030-02` narrows the earlier startup failure. The second `UsbDk_StartRedirect` attempt reached USBHUB3's port-cycle request handling. USBHUB3 reported successful dispatch completion, but no subsequent enumeration for that hub/port is recorded. This is stronger evidence than the worker journal alone, which ended at redirect entry. It does not identify the exact outstanding UsbDk wait or establish a repair.

The [exporter](../scripts/export-reopen-usb-timeline.py) verifies the historical run/probe, exact observed journal prefixes, ETL and decoded XML hashes. It checks all 14,368 decoded events against the bound count; the original capture reports zero lost events/buffers. [Exported timeline and raw event fields](evidence/reopen-usb-timeline-20261030.json). It opens no device and changes no native binary, driver or policy.

Verification: actual export and byte-identical regeneration pass, Python syntax passes, and a temporary-copy negative check replacing the decoded trace rejects at the hash gate before any analysis output. No native build or physical test was needed for this evidence-only change.

| UTC on 30 October 2026 | Observed event |
| --- | --- |
| 17:23:20.9836748 | First worker PID 25532: SL3 recovery action, cycle request `0x22001f`. |
| 17:23:21.0828648 | Port 3 enumeration completes with status zero. Child object changes. |
| 17:23:21.0871300 | New child information describes the temporary UsbDk device. |
| 17:23:21.1350871 | First worker initiates another cycle during release. |
| 17:23:21.2370815 | Port 3 enumeration completes with status zero and another child object. |
| 17:23:21.2436044 | Second worker PID 32156: SL3 recovery action for the cycle request. |
| 17:23:21.2436070 | USBHUB3 emits “Unhandled State Machine Event” for the latest child: state `0x1080`, event `0xFAB`; context/index/depth remain in the export. |
| 17:23:21.2436078–21.2436083 | USBHUB3 records cycle dispatch start and completion, status zero. |
| Through capture stop 17:24:20.5866067 | No further enumeration-start/completion event for this hub/port. The bounded second-worker journal never records redirect return. |

Correlation uses the initial **Rane SL3** rundown, its hub/port, child identities from successive enumeration completions, and worker PIDs from hash-bound journal prefixes. `fid_UsbDevice` denotes the hub in recovery/start/status events but the child in device-control events. Treating every equal pointer as the target would incorrectly include other root-hub ports. Addresses are meaningful only within this trace. The temporary UsbDk identity is transport behaviour, not a proposed Serato identity substitution.

The local WDK `usbioctl.h`/`usbiodef.h` define `IOCTL_INTERNAL_USB_CYCLE_PORT` as `CTL_CODE(FILE_DEVICE_USB, USB_CYCLE_PORT, METHOD_NEITHER, FILE_ANY_ACCESS)`, with device type `0x22` and function `7`: `(0x22 << 16) | (7 << 2) | 3 = 0x22001f`. The reviewed [UsbDk reset sequence](usbdk-detachment.md) performs its optional D0 wait before sending this request. The second attempt progressed beyond that preceding stage. Successful USBHUB3 dispatch does not prove the entire synchronous call stack returned to UsbDk, its attachment event signalled, or PnP became ready for another cycle. No undocumented numeric state interpretation is assigned.

The next supervised capture should correlate the prepared shared UsbDk WPP/USB trace with these cycle and child-state events. It must distinguish reset return, redirect attachment and user-handle readiness. Missing events remain absent evidence, even with zero reported capture loss. This result does not justify arbitrary sleeps, a kernel change, suppressing an error or repeating the failing rapid-open sequence unattended.

The subsequent [current-image symbol analysis](reopen-state-context.md) distinguishes ETW from internal state values and conditionally labels the unhandled event as a client cycle in StoppedEnumerated. The saved child then follows a roughly ten-second driver-start-timeout sequence to Stopped. Historical loaded-image identity was not captured, so this narrows the candidate readiness fault without proving a repair.

## Compare the hub response with successful cycles

The failed-reopen capture also contains a successful acquisition and release on the same port. Those two cycles, the later controls-only pair and the silent-stream pair all returned hub dispatch status zero. Each also recorded a detach transition for the exact original child followed by a successful enumeration of a different child on the same port. Across those six cycles, enumeration completed 97.77 to 103.14 ms after the request.

The failed reacquisition returned the same dispatch status. It recorded the unhandled client-cycle event 2.6 microseconds after the request, with no matching detach transition or replacement enumeration in the saved window. The next traced acquisition can use this difference to distinguish hub dispatch completion from a cycle that produced a replacement. The successful captures establish the transition after each request. They do not establish a supported way to check the hub's readiness before another request. [Comparison evidence](evidence/sl3-cycle-outcomes-20261107.json)

The [read-only comparator](../scripts/compare-sl3-cycle-outcomes.py) pins the three saved XML files and the state-name report. It joins each cycle to its dispatch using worker PID and child identity, then checks the separate hub and port fields for replacement enumeration. Two exports matched byte for byte. Four altered-outcome checks refused the supplied data. The symbolic names retain the image qualification of the original traces.

The ASIO metadata review also ruled out substituting a configured expected rate for a live clock observation: `DriverFacade::init()` obtains the observed rate, while a timing profile records an expected/reviewed rate. Removing that acquisition would alter the current-rate contract. No such shortcut was implemented. Safe acquisition across Serato's object recreation remains required.
