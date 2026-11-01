# Current Serato application/ASIO buffer adaptation

The retained PortAudio ASIO path in the pinned Windows Serato DJ Pro 5.0.0.1278 executable retries the driver's preferred bank after failing to create the application's requested size. It initializes its buffer processor with separate application and host frame counts. The historical descriptor's alignment of 48 therefore does not, by itself, require our ASIO driver to accept multiples of 48.

This is static evidence plus tests of our own unregistered DLL. Serato and its PortAudio code were not executed. No hardware, production profile, registration, application file or security policy changed.

## Verified original executable path

The [machine-checked evidence](evidence/serato500-bank-adaptation.json) pins SHA-256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`, focused decompilation reports and exact instructions. Addresses are image virtual addresses; some functions have multiple unwind regions, so the first region does not delimit the complete logical body.

| Stage | Address | Observed contract |
| --- | --- | --- |
| PortAudio connection open | `1421e60a0` | Takes rate and application frames separately and forwards them to `1421e69b0`. |
| CPortAudio open | `1421e69b0` | Preserves requested application frames through the stream-open call. |
| Stream dispatch | `142215a10` | Resolves the host API and invokes its open slot at `+0x38`. |
| ASIO initialization | `1422187d0` | Installs `142217160` at that slot; its original diagnostic identifies `PaAsio_Initialize`. |
| ASIO driver setup | `142217040` | Reads minimum/maximum/preferred/granularity through `142221eb0`, IASIO slot `+0x58`; preferred reaches host API `+0x1d8`. |
| ASIO stream open | `142217160` | Calls createBuffers through `142221e00`; on failure, tries preferred frames unless the first request already used preferred. |
| Processor initialization | `142221680` | Stores separate user frames at field `+0`, host frames at `+4`, mode at `+8`. |
| Audio callback | `142216150` | Uses the stream's buffer processor at `+0x80`, including its end-processing operation. |
| End processing | `142221440` | Selects its adapting branch when the non-adapting flag at `+0xc` is zero. |

The first createBuffers call is at `142217745`. Its failure path compares the requested size with preferred at `142217758`, loads preferred at `142217777` and retries at `1422177a4`. The selected host size is retained at stack `+0x78`. Before processor initialization at `142217adf`, host frames are passed at stack `+0x50`, while the unchanged original application frame count is passed at `+0x40`. These are distinct arguments under the Windows x64 calling convention.

The processor's fixed-host mode uses the non-adapting path when host frames divide evenly by user frames; otherwise it prepares temporary buffers and adapting state. With user 240 and host 128, that division does not have zero remainder. The callback reaches the processor, whose adapting body buffers/converts and invokes the user callback in user-frame units. This establishes the static path, not measured scheduling or audio correctness.

Names and argument interpretation are cross-checked against the primary [PortAudio ASIO source](https://github.com/PortAudio/portaudio/blob/master/src/hostapi/asio/pa_asio.cpp) and [buffer processor declarations](https://github.com/PortAudio/portaudio/blob/master/src/common/pa_process.h). Those sources explain the API; they do not establish the exact version or identity of Serato's bundled implementation. The original executable instructions remain the evidence for this build.

## Original DLL retry tests

The actual unregistered IASIO test DLL first completes its existing two 64-frame sessions. After disposing buffers, a 240-frame request returns `ASE_InvalidMode`, starts no callback and publishes no planes. Metadata remains readable; requesting preferred 128 frames then succeeds and completes two fresh callback/start/stop sessions, with orderly buffer disposal and DLL retirement. Callback position and copy lengths use the selected bank size. Tests also reject callback lifecycle reentry.

The explicitly synthetic latency profile adds 7 input and 11 output frames, so this test reports 135/139 frames at a 128-frame bank. Those numbers are not physical SL3 latency. A separate facade test with a bound 128-frame profile rejects 64 and 240 before accepting 128.

All 27 native tests pass in both Release and Debug. The exporter checks current build input hashes, script/log hashes and the actual tested executables/DLL, rather than relying on a test-count statement. SDK-free tests were not repeated for this SDK-only change; the prior 19-test checkpoint remains historical.

Reproduce after both builds:

```powershell
.venv/Scripts/python.exe scripts/export-serato-bank-adaptation-evidence.py
```

The focused analysis reports and vendor executable are local prerequisites and are not redistributed. No vendor binaries, decrypted resources or SDK implementation are added to the repository.

## Consequences for the next test

Keep production ASIO rate/bank acceptance tied to a measured timing profile. A failed initial application-size request must remain recoverable, as the new DLL test verifies. Do not introduce arbitrary bank acceptance or change the application alignment to make one example fit.

Physical input/output pacing, device/transport delay and application adaptation delay must still be measured. The current supported descriptor route, legitimate original device exchange, clock selection, installed transport admission and current Serato/DVS integration remain separate unresolved requirements. The [clock/handshake contract](serato-clock-handshake.md) and [bounded control codec](native-control-frames.md) retain their limitations. A passing simulated retry is not an application or hardware success.
