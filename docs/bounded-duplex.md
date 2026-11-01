# Bounded duplex ownership and silent-output test

The [first physical runs on 30 October](first-physical-usbdk-tests.md) now pass silent duplex at 44.1 and 48 kHz, including actual completion, zero-buffer and recovery checks. Earlier preparation-only observations below are historical. Analogue output, continuity, latency and application integration remain unverified.

A finite duplex pipeline and native UsbDk test mode are now implemented. The pipeline prepares both directions, derives output lengths only from successful completed input packets, and retires all pending work before releasing storage. **The hardware mode has not been executed; no audio OUT request was submitted in this work.**

This advances transport/session ownership. It is not yet a continuous audio session, an ASIO driver or proof of working SL3 playback.

## Request pipeline

`src/core/duplex.cpp` uses up to four input/output pairs. Even resource slots are IN; the next odd slot is its corresponding OUT. It prepares all resources before any I/O, submits the input requests, then stages/submits each output only after its input completes successfully. It waits for all outputs before success.

A single five-second operation deadline and shared two-second drain deadline bound the transaction. Any error first cancels **every pending direction**, then drains completions. Cancellation alone never permits freeing memory. Unknown completion or failed release returns the retained slot IDs; the isolated native diagnostic records that failure and terminates without unwinding pending storage. Windows performs process I/O teardown. Its existing 20-second watchdog also bounds blocked synchronous APIs and device cleanup.

This permits a valid earlier output request to be pending when a later input fails. The tests specifically verify cross-direction cancellation in that case, rather than assuming input and output can be cleaned up independently.

## Silent output layout

The native mode prepares eight independent requests: four × 64 intervals IN on 0x82 and four matching OUT on 0x06. At the descriptor's high-speed interval, this is **32 ms planned per direction**, not proof of a gap-free stream or total elapsed duration.

The shared `stage_silent_output` validates every full-width packet status/length before changing output storage. Empty/error packets, lengths above 126 or nonmultiples of 18 fail; there is no 108-byte recovery substitution or narrowing of an invalid 64-bit value. It copies the accepted lengths and zeros the bounded output buffer. UsbDk converts the size array into cumulative URB offsets; the request's total buffer length is the sum of those sizes.

The test can send only **zero PCM**. It has no file/waveform/output-channel routing option. All output storage is prepared before requests are submitted. The only device command remains the observed 0x30 rate getter; no 0x31, 0x36, routing, reset or firmware command is added.

OUT completion checks request and packet statuses. Returned OUT packet lengths are recorded but **not interpreted as actual transmitted byte counts**: Windows defines the length field as an IN result and does not use it for OUT. Requested sizes, reported request bytes and completion status remain separate evidence. [Microsoft URB contract](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usb/ns-usb-_urb_isoch_transfer).

## Native record and recovery

Explicit `--duplex-silence` writes a fresh `duplex.json` and local raw buffer snapshots. Records include direction, resource/packet index, requested lengths/cumulative offsets, uninterpreted returned lengths, Win32/USB/packet status, submission/completion times and counts. Attempted output requests/bytes and API-accepted requests/bytes are counted separately; neither proves analogue playback. A synchronous API failure is recorded as terminal failure, not as a claim that no USB attempt occurred.

Before potentially queuing output, progress records mark its submission count **unknown**. An interrupted process must not be assumed to have sent zero requests. On a normal result, attempted/API-accepted counts and retained leases are recorded explicitly. Normal cleanup restores attempted audio alternates to zero and stops redirection; failed cleanup is a failed test.

UsbDk's scheduling is ASAP. The record explicitly leaves continuity, actual sample-clock validation, analogue output and alternate readback unverified. Even a successful transport result would not establish audio quality, physical channel mapping, DVS, latency or Serato integration.

## Tests actually run

Ten native checks pass in Release/Debug with the SDK component enabled; a separate SDK-free build passes nine. Duplex tests cover full preparation before I/O, input-gated output staging, one/four pair bounds, partial preparation/submission, input/output completion failures, invalid input, cancellation exceptions, shared deadlines, retained IN/OUT requests and failed resource release. The real staging helper is tested for variable lengths, all-zero bytes, invalid/empty/oversize/unaligned packets, high status bits, insufficient storage and atomic rejection.

CLI tests reject combining capture-only and duplex modes before device access. The read-only preflight checks the rebuilt binary/source identities and plan-only behaviour. The real `--duplex-silence` mode was **not invoked, even as a missing-driver test**. [Build and preflight evidence](evidence/bounded-duplex-build.json).

## Owner-present hardware sequence, still pending

First run the already-prepared WinUSB IN-only capture. Establish real packet lengths, statuses and frame counts before expanding the physical experiment.

Separately validate installation/loading of the unchanged Microsoft-signed UsbDk package under normal Secure Boot/CI, its descriptor-only list, and then its IN-only capture. No UsbDk installation has happened while the owner is away. The system-filter installation/recovery gate remains separate from this command.

The prepared wrapper defaults to a plan. It requires an already elevated PowerShell 7.5+ terminal and already running UsbDk; it does not install the filter, import trust or request elevation. Its explicit modes start the passive trace before launching the bounded native scenario. Use fresh directories for each step:

```powershell
./scripts/test-usbdk-traced.ps1 -Mode List
# Owner-present sequence, after the separate driver-load/recovery gate:
./scripts/test-usbdk-traced.ps1 -Run -Mode List -ResultDirectory tests/results/local/usbdk-list-01
./scripts/test-usbdk-traced.ps1 -Run -Mode Capture -ResultDirectory tests/results/local/usbdk-capture-01
# Only after the capture result is reviewed:
./scripts/test-usbdk-traced.ps1 -Run -Mode DuplexSilence -ValidatedCaptureRun tests/results/local/usbdk-capture-01 -ResultDirectory tests/results/local/usbdk-duplex-01
```

Afterward, correlate every input/output dispatch and completion with the native record; inspect lost-event counts, cleanup, enumeration and original descriptors/security state. A failed or ambiguous result must not lead to an automatic retry, guessed command replay or audible output.

The wrapper checks tested source/executable identities, a live trace session with enough time remaining, native deadlines, successful native cleanup, ETW loss counters and baseline device/driver/security/application recovery. It saves raw ETL/XML and state locally. Stuck native/decoder children are terminated after bounded waits; a stuck recorder permits cleanup only of its uniquely named, successfully created session. Any timeout fails the run even if cleanup succeeds. [Offline verification record](evidence/usbdk-traced-run-preparation.json).

Before silent output, `validate-usbdk-capture.py` requires capture evidence from the same native executable, checks the decoded trace hash/header/session, snapshot hashes, packet statuses and times within the trace, all four raw buffer sizes, and reconstructs packed PCM from the actual returned slices. It rejects empty or malformed packets and implausible frame totals for the reported rate. This is recorded-evidence consistency, not hardware attestation, proof of USB continuity or analogue audio. The new wrapper has **not run with `-Run`**. Eight evidence-validator tests pass, all 20 Python tests pass, all three plan modes are checked, and the trace parser reproduces the previous real recording's 21,382 events with zero lost events/buffers. The full live orchestration and its emergency cleanup still require owner-present validation.

The next software layer still needs a continuous transport/session owner and ASIO/COM lifetime handling. Reuse these ownership rules rather than placing potentially stuck USB requests directly in a host that cannot safely terminate for cleanup. [Current ASIO component](asio-buffer-component.md), [UsbDk prerequisites](native-usbdk.md).
