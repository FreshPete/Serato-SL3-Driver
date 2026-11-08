# Rane SL3 Windows beta installation guide

Use this guide for **v0.1.0-beta.1**, a community beta for the Rane SL3 on Windows 11 x64. Install it once, then open Serato from your usual shortcut.

## 1. Check prerequisites and download the beta

- **Serato DJ Pro 5.0.0.1278 for Windows** must already be installed at `C:\Program Files\Serato\Serato DJ Pro`. The beta checks the exact executable and resource file. [Serato DJ Pro 5.0.0 download page](https://serato.com/dj/pro/downloads/5.0.0)
- **UsbDk 1.0.22 x64** is installed separately. Under **Assets**, choose `UsbDk_1.0.22_x64.msi`. Run it if UsbDk 1.0.22 x64 is missing, then restart Windows if the installer asks. [Official UsbDk release](https://github.com/daynix/UsbDk/releases/tag/v1.00-22)
- **The SL3 beta ZIP** contains the setup app and the files it needs. Download `SL3-Compatibility-Setup-v0.1.0-beta.1-win-x64.zip`. [Download the setup ZIP](https://github.com/FreshPete/Serato-SL3-Driver/releases/download/v0.1.0-beta.1/SL3-Compatibility-Setup-v0.1.0-beta.1-win-x64.zip)

## 2. Install SL3 support

1. Close Serato. Connect the SL3 directly to a USB port on the PC.
2. In File Explorer, right-click the beta ZIP and choose **Extract All**. Use a short, writable local folder, such as `Downloads\SL3-Beta`. Keep the full extracted folder together, including the `kit` and `watcher` folders.
3. In the extracted folder, open `SL3_Compatibility_Setup.exe`. It has a green PF icon.
4. Click **Check setup**. Wait for **Ready to install**.
5. Click **Install** and approve the Windows administrator prompt. Leave the setup window open while the progress bar is moving.
6. When you see **Installed — ready for a Serato startup test**, close the setup window and launch Serato normally.

Setup registers the rebuilt ASIO driver, applies a version-specific change to Serato’s local device resource and adds a Windows sign-in watcher for the account that runs setup. Keep the extracted folder so you can restore the original setup later.

## 3. Check audio before trying DVS

1. Keep the SL3 connected when you launch Serato.
2. Load a local track on one deck, select **INT** and press Play. If you’re monitoring through an external mixer, connect the corresponding SL3 RCA output to a **LINE** input and start with the volume low. [Serato’s INT mode guide](https://support.serato.com/hc/en-us/articles/234760888-Internal-Mode)
3. If you use Phase over RCA, the tested two-deck setup had Phase A on SL3 inputs 3/4 and Phase B on 5/6, both set to **LINE**, with both decks in **REL**. [Phase demo and test setup](demo-20261105.md)

## Restore the original setup

1. Close Serato completely.
2. Reopen `SL3_Compatibility_Setup.exe` from the same extracted folder.
3. Click **Check setup**, then **Restore original setup**. Approve the Windows administrator prompt and wait for **Original setup restored**.

Use Restore before updating Serato or switching to another SL3 beta package.

## If setup or audio gets stuck

| What you see | What to try |
| --- | --- |
| **UsbDk is unavailable** | Confirm the x64 UsbDk prerequisite is installed, finish any requested restart and run **Check setup** again. |
| **Close Serato before continuing** | Exit Serato completely, then run **Check setup** again. |
| **Setup needs review** or **Setup needs attention** | Open **Show diagnostic details**. Check the exact Serato build and install location. If they match, include the status and relevant details in a beta issue. |
| Serato opens in offline mode with the SL3 connected | Close Serato, confirm the SL3 is plugged directly into the PC, and check that setup still reports the package installed. Reopen Serato from its usual shortcut. If it still opens offline, report it. |
| Serato’s controls freeze before SL3 audio connects | Try turning off **Setup → Library + Display → Show Streaming Services** and restart Serato. That stopped repeated stalls on the test PC, although some control and waveform lag remained. [Serato’s settings guide](https://support.serato.com/hc/en-us/articles/223364427-Library-Display) |

For a report, include the beta version, Windows build, Serato version, the exact message you saw and whether the problem happened during setup, startup or playback. If you were playing, mention **INT**, Phase or timecode vinyl. [Report a beta issue](https://github.com/FreshPete/Serato-SL3-Driver/issues)

## What has been tested

- The 64-frame driver completed a two-minute loop in Serato with zero reported callback dropouts and verified USB release on exit. In this test Serato used a separate 128-frame application buffer. [Playback evidence](one-time-setup-window.md#serato-playback-comparison)
- An earlier installer-assisted run demonstrated two Phase Essential decks in REL with both remotes on one platter. [Demo](demo-20261105.md)
- The setup window has a PF icon, a Windows progress bar while an action is running, and links to the repository and Peter French's site. [Icon source](https://peterfrench.dev/)

The beta removes the earlier ten-minute test cutoff. Closing Serato ends the audio session. We are working to lower latency as far as we can while keeping playback reliable. 32 frames remains experimental. Timecode vinyl, independent two-platter control and longer sessions need further testing. [Report a beta issue](https://github.com/FreshPete/Serato-SL3-Driver/issues)

## Source and build inputs

The corresponding-source archive includes the project tree and the three ASIO SDK 2.3.4 interface headers used in this build under `artifacts/references/asio-sdk-2.3.4/ASIOSDK`, with Steinberg's license text. The project and these interface headers are distributed under GPLv3. The setup ZIP includes its third-party notices. [ASIO SDK license](https://github.com/audiosdk/asio/blob/main/LICENSE.txt)

The audio build used Visual Studio 2019 x64 with Windows SDK 10.0.19041.0 and `scripts/build-native.ps1 -Configuration Release -WithAsioComponent -WithUnmeasuredAsioDiagnostic`. Prepare the [activation package](../scripts/prepare-asio-activation-deployment.py) with `--application-bound --playback-keepalive --buffer-frames 64 --until-application-exit`. The source includes the [native entry](../scripts/build-on-demand-entry.ps1), [setup window](../scripts/build-setup-window.ps1) and [portable ZIP verification](../scripts/package-setup-window.py). The [sign-in watcher source](../scripts/native/serato-notice-startup/notice-startup.cpp) builds as a Windows x64 DLL with the C++17 MSVC toolchain and User32. A locally rebuilt watcher DLL must be reviewed and pinned in the watcher script before preparing a new setup bundle. The [setup engineering notes](one-time-setup-window.md) document the package and its local prerequisites.
