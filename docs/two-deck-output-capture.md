# Two-deck test with two RCA leads

The owner currently has Phase A connected to SL3 inputs 3/4 and Phase B to inputs 5/6, both set to LINE. Both remotes are on the same physical turntable. This can test simultaneous signal delivery and tracking on two Serato decks. Independent platter control still needs a later test with separate turntables.

Both stereo RCA leads are occupied by Phase. The previous output-to-AUX return for laptop-speaker monitoring is therefore unavailable. The new optional software recorder can produce separate WAV files to listen to through the PC after capture. It does not provide live laptop-speaker monitoring.

## What is recorded

The recorder taps a successfully dequeued ASIO output block in the retained device worker, before USB output submission. It preserves the original six-channel packed 24-bit little-endian PCM and its logical frame position. This establishes the software samples headed toward the SL3. It does not prove successful USB completion, physical RCA output or audible playback through the SL3.

The historical descriptor maps Deck 1 to logical output channels 3/4, Deck 2 to 5/6 and Deck 3 to 1/2. The exporter labels the logical pairs explicitly. Physical socket mapping remains a separate validation. See [routing analysis](serato-output-routing.md#conditional-historical-sl3-order).

## Recording contract

- Disabled unless the worker inherits `SL3_OUTPUT_CAPTURE_DIRECTORY` before its first audio start.
- The destination must be a fresh directory on a local fixed drive, with existing parents and no reparse points. Existing captures are never replaced.
- Storage for five seconds is allocated before audio activation. The recorder supports 44.1 and 48 kHz.
- Creation of `ready.json` means the recorder is prepared, not recording. Create an ordinary `arm.txt` file in that directory after both tracks are loaded and the platter is moving.
- The next complete dequeued output block begins the clip. Copying stops at exactly five seconds, potentially trimming the clip's final block without changing the original block.
- The stream path performs bounded copies and atomic state access. It performs no capture file operations, allocation, waits or locks. A separate background thread watches the arm marker and writes the completed clip.
- A rate change, discontinuity or malformed block seals the capture as failed. A stop before completion produces an incomplete diagnostic, not a successful short clip. Ordinary stream stop seals an unarmed capture too. A fresh capture requires a fresh worker/session.
- `capture.pcm` is followed by `capture.json`, published last, including frame count, first frame, rate and a SHA-256 of the PCM. Failed or partial files are never sufficient evidence of a completed clip.
- Recording faults do not change the audio payload or request device shutdown. An invalid opted-in destination prevents that diagnostic stream from starting.

## Export and listening

After completion, run `scripts/export-output-capture.py CAPTURE_DIRECTORY FRESH_EXPORT_DIRECTORY` with the project's Python interpreter. This is an offline operation and does not acquire the SL3. It validates the metadata, length and PCM hash before writing stereo 24-bit WAV files for each logical pair. `export.json` is published last and explicitly records that analog output and USB completion are unverified.

Each exported pair reports the longest run of zero-valued stereo frames and the longest run of identical stereo frames. These counts help identify muted or held samples during a continuous test signal. Music may contain intentional silence, and the counts cover only the captured software samples.

Use distinct tracks on the two decks so the two output files can be distinguished. For this first shared-platter test, check that both decks follow spin/stop movement, then arm the five-second recording while both are advancing. Listen to the exported Deck 1 and Deck 2 files through the PC. Keep raw recordings under ignored `artifacts/` or `analysis/`; do not publish recordings of commercial tracks as project evidence.

Do not attach desktop automation or leave startup instrumentation attached during this test. The existing successful manual-session route fully detaches its tracer before interaction.

## Paired RCA loopback capture

The paired-capture development build also accepts `SL3_LOOPBACK_CAPTURE=1` alongside a fresh `SL3_OUTPUT_CAPTURE_DIRECTORY`. Confirm the physical output and a separate LINE return pair before using this mode. Disconnect unrelated input sources because the diagnostic saves all six inputs and six outputs. Keep the track in INT and avoid a through or input-monitoring route that would feed the return back to the output.

Load the quiet, nonrepeating `artifacts/audio/SL3 Physical Loopback Test.wav` and enable a manual loop. Once the loop is playing, create `arm.txt`. The worker saves five seconds in each direction and publishes `capture.json` only after both files have been written. The input tap records USB input blocks after they enter the host queue. Each direction has its own first-frame position on the common worker timeline. The output-only mode still records only the output queue.

Use `.venv/Scripts/python.exe scripts/analyse-worker-loopback.py CAPTURE_DIRECTORY --output-pair 3 --input-pair 1` for a Deck 1 logical output and a logical 1/2 return. Adjust the pair numbers to match the observed route. The analyzer checks both hashes, searches for a clear stereo match within 100 ms and flags 20 ms windows where the aligned signals disagree. The resulting delay is from the worker's output timeline to its input timeline. Measuring ASIO callback round-trip latency requires the separate callback probe. The matched route, weak windows and any native faults need to be reviewed together.

The local test track is a synthetic, band-limited stereo signal at 44.1 kHz with a peak below −28 dBFS. Its SHA-256 is `58622b5e86cc0e2416bbcf61e0c2c32d83f16cc10ec05646c33f02664c903785`. Keep the track and captures local. The physical output mapping and the 64/32-frame Serato playback results are still open.

The 73-test Windows Release build covered capture and export through the real shared queues with synthetic input and output. The paired capture test also checks that a missing input prevents completion and a changed input hash prevents export. A separate synthetic analysis recovered 199- and 201-frame offsets from clips with different first-frame positions, reported a late gap and refused a silent return pair. The local native build record SHA-256 is `39c07e134f0ef397e42e5b15c34dbf1a5ee8127cf4e191d7fd9c3adb7c85b29c`. [Comparison installers](one-time-setup-window.md#serato-playback-comparison)

## Software validation and remaining live test

The native recorder test checks arbitrary start positions, exact packed-byte preservation, no allocation during copying, bounds, terminal partial-block trimming, sequence/rate/shape rejection and sealed results. The Windows lifecycle fixture uses the real shared output queue with synthetic six-channel samples. It verifies five-second captures at both supported rates, offline WAV channel order, early-stop refusal, invalid arm markers, file-write collision refusal and preservation of existing captures. The Python exporter regressions check signed 24-bit extrema, channel labels and refusal of incomplete, oversized or hash-mismatched input.

The subsequent attended Serato 5.0 test completed a five-second capture of 220,500 frames at 44.1 kHz. The owner confirmed both decks followed the shared platter in the requested REL test and Serato remained responsive. Channels 3/4 and 5/6 each contained nonzero music PCM, with no samples at the signed 24-bit clipping limit; channels 1/2 were silent. Deck 1 RMS measured approximately −17.89/−20.37 dBFS and Deck 2 −17.27/−17.47 dBFS. These measurements do not establish dropout-free playback or physical output. The raw PCM and WAV files remain private under ignored directories. [Live session evidence](evidence/phase-two-deck-session-20261105.json)

The session ended at the owner's request. The broker reported `owner_failure` and `successful=false`; I/O retirement, device release, worker exit, empty job and original-resource restoration all verified. The shutdown failure remains open. Mode labels were not independently observed, and both remotes shared one turntable, so independent platter control remains untested.

Before that live test, the refreshed Release build passed all 71 native checks, including the new recorder and Windows lifecycle tests. All 26 deployment checks and both exporter regression tests passed. A fresh private diagnostic bundle passed native destination and direct-import checks. The reviewed manual-session wrapper passed its read-only plan with original Serato resources, absent registration and no staged installer. The preparation evidence predates the live result above. [Software-only preparation evidence](evidence/two-deck-output-software-20261105.json)
