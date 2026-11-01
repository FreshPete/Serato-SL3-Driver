# Read-only loaded hub metadata

A bounded, non-elevated query can now identify the loaded USBHUB3 path and report its size and checksum on this host. **Its timestamp is zero, so the result is incomplete identity evidence.** It does not replace the missing historical image record or establish safe reopening.

[Diagnostic](../scripts/inspect-loaded-hub.py), [six offline tests](../scripts/test-loaded-hub.py), [actual-query evidence](evidence/loaded-hub-metadata-20261031.json).

## Actual result

The tool queried its own token: non-elevated, elevation type 3. It made one fixed-size, read-only `NtQuerySystemInformation` class-77 call. Windows returned success and 82,882 bytes: 259 inspected x64 records plus a two-byte terminator. All image base addresses remained redacted. No privilege was enabled or adjusted; no driver/device handle or trace session was opened.

The unique exact target path was `\SystemRoot\System32\drivers\UsbHub3.sys`:

| Field | Loaded-module query | Copied current PE |
| --- | ---: | ---: |
| Size of image | 733,184 | 733,184 |
| Image checksum | 781,464 | 781,464 |
| Timestamp | **0** | 180,548,141 |

The copied file still hashes to `f93fa3a32037c597fd19ca9d65f59e53a1e337123582ed2479d5c16a4848df16`. That hash belongs to the disk file; it is not a hash of kernel memory. The report deliberately distinguishes `availableMetadataMatches: true` from `identityMetadataComplete: false` and `completeMetadataMatches: false`. Its memory-identity, USB-window and readiness fields all remain false. The reason Windows returned zero for this timestamp is not established by this observation.

This extends, rather than contradicts, the earlier [EnumDeviceDrivers result](kernel-image-rundown.md). That API returned null bases and could not provide a hub-module identity. The private extended query supplies additional metadata while leaving addresses redacted.

## Interface and limits

Microsoft documents that [NtQuerySystemInformation and its returned structures can change](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntquerysysteminformation), and recommends runtime linking when it is used. Class 77 and its extended module layout are private; the inspected layout is documented in the [phnt header at pinned commit 53fbbdc](https://github.com/winsiderss/phnt/blob/53fbbdc5b5d2b08761db1c7b26bfa8c820924356/ntldr.h), with the class enumeration in [ntexapi.h](https://github.com/winsiderss/phnt/blob/53fbbdc5b5d2b08761db1c7b26bfa8c820924356/ntexapi.h). Source headers and MIT license are retained locally as research references; the tool uses original Python code and Windows' existing DLLs.

The diagnostic requires native x64 Windows, dynamically loads system DLLs from System32, queries only its own token and this fixed information class, and allocates at most 1 MiB. It rejects a changed record stride, malformed extent, missing terminator, invalid path offset, absent image size or duplicate target. It does not retry with privileges, infer identity from an API success code, or print kernel base addresses. Unsupported or denied results remain failed diagnostics.

The six offline tests check redacted/missing fields, complete-but-still-non-admitting metadata, disagreements, duplicate/lookalike paths and malformed bounds. The saved actual response replays to the same 259 records and exact reported target fields, with its hash matching the real query record. Actual CLI failures preserve an existing report and reject a malformed comparison image before querying.

```powershell
.venv/Scripts/python.exe scripts/inspect-loaded-hub.py `
  --image artifacts/references/windows-usbhub3/USBHUB3.SYS `
  --output analysis/new-loaded-hub-observation.json
.venv/Scripts/python.exe scripts/test-loaded-hub.py
```

The report path must be new. This is a standalone research diagnostic, not an added dependency of the prepared USB collector or production ASIO runtime. No native build inputs changed, so their archived suites were not repeated.

For the next attended run, this can supply supplementary loaded-module observations before and after the trace. Its missing timestamp and lack of intervening load/unload coverage mean a fresh image source and USB-window correlation are still outstanding. The [kernel image inspector](kernel-image-rundown.md), [numeric state reader](usb-state-observer.md), normal-token transport test and actual application/DVS work retain their separate scopes.
