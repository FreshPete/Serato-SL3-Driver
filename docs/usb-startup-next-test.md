# Next SL3 startup experiment

Prepared and executed 26 October 2026. The pre-test specification below is retained with the subsequent result recorded first.

**Completed subsequent binding test:** WinUSB started successfully, PnP event 410 and both read-only probes passed, and all interfaces were active at alternate 0. Trace: 22,044 events with no lost events/buffers. Cleanup restored the original baseline without a power cycle. The earlier fault did not reproduce. [Actual result and revised next gate](windows-traced-test.md). The remainder records the pre-test specification; a KMDF replacement is conditional and is not the immediate next step after this success.

**Completed audio-alternate follow-up:** WinUSB also selected and restored both audio interfaces successfully. [Current result and next gate](windows-audio-alternates-test.md).

## Concrete change

Instrument startup **before** a controlled binding attempt. The previous development package was accepted but failed before a user-mode handle existed. Changing the endpoint probe cannot affect that failure. A transport rewrite is a candidate, not yet an established fix.

The project now includes `scripts/capture-usb-startup.ps1`. Its default mode only checks the three local USB ETW providers and prints a plan. `-Capture` requires elevation and records for 5–60 seconds into a new directory, with a 64 MiB circular file. It captures hub, controller-extension and xHCI events using Default, PartialDataBusTrace and StateMachine keywords. Raw traces include other devices on that stack and limited transfer data; keep them under ignored local results. It installs nothing and does not trigger a device start.

The provider names and numeric keywords were verified on this host. PowerShell syntax and default preflight pass. An elevated five-second passive capture at 22:42 UTC recorded a 3,014,656-byte ETL with **5,215 events, zero lost events and zero lost buffers**. The original Rane/code-39 state was unchanged before/after; the unique collector was deleted. The automatic timeout had already stopped recording before the final explicit stop, which correctly reported “not running”. [Sanitized smoke evidence](evidence/usb-startup-trace-smoke.json).

Built-in `tracerpt` decoded all three USB providers. Strict XML reported one schema mismatch in a system trace metadata event, with no USB-provider processing errors; relaxed XML completed successfully. This establishes capture/decoder operation, not that the absent failure has been identified. The timeout and finally block bound and clean up the unique session, without touching any pre-existing trace session.

```powershell
# Read-only provider preflight; no session or file is created.
./scripts/capture-usb-startup.ps1

# Elevated passive smoke capture, without any driver/device changes.
./scripts/capture-usb-startup.ps1 -Capture -DurationSeconds 5 -OutputDirectory tests/results/local/usb-trace-smoke-02
```

The completed run is retained under `tests/results/local/usb-trace-smoke-01`; select a fresh directory for another capture. Decode its versioned ETL using `tracerpt <file.etl> -o <new-events.xml> -of XML -lr -summary <new-summary.txt>`. Check the header's `EventsLost` and `BuffersLost`, and the trace's own start/end bounds; manifest `startedUtc` is the acknowledgement after `logman start`, not the exact ETL start timestamp.

The commands follow Microsoft's [USB trace capture guidance](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/how-to-capture-a-usb-event-trace), using only this host's USB 3 stack providers. A high-speed USB 2 device on an xHCI controller still uses that stack. The collector does not filter capture to the SL3; correlate by hub/port and device identity during analysis. No claim is made that ETW necessarily exposes every on-wire packet.

## One diagnostic reproduction, after capture validation

1. Confirm the recovered baseline: SL3 normal four-interface descriptors, original Rane binding/code 39, no experimental INF/trust entries. Save the current hub/port association. A trace with the blocked original driver cannot show Rane's D0 implementation executing.
2. Start a 60-second passive capture in a fresh directory **before** staging/binding. Run the approved development installation from a separate elevated process only once the trace is recording. The historical installer deliberately refuses to overwrite its existing test record; a reviewed distinct result path/retry guard change is needed before using it for this diagnostic reproduction. Do not delete old evidence merely to bypass that guard.
3. A reproduction with the unchanged signed package is justified only to locate the previously unrecorded failure. It is not an attempted functional fix. Its unexpired public certificate/catalogue still exist, but temporary trust was removed; the documented local trust setup would need to be deliberately reapplied and subsequently cleaned up. The private key was deleted, so a changed INF/catalogue needs a newly prepared signing identity. No trust import is performed by the capture script.
4. Stop at the first startup failure. Save PnP events, trace files and exact UTC bounds. Do not run command replay, audio, repeated reconnects or automatic port cycling. Restore the original binding and remove only the experimental package/trust/GUID as in the completed recovery; full power removal was required last time.
5. Decode the ETL locally, check events lost/buffers lost and circular-file overwrite, and establish the first failing stage in the table below. If the trace lacks the needed URB/setup/completion information, improve capture/decoding before claiming a protocol cause.

The existing generic WinUSB installer is **not** enabled for automatic retries by this work. The preceding prerequisites explain what must be prepared before that single diagnostic reproduction.

## Decision from the first failing stage

| Trace observation | What it establishes | Next implementation change |
| --- | --- | --- |
| Descriptor/port failure before a configuration request | The failure precedes the original driver's setting-pair difference | Investigate that enumeration/host/port failure; do not send SL3 commands |
| SET_CONFIGURATION / select-configuration fails with alt-zero interfaces | Configuration is the failing boundary; not yet proof that alternate 1 fixes it | Build a minimal KMDF diagnostic transport selecting pairs `[0,1,1,0]` in prepare-hardware; log NTSTATUS and underlying USB status |
| Configuration succeeds, D0/power transition fails before open | The failure lies after configuration and before user mode | Follow the captured failing power request; change only the established cause |
| Driver starts and handle/associated interfaces open | User-mode work can now affect the device | Descriptor/pipe queries first; then a separately gated alternate-setting test if needed |
| Queries and settings succeed but control replies do not | Configuration alone is insufficient | Compare interrupt reader timing and 64-byte framing with the recovered original; verify command semantics before sending writes |

## Minimal KMDF candidate, if the trace supports it

The proposed first revision should contain only the ordinary four-interface configuration path and operation/status logging. Validate VID/PID, configuration descriptor and high-speed operation; reject other personalities. Select interface settings `[0,1,1,0]` with an explicit pair array in prepare-hardware, validate pipes 0x06/0x82/0x81/0x01, expose a diagnostic interface and return. Log all errors rather than ignoring selection results as the legacy path does in places.

Do not copy the whole original driver or its legacy request allocator, firmware helpers, command error recovery/port cycling or unconditional control writes. A later revision can test the original IN-then-OUT audio-pipe reset order, followed by a separately reviewed interrupt-reader experiment. Command 0x03's response check precedes reader start in the original, 0x36's semantics remain unknown, and sample-rate setup is conditional; none should be guessed into the first revision.

A new kernel binary needs a Windows signing route compatible with the security target. The prior acceptance of an INF catalogue for Microsoft's inbox WinUSB binary does **not** establish that a self-signed new kernel binary will load. Do not change Secure Boot, code-integrity policy or test-signing settings to bridge that gap.

## Result required before advancing

An interpretable trace identifying the first failing request/state transition, or a successfully started transport with verified descriptors and pipe map. A PnP status change alone is insufficient. Audio/ASIO/Serato/DVS work remains conditional on this transport gate.
