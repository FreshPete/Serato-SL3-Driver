# Attended SL3 release trace on 7 November 2026

After a 30-second power cycle, the refreshed production ASIO build acquired the SL3 and completed 1,034 callbacks during a three-second silent duplex test at 44.1 kHz. The worker retired I/O and released the device. Both owned processes exited normally.

| Observation | Result |
| --- | --- |
| UsbDk release | The worker logged successful detachment and redirection removal at 13:31:47.729 UTC. The observed detachment wait took 1.251 ms. |
| Stop window | Six isochronous requests reported `STATUS_CANCELLED`, three on input endpoint `0x82` and three on output endpoint `0x06`. The ASIO host and native retirement records both report success. |
| USB port | Hub events bind two successful enumerations to the worker's acquisition and release cycles on port 4. The original device, redirected device and post-release device each have a distinct state context. |
| Original stack startup | The post-release context entered the stopped and enumerated state. The startup timer fired 10.0001095 seconds after its last successful entry, followed by device and port disable events. The port reached the stopped state 10.0313277 seconds after the probe finished. |
| Device Manager | The original Rane binding reported Code 39 after the capture. |

The capture covered 60.020 seconds and decoded 147,471 events with zero reported event or buffer loss. The collector reached its automatic stop and its definition was deleted successfully. The first UsbDk decode left six transfer-error messages unformatted. Adding message 26 from the pinned MSI decoder resolved all six as cancellations and brought the decode to 27 UsbDk records with zero format errors or unknown formats. The offline analysis reused the existing port correlation and lifecycle readers. State labels use the cached PDB matched to the current hub image on disk. [Compact evidence](evidence/attended-native-stream-release-20261107.json).

The trace places this startup timeout after successful UsbDk release and re-enumeration, consistent with the earlier controls-only trace. Serato's successive ASIO opens need a transport lifetime that accounts for this handoff. A retained USB session is a design to evaluate because it can avoid returning the device to the original binding between opens. Any later reacquisition claim needs a separate observed test. The one-time Serato setup and normal launch remain to be tested. [Earlier controls-only result](attended-port-lifecycle-20261101.md).
