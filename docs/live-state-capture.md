# Optional live-state capture

The administrator collector now has a prepared `-WithStateObserver` option. It enables file and real-time delivery in the existing shared USB/UsbDk session, supervises the reviewed reader and preserves its output beside the ETL. The ordinary probe remains non-elevated. The option is off by default and makes no readiness or automatic-reopen decision.

**No positive live capture has occurred.** Offline checks cover plan-only calls, synthetic consistency cases and the actual saved-ETL reader. The next physical prerequisite remains an attended current-build normal-token read-only control run.

## Attended use

Start the ordinary role from [the read-only procedure](controls-user-probe.md). In the separate already-elevated terminal, use the same fresh context:

```powershell
./scripts/capture-controls-user-context.ps1 -Run -WithStateObserver -ContextDirectory $freshContextDirectory
```

Omitting `-Run` reports a plan without creating output. Direct capture-source use also requires `-WithUsbDkLifecycle`. No script launches an administrator prompt. The source adds the documented [logman real-time flag](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/logman-create-trace) and a one-second flush interval to its owned 64 MiB session. Existing USB/WPP providers and the 60-second context window remain. No USB request, binding, firmware or security change is introduced. Instrumentation can affect timing.

The reader manifest, executable, retained replay and source inputs must match references in the main native build before capture. There are now 18 capture dependencies and 22 setting-runner dependencies. The installed hub-image hash/version/signature is recorded before and after; this does **not** attest the loaded kernel image.

## Evidence and failures

The collector queries its reader's actual process/token and checks the source-session header before publishing `recording`. It calls this `consumerAttemptVerified`, not successful subscription: opening a consumer and writing a header can precede a failed `ProcessTrace` call. The normal probe's admission still concerns its recording source, not guaranteed early observer coverage.

The source keeps its independent automatic stop limit. Cleanup stops/deletes only that source, then allows the owned reader five seconds to drain. A stuck reader is contained as a failed diagnostic. Original operation errors and observer errors remain separate. No source session is stopped by the reader itself.

Capture validation requires one hash-bound ETL, normal reader retirement, matching session/PID/build, elevated reader-token evidence, ordered process timestamps, nonempty live state records, and no containment. It rejects saved-file replay presented as live. Partial/failed outputs remain diagnostic.

After the ordinary wrapper decodes the ETL, the read-only and setting validators recheck the reader and match every live row against that session's loss-free XML, preserving duplicate counts, pointers, namespace and exact timestamps. Coverage counts distinguish a subset from all source state events. A missing initial prefix is not silently promoted into full-window coverage. Live loss counters remain incomplete snapshots; the full source ETL and ordinary trace checks stay authoritative.

A matched observation is not physical target identity, a safe cycle, audio continuity or Serato admission. Loaded-image qualification and target/generation correlation remain necessary before a second-open policy. The reader continues to emit `readinessAdmission: false`.

## Verification and remaining work

Three new Python tests exercise actual optional plans without output, replay/role/type/partial-result rejection, and synthetic source/build/window/cleanup/image/XML failures. The synthetic fixture isolates build preflight and creates no trace session. Actual Release/Debug saved-file reader checks remain separate.

The next attended run should inspect controls once, then examine real-time delivery and the full post-release sequence. Failed observation preserves the source trace and never authorizes another redirect. Live subscription, cancellation/drain and safe reopening still need physical validation; the reader's requested duration is not a hard wall-clock retirement guarantee because queued events can drain after consumer closure.
