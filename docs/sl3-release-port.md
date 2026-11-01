# SL3 release mapped to its physical port

The complete 1 November control trace maps the post-release timeout to the SL3's root-hub port 4. This resolves the old trace's ambiguous shared-hub-cookie correlation. It does not establish a safe reopen condition.

The initial `Rane SL3` device-information event identifies the hub, port and initial child. Two worker-PID cycle events carry VID `1cc5`, PID `0001`. Two enumeration completions independently associate the same hub/port with the redirected child and then the replacement child after release. A new-device-information event identifies the temporary UsbDk child on that exact port. Selecting DSM contexts by those enumerated **child** cookies yields three distinct contexts with 11, 158 and 97 rows. A shared hub cookie alone never selects a child.

All 493 live state rows match the retained XML. The cached USBHUB3 image and matching PDB supply the ETW state namespace. The observed image rundown brackets both the collector interval and the native USB ETL header boundaries. The native USB start precedes the collector's ready notification. This is matching version metadata, not a loaded-memory hash. Raw cookies remain local.

| Observation after the probe finished | Exact interval |
| --- | --- |
| First successful `StoppedEnumerated` entry | 47.4256 ms |
| Last successful entry to `TimerFired` | 10.0000898 s |
| `Stopped`, following `PortDisabled` | 10.0511163 s |

The selected context follows `CheckIfDeviceCanBeDisabledOnDriverNotFound`, `DisablingDeviceInControllerOnStartTimeout`, `DisablingPortOnStartTimeout`, then `Stopped`. The [inspected driver tables](reopen-state-context.md) accept client cycle requests in `Stopped`, while the `StoppedEnumerated` top-level table lacks that transition. This strengthens the startup-state explanation for investigating rapid reopen. It does not demonstrate a successful second acquisition, exhaust every nested-state path or justify a fixed ten-second production sleep.

The native trace headers from 31 October and 1 November have the same Windows boot identifier. This does not rule out an intervening physical power cycle, so it is not proof of recovery without intervention.

Run `scripts/analyse-sl3-release.py` to reproduce the [compact port evidence](evidence/sl3-release-port-20261101.json). Eight tests exercise exact-port joins, hub/child separation, competing same-hub contexts, wrong worker/VID/status/port, null or ambiguous context identities and invalid timeout tails. The original combined-capture records remain unchanged.

## Normal-user port query

A separate real read-only test successfully opened the currently mapped root-hub interface with **zero desired access**, queried connection information for port 4, closed its handle and exited under a normal type-3 token. No UAC prompt, child-device open, reset, cycle or audio request ran. The selected before/after PnP parent, port, location and original driver problem code 39 match.

Microsoft documents [IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usbioctl/ni-usbioctl-ioctl_usb_get_node_connection_information_ex) as a user-mode request to a USB hub, with an indexed connection-information buffer. Its [descriptor field](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usbioctl/ns-usbioctl-_usb_node_connection_information_ex) reports the descriptor returned during enumeration. Our tool issues only that request. Nine compile-only assertions against the installed Windows SDK verify the packed layout, offsets, pipe-record size and IOCTL value; six software cases pass. Native product sources/binaries were not rebuilt.

The actual response reports `DeviceConnected`, SL3 VID/PID, speed code 2, address 1, configuration zero and zero open pipes. The host query returned in 14,200 ns; that is a single cached-query observation, not audio latency or a guaranteed sampling cadence. Neither the descriptor nor `DeviceConnected` has been shown to distinguish `StoppedEnumerated` from `Stopped`.

The venv executable launched a separate Python producer. Both PIDs were later confirmed absent. This successful query closed normally, but terminating only the venv launcher's PID would not establish descendant containment on a future timeout. A repeated observer should launch the pinned base interpreter directly or use verified job containment before live integration.

`scripts/query-sl3-hub-port.py` plans by default. A live query requires `--run`, an explicit root-hub instance/port and a fresh output file; use a supervised child. `scripts/export-sl3-hub-port-baseline.py` reproduces the [actual baseline evidence](evidence/sl3-hub-port-baseline-20261101.json). This standalone observation has selected PnP recovery evidence, not a fresh full security attestation.

The next experiment should compare measured ordinary-user query samples with the mapped state transition during one bounded control capture. It must establish whether any returned field discriminates the two states before becoming a readiness gate. Full Windows audio, safe successive acquisition, current Serato admission and real two-deck DVS remain incomplete. No signing, binding or firmware change was made.
