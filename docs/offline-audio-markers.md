# Offline audio channel markers

The file-only tool [analyse-audio-markers.py](../scripts/analyse-audio-markers.py) supplies a repeatable signal and analysis for future analogue channel identification. It never opens an audio device, plays sound, changes controls or invokes the native worker. There is no physical audio result yet, and no new playback/capture workflow is admitted by this tool.

Generation creates a two-second, six-channel, packed PCM24 WAV at 44.1 or 48 kHz. Each logical output index has a distinct hash-derived 4096-frame marker in its own time slot. The digital peak is 0.015 full scale, about −36.5 dBFS. This does not establish analogue voltage, safe phono-input level, gain, physical jack order or channel calibration. Indexes 0–5 deliberately have no physical jack labels.

```powershell
.venv/Scripts/python.exe scripts/analyse-audio-markers.py generate --rate 44100 --output analysis/sl3-markers-44100.wav
# With a separately recorded packed PCM24 capture at the same rate:
.venv/Scripts/python.exe scripts/analyse-audio-markers.py analyse --reference analysis/sl3-markers-44100.wav --capture analysis/separately-recorded-capture.wav --output analysis/new-marker-analysis.json
```

Both outputs must be new files. These commands only write/read files. Analysis accepts the exact canonical reference, one to six captured channels and no more than ten seconds. It rejects other sample rates/formats, inconsistent/truncated payloads and oversized declared frame counts before allocating their payloads. NumPy `2.3.4` is pinned in the analysis requirements and installed in the private virtual environment; production native dependencies are unchanged.

Each captured channel is compared with all six reference markers using zero-padded linear FFT correlation, normalized after removing the local DC component. The implementation follows the correlation convention documented by [NumPy](https://numpy.org/doc/stable/reference/generated/numpy.correlate.html) and uses its [real-input FFT](https://numpy.org/doc/stable/reference/generated/numpy.fft.rfft.html). It preserves polarity, best/runner-up matches and possible repeated peaks. A candidate requires absolute correlation at least 0.8, separation of 0.15 from the next reference, no other separated peak at least 0.8, and no full-scale rail samples. These are diagnostic heuristics, not measured hardware acceptance thresholds. Filtering, noise and clock drift can reject an actual route; the tool does not resample, repair or hide them.

`relativeFileOffsetFrames` is reported only for an accepted correlation candidate. It includes arbitrary playback/capture file origins and must not be interpreted as ASIO, converter or round-trip latency. All reports explicitly retain `physicalChannelMappingVerified=false`, `measuredLatencyAvailable=false` and unverified file provenance. Even an exact file match cannot prove the samples traversed the SL3. Actual mapping needs recorded wiring, exact runtime/device provenance, a reviewed nonzero-output experiment and independent capture. Measured latency additionally needs a common timing origin and an appropriate measurement design; this tool does not populate a production latency profile.

Fourteen software cases pass: FFT results against independent direct-window calculations, synthetic delayed/permuted/inverted packed PCM24, silence/noise rejection, mixed/repeated-marker ambiguity, full-scale rail detection, rate/reference mismatch, truncation, PCM boundaries/nonfinite values, CLI overwrite refusal and oversized declared frames. Both rates are covered. These tests use synthetic files, with no audio device access, and establish neither physical channel order nor DVS.


The later [input recording diagnostic](input-record-probe.md) can preserve a nominal three-second six-channel callback prefix and export its exact validated bytes to WAV. Separate-process simulated recording/export/marker integration passes; its synthetic input is correctly rejected as a marker route. An attended native recording/traced runner and reviewed nonzero source/wiring test remain unrun.
