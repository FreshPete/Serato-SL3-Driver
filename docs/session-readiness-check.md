# Read-only checks before the first approval prompt

The kit now has an explicit native readiness command. On this Windows host it observed six passing prerequisite checks without opening the SL3, loading a package DLL, creating a session or requesting elevation. This is readiness for a startup attempt, not evidence that the new kit starts audio or shuts down reliably. [Host observation and test evidence](evidence/session-readiness-20261106.json)

## Scope

`scripts/inspect-sl3-session-readiness.py` verifies the reviewed origin package and proposed current-account binding, then checks:

- Native x64 Windows and an ordinary desktop token.
- No running process named `Serato DJ Pro.exe`.
- An installed/running UsbDk kernel service whose configured image on disk has the reviewed hash.
- Exactly one present Windows PnP identity matching the genuine SL3 VID/PID.
- Original Serato resources, absent planned native installation/pointer/permit/installer-resource state, and absent temporary ASIO/CLSID registration.
- Direct imports of the native package resolving from protected native System32 files through the existing runtime checker.

The actual host observation found Windows build 26300, an ordinary native x64 process, no Serato process, one matching present SL3 identity, the running reviewed UsbDk service, clean planned state and 16 resolved import modules backed by ten system files. No device serial/instance names are included in the report. The service check observes the configured image on disk, not the identity of kernel memory. It does not claim a signature-policy or in-memory attestation.

PnP inspection uses Configuration Manager's present USB identity list, with a bounded retry if that list changes. It does not load UsbDkHelper, redirect the device, read hardware descriptors, query the clock, select alternates, change rate, submit audio or write firmware. The runtime checker may initialize Windows System32 dependencies, as in its existing contract; it never loads the package's DLLs/executables and does not certify delayed/transitive behavior. No driver installation, service start, reset, policy change or automatic repair is attempted.

Each query reports pass, blocked or unknown. Any blocked/unknown result prevents readiness. Existing state is reported for review/recovery and is preserved. The result is a point-in-time observation: normal wrapper/staging/transport checks still apply at use, and connection or process state can change afterward.

## Native and startup integration

The developer entry uses the normal kit argument shape:

```text
SL3_Rebuild_Development_x64.exe --check-kit --kit-manifest ABSOLUTE_KIT_DIRECTORY/kit-manifest.json --expected-kit-manifest-sha256 REVIEWED_KIT_MANIFEST_SHA256 --app "ABSOLUTE_SERATO_DIRECTORY/Serato DJ Pro.exe"
```

Exit 0 means the observed prerequisites passed; exit 3 means blocked/unknown. The native launcher pins forty source/license/evidence files and both runtimes before the checker can execute. Full static kit verification precedes host queries. No persistent session directory is created by Check.

`--start-kit` now performs this same readiness check before preparing session state or requesting its first administrator approval. If readiness does not pass it returns without entering startup. `--plan-kit` and `--prepare-kit` remain offline metadata/preparation operations; they do not require connected hardware. The advanced existing full-session entry and protected wrapper guards retain their own contracts. **The combined Start route, including this new precheck, has not been run live.** No claim about an observed blocked live Start is inferred from the separate Check tests.

## Verification and remaining work

Seven policy checks cover ordinary/native token requirements, a closed application, all three filter conditions, exactly one identity, clean state, direct imports and unknown check rejection. Four actual Windows checks cover native readiness in a moved spaces/Unicode kit with empty `PATH`, changed-code refusal before Python, incomplete context refusal and an existing-pointer fixture which was reported as blocked and preserved. That fixture lived in an owned temporary directory; no global pointer or fake protected installation was created.

Thirteen native kit preparation/refusal regressions, eleven capsule entry cases and eight Windows argument round trips also passed: 43 targeted checks in this run. The strict private runtime inventory passed afterward. Native audio binaries were unchanged. The test copies were removed; the assembled private kit remains uninstalled and has no session state.

The next attended test still needs real startup through the kit, actual installer context/approvals, ASIO callbacks and manual close before the diagnostic limit, followed by rollback and reopen. Physical output, measured timing, longer operation, another account/PC, prerequisite installation and a simple launch/recovery interface remain unfinished. Windows/PnP readiness does not prove descriptor acquisition, current rate, Phase signal, DVS tracking, audio continuity or hardware recovery.
