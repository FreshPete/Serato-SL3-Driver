# Isolated original-driver timer query

The new explicit `--timer-query` mode sends the original SL3 interrupt command `0x37` with an eight-byte caller-supplied challenge and preserves a genuinely received eight-byte reply. It is a diagnostic step toward the historical driver contract, not a current Serato integration or a replacement for the unresolved release/reopening work.

The worker admits exactly one outgoing 64-byte frame on endpoint `0x01`, then at most four complete 64-byte frames on `0x81`. The existing codec accepts up to three asynchronous notifications before the reply. A fourth notification, bad tag, short transfer, timeout or cancellation fails the query without a retry or fallback. The independent native adapter accepts only the exact challenge frame; it rejects another opcode, challenge, duplicate write or extra read.

The transaction has a 1,500 ms budget, with individual write/read waits capped at 100/300 ms. This budget excludes device enumeration/opening, cancellation and draining, and redirect release. Existing transfer retirement/containment and the process watchdog remain in force. A transfer cannot return normally with pending I/O storage freed. No audio alternate is activated, PCM submitted, rate changed or firmware operation performed. Normal startup, ASIO and IPC do not call this diagnostic.

`timer.json` records intent before redirect opening and each transfer, attempt counts, I/O retirement, parsed response and redirect closure separately. A closed redirect does not establish kernel detachment or readiness for another open. Pre-diagnostic helper/selection failures retain a zero-attempt error record; existing output directories are refused without overwriting their contents. Raw challenges/responses stay in ignored local results. They are not published as authentication evidence.

The [offline comparison](timer-verification.md) still has no runtime call site or embedded vendor key. This diagnostic does not compare the reply with that transform. Its `response_verified`, `serato_admission_verified` and `reopen_ready_verified` fields remain false even after successful parsing. The [missing current DRIVER_API handshake](serato-clock-handshake.md) remains a separate integration requirement; no default handshake or another device identity is substituted.

## Build and software evidence

Build in a separate directory so that the worker used by the successful physical controls capture remains intact:

```powershell
./scripts/build-native.ps1 -Configuration Release -WithAsioComponent -BuildDirectory artifacts/build/timer-diagnostic
./artifacts/build/timer-diagnostic/Release/sl3_usbdk.exe --plan --challenge 0123456789abcdef
```

The 1 November Release build passed all **47 native tests**, including injected native transport failures, notification limits, malformed replies and budget exhaustion. Eight actual CLI failure cases passed using a nonexistent helper; these verify argument refusal, durable pre-load error reporting and existing-output preservation without loading a DLL or opening the SL3. The exporter also executes the no-device plan and verifies the exact source/build/test hashes and preservation of the older physical-capture manifest, worker and host probe.

The default live controls scripts target `artifacts/build/native`. That target was subsequently rebuilt from the current sources and passed all 47 tests and the normal-token read-only preflight. The older physical-capture build is preserved under `artifacts/build/checkpoints/native-controls-build-20261101`, including its source inputs and complete Release directory. Historical physical evidence binds that archive; it does not validate the newly built default worker. [Refresh and unstarted-plan evidence](evidence/native-default-refresh-20261101.json).

Regenerate [compact evidence](evidence/driver-timer-diagnostic-build.json) with `./.venv/Scripts/python.exe scripts/export-driver-timer-diagnostic.py`. The local `artifacts/build/checkpoints/driver-timer-diagnostic-20261101` capsule retains the corresponding source inputs, manifests, logs, executables and CLI record. These are software-only results. The new worker has not run a physical timer query, audio or Serato session; it inherits no hardware pass from the older worker.

## Physical test remains pending

The independent macOS [SL3 protocol notes](https://github.com/pepeleedj/Rane-SL3-Macos-ARM-Driver/blob/main/docs/PROTOCOL.md) report that USB playback needs both the per-deck USB switch and recurring `0x37` traffic at roughly 100 ms intervals. [Ben's SL2 test](https://github.com/pepeleedj/Rane-SL2-Macos-ARM-Driver/pull/1) reports a similar dependency on different hardware. Our native silent-output runs confirm transport only. The known-input test stays independent of the timer so its result is attributable to the capture path.

The current single-shot adapter cannot simply be called on each audio callback. One exchange allows up to 1,500 ms and may occupy interrupt IN while waiting for notifications or the matching reply. A periodic playback experiment needs one owner for the interrupt endpoints, one exchange in flight, and separate scheduling from the isochronous queues and ASIO callbacks. Measure actual request and reply spacing on the physical device. A missed deadline should end the experiment and enter cleanup rather than queue a burst of challenges. Keep the driver-liveness exchange separate from any Serato authentication decision.

There is also a framing difference to resolve before periodic use. Our Windows codec emits and checks the original fixed four-byte tag `1c c5 00 01`. The [macOS stream code](https://github.com/pepeleedj/Rane-SL3-Macos-ARM-Driver/blob/main/src/iousbhost_streams.m) increments a little-endian sequence at the same offset and matches replies against that sequence. The 4 November Release executable still passed its inert one-shot plan with the fixed Windows form. Keep that original framing for the first physical check. If testing a sequence variant later, isolate it in the playback diagnostic and verify real echo behavior before changing any existing parser or routing control.

For a later audible experiment, snapshot the actual control table under the retained acquisition before touching routing. Use the verified write/readback path for only the selected deck, keep output initially zero, and independently observe whether a bounded known signal reaches that deck. Restore and read back the original routing before releasing ownership. If restoration cannot be verified, preserve the result as a cleanup failure. A periodic exchange and a routing write are additional operations that the existing one-shot diagnostic does not perform.

After fresh device/recovery admission, a reviewed traced run can use this explicit form with an exact pinned helper and a fresh local output directory:

```text
sl3_usbdk.exe --timer-query --challenge <16 hex digits> --helper <reviewed UsbDkHelper.dll> --output <fresh local directory>
```

Do not run it as an automatic startup probe or immediately after a failed redirect. First resolve the [ordinary-user phase observation](hub-port-observer.md) or establish a reviewed ownership design for the known second-open stall. A future physical result must bind its challenge, response, trace, executable identity, cleanup and selected recovery. It must still be reported separately from key verification, current Serato admission, analogue audio, DVS and stability testing.
