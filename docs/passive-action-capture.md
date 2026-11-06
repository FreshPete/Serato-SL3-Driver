# Passive action receiver observed in Serato

Two bounded captures of the original Serato 5.0.0.1278 executable in the existing isolated notice workspace observed the expected Download Driver callback receiver. In both, callback capture, popup return and genuine SL3 arrival publication occurred on the same observed thread, in that order, without observer faults. This is new runtime evidence for the receiver investigation, not an automatic-start or audio result. [Evidence and preserved failures](evidence/passive-action-capture-20261106.json)

## Scope and observations

The workspace uses the earlier notice archive (`f7bfe219…`), not the current 44.1 kHz Phase archive. All 165 native files matched their installed originals before launch and remained unchanged afterward. The rebuilt ASIO installation and registration, broker pointers, rebuilt installer resource and cached rebuilt launcher were absent. The observer invoked no callback, requested no installation, read no audio and opened no device. Serato's own USB behaviour was not measured.

The standalone observer saw six numbered events in each capture: readiness, the exact callback/table/capture match, popup return, two controller-message returns (`0x4f` and `0x2d0`), then genuine SL3 arrival publication. The observed thread matched across the receiver, popup and arrival events. These records do not establish the owning Windows window thread, a delivered arrival at the installer panel, or a lifetime lease on the raw controller pointer. The separate combined-supervisor mode remains untested live.

Each application ran for a twenty-second observation window inside an owned job restricted to one active process, without breakaway. This restriction applies to the workspace process and its children, not host-side Frida services. An owned-Python test verified the limit by observing Windows reject a child launch with error 1816, with no child marker executed and clean fixture exit. The limit uses the documented [Windows job active-process constraint](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information).

## Close requests still did not exit Serato normally

Both application captures accepted one posted window-close request but retained a visible window after the twenty-second grace. The owned process was then forcibly terminated; its job was observed empty. The second capture explicitly unloaded/detached the probe before closing and still timed out. Its command returned failure instead of treating collected observations as clean shutdown.

The first experimental runner's zero exit code meant capture completion and empty-job cleanup only; its saved result explicitly records forced termination and a detach-after-destruction error. The current runner requires normal exit for command success. Both raw results remain preserved.

This demonstrates that a posted-close timeout can occur in a different startup setup with the rebuilt driver absent. It does not prove the ASIO driver caused or did not cause the earlier playback shutdown problem. The older notice archive, one-process restriction, denied auxiliary children, application state, instrumentation and the security events below are material differences. A successful close-post is still not proof that Serato accepted an application quit.

## Defender quarantined a Frida helper

Defender events 1116/1117 during this period record `Behavior:Win32/DefenseEvasion.A!ml` detection and quarantine of temporary `frida-…/idund.exe` files. The latest record names the project's private Python process; an earlier record names an Intel service, so not every event can be attributed solely to these captures. The second console also reported helper startup error 225.

Frida's official [Idun source documentation](https://github.com/frida/idun) describes `idund` as its Apple-device tunnel daemon. That identifies the upstream component name and purpose; it does not attest the exact quarantined file or determine that Defender's finding is a false positive.

Further Frida launches are on hold. No exclusion, protection disablement, quarantine restoration, certificate trust or signing-policy change was attempted. Antivirus, real-time protection and behaviour monitoring remained enabled. The local capture command refuses before importing Frida or creating an application process while `analysis/frida-runtime-security-hold.json` exists; that refusal was checked. This is a local diagnostic hold, not a system policy and not an automatic guard in every historical startup entrypoint. The existing Frida-based session path should not be run again under this unresolved condition.

The next independent work is to establish a compatible local-Windows instrumentation/startup route under unchanged protection. The helper's Apple-device feature is outside the current Windows SL3 scope. A different dependency configuration or toolchain would need its own provenance and checks; bypassing Defender is not the proposed route. An [offline local-only build investigation](frida-local-windows-build.md) now verifies the pinned configuration with nonlocal backends disabled; compilation still needs a newer compiler, and no replacement runtime has been launched.

## Current state

No matching Serato, SL3 worker, Frida or `idund` process remained in the post-capture process snapshot. A fresh native read-only check reported original installed resources clean, no temporary registration and no occupied staging paths. The prepared audio package's four binary hashes are unchanged. No new physical audio/DVS test, normal playback shutdown proof or public installable release was produced.

The owner-local runner is [observe-serato-download-action.py](../scripts/observe-serato-download-action.py); without `--run` it performs input inspection only. Its workspace requirement prevents treating it as a portable user launcher. The containment fixture is [test-passive-action-job.py](../scripts/test-passive-action-job.py) and uses a mocked Frida boundary with owned Python processes, never the actual SDK or Serato.
