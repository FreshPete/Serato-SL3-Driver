# One-time SL3 setup window

The current local build binds the setup window to the [application-bound ASIO package](asio-on-demand-deployment.md#application-bound-candidate). The window still offers **Check setup**, **Install** and **Restore original setup**. Install and Restore request separate Windows approvals when invoked. Serato starts separately from its usual shortcut.

Follow-up: [administrator result capture and local diagnostics](setup-result-diagnostics.md) now preserve failure details across the postcheck and show the existing ten-minute diagnostic bound. The earlier build/visual evidence below is historical; the latest rendered review was interrupted by the locked desktop.

The simple Windows setup window is now implemented and built. It offers **Check setup**, **Install**, **Restore original setup** and optional diagnostic details. Opening it runs no command. Sixteen checks pass, and the ordinary/expanded layouts and selected keyboard behavior were inspected on this host. **Administrator installation/restoration and normal Serato startup have not run through this window.** [Source, build and observation evidence](evidence/one-time-setup-window-20261106.json)

This is a host-bound engineering prototype around the [reviewed native entry](native-on-demand-experiment-entry.md), not a public installer. It preserves the intended experience: install once, close the setup window and use the original Serato shortcut. Phase and timecode vinyl share the driver; the UI has no Phase-specific installation mode.

## Actions and state

| Action | Behavior |
| --- | --- |
| Check setup | Runs the native read-only experiment check in the background. It checks the selected files/registration and reported Serato process state; it does not open the SL3. |
| Install | Enabled only for a recognized install/retry state with Serato stopped. It rechecks before requesting Windows administrator approval for the fixed native setup action, then observes the resulting state. |
| Restore original setup | Enabled only for a recognized non-clean state with Serato stopped. It requests Windows approval for the fixed native restore action, then observes the resulting state. |
| Diagnostic details | Shows bounded, read-only command output. No upload or message is sent. |

Unknown/conflicting states do not enable privileged actions. The reported running-Serato Boolean disables both installation and restoration; that rule and typed parsing are tested with fixtures without launching Serato. A successful installer exit alone is insufficient for the success label: the following read-only check must observe the expected installed or restored state. Installation success is labelled readiness for a **startup test**, not working audio or DVS.

Commands run on a worker thread. While busy, command buttons are disabled and closing the window is refused. The existing read-only job timeout is retained; privileged transactions are not terminated by the window. Cancelled elevation or failed commands do not trigger another operation automatically. The Install/Restore UAC sequence, failure receipts and real partial-state recovery still need an attended test.

## Interface brief and review

Mode: **Operate**. This extends the existing `DESIGN.md` native Windows world: system colors, standard controls, Segoe UI, scaled layout, visible keyboard focus and optional details. It adds no visual identity or web styling. The skill's platform classifier does not recognize Win32; the established Windows implementation was retained rather than relabelled as a web/mobile platform.

Check setup is the default button; Install is not the default. Access keys are C, I, R and D. Live inspection confirmed the Details access key expands the read-only area and reverse Tab skips disabled installer actions back to Check setup. Both ordinary and expanded views were inspected. Windows reports Segoe UI for body and heading. The native-C++ mechanical detector reported no findings, with limited coverage. Minimum-size interaction, high DPI and high contrast are not claimed validated.

Sixteen actual checks cover clean/installed/partial/conflicting eligibility, the running-state gate/parser, inert opening and preview behavior, command disabling, refusal to close mid-check, a real native read-only check and normal idle close. Preview never dispatches commands. No installer button was clicked in desktop inspection, and all inspected windows were closed afterward.

## Current private candidate

```text
artifacts/build/native-setup-window-app-bound-20261107/build/Release/SL3_Compatibility_Setup.exe
SHA256 9dd0520ba010efe26602253ace5daa8c9782d6197c40a431218d82d88579df86
```

The setup-only kit is `artifacts/build/sl3-on-demand-kit-app-bound-20261107`. All 27 moved-kit checks and 18 window checks passed. The moved kit preserved `asio-init-application-v2` and its native binaries, and the entry rejected an altered activation header before starting the helper. The read-only host check found the original Serato archive, Serato stopped and no temporary native package. This build used the existing window code and had no new visual inspection or privileged actions. Normal Serato startup and physical use of this package still need an attended test. [Build and test evidence](evidence/application-bound-setup-window-20261107.json)

### Earlier review build

```text
artifacts/build/native-setup-window-release-review-20261106/build/Release/SL3_Compatibility_Setup.exe
SHA256 b0a976b9f2def6a07abda8966c70aa0f865dfac2541dcb98de8806fa5d27ff8e
```

Build metadata binds the exact native entry, setup-only kit, generated experiment and source/header files. The review build is an x64 Windows GUI executable with no CLR or external MSVC runtime imports. Each window build requires the selected kit, its prepared state and the native entry at their bound paths.

`prepare-setup-window.py` creates the bound project; `build-setup-window.ps1` builds and runs the owned-window tests. Preparation on this host generated fresh local compatibility resources from the original Serato installation; no vendor archive or application is published with the source. Final postchecks show original installed resources, no occupied session paths or temporary registration, no action lock and no running SL3/Serato process. The earlier standalone normal-start candidate remains source-current. Actual installation, normal Serato selection, physical output/vinyl and reliable native lifetime remain separate requirements.
