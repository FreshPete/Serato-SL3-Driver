# Offline comparison for the original driver-timer reply

The original eight-byte response calculation is now implemented as a fixed-storage comparison function. It accepts the caller's challenge, a caller-supplied 16-byte key and an already parsed control event. It returns a comparison result without emitting a device response, retaining a key or performing I/O. No vendor key is embedded. There is no runtime, IPC, CLI or ASIO call site for this function yet.

This extends the [control-frame codec](native-control-frames.md), which already constructs command `0x37` and preserves its actual eight-byte reply. Neither layer makes a synthetic reply into physical evidence. The current Serato handshake map still lacks the historical DRIVER_API entry, and no current application handshake has been implemented.

## Recovered original calculation

In original Serato 2.5.5, `RaneSL3API`'s check at `140691980` calls the real driver export, copies its challenge and invokes `14054f520` with length 8, a key argument and callback `14054f250`. It compares the transformed copy with the actual driver output at `140691aa2`; success is conditional at `140691ab6`.

Wrapper `14054f520` reverses the bytes in each four-byte word of both the 16-byte key and the challenge before invoking the word transform. It reverses the output words back afterward. Thus the interoperable calculation interprets challenge, key and reply words as **big endian**. It does not use the little-endian word interpretation recovered for the unrelated resource archive.

The callback uses the corrected block-TEA operation, with `6 + 52 / word_count` rounds and 32-bit unsigned arithmetic. An eight-byte challenge has two words and therefore **32 rounds**. The original callback spans adjacent unwind regions; its loop body at `14054f2af:14054f392` was inspected as well as its entry. The shifts, additions, key-index operation, delta and loop condition agree with the [authors' corrected-block operation](https://www.cl.cam.ac.uk/ftp/users/djw3/xxtea.ps). The paper was inspected as source data, not executed.

The new function `sl3::control::matches_driver_timer_reply` implements only this two-word comparison. It first requires a reply event with no framing error, command `0x37` and exactly eight defined payload bytes. It performs all 32 rounds, compares both reply words and leaves the input data unchanged. The function does not load the original key from an application, offer a constant-success path or implement a response emulator. An appropriate reviewed key source and a real device exchange remain future integration requirements.

## Actual validation and limits

Four synthetic reference vectors exercise zero, all-ones and nonpalindromic challenge/key data. A separately written variable-word reference calculation checks their expected bytes. Tests pass those response bytes through the actual control-frame parser before comparison, then reject every single-bit change to each reply and challenge, synthetic key-bit changes, reversed reply bytes, wrong commands, incorrect widths, notification/failure events and framing errors. All keys in these fixtures are synthetic public test values.

The complete native suite passes **29/29 Release** and **29/29 Debug**. A separate build with the ASIO component disabled and an explicitly nonexistent SDK path passes **21/21**. All **42 Python tests** also pass, including the new archive parser tests. These are software results. No physical `0x37` exchange, USB startup, audio, timing, ASIO host or DVS validation follows from them.

The [build evidence](evidence/timer-verification-build.json) verifies current source/build/log hashes, original call/byte-order/round instructions, the focused transform report and the synthetic reference values. Reproduce with `.venv/Scripts/python.exe scripts/export-timer-verification-evidence.py` after the native builds and local evidence are present. Older build-checkpoint reports retain their earlier counts and hashes; this record is the current superset checkpoint.

The [isolated timer diagnostic](driver-timer-diagnostic.md) now implements a separate explicit native query, with software-only validation and no connection to this comparison function. Its physical exchange remains pending, subject to the current release/reopening investigation. No timer exchange is silently added to startup or used as a fallback after another operation fails. A comparison match alone cannot prove an event's physical origin, product/account entitlement, firmware behavior, audio readiness or current Serato integration.
