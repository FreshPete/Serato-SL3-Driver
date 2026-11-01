# Saved capture content and startup investigation

Offline analysis of the two archived 30 October input captures reveals substantially larger sample magnitudes in their first two stored packet records than in the remainder. This is a content observation, not a diagnosed firmware, converter, cable or transport fault. The original input wiring/intended signal was not recorded. Both captures explicitly lack verified continuity. [Exact source hashes, values and limits](evidence/capture-pcm-20261101.json).

| Recorded getter rate | Retained frames | Largest magnitude in full file | Largest magnitude after first two stored packets |
| --- | --- | --- | --- |
| 44,100 Hz | 1,411 | 8,386,111 | 1,118 |
| 48,000 Hz | 1,534 | 165,120 | 1,953 |

These magnitudes are signed-24 PCM code units, with negative full scale at -8,388,608. The largest 44.1 kHz value occurs in stream channel 3 at retained frame 6; the largest 48 kHz value occurs in stream channel 1 at frame 5. There are no exact rail-code hits. That does not establish absence of analogue clipping, nor does it justify calling the smaller remaining samples a measured input noise floor.

Both descriptive boundaries are at retained frame 11, because the first two stored packet lengths contain five and six six-channel frames. The boundary was selected after examining the data. Full statistics and exported WAVs retain every original sample. There is no automatic rejection, zeroing, normalisation, prefix removal or new audio-start policy.

The recorded packet frame-count histograms are `{5:125, 6:131}` at 44.1 kHz and `{5:9, 6:240, 7:7}` at 48 kHz. These support retaining the actual variable packet lengths; they do not measure clock frequency or prove gap-free USB timing. The stored order is the capture's request/packet order, not an independently recovered native USB frame timeline.

## Offline analyser

`scripts/analyse-capture-pcm.py` accepts only a completed finite UsbDk capture directory with `capture.json` and `capture.pcm`. It verifies the existing four-request/256-packet geometry, exact packet order/offsets, nonempty whole frames, successful recorded completion/status/cleanup fields, supported getter rate and complete PCM byte/frame coverage. The analyser does not reopen the device or re-attest the old capture's physical provenance. Its output hashes bind the metadata and retained PCM actually analysed.

It decodes six interleaved signed little-endian 24-bit channels and reports minima/maxima, maximum positions, mean, RMS, exact-integer-centred AC RMS, zero/rail/distinct-code counts and every packet's channel peaks. All-zero RMS is JSON null in dBFS, not an invalid infinite number. Channels remain numbered stream channels 0..5; no RCA-jack or deck association is inferred.

```powershell
./.venv/Scripts/python.exe scripts/analyse-capture-pcm.py `
  --capture tests/results/local/usbdk-capture-postrestart-20261030-01/capture `
  --output analysis/capture-content-<fresh-name> --describe-prefix-packets 2 --wav
```

The output directory must be new. `--describe-prefix-packets` requests a labelled post hoc comparison; full statistics still include the prefix. `--wav` writes `capture.wav` and never plays it. The WAV payload is byte-for-byte identical to `capture.pcm`. It uses [WAVEFORMATEXTENSIBLE](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ksmedia/ns-ksmedia-waveformatextensible), six 24-bit integer channels and a zero/direct-output channel mask, preserving stream order without assigning 5.1 speaker positions. This representation preserves recorded code bits; it does not measure effective converter precision. Its rate is the recorded getter value; WAV playback timing cannot reconstruct unknown gaps or prove latency.

The existing exports under `analysis/capture-pcm-44100-20261101` and `analysis/capture-pcm-48000-20261101` include the large stored-prefix samples unchanged. No output endpoint, audio API, helper DLL or device is opened by this tool.

## Verification and next physical requirement

Twelve focused software tests pass: signed extrema/endianness/all six channels, exact centred energy near a large DC, silence/JSON handling, packet/status/type/length/order refusals, frame-count failures, complete split coverage, an independent WAV reader and actual CLI fresh-output/refusal behaviour. The two real saved captures were then analysed and independently decoded from their WAVs back to the exact original PCM bytes. Their metadata/PCM/run hashes also match the earlier physical checkpoint. Regenerate compact evidence with `scripts/export-capture-pcm-evidence.py`.

Before interpreting analogue quality or enabling nonsilent/loopback experiments, record a known input, its wiring, line/phono state, controls and exact worker identity, then characterise the stored-prefix behaviour under the reviewed startup scenario. Investigate the original input-start handling and reproduce with a known signal before selecting any settling/discard policy. Do not silently trim these samples or extrapolate a duration from one post hoc split. Resolve the [release/readiness gate](sl3-release-port.md) before any successive-open experiment.

Physical jack/routing/gain mapping, sample continuity, output signal tests, measured round-trip latency and DVS are still pending. These files are from the earlier archived capture worker; they do not validate the current worker, Serato session or a four-hour stability run. No new hardware/UAC/driver/trust/security/firmware operation occurred. The exact raw captures, analyses, WAVs and source/tests are retained in `artifacts/build/checkpoints/capture-pcm-20261101`.
