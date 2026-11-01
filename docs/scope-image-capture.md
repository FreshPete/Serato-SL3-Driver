# Combined metadata-scope and image capture

The combined collector now has a separate **Scope** scenario: a fixed 120-second image-source job enclosing a 60-second USB/WPP/state capture. The ordinary-user role selects the native metadata-scope probe, requesting one acquisition, three facade lifetimes, three clock reads and final release. The administrator role collects traces and state only. One explicit attended launch is intended to request one administrator approval; it installs no persistent broker.

The original Controls scenario remains a 60-second image job around a 20-second USB capture. Scope has distinct collector/result schemas, a `scenario: Scope` marker, its own native executable/hash, nineteen reviewed probe dependencies and the existing scope-runtime checks. The common plan filename and launcher retain their historical names; they do not make a controls-only result a scope result.

The image-source preparer, validation-only check and source runner accept durations 1–60 seconds or the fixed 120-second window. Other intermediate/longer durations are rejected. A logging batch using 120 seconds must contain exactly one job and use `observed-rechecked` native source identity. Existing ownership, no-append/no-overwrite, source validation, query deadlines, loss rejection and cleanup rules remain. The 64 MiB post-capture inspection bound is unchanged; this is not a claim of an enforced native hard file cap.

## Plan and launch roles

Preparation and inspection run without starting any trace or device operation:

```powershell
.venv/Scripts/python.exe scripts/collect-controls-with-images.py --prepare analysis/logging-batch-scope-FRESH --scenario Scope
pwsh -NoProfile -File scripts/start-controls-image-capture.ps1 -Plan analysis/logging-batch-scope-FRESH/controls-image.json
```

Choose a genuinely fresh name each time. An attended launch would explicitly add `-Run` to the second command. That path has **not** been exercised for Scope. The launcher uses the frozen reviewed PowerShell path for both roles. The normal role keeps its existing admission, token, native watchdog/whole-child deadline, no-retry and selected recovery checks. The collector starts USB collection only after fresh strict image-source observations and the owned committed-source check. It requests 60 USB seconds for Scope; it never starts the device probe itself.

The longer image window allows startup/inspection margin around the full USB window. Actual timestamps remain decisive: the collector does not set a successful window-qualification flag merely because both jobs complete. The image owner gets a bounded 190-second completion wait for Scope, preserving its cleanup responsibility on errors. A timeout reports the exact still-owned process; it does not kill a collector that may own cleanup or permit another acquisition. Controls retains its 130-second wait.

## Independent qualification

`validate-controls-image-window.py` selects the scope native image and invokes the split-role validator with Scope enabled. It checks the distinct collection schema, fixed 120/60 durations and observed/rechecked source policy before inspecting the frozen evidence. A controls collection result or shortened image job is refused even when other saved hashes are made consistent.

The image ETL is re-inspected against the current disk image. Consistent USBHUB3 DCStart/DCEnd metadata must bracket the **whole actual USB/probe window**, including at least twelve seconds after probe retirement. Loss, reload, metadata mismatch and wrong timing remain failures. Success means same-window image-version metadata consistency; loaded-memory identity, physical-device identity, readiness, audio and Serato compatibility are not established by it.

## Verification scope

Actual normal-token checks prepared the 120-second PLA configuration, inspected the generated combined Scope plan through the default launcher, and performed `plaValidateOnly` (`0x1000`) validation. They started no source, created no capture/test context and requested no UAC prompt. Intermediate and overlong duration checks reject before collection. Mocked collector checks verify the selected USB duration, no device-probe launch, distinct result schema and cleanup-owner handling. Qualification tests use synthetic image metadata and mock native validation/ETL decoding; they verify Scope validator/image selection and reject cross-scenario/short-window substitution. They are not physical trace evidence.

The native C++/ASIO build inputs and reviewed scope probe dependencies are unchanged. No archived physical result is promoted to this collector revision. The full Python suite result and exact hashes are recorded in [verification evidence](evidence/scope-image-integration-20261101.json). The live elevated Scope launcher, real image/USB window, physical scope reuse, current-build analogue audio/latency, deployed ASIO and current Serato/DVS remain unverified. No driver, binding, trust, registration, firmware or security-policy change ran.

See [metadata probe](metadata-scope-probe.md), [USB-only scope launcher](scope-trace-launcher.md) and [original combined Controls capture](combined-controls-image-capture.md).

The subsequent [rate observation update](rate-observations.md) changes native worker inputs. The original prepared `logging-batch-scope-image-ready-20261101` plan was explicitly disarmed without execution and must not be rearmed. Its passing preparation checks remain historical; prepare a new plan against the rebuilt worker for any future attended test.
