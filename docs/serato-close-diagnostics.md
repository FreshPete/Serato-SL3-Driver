# Evidence for the next Serato shutdown test

**Later update:** the [shutdown-grace and marker-free inspection checkpoint](asio-shutdown-evidence.md) increases the grace from eight to twenty seconds. The eight-second behavior below describes this earlier build.

The latest playback reports establish owner-confirmed two-deck tracking, but not clean post-playback shutdown. The supervisor reached its viewing limit, requested a close, waited eight seconds and forcibly terminated its retained application process. The broker then reported an abandoned control connection. These records do not identify why Serato remained alive or prove that the broker caused a hang.

The supervisor previously ignored the return value of each `PostMessageW(WM_CLOSE)` call. Its result now records window metadata and posting outcomes before the grace period, plus a second observation if that period expires. [Build and test evidence](evidence/serato-close-diagnostics-20261106.json)

## New observations

`process.closeWindowObservation` includes owned top-level window count, visible count, enabled-visible count, close messages posted, post failures and up to eight Windows error codes. Enumeration success/error and bounded callback errors are explicit. `process.closeTimeoutWindowObservation` repeats the observation without posting another close request before the existing forced-termination fallback.

Only windows belonging to the retained, still-live supervised process can receive the request. Hidden windows remain excluded from close requests. The callback rechecks the owned process wait handle before using its PID. No foreground changes, desktop automation, screenshots, titles, synchronous window messages or recurring UI polling were added. The eight-second grace period, five-second termination wait and job containment remain unchanged.

Enumeration failure now remains in the result while the supervisor continues its bounded wait and fallback. Previously it could throw out of cleanup before returning the process report. The real owned-child test also injects enumeration access denial and verifies that the final forced-exit report preserves the error; no successful close is fabricated.

Microsoft documents that [PostMessageW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-postmessagew) reports queue posting rather than processing, and can return access denied when integrity levels prevent delivery. [WM_CLOSE](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-close) also permits an application to request user confirmation. Thus a successful post is not proof of exit; disabled/remaining-window counts are diagnostic clues, not a modal-dialog or deadlock diagnosis.

## Verification and limits

Six diagnostic cases cover ownership/visibility selection, a disabled main window, access-denied preservation, observation without repeat posting, exited owners, enumeration/callback failures and actual Windows hidden-window operations. The real API case creates an invisible window in the test process, verifies its native ownership observation, and retrieves an actual queued WM_CLOSE. Visibility/enumeration selection for that posting case is synthetic; no visible UI or Serato dialog was exercised. The message is removed without dispatch, so this does not claim an application shutdown.

Fourteen supervisor cases passed, including existing real owned-child normal/forced exit tests. The forced headless case confirms the new observations report zero visible windows and zero posted closes rather than implying a delivered request. The refreshed native launcher/kit also passed 15 kit entry/refusal, 11 capsule entry, eight Windows argument and eight owned-process Stop cases. Eleven status, six saved-result and four plan cases passed: 83 targeted checks total. The four audio binaries are unchanged.

The refreshed development kit is prepared privately; combined live Start and real Serato post-playback shutdown remain unverified. No administrator prompt, Serato launch or device access occurred in these checks. Existing source-bound launcher/session plans are preserved; the new release has fresh bindings.

## Next attended run

Use a freshly prepared session and manually stop both tracks and close Serato before the viewing deadline. Verify application exit, broker retirement and original-state restoration together. If the application remains alive, the new evidence can distinguish no visible target, rejected posts, and accepted posts with remaining windows. A deeper ASIO stop/dispose trace may still be needed; do not label the broker's forced-close consequence a root cause or weaken its abandonment failure checks.
