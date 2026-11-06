# Prepared-session window: engineering tool

The native Win32 prototype wraps one existing, hash-bound development session. It is **not** the final install-once experience: the owner clarified that normal use should be opening Serato itself, with either Phase RCA or timecode vinyl through the SL3. See the [installed-use target](installed-use-target.md).

The window provides Check setup, Start session, Session status and Recovery. No action runs automatically. Check first verifies the complete prepared session, then the copied kit's prerequisite checks and current recovery state. A successful check enables one Start for this prepared window. Competing commands are disabled while work runs, and the window refuses normal close until that command finishes. The user closes Serato normally; this window adds no desktop inspection during audio. Diagnostic output is optional and bounded in memory to the latest 64 KiB.

Every command holds read-only identity leases on the reviewed CLI executable and selected plan. The existing native CLI still verifies its sources, runtimes, application, kit/session and protected state. No shell command string is interpreted: the child receives a quoted argument vector and an explicit handle-inheritance list. Read-only commands run in a kill-on-close job with a two-minute bound. Active Start/Recovery commands are not terminated by the GUI; an output error still retains process ownership until command exit. The original session wrapper's diagnostic limits remain unchanged.

The preparer verifies the full plan, kit inventory, CLI release sources and portable PowerShell manifest. It reconstructs the CLI's generated verification header from its reviewed release record and refuses differing bytes, then copies that exact header into a fresh private build directory. This avoids compiling against an unchecked generated include. Configuration embeds this host's paths and hashes, so the resulting binary is private and not a relocatable installer. It requires no .NET runtime.

## Validation scope

The MSVC 2019 x64 Release build uses Windows SDK 19041, static CRT and warnings as errors. Its owned native fixture exercises the production window handlers without starting Serato or requesting elevation:

- Preview mode disables actions; unchecked and already-consumed Start requests are refused.
- Check executes the actual pinned CLI's Plan, kit readiness and recovery-check routes. Status executes the actual read-only status route.
- Check/Start remain disabled while the worker runs; normal window close is refused while busy and succeeds when idle.
- A consumed window can recheck, but cannot restart and explicitly says a new prepared session is required.
- Control bounds, detail expansion/collapse and the initial/ready/consumed/details client renders are inspected.

The first desktop inspection showed the native controls correctly. The desktop helper subsequently returned `GetCursorPos: Access is denied`, so its attempted Check click did not run. Fixture-owned rendering and handler tests were used instead. The first PrintWindow-based fixture capture was blank despite returning success; that capture was rejected, and the fixture now paints only its own client/controls through `WM_PRINT` and rejects uniform output. These are client renders, not full desktop screenshots or proof of live keyboard/DPI/accessibility behavior. The earlier idle visible prototype was subsequently closed successfully through the desktop helper.

An independent finish review found a misleading consumed-session recheck message; the wording and ready-state handling were corrected and a real recheck case added. The final review result and hashes are recorded separately. Start with real Serato, elevated recovery, forced read-only timeout, extended output-writer behavior, multiple DPI settings and high-contrast/screen-reader behavior remain untested. Audio-driver binaries and the existing attended-test kit are unchanged.

The source and build helper are retained for debugging and possible setup/recovery UI reuse. Future work must prioritize the installed-use route, not require this prepared-session window for everyday operation.
