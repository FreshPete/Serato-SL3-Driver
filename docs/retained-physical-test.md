# Native retained-device test — 30 October 2026

The owner-attended traced sequence passed on the current native worker: fresh input capture, silent duplex, then two one-second silent streams on one acquired SL3 connection with buffer disposal/recreation between them. Final cleanup released the device and retired audio, worker and private job without forced termination. [Checked metadata](evidence/retained-physical-20261030.json).

| Measurement | Stream 1 | Stream 2 |
| --- | ---: | ---: |
| Actual rate | 44,100 Hz | 44,100 Hz |
| Callbacks | 339 | 344 |
| Input frames / published output frames | 43,479 | 44,096 |
| USB OUT submissions | 984 | 998 |
| Successful OUT completions | 980 | 994 |
| Submitted output frames | 43,391 | 44,008 |

Both used eight USB intervals and 128-frame banks. Each restarted its callback frame position at zero. Audio I/O/callbacks retired and buffers were disposed after each stream while the device and worker remained held. One complete worker journal establishes one PID, one redirect, three clock getter pairs and one final close/helper unload. The final root record separately proves device/process release.

The final USB trace contains 58,075 events with no reported event/buffer loss. Secure Boot was enabled before and after; selected Windows recovery matched. The normal Rane SL3 resting identity returned, with no remaining device-test worker. No driver, registration, configuration, rate, firmware, trust or security-policy change occurred.

Native error 1168 is retained alongside zero stream fault; this aggregate field does not identify a particular canceled request. Published/submitted/completed counts remain distinct, and successful completion is not claimed for every submission. Software callback timing is not physical clock, continuity or latency measurement.

Local raw evidence is under `tests/results/local/retained-sequence-20261030-200120`. Worker SHA-256 starts `578AE92C`; probe starts `ACD89D42`; full hashes and source/prerequisite/trace bindings are in the metadata. The strict retained validator was rerun against both actual streams/journal and fresh prerequisites; trace ETL/XML and before/after hashes were independently rechecked. Raw USB/audio data remains local.

This passes the prepared within-object retained-lifetime test. Successive COM object release/recreation remains separate, as shown by the [current Serato lifetime analysis](serato-asio-object-lifetime.md). Controlled analogue mapping, audible/loopback tests, sustained timing, measured production configuration, actual application open and two-deck DVS are still required. The original Rane kernel driver remains rejected at rest; the working transport temporarily redirects through the installed signed UsbDk filter.
