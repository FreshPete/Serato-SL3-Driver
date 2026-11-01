# Shorter controls capture, 1 November 2026

The split-role collector and normal-user probe now accept `-TraceSeconds` from 20 through 60, with the existing 60-second default. Both roles must request the same duration. The collector records it in its context; admission and final validation bind it to the USB trace and probe record. A legacy context without this field still requires 60 seconds.

For a 20-second window, admission must occur within five seconds of trace start. Final validation requires at least twelve seconds between probe retirement and trace stop. A slow probe can therefore fail this capture; the change does not shorten the native deadline, retry an acquisition or claim success when the observation interval is missing.

The saved 31 October probe ran from 12:05:24.5104390Z to 12:05:24.7978268Z. Its candidate later USB state transition occurred roughly ten seconds after retirement, while the sixty-second circular ETL overwrote most live state rows. Twenty seconds is a proposed bounded follow-up window, not an observed capacity or recovery guarantee. The corrected sequential collector still rejects a file that reaches its 64 MiB capacity.

Fifteen split-role tests, eleven capture-evidence tests and three live-consumer contract tests passed. These include actual plan-only PowerShell invocations for twenty and sixty seconds, invalid-duration rejection, mismatched duration and stale admission rejection, and the twelve-second retention boundary. No device was opened for these checks.

The local Release manifest records a capture-runtime revision, with six updated pins across the controls and selection trace maps. All 114 recorded native source hashes and the probe/worker binary hashes were checked unchanged. There was no native rebuild. The previous manifest and reviewed files are preserved in `artifacts/build/checkpoints/short-controls-trace-20261101`; the local review record is `analysis/short-controls-trace-20261101.json`.

No new physical capture has run. Coupling the successful [image source](native-guid-live-20261101.md) to this USB/control window, checking actual overlap, and resolving physical SL3 port identity remain required before using this evidence to choose a reopen policy.
