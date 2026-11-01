# First real read-only USB identity baseline

The pinned installed Serato libusb library successfully enumerated the SL3 on this Windows host while the original Rane driver remained blocked. One supervised request for five seconds produced **four complete samples with the same identity**, then closed its context and exited normally. This validates the observer's actual ABI/API path and cleanup. It is not a USB redirection, audio-driver or current Serato/DVS result.

Local record: `tests/results/local/usb-identity-baseline-20261030-01`. [Verified source/file hashes, child result, sample timings and derived cadence](evidence/usb-identity-baseline-20261030.json).

| Observation | Actual result |
| --- | --- |
| Library | Installed `libusb-1.0.dll`, SHA-256 `68883bc3254dbb4129cf68b49f9efe149cd50fd15e990c58a94a53d3ed4f7151` |
| SL3 identity in every sample | VID 0x1cc5, PID 1, USB revision word 0, bus 3, address 1 |
| Completeness | Four complete snapshots; zero descriptor failures; twelve devices enumerated per sample; only SL3 identity fields retained |
| Sampled changes | Zero across three comparable adjacent pairs |
| Host enumeration duration | 1.326–1.344 seconds per call sequence; mean 1.336 seconds |
| Return-to-return sample gaps | 1.576–1.595 seconds; mean 1.585 seconds |
| Requested post-call sleep | 250 ms; this is additional to synchronous enumeration |
| Final loop elapsed / child lifetime | 6.096 / 6.405 seconds; final synchronous call crossed the requested five-second loop duration |
| Process retirement | Exit 0, no watchdog timeout or forced termination; `context_closed` present |
| Post-run resting state | SL3 present, original `strmdrv` / `oem136.inf`, problem code 39; no SL3 test/observer process remains |

The supervisor and independent validator accepted the actual complete lifecycle, exact producer/library hashes, fixed command, raw-record hash, timing window and confirmed child exit. The supervisor did not need elevation or an owner action. The task's autonomous read-only diagnostic scope allowed this check; no ownership handoff or audio test was attempted.

The revision word is descriptor data, not an identified firmware version. Enumeration duration covers the whole host-side call sequence; it does not identify which libusb function or Windows backend stage accounts for the delay. The monotonic host timings are not a measurement of SL3 sample-clock accuracy or audio latency.

## Consequence for the next diagnostic

The observer's requested interval is a sleep after a synchronous enumeration. It is not an achieved polling period. The integrated control trace requests 50 ms, but that mode has not run on hardware; this baseline cannot establish its exact cadence. It does establish that assuming millisecond-scale coverage from the interval alone is unjustified on this host.

Returned identities were stable in these samples. Short changes may be missed, and libusb caching remains an interpretation limit. No guaranteed transient-detection duration can be derived. The prepared [shared control/USB/WPP trace](controls-probe.md#optional-identity-observation-in-the-shared-trace-window) must retain measured observation intervals and actual lifecycle events. Its held-device and Serato-coexistence flags remain false.

There is no before/after full security/device-state attestation in this standalone run. The saved post-state confirms the original failed-driver resting binding, not a repaired audio driver. Secure Boot was not freshly queried; no security setting changed. No USB redirect, rate/control setter, audio alternate/endpoint activation, firmware request, driver binding, ASIO registration or application change ran.

## Reproduction of saved evidence

These commands read the saved result and original producer sources; they do not load the vendor library or repeat the physical observation:

```powershell
.venv/Scripts/python.exe scripts/supervise-usb-identity.py --validate tests/results/local/usb-identity-baseline-20261030-01
.venv/Scripts/python.exe scripts/export-usb-identity-baseline.py
```

Four cadence-analysis tests distinguish requested sleep from observed gaps and reject incomplete, overlapping, regressing or nonfinite timing inputs. The full Python suite passes 109/109. Native sources/binaries and their preceding 39/39 Release, 39/39 Debug and 25/25 SDK-free evidence are unchanged; no native rebuild was needed for this observation.
