# Keep the administrator action result

**Fresh payload follow-up:** [failed ASIO activation reporting and the refreshed setup candidate](asio-activation-failure-report.md) now bind a newer tested native build into a separate kit, entry and window. The result-channel implementation below is unchanged; its earlier candidate identities remain historical.

The setup window now receives and preserves the administrator-run controller's output, rather than replacing it with a later file-state check. This fixes a real reviewability gap: a failed install could previously leave only the final observation visible, losing its detailed component failure. Eight actual IPC scenarios, 25 native-entry checks and 18 window checks pass. **The elevated/UAC result path has not run.** [Bound evidence](evidence/setup-result-diagnostics-20261106.json)

## Result channel

An explicit Install/Restore action creates a fresh local, one-way result pipe before requesting Windows approval. The reader accepts output only from the exact launched native process while that retained process object is still alive. Other writers are disconnected and their bytes discarded. The client checks the expected server PID and same user/session, and opens with anonymous SQOS so the ordinary reader cannot impersonate it. The pipe carries diagnostic bytes, not commands or file destinations. [Microsoft's client-impersonation/SQOS contract](https://learn.microsoft.com/en-us/windows/win32/ipc/impersonating-a-named-pipe-client) · [Overlapped connection semantics](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-connectnamedpipe)

The native setup entry redirects only its fixed Python helper's stdout/stderr and its own guarded error text. Result options are accepted only for setup/restore with an already elevated token. Read-only actions refuse them, and ordinary-token setup still refuses before opening a channel. No elevation policy or broker authentication rule was weakened.

Capture is bounded to 512 KiB. Oversized output is marked incomplete and continues draining so it cannot block transaction completion. Missing, unauthenticated, incomplete or mismatched successful results cannot produce a successful install label. A channel failure closes the diagnostic connection and waits for the actual process; it does not terminate an administrator transaction or guess a rollback.

## Local diagnostic copy and actual state

The ordinary setup window creates a new `ui-action-<UUID>/administrator-result.txt` beside the selected experiment. It records the exit code, channel status, selected experiment hash and captured output. Files use exclusive creation and are not uploaded. They are **ordinary diagnostic copies, not trusted recovery receipts**; the protected native installer journals and validated component witnesses remain the recovery authority.

The post-action native observation is still required. It is appended to the visible details rather than erasing the administrator report, including when observation itself throws. A successful exit, a complete authenticated report and the expected observed installed/restored state are all necessary for success. The full diagnostic copy remains available after closing the window. A test-generated copy clearly contains fixture failure text and does not describe a real installer run.

The window now also states the existing **10-minute diagnostic audio-session limit**. That bound was already enforced by the native package; it is not a newly introduced timeout or a claim that normal-length sessions work.

## Current private candidates and verification

The source-current native entry is under `artifacts/build/native-on-demand-entry-result-channel-20261106`; its executable SHA-256 is `c026d647ffeb75132269154f19d31f3a664c5c9977247b6f2b60b1dcd6b1026d`.

The source-current window is under `artifacts/build/native-setup-window-results-reviewed-20261106`; its executable SHA-256 is `698e3e0670405e628ab3d736e8bf95aaed4c0e77e005409c36c89ad0ac8296dd`. The kit and selected experiment are unchanged. Earlier window/entry binaries remain historical checkpoints.

Owned ordinary-process tests cover exact delivery, both helper streams with a failed exit code, rejection of a different process, no-report exit, wrong server PID, over-budget draining, namespace refusal and anonymous-client behavior. Window checks additionally preserve exact diagnostic file bytes and retain the administrator text across an actual read-only postcheck. The moved-kit regression now copies only immutable payloads, allowing the origin kit to contain existing prepared state.

All production files/registration remain restored. No administrator action, Serato launch, firmware operation or USB acquisition ran for this change. Windows became locked during the latest visual review; desktop interaction stopped. Accessibility confirms the new limit notice, but final rendered review remains pending and the idle setup window was left open. The next attended test must exercise the real approval/result handoff and normal Serato startup; current physical transport and DVS validation remain separate.
