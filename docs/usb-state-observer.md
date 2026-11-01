# Passive hub-state reader

`sl3_usb_state_observer` now reads the USBHUB3 state events needed to investigate the [reopen fault](reopen-state-context.md). The actual Release and Debug executables replay the saved ETL under non-elevated Windows tokens. Each reads all 14,368 events and produces 585 USBHUB3 state records, matching the independently decoded XML field-for-field, including exact 100-nanosecond timestamps. No SL3 request or new hardware test ran.

Live subscription is implemented but **has not passed an attended positive test**. The reader makes no readiness decision and launches no device worker. It is not yet connected to a production reopen policy.

## Why the ordinary connection query is insufficient

Microsoft documents [a user-mode hub connection-information request](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usbioctl/ni-usbioctl-ioctl_usb_get_node_connection_information_ex) and its [connection-status enum](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usbioctl/ne-usbioctl-_usb_connection_status). These are useful diagnostics, but a connection report does not by itself establish the hub state that accepts a cycle.

In the pinned current USBHUB3 image, one `HUBFDO_IoctlGetNodeConnectionInfo` path copies `_PORT_CONTEXT.ConnectionStatus` at offset `0x590` to output offset `0x1f`. The inspected `HUBPDO_CreatePdo` branch assigns `DeviceConnected` (1) to that cached port field during PDO creation. The small `HUBDSM_Stopped` entry does not update the field. [Source/layout/disassembly evidence](evidence/usbhub3-connection-status.json).

This is a reason **not to promote “connected” into “safe to redirect.”** It is not a complete write/call-graph analysis or proof that the cached field has the same value in every runtime state. No actual hub IOCTL or normal-user hub-access test was performed. Other supported observation APIs remain possible; a privileged broker is not inferred to be necessary.

## Reader behaviour

The separate C++ executable uses the Windows event consumer and TDH property APIs. It accepts a bounded local ETL file or an explicitly named existing `SL3Startup-<32 lowercase hex digits>` real-time session. It creates neither a source session nor a provider configuration, closes only its own consumer handle, never elevates itself and sends no USB request. Default/`--plan` mode only reports its contract.

Output is a new, never-overwritten NDJSON file: header, state observations and final summary. The header records the executable's actual PID, queried elevation state and token type. Each observation preserves event/task/PID, normalized FILETIME, trace-local device/context pointers, state-machine namespace, state, event and depth. Pointers and FILETIME are decimal **strings**, preserving all bits when consumed by JSON tools with limited numeric precision. The other bounded integer fields remain numbers. Unknown state names are not invented: this reader emits numeric fields only.

It includes USBHUB3 events 110 and 111 across the recorded ports. An SL3-specific consumer must separately correlate physical identity, hub/port, context and re-enumeration generation. The reader deliberately emits `readinessAdmission: false`; neither a state number alone nor an empty observation window is permission to reopen. Loaded-image qualification also remains a separate requirement before applying the current-image symbol names to future events.

Event/property/output counts are bounded, malformed property widths fail, partial outputs remain diagnostic, and summaries distinguish failed processing from successful reading. Opening a consumer can succeed before reading discovers a nonexistent source session. That observed case returns failure with status 4201 and zero events, retaining a failed diagnostic file when one was created.

Saved-file summaries use the completed file's `TRACE_LOGFILE_HEADER` loss counters. The unused `EVENT_TRACE_LOGFILE.EventsLost` member is not used. Live summaries explicitly mark their header loss snapshot as incomplete; the full source ETL and existing trace-loss validation remain authoritative. A successful consumer read does not attest source-session cleanup, kernel retirement, uninterrupted identity or driver readiness.

## Build and replay

The observer has its own small CMake project under `scripts/native/usb-state-observer`; it does not change the frozen ASIO/worker build inputs.

```powershell
./scripts/build-usb-state-observer.ps1 -Configuration Release
./scripts/build-usb-state-observer.ps1 -Configuration Debug
```

Both commands build with warnings treated as errors and run the actual executable checks against the hash-bound historical ETL. They save manifests containing source, binary and verification-record hashes. [Build-bound evidence](evidence/usb-state-observer-build.json).

Explicit saved-file replay requires absolute local paths and a fresh output file:

```powershell
& ./artifacts/build/usb-state-observer/Release/sl3_usb_state_observer.exe `
    --etl $savedEtlAbsolutePath --output $freshObservationAbsolutePath
```

Checks cover actual native ETL replay versus all 585 XML observations, normal producer tokens, no overwrite, missing files, malformed ETL, invalid session names/durations and a nonexistent session. Binary imports confirm the executable uses `OpenTraceW`, `ProcessTrace`, `CloseTrace` and TDH, with no direct USB, source-session creation/control or elevation API import. This supplements source review rather than proving the behaviour of every Windows DLL it calls.

## Next attended integration

The [optional collector integration](live-state-capture.md) now prepares file plus real-time delivery and supervises this reader in the administrator tracing role. Its live positive path has not run. Windows also restricts [real-time consumption](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/ns-evntrace-event_trace_logfilew) to appropriately authorized users/services. Saved-file replay under a normal token does not prove live subscription under that token. No groups, access rules or security settings were changed here.

The intended diagnostic use is a separate observer in the existing administrator tracing role, leaving the probe/worker in the ordinary role. It should follow release into the original stack's settled state, with a qualified hub-driver image and exact target generation. It must first prove live delivery, identity correlation, loss handling and private-consumer shutdown before its output participates in any supervised second-open test. Production application permissions and a supported readiness predicate remain unresolved.

The session mode accepts a requested 1–60 second observation window. At expiry it requests closure of its consumer handle. [CloseTrace](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/nf-evntrace-closetrace) permits queued real-time events to drain afterward, so this is not a hard wall-clock retirement guarantee. A supervising process still owns the diagnostic deadline; it must not stop the separate source collector. No positive live subscription, cancellation/drain or actual reopening test is claimed by the saved-file checks.
