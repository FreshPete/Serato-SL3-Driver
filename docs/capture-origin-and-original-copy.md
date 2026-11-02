# Saved packet-byte origins and the original PCM copy

Both archived finite captures reproduce byte-for-byte from their saved registered-buffer packet slices. Their large stored-prefix samples are already present in those saved source files. A selected original Rane kernel copy path preserves each sample's low three bytes, with six channels per frame, and a separate original ASIO instruction reports type 17. Together these checks support retaining the current packed-24 representation; they do not diagnose the startup anomaly. [Checked evidence](evidence/rane-pcm-copy-origin-20261102.json).

## Original selected copy contract

The unchanged x64 kernel is SHA-256 `e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5`; the original ASIO DLL is `e3d88039547b70915b1a9bc9e3e3f7dba32aaa9bc3ce8fd51616565ea1734141`. Neither was executed or loaded as code. Preferred VAs are used below.

In complete function `1301c:1395f`, the selected loop at `13469` reads a source DWORD, advances the source by three bytes and performs the masked destination store:

```text
destination = destination XOR ((source XOR destination) AND 0x00ffffff)
```

The loop advances that channel's destination by three bytes, selects the next channel pointer, and repeats six times. Its next frame therefore consumes eighteen source bytes. A checked second store site uses the same mask. The fourth destination byte is preserved; it is not a fourth PCM byte. The model deliberately supplies a synthetic fourth source byte instead of reproducing the vendor's wider load beyond a three-byte sample, and verifies independence from that byte.

This path is conditional on complete-object byte `+0x2c481` being zero. Its meaning and actual runtime value are not assigned here. The exporter binds the entire focused function to the exact original PE unwind extent, checks 26 selected kernel instructions, and checks the original ASIO type-17 store at `180010ddc`. This is a selected copy contract, not a new attestation of source-pointer/pipe direction, ring wrap, startup mode, routing or every original conversion path. The existing [clock/sample contract](clock-control-audio.md) and [current Serato packed-24 path](serato-packed24-path.md) retain their separate scopes.

## Saved-file origin checks

The auditor validates the recorded four-request/256-packet geometry and all successful completion/cleanup fields, then independently concatenates only each packet's recorded offset/length from the four 8,064-byte registered files. It compares every reconstructed byte with `capture.pcm`. It does not flatten slot padding. Both rates also produce the same six channel-byte planes under the selected masked-store model, with source guard bytes 0 and 255 and unchanged destination guards.

The largest samples map as follows. Channel/frame indexes are zero-based retained-stream indexes; these are not jack or USB-frame assignments.

| Recorded rate | Retained frame/channel | Saved request/packet | Registered byte offset | Signed sample code |
| --- | --- | --- | --- | --- |
| 44,100 Hz | 6 / 3 | 0 / 1 | 153 | 8,386,111 |
| 48,000 Hz | 5 / 1 | 0 / 1 | 129 | 165,120 |

All 1,411 and 1,534 retained frames remain unchanged. The ordinary three-byte copy model preserves these values; it does not turn them into a smaller value, remove a header or scale them. No samples are discarded, replaced, normalized or played. No new startup trim/mute policy follows from this observation.

The historical run, capture-record and packed-PCM hashes match the earlier physical report. **No contemporaneous hash witness for the registered-buffer files was found.** All eight raw files also match their copies and hashes in the earlier `com-activation-20261102` private checkpoint. That later witness strengthens file continuity through 2 November; it is not a capture-time witness. New hashes bind the files read now. Equality with historical PCM is useful file evidence; it does not independently establish that these raw files are unchanged since capture, that the helper/DMA path was correct, that the ADC produced valid samples, or what signal was wired. The startup cause, sample continuity, analogue quality and effective precision remain unknown.

## Reproduce and verify

```powershell
.venv/Scripts/python.exe scripts/audit-capture-origin.py `
  --capture tests/results/local/usbdk-capture-postrestart-20261030-01/capture `
  --output analysis/capture-origin-NEW.json
.venv/Scripts/python.exe scripts/export-rane-pcm-copy-evidence.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_capture_origin.py
```

Outputs must be new. The generic auditor accepts saved files only; the exporter additionally needs the pinned local original binaries, focused report and two historical captures. Regeneration is byte-identical and existing-output refusal preserves the evidence. Six new tests cover signed extrema/all channels, source and PCM corruption, nonzero padding, exact request shape/types, packet faults/order/partial frames and masked-store guards. The twelve existing PCM-analysis tests also pass.

Native Release/Debug source readsets, build manifests and DLL images remain unchanged; native suites were not rerun. Raw registered buffers, PCM and focused vendor output remain private. No driver/binding/trust, firmware, ASIO configuration, Serato session or physical audio operation ran. The next useful measurement still needs a documented known input, wiring and control state after the attended recovery/readiness test. Physical mapping/levels/timing and current Serato/two-deck DVS remain unfinished; Mac is deferred.
