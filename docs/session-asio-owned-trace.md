# Session-bound ASIO metadata logging

The complete temporary-session plan now has an explicit Boolean `asioPrivateTrace`. It defaults to false. Plan construction accepts `--asio-private-trace` to opt in before computing the reviewed plan identity; verification reconstructs the same choice. Fresh preparation preserves it, while ordinary kit preparation continues to produce a false/default plan. [Verification evidence](evidence/session-asio-owned-trace-20261106.json)

The wrapper passes the option to the ordinary supervisor. Its child environment explicitly sets `SL3_ASIO_PRIVATE_TRACE` to `1` or `0`; an inherited flag cannot silently enable logging in a default session. The supervisor records the requested choice in its intent and final report. This is a request, not evidence that a logger started or produced a complete trace. Non-Boolean settings are refused.

No audio binary was changed. The already-tested DLL owns its existing private in-process ETW session and can log selected ASIO control calls through shutdown without retaining Frida hooks. Startup probes still detach after audio starts. No desktop automation or additional administrator logger is introduced.

## Exact packaged-DLL verification

`scripts/test-packaged-asio-owned-trace.py` verifies the selected deployment bundle and the existing source-bound Release diagnostic. It copies the exact bundled ASIO DLL into an otherwise empty directory, with no configuration. The bounded native fixture verifies unavailable-state API results and full DLL unload. Three real child-process cases passed:

- Default-off: no trace directory; ordinary ASIO results preserved.
- Invalid logger location: logging fails gracefully; ordinary results and unload preserved.
- Explicit opt-in: 16 real events/eight complete call pairs decoded, with successful logger stop, zero reported losses and full unload.

The tested DLL SHA-256 is `695f87e0cff1733e4aee8ab6b311d1cbc87b087a874fab5dddfef2404dd6e6bc`, matching the working temporary audio package. The fixture sets a private child-only profile under its analysis directory. No Serato, configuration, USB acquisition, protected installation or registration ran. The method calls were unavailable-state calls, not playback or a Serato shutdown.

The refreshed launcher/kit also passed preparation and control regressions. Fresh sessions built from the explicit true template preserve true; copied-kit preparation remains false. The wrapper parses successfully, and owned-process supervisor tests verify the requested child environment for both choices. Actual combined Start with this profile remains untested.

The checkpoint records 79 targeted cases: 15 supervisor, six window-close, eleven status, six saved-result, five plan, fifteen kit, eight Stop, eight fresh-preparation, three packaged-DLL logging and two supervisor CLI Plan cases. A flaky preparation-test leaf name was corrected to satisfy the existing tag grammar; production path checks were not relaxed.

## Limits and next attended test

Driver-owned logging remains optional and best effort. Its existing limits are four session attempts, 4 MB per session, and 4,096 selected calls/8,192 records per loaded module. It does not instrument audio callbacks, sample-position queries, `AddRef` or `Release`. It cannot prove those operations completed. Selected `stop` and `disposeBuffers` calls are logged if the logger is active and its budget remains.

Ordinary-session logs are private below `%LOCALAPPDATA%\SL3Rebuild\AsioTraces`. The next real Serato run must establish which log belongs to its process and loaded DLL; the requested flag alone does not do that. A failed logger startup, force termination, missing stop marker, reported loss or exhausted budget can leave incomplete evidence. Keep ETLs and raw paths private; do not fabricate completion markers. Existing strict completed-log analysis remains unchanged.

For the next attended test, prepare a fresh session from the reviewed trace-enabled template, start playback briefly, stop both tracks and close Serato before the viewing deadline. Correlate the actual ASIO stop/dispose records with the [owned-window close observations](serato-close-diagnostics.md), broker retirement and restoration. This should narrow the failure point; neither the shutdown root cause nor a successful physical shutdown is established yet.
