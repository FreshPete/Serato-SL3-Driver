# WinUSB audio-interface activation — 26 October 2026

**Result: both audio interfaces selected alternate 1 successfully, their active pipe maps matched the fixture, and both returned to alternate 0 successfully.** The USB trace independently confirms each change. No audio was transferred.

The owner explicitly authorized this test. One traced binding attempt used the unchanged development package and previously approved temporary certificate trust. Windows started WinUSB again. After a read-only identity/descriptor check, the experiment selected interface 1 then interface 2, held the combined setting for two seconds, and restored interface 2 then interface 1. The parent imposed a 20-second process deadline and retained the original-driver cleanup procedure.

## Actual sequence

| Operation | API completion UTC | Queried active alternates for interfaces 0–3 | xHCI endpoint configuration / hub USBD status |
| --- | --- | --- | --- |
| Activate interface 1 | 22:59:31.112521 | `[0,1,0,0]` | 0 / 0 |
| Activate interface 2 | 22:59:31.116508 | `[0,1,1,0]` | 0 / 0 |
| Restore interface 2 | 22:59:33.120473 | Restoration in progress | 0 / 0 |
| Restore interface 1 | 22:59:33.124475 | `[0,0,0,0]` after both restorations | 0 / 0 |

All four `WinUsb_SetCurrentAlternateSetting` calls returned success, with Win32 error recorded as zero. The associated-interface handles were mapped by their queried interface numbers, rather than assumed from handle order. Active settings were read back and the pipe maps checked after each activation and after restoration.

At `[0,1,1,0]`, interface 1 exposed isochronous OUT **0x06**, and interface 2 exposed isochronous IN **0x82**, each with maximum packet/bytes-per-interval **126** and interval **1**. Interface 3 retained its two 64-byte interrupt endpoints, IN 0x81 and OUT 0x01. Interfaces 0 and 3 remained at alternate 0. The audio topology matches the original driver's statically recovered setting-pair choice, reached here through WinUSB.

The experiment uses Microsoft's [alternate-setting selection API](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_setcurrentalternatesetting) and [current-setting query API](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_getcurrentalternatesetting). The normal probe remains read-only; state changes require the separate experiment's explicit `--activate` switch and the runner's `-ActivateAudioAlternates` option.

## USB trace

The 60-second recording contains **37,990 events with zero lost events or buffers**. VID/PID identity-to-device-pointer correlation selects 302 SL3 events. The xHCI configuration sequence includes initial interface-0 setup followed by `(1,1) → (2,1) → (2,0) → (1,0)`. All four experiment configuration events have endpoint-configuration status zero, and their corresponding hub select-interface completions have USBD status zero. Event timestamps fall within the recorded API calls.

The target's recorded completion fields contain 25 UCX IRP statuses, 10 hub NTSTATUS values and six hub USBD statuses, all zero. No SL3-correlated UCX isochronous or bulk/interrupt dispatch events were observed. The experiment code contains no streaming or interrupt-transfer submission APIs; no vendor controls, pipe/port reset, firmware operation or sample-rate command was sent.

## Cleanup and validation

At 23:00:23 UTC cleanup restored original `oem136.inf` / `strmdrv` and its existing code-39 rejection. It removed development `oem152.inf`, the project interface GUID, and both temporary machine certificate trust entries. The signing identity/private key remains absent. Secure Boot was true before the trial and after cleanup. An independent final check and descriptor capture confirmed the original identity and byte-identical device/configuration descriptors. No USB disconnect, power cycle or restart was needed.

Three fault-injection tests ran before the physical experiment: successful reverse-order restoration; a second-interface failure that partially changes state and still restores both attempted interfaces; and an unexpected pipe fixture preventing every setting change. All passed. The full six-test suite, Python syntax checks and PowerShell parsing also pass. These simulated failures validate the recovery logic, not every possible hardware failure.

## What this establishes

WinUSB can reach and leave the original audio-interface topology on this host while retaining the security target. Together with the preceding traced binding success, this supports continuing the inbox-driver/user-mode transport route before considering a replacement kernel driver. It is still only one activation/restoration cycle.

This does not establish converter clocking, sample packing, USB packet scheduling, sustained capture/playback, latency, ASIO or current Serato/DVS operation. The next investigation should recover the status/clock/control semantics and define a bounded data-transfer experiment with verified formats and stopping conditions. Do not treat alternate selection as proof that the device's audio engine is running, or replay the unidentified startup commands to try to make it run.

[Sanitized evidence](evidence/winusb-audio-alternates.json) is regenerated by `scripts/export-audio-alternate-evidence.py`. Raw ETL/XML, transcripts and detailed state remain ignored under `tests/results/local/winusb-audio-alternates-01`.
