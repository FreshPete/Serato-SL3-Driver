# SL3 left-deck through-routing baseline

On 13 November 2026, Phase A fed the physical LEFT DECK inputs (stream channels 3/4), and an RCA lead connected LEFT DECK OUT to AUX IN. Both inputs were set to LINE. The operator confirmed the Phase remote was spinning. Serato was closed.

The independent input recorder sent zero PCM to the SL3 and captured 132,352 six-channel frames at 44.1 kHz. During 1.5–2.5 seconds of the recording, channels 3/4 measured approximately −12.4 dBFS RMS and both peaked near 976 Hz. The AUX return on channels 1/2 was about −98 to −99 dBFS RMS over the same interval. There was no usable through signal on that return in this run.

The collector recorded 148,557 USB trace events with zero reported events or buffers lost. The validator accepted the run and confirmed selected before/after recovery. The probe and worker retired and released the device normally. The capture made no routing or sensitivity writes and did not query the control table during the stream.

Local run: `tests/results/local/physical-through-20261113-phase-live`. The saved PCM SHA-256 is `4659f8b5cfa019ac6ff4d98472b1d21ae1764d850f6a2a088b2464f660f6c43b`. The validated run record SHA-256 is `6a807694acf7ac46daa0b429ed39931bf2fa87e8f81d3b6c235a5cfdbe75e29a`.

## Output and return check

A separate ordinary-user run sent 650 ms USB markers to output channels 3/4 through the same RCA lead. The 997 Hz marker appeared on AUX channel 1 at −29.97 dBFS peak and the 1301 Hz marker appeared on AUX channel 2 at −30.03 dBFS peak. Each fit explained over 99.8% of its return channel's centred energy. A strong Phase tone near 997 Hz was already present on channels 3/4 before the marker, so the analyzer rejected the first marker under its all-channel isolation rule. On AUX channel 1 the 997 Hz component increased from below −120 dBFS peak outside the marker to about −30 dBFS during it. Both AUX returns followed the marker envelopes. The worker released the SL3 and exited normally. This run had no USB trace.

Local run: `tests/results/local/physical-through-20261113-deck1-marker`. The saved PCM SHA-256 is `b95c77ce2c2c014bac09f240c8f56a2481efd7622083f2692c7864636e65d881`.

With the platter stopped and the wiring unchanged, both markers passed the analyzer's isolation and envelope checks. Return levels were −29.97 dBFS peak on AUX 1 and −30.03 dBFS peak on AUX 2. The probe released the SL3 and exited normally. Local run: `tests/results/local/physical-through-20261113-deck1-marker-quiet`. PCM SHA-256: `10edfad47cb99147d39c7c680fe21fafaf02ac95934efc29e2a6333b2cd84789`.

The subsequent ordinary-user read-only probe passed its record validator at 44.1 kHz, reported LINE, sensitivity code 5 and raw through value 1 on all three groups, and released the device. Local run: `tests/results/local/physical-through-20261113-controls-local`. This separate read does not establish the table state during either recording.

A through comparison needs a verified control state when sampling the return. The current setting probe and recorder acquire separately, so state persistence across acquisition is an open question. The PHONO sensitivity measurement needs a phono-level source.

## First through toggle

The ordinary-user setting probe changed group 1 from raw 1 to raw 0 and verified that the other 21 table bytes stayed the same. Group 1 was chosen from the historical slot ordering as a candidate for LEFT DECK. Its physical mapping remains open. Local run: `tests/results/local/physical-through-20261113-group1-on`.

The following 44.1 kHz recording sent zero USB PCM and passed the recording validator. It contained no usable Phase signal on either the direct 3/4 input or the AUX return. The middle half-second measured approximately −101 dBFS RMS on inputs 3/4 and −96 dBFS RMS on AUX 1/2. The capture is inconclusive for through routing. Local run: `tests/results/local/physical-through-20261113-group1-phase`.

Both restore attempts stalled at UsbDk redirect startup before reading or writing any control. After the operator power-cycled the unit, the ordinary-user read-only probe returned the original 22-byte table exactly, including through value 1 on group 1. Local runs: `tests/results/local/physical-through-20261113-group1-restore`, `tests/results/local/physical-through-20261113-group1-restore-retry` and `tests/results/local/physical-through-20261113-after-power-cycle`.

## Baseline checks before retry

Two three-second captures with zero USB output found no sustained Phase tone on inputs 3/4. The second showed a brief low-level signal before returning to about −100 to −102 dBFS RMS on those channels. Both recordings finished and released the device. The routing was left at its original setting. Local runs: `tests/results/local/physical-through-20261113-retry-before` and `tests/results/local/physical-through-20261113-retry-before-second`.

After the operator confirmed Phase A was spinning, the first capture failed before saving PCM and its worker exited. The next capture showed a sustained 990–992 Hz tone near −12.4 dBFS RMS on inputs 3/4 with AUX near its noise floor. The setting probe then changed group 1 from raw 1 to raw 0 and verified the full table. The zero-output recorder stalled inside the next UsbDk redirect before recording any samples. After the operator power-cycled the unit, a read-only probe returned the original table and released the device. This attempt establishes the input baseline and the verified control write. Whether the Phase signal reached AUX with the changed state remains open.

Local runs: `tests/results/local/physical-through-20261113-confirmed-spin-retry`, `tests/results/local/physical-through-20261113-spin-group1-on`, `tests/results/local/physical-through-20261113-spin-group1-after` and `tests/results/local/physical-through-20261113-spin-group1-check`.

## Single USB connection

The `sl3_usbdk --through-capture --helper FILE --output NEW_DIRECTORY` diagnostic captures six input channels at 44.1 kHz with zero USB PCM. It requires a sustained signal on both deck channels before it will compare the original 22-byte table and change group 1. It drains and restarts the stream on the same USB redirect and verifies the original table before closing if a write may have occurred.

The first run saved two seconds of baseline PCM. Inputs 3/4 measured about −74 to −75 dBFS RMS in the middle second, with no sustained Phase tone. The diagnostic closed the redirect before any routing write. The first build then failed while writing the helper-unload journal because the journal object had already closed. The lifetime order was corrected and the diagnostic rebuilt. Local run: `tests/results/local/physical-through-20261113-single-open`.

The rebuilt diagnostic passed all 67 Release checks. Its second live run again recorded no sustained tone on inputs 3/4. It completed the USB close and helper unload without a control write. Phase rotation was not confirmed during either single-open capture. Local run: `tests/results/local/physical-through-20261113-single-open-retry`.

With Phase A confirmed spinning, the next run completed the baseline, group 1 toggle, second capture and restoration on one USB redirect at 44.1 kHz. Both two-second captures sent zero USB PCM. In the middle second, inputs 3/4 remained at about −12.4 dBFS RMS. AUX 1/2 rose from −77.95/−77.25 dBFS RMS to −12.40/−12.45 dBFS RMS after the toggle and carried the same Phase tone near 991 Hz. This verifies that group 1 raw value 0 routes the physical LEFT DECK input through LEFT DECK OUT to the AUX return with the stated wiring. The probe restored raw value 1, verified the original 22-byte table and closed the redirect normally.

Local run: `tests/results/local/physical-through-20261113-single-open-spinning`. PCM SHA-256 before: `bba06c528880cea4f6bfa7cb21ae944abedd9ff287c840afd82b3b09595e58a9`. After: `b5b69b8363eb603c914c0a904887b90ea97e42edab871afbca3eed5baf2d03e5`.
