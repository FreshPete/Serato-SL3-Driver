# Identifying the hub image used by a trace

31 October attended update: the checker now supports explicitly validated version-3 image metadata. The logging-only ETL contains 259 consistent kernel rundown pairs and a USBHUB3 size/timestamp/checksum match. [Actual evidence and strict limits](attended-hub-image.md). This image window occurred after the control trace; the earlier failed-reopen trace remains unqualified. The original source run still failed its GUID query and does not establish timer expiry or a file-size bound.

The saved failed-reopen trace cannot identify its loaded USBHUB3 image. A fresh offline decode reproduces all 14,368 events and the original XML hash, but finds no kernel image events. The current disk image and matching PDB therefore remain conditional labels for that historical trace.

There is now an [offline image-rundown inspector](../scripts/inspect-kernel-image-rundown.py), with [ten independent software tests](../scripts/test-kernel-image-rundown.py) and a [verification record](evidence/kernel-image-rundown-20261031.json). It prepares the analysis needed for a future trace; it does not start tracing or change the SL3 test sequence.

A subsequent [bounded extended module query](loaded-hub-metadata.md) now returns the loaded hub path, size and checksum with an actual limited token. The size/checksum match the copied image, but its timestamp is zero; this additional observation remains incomplete and does not retrospectively identify the historical loaded image.

The [timed-source preparation](hub-image-source-preparation.md) subsequently validates an uncommitted PLA configuration for the modern System Process Provider. Its unique name/GUID, loader keyword and requested system-logger mode survive the actual Windows XML round-trip. No live source, runtime flag forwarding or independent stop has yet been validated.

## What was actually checked

A normal-token `K32EnumDeviceDrivers` query succeeded and reported 259 entries, but every base address was null. The actual process token was non-elevated, elevation type 3. No privilege was enabled. This matches the documented [Windows 11 24H2 restriction](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-enumdevicedrivers): a successful return without enabled debug privilege can contain only null addresses. That result cannot identify the hub module.

Instead, the inspector was exercised against Microsoft's public PerfView `net.4.5.2.x64.etl` test input, pinned to [commit 9f071a5](https://github.com/microsoft/perfview/tree/9f071a5cb2e70cdfee13abc510344ab1e8840c90/src/TraceEvent/TraceEvent.Tests/inputs). Its ZIP, extracted ETL, parser source and MIT license are retained locally under `artifacts/references/perfview-image-rundown`. This is a third-party historical test trace, not a recording of this PC or the SL3.

Windows' actual offline decoder produced 179,474 events. The inspector recovered 141 kernel image DCStart/DCEnd pairs, with matching base, size, checksum and timestamp in each pair. It separately counted 3,314 process-image events and two other image opcodes. The sample contains no USBHUB3 target, so comparing it with our copied image correctly reports `targetPresent: false` and `matchingRundownMetadata: false`.

The original failed-reopen ETL likewise reports no target or metadata match. Both records retain `loadedMemoryIdentityVerified: false`, `usbWindowQualified: false` and `readinessAdmission: false`.

## Meaning and limits

Microsoft documents the [classic image events](https://learn.microsoft.com/en-us/windows/win32/etw/image-load), including load, unload and start/end enumeration. The checker recognizes the classic image event GUID inside tracerpt's `ExtendedTracingInfo`, together with the system provider GUID. Looking only at the top-level provider would miss these events. It accepts the inspected version-2 schema, uses the payload's process ID to distinguish kernel images, and preserves full kernel paths and 64-bit bases.

A candidate metadata match needs exactly one start/end pair at the requested full path, no intervening recorded load/unload, consistent nonzero identity fields, and source headers reporting no lost events or buffers. It compares the selected disk PE's `SizeOfImage`, `TimeDateStamp` and checksum. Missing, unknown or contradictory records cannot supply a match. A matching pair would still only qualify metadata for its own image trace. It would not establish complete coverage of a separate USB window or cryptographically identify loaded memory.

In particular, XPerf's ImageID/RSDS records are ignored. Microsoft's [symbol parser source](https://github.com/microsoft/perfview/blob/9f071a5cb2e70cdfee13abc510344ab1e8840c90/src/TraceEvent/Parsers/SymbolTraceEventParser.cs) describes those as records added by XPerf. They must not be presented as direct proof of the loaded module's PDB GUID.

The CLI decodes only an existing ETL, hashes the source before/after, bounds its size to 64 MiB, bounds decoded XML to 512 MiB/two million events, and creates a new report without overwriting an existing one. It rejects DTD/entities and malformed properties. It neither opens a USB device nor controls a trace session. The standard decoder can warn about unrelated schemas in the public sample; the inspected kernel records must still have all required named fields.

## Reproduction and next capture

From the project directory, using a new output filename:

```powershell
.venv/Scripts/python.exe scripts/test-kernel-image-rundown.py
.venv/Scripts/python.exe scripts/inspect-kernel-image-rundown.py `
  --etl artifacts/references/perfview-image-rundown/net.4.5.2.x64.etl `
  --image artifacts/references/windows-usbhub3/USBHUB3.SYS `
  --kernel-path '\SystemRoot\System32\drivers\USBHUB3.SYS' `
  --output analysis/new-image-rundown-report.json
```

For a future attended capture, a kernel image source must begin before the USB interval and retire after it, with no relevant loss or target reload. Its observed path and metadata then need comparison with the pinned disk image/PDB and correlation with the USB interval. A complete capture implementation and a positive USBHUB3 result remain outstanding.

Microsoft supports [separately named system tracing sessions](https://learn.microsoft.com/en-us/windows/win32/etw/configuring-and-starting-a-systemtraceprovider-session) with a fresh GUID and `EVENT_TRACE_SYSTEM_LOGGER_MODE`. Such a collector must own and bound its session, leave other sessions alone and handle unavailable system-logger slots without changing quotas or privileges. The existing ordinary logman session must not simply be assumed to collect kernel image rundown. No such new live source was started here.

This addition does not delay the first attended current-build normal-token read-only control test: that run can still establish actual access and preserve numeric state observations. It does prevent the offline checker from silently upgrading those observations into version-qualified cycle readiness. Reliable repeated opens and current Serato/DVS operation remain unverified.
