# 4 November attended Windows test

## 13:38 UTC follow-up

The follow-up completed with one 44.1 kHz control acquisition and no audio. Both launcher roles and the observer retired with exit code zero. The independent controls validator confirmed selected recovery. The USB trace reported 7,672 events with zero events or buffers lost. The image rundown validator matched USBHUB3 version metadata across the USB window and retained a decoder schema warning.

The port observer completed 72 observations. The phase analyzer accepted 40 whole snapshots while driver startup was pending and 29 after the port reached its stopped state. It excluded one malformed enumeration reply and two observations outside the selected phases or crossing their boundaries. Every accepted snapshot had the same fingerprint across both phases, including `DeviceConnected`, the matching SL3 descriptor, configuration zero, no open pipes and devnode problem 39. There were no disjoint fields. These ordinary-user fields cannot distinguish the two phases in this run.

The next design to validate is one retained UsbDk acquisition shared across client lifetimes. The existing [broker scope diagnostic](broker-scope-probe.md) exercises this in software and has an attended read-only [trace workflow](broker-scope-trace.md). This run supplies no safe reopen threshold and performed no second acquisition. Keep the raw USB, image and observer records local.

## Initial attempt

The 2 November packet ran once on 4 November. The ordinary-user Release worker redirected the SL3, read back 44,100 Hz and the full 22-byte control table, then closed the redirect. The physical probe validator passed. The run performed no second acquisition, audio transfer or rate change.

The independent root-hub observer recorded two valid samples for port 4. At 11:53:47.974736 UTC its third query returned 35 bytes with index 0, status 9 and an all-zero device descriptor. The query rejected the mismatched index, preserved the raw response and stopped without retry. The supervisor recorded exit 1 and confirmed that the observer retired. This reproduces the malformed response seen during the earlier handoff. It gives no valid port sample for that instant or for recovery afterward.

The USB collector retained a 20-second ETL. Offline decoding with tracerpt processed 7,563 events across 213 buffers. The trace header reported zero events lost and zero buffers lost. The live state observer retained 486 rows and passed its live consumer/source consistency check. Source XML alignment and the combined image window were not validated. The explicit USB stop returned an error after the timed window. Neither named trace session was running at the follow-up check, and Windows again listed the original Rane SL3 with Code 39.

The combined collector left its start and intermediate image-source records but no terminal result. The cause of the missing terminal record is undetermined. Treat the packet as spent. The next diagnostic needs to preserve the malformed hub reply as a gap and capture later observations under the same fixed deadline, with port and descriptor checks applied to each valid sample. It also needs to retain collector retirement and the image-source stop/export outcome. These are prerequisites for evaluating a safe reopen, alongside a separate known-input audio test and eventual current-Serato DVS validation.

## Offline release timeline

Tracefmt decoded the same 7,563-event ETL with the pinned UsbDk message formats. It reported zero lost events, format errors and unknown formats. The USBHUB3 times below come from the saved ETL decoded with tracerpt. State names use the cached image and PDB interpretation.

| UTC on 4 November | Observation |
| --- | --- |
| 11:53:47.9373586 | UsbDk reported redirect removal successful in the worker's trace. |
| 11:53:47.9420353 | USBHUB3 started enumeration on the mapped root-hub port 4. |
| 11:53:47.9434963 | The redirect child's state context reached `WaitingToBeDeleted`. |
| 11:53:47.973557–47.974736 | The port-4 query returned the rejected zero-index reply. |
| 11:53:48.0404371 | USBHUB3 reported successful enumeration on port 4. |
| 11:53:58.0446694 | The post-release child context reached `Stopped` after the driver-start timeout and port-disable states. |

The bad query interval falls wholly inside post-release enumeration. The observer supplied no valid sample after that interval. The original run record lacks the probe-completion timestamp, so the strict release correlator cannot validate the full lifecycle. UsbDk's removal-success event came before the redirect child's final deletion state and cannot stand in for probe retirement. The timeline provides no reopen threshold.

Windows event logs independently identify the driver failure after enumeration. Code Integrity Operational event 3077 (record 89086) reports a signing-level or policy block for `strmdrv.sys` at 11:53:48.0500192 UTC. Kernel-PnP event 219 (record 83700) reports the corresponding load failure at 11:53:48.0501883 UTC. This places the block about 9.6 ms after successful USB enumeration. It explains the original-driver failure, while the UsbDk control read belongs to the earlier redirect.

The block event's XML identifies the enforcing policy as **Microsoft Windows Cross Certificates for Code Integrity Exceptions Policy**, version `10.29611.0.0`, with status `0xc0e90002`. The ordinary-user policy inventory query returned access denied, so this identification comes from the historical event, whose policy GUID matches the block message.

Application events show the Codex sandbox service stopping at 11:54:09.9993725 UTC, after the USB trace window but before the configured image collection window could finish. The events do not identify the collector PIDs. They provide a possible interruption point for the missing reports, with process-exit causality still unresolved.
