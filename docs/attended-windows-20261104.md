# 4 November attended Windows test

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
