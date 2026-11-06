# Read-only session status

Prepared sessions now include `statusArguments` alongside Plan, Start and Stop. The native `--status-session` entry reads progress, saved shutdown reports, owner identities and current restoration state. It does not repair files, request elevation, open the SL3 or start Serato. [Verification evidence](evidence/session-status-20261106.json)

```text
SL3_Rebuild_Development_x64.exe --status-session --session-plan ABSOLUTE_SESSION_PLAN --expected-session-plan-sha256 REVIEWED_SESSION_PLAN_SHA256 --powershell-directory ABSOLUTE_POWERSHELL_DIRECTORY
```

The current launcher pins 43 source/license/evidence files and both runtime inventories. Complete embedded-Python plans pin 29 sources. Changed helpers are refused before Python execution. Existing source-bound plans must be regenerated; the standalone read-only inspector can inspect historical reports using their recorded plan identity.

## Result contract

| State | Meaning |
| --- | --- |
| `prepared` | Original setup is clean; no selected session intent or result was found. |
| `starting` / `running` | A recorded owner is alive; running additionally requires matching intent and the startup/detachment event. |
| `stopping` | A recorded owner remains alive after a bound stop request or host result. |
| `completed` | Deliberate exit or a bound requested stop, clean host/broker/retirement/restoration reports, retired owners and currently restored setup agree. |
| `cancelled_restored` | Startup cancellation has a bound request, retired owners, restoration and proof that the broker never started. This is not audio completion. |
| `ended_unverified` | Original setup is restored, but clean completion is not established. |
| `recovery_review` / `conflicting_state` / `unknown` | Restoration, ownership or progress cannot be established consistently. No automatic repair runs. |

A viewing-limit exit never becomes a successful session. Forced termination and broker failures stay visible even when rollback succeeds. A stop request alone is not completion. Missing ownership or reports cannot produce completion. The saved-result inspector's original checks, including whether application exit preceded observer close, remain available unchanged.

This is a point-in-time observation, not a continuous monitor. An incomplete trailing event append is ignored; partial JSON reports become issues. Archive reads share write/delete access to avoid blocking restoration. Status does not verify current USB readiness or physical audio.

## Verification

Eleven status, six saved-result, four complete-plan, 15 moved-kit entry/refusal, 11 capsule entry, eight Windows argument and eight owned-process Stop cases passed: 63 targeted checks. The copied-kit entry reported a prepared session. Modifying its status helper was refused before Python execution. The Stop fixture used synthetic startup events and a headless child, not Serato.

The latest saved looped playback run reports `ended_unverified`: the owner reported both decks worked and closed normally, while the supervisor recorded `viewing_limit`, forced termination and exit code 1. Broker `owner_failure` / `client_control_abandoned` / pipe error 109 is preserved. Original archive and absent temporary registration/files were independently observed. This improves reporting; it does not resolve the shutdown discrepancy.

## Remaining attended checks before a public package

1. Close Serato before the viewing limit; confirm clean host/broker shutdown and restoration.
2. Repeat playback startup and normal close without power-cycling the SL3.
3. Verify audible physical outputs and channel mapping, then independently control both Phase remotes.
4. Run longer playback and check interruptions, timing and supported buffer/rate behavior.
5. Exercise kit Start/Stop, cancellation and recovery here, then another account/PC and install/uninstall.

Packaging can progress alongside these checks. A simple interface and public installer remain unfinished; binary distribution has not been validated.
