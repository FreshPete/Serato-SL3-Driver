# Finite input PCM recording through the diagnostic host

The new `sl3_input_record_probe` preserves a nominal three-second prefix of all six input channels through the existing worker/diagnostic host. Output buffers remain zero. This supplies the longer PCM missing from the old 32 ms finite USB capture and statistics-only host probe. It does not establish a physical recording, measured latency, channel mapping or a current Serato session.

## Collection contract

The native and explicitly simulated executables have an inert default/`--plan`. Explicit recording requires a reviewed worker path/hash, helper path, new output directory and expected getter rate of 44.1 or 48 kHz. The program uses the existing one-open `start_checked` diagnostic entry, not inspect/close/reopen. The native factory must match that rate on its acquired device before audio activation; no rate setter or control setter is requested.

The requested prefix rounds three nominal seconds up to a whole 128-frame bank: 132,352 frames at 44.1 kHz and 144,000 at 48 kHz. Those are 2,382,336 and 2,592,000 packed PCM bytes respectively. A preallocated collector copies every channel's three little-endian container bytes, with no sample conversion, filtering, startup trimming, callback allocation or callback file writes. Source frame zero and sequential whole banks are required. This is the first SDK callback prefix; earlier bridge/worker buffering and independent USB packet completeness remain separate, and the zero startup-discard count describes this collector only. Capturing signed-24 container bits does not measure converter precision.

After the prefix is complete, additional callbacks are explicitly counted as `trailingCallbacksNotRecorded` until the control thread stops the session. They are outside the declared finite prefix; the diagnostic does not claim to save every sample acquired by the worker. Missing/repeated logical positions, invalid planes, bank errors and collection faults prevent a successful result. The collection deadline is six software seconds, with the independent twenty-second process watchdog still covering startup/retirement. A simulated transport can deliver three nominal seconds much faster than wall time; neither quantity is a measured ADC clock.

Each callback clears all six output planes. The default simulated worker fixture additionally rejects a nonzero submitted payload. Its separate 44.1 kHz clock-file fixture checks the other rate/rounding path, without implying a physical packet clock or independent output-level test. The test-only clock flag is refused by the native executable before it creates an output directory.

## Evidence and retirement

The program writes new flushed phase records, then requests normal stop and checks worker, I/O and callback retirement before reading callback-owned PCM or observations. A retired partial recording can retain its actual captured prefix with an unsuccessful result; unused capacity is never saved as artificial zero samples. Successful results require the full prefix, expected observed rate, successful stream counters, normal retirement and disposed buffers.

If retirement is unproved, the program writes only a separate failure snapshot and exits through process containment. It does not read potentially live PCM, unwind callback storage or report successful cleanup. The native-kind rejection test exercises that conservative path using a truthful simulated worker; it is not a physical USB test or a proof of kernel quiescence.

Completed evidence consists of:

- `input.pcm`: interleaved six-channel packed PCM24 callback prefix, including startup.
- `result.json`: exact byte/hash/geometry, recorded and trailing callback counts, per-bank logical position/publication/QPC/bank observations and retirement state.
- Native mode's `worker-1.tsv`: original worker startup journal, hash-bound after retirement.

The native journal validator requires one acquisition, one fresh getter, one release and helper unload, with complete ordered records. Extra acquisitions, setters, incomplete tails or different worker PIDs are refused. The simulated case must not contain a native journal. Startup markers do not establish packet continuity, kernel quiescence or next-open readiness.

Software timestamps and logical frame counters are not ADC/DAC playheads or a common analogue round-trip origin. No production timing profile, ASIO registration or configuration is read/written by this diagnostic. It uses the diagnostic `HostSession`, not a deployed ASIO facade, so production profile requirements are unchanged.

## Offline validation and existing marker analysis

`scripts/validate-input-record-probe.py` validates successful saved evidence without opening a device. It checks kind/worker binding, exact prefix and byte coverage, strict integer/Boolean fields, sequential observations, retirement, native journal grammar and the original PCM hash. Duplicate JSON keys and nonfinite JSON numbers are refused. It always leaves physical provenance and latency unverified.

The optional `--wav-output NEW_FILE` wraps the validated bytes in a six-channel PCM24 WAV at the recorded nominal rate, without changing the payload. Both input hashes are rechecked before writing; an existing output is never overwritten. Add `--simulated` only for explicitly simulated recordings. This file-only step can feed the existing [marker analyser](offline-audio-markers.md). It cannot turn a file offset into latency.

```powershell
.venv/Scripts/python.exe scripts/validate-input-record-probe.py <saved-directory> `
  --worker-sha256 <reviewed-lowercase-worker-hash> --wav-output <new-file.wav>
```

No physical native recording was launched for this checkpoint. The dedicated [InputRecord traced workflow](input-record-trace.md) is now prepared offline, with this executable in the before/after process guard. A native recording still needs a fresh plan, resting-device/readiness checks and owner availability for recovery; existing controls/facade/broker-scope scenarios cannot qualify it. The existing [supervised queue](next-tests.md) remains relevant; this executable does not automatically arm or retry a hardware test. Nonzero marker playback needs its own reviewed source/wiring/level experiment. Phase is not assumed to be a calibrated sine source.

## Verification

The core tests compare every interleaved byte, including signed container extremes, assert no C++ allocations in the prefix/trailing path, and exercise guards, sequence faults, sealing and no partial-bank copy. Separate-process simulated runs preserve every expected packed byte at both rates. CLI checks cover inert plans, invalid options/rates, existing-output preservation, native fixture-flag refusal, genuine kind mismatch containment and rate mismatch before streaming. WAV export preserves the exact payload.

Nine synthetic evidence tests cover both rates, count/type/geometry/deadline mutations, unsupported claims, frame/time/bank discontinuities, PCM corruption/truncation, strict JSON and native-journal grammar. A synthetic native grammar fixture remains explicitly unverified physical provenance. The recorded synthetic WAV was also read by the existing marker analyser and correctly rejected as a marker route.

Release and Debug each pass 64/64 native checks, and the SDK-free build passes 39/39 (the recorder core, with the SDK-dependent probe excluded). Each SDK build also runs 18 simulated/CLI cases within its recording lifecycle test. The [verification record](evidence/input-record-20261102.json) binds exact builds, tests, private synthetic artifacts and source versions. No hardware recording, new binding/trust, firmware, rate/control write, protected deployment or Serato operation ran. Physical input/output mapping, analogue levels, timing/latency, stable reopening and genuine current Serato/two-deck DVS remain required. macOS remains deferred.

The saved prefix also feeds [known-input tone analysis](known-input-tone-analysis.md#three-second-recorded-prefix-input) through its separate `--recording` mode. This preserves the recorder schema/worker/journal bindings, all prefix samples and four predetermined callback windows. The adapter is verified offline at both rates; no known physical source or native recording is claimed.
