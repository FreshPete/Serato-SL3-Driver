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

After fresh device/recovery admission, a reviewed traced run can use this explicit form with an exact pinned helper and a fresh local output directory:

```text
sl3_usbdk.exe --timer-query --challenge <16 hex digits> --helper <reviewed UsbDkHelper.dll> --output <fresh local directory>
```

Do not run it as an automatic startup probe or immediately after a failed redirect. First resolve the [ordinary-user phase observation](hub-port-observer.md) or establish a reviewed ownership design for the known second-open stall. A future physical result must bind its challenge, response, trace, executable identity, cleanup and selected recovery. It must still be reported separately from key verification, current Serato admission, analogue audio, DVS and stability testing.
