# Timed hub-image source configuration

Windows accepts and round-trips an **uncommitted five-second PLA configuration** for a separately named System Process Provider session. Its XML preserves a fresh session GUID, system-logger mode, the loader keyword, QPC timing and disabled schedules. This supplies a concrete configuration candidate for the missing hub-image recording. **No session was committed or started; runtime flag forwarding, image emission and independent stopping remain unverified.**

[Preparation tool](../scripts/prepare-hub-image-source.ps1), [actual configuration evidence](evidence/hub-image-source-preparation-20261031.json). The tool has no `-Run` option and no Commit/Start/Stop/Delete calls. It creates COM objects in memory, validates serialized properties, and optionally writes a new JSON report. Its prospective capture directory is neither created nor populated.

## Provider and ownership choices

The selected provider is `SystemProcessProviderGuid`, `{151F55DC-467D-471F-83B5-5F889D46FF66}`. Microsoft documents its [loader keyword as corresponding to image-load events](https://learn.microsoft.com/en-us/windows/win32/etw/system-providers); these System Providers require `EVENT_TRACE_SYSTEM_LOGGER_MODE`. The pinned Microsoft SDK header confirms loader keyword **0x1000** and logger-mode bit **0x02000000**. This is distinct from the ordinary manifest `Microsoft-Windows-Kernel-Process` provider and its keyword values.

The configuration requests a new `SL3Image-<32 hex digits>` name and a fresh GUID. It does not select `NT Kernel Logger` or use the classic SystemTraceControlGuid as its session identity. PLA reports `IsKernelTrace=false` for this modern-provider configuration. That is its reported legacy classification; it does not prove what a live start will do or claim that the requested events are unrelated to the kernel.

The prospective output root is a new path under this project's `tests/results/local`. The template requests file output, no append/overwrite, `SegmentMaxSize=64`, one-second flush, no segmentation, no schedules or task, and a data-set duration of 1–60 seconds. Microsoft documents [Duration as the data collector set's run duration in seconds](https://learn.microsoft.com/en-us/windows/win32/api/pla/nf-pla-idatacollectorset-get_duration). An operating-system-owned duration is the candidate independent stop mechanism; acceptance of its XML is not an observed stopping guarantee or file-size bound. Microsoft also describes [the size setting as a best-effort limit](https://learn.microsoft.com/en-us/windows/win32/api/pla/nf-pla-idatacollectorset-get_segmentmaxsize), so actual file bounds still need checking.

## What was tested

The actual Windows PLA object accepted the five-second configuration with zero validation entries. It also accepted the one- and sixty-second boundary configurations. For every positive, the script reread XML and checked session identity, provider/keyword, logger/clock modes, duration, disabled schedules, output policy and legacy classification. GUIDs are set through XML serialization to handle the observed PowerShell COM GUID-marshalling limitation.

Four actual CLI refusals reject duration 0, duration 61, an existing report path and `-Run`. The existing report remains intact. No native transport or USB capture dependency changed, so archived native suites were not repeated.

```powershell
pwsh -NoProfile -File scripts/prepare-hub-image-source.ps1 `
  -DurationSeconds 5 -Output analysis/new-hub-image-source-plan.json
```

The report path must be new. `configurationValidated` means the uncommitted model survived the checked round-trip. The report explicitly retains false fields for source persistence/start, runtime flag forwarding, independent stopping, observed rundown and readiness admission.

The subsequent [validation-only preflight](hub-image-source-validation.md) now reaches PLA's Commit API with only `plaValidateOnly=0x1000`. It passes with a directly queried limited token, records two specifically checked inactive-field warnings, and verifies that the named collector remains absent. The preparation tool itself still has no Commit call or live-start option.

## Outstanding runtime work

Microsoft's [ExtendedModes documentation](https://learn.microsoft.com/en-us/windows/win32/api/pla/nf-pla-itracedatacollector-get_extendedmodes) lists older flags and does not promise forwarding of the system-logger bit. Local object acceptance therefore cannot establish that PLA's start path will honor it. This is a specific remaining implementation question, not permission to use a global logger instead.

Before joining this to a USB experiment, an owned collector needs create-new semantics, verified identity, bounded status observation and cleanup of only its own configuration/session. A short administrator-context source-only test must verify the effective session name/GUID/mode, useful kernel image/rundown events, loss counters and retirement. A separate test must show that the configured duration still ends the source after its launching process exits. Failure or an unavailable system-logger slot must not trigger quota, privilege or existing-session changes.

Only a qualifying recording can then be checked with the [offline kernel-image inspector](kernel-image-rundown.md) and correlated with the USB window. The [normal-token module query](loaded-hub-metadata.md) remains partial because its timestamp is zero. The first current-worker normal-token read-only control test can still preserve numeric USB states without this new source; no automatic second redirect is admitted by the preparation tool.
