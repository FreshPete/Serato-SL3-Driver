# Windows SL3 beta

The beta targets a Rane SL3 on Windows 11 x64 and Serato DJ Pro **5.0.0.1278** installed in its default Program Files location. It requires the signed x64 UsbDk 1.0.22 filter, installed separately. [UsbDk release](https://github.com/daynix/UsbDk/releases/tag/v1.00-22)

1. Close Serato and connect the SL3 directly to the PC.
2. Extract the whole beta ZIP into a writable local folder. Keep its files and folders together.
3. Open `SL3_Compatibility_Setup.exe` and select **Check setup**.
4. Select **Install** when it becomes available and review the Windows administrator prompt. Keep the setup window open while it works.
5. When setup reports that installation is ready, open Serato from its regular shortcut.

Setup registers the rebuilt ASIO driver, stages a version-specific change to Serato's local device resource and adds a Windows sign-in watcher. To remove it, close Serato, open setup again and choose **Check setup → Restore original setup**. Keep the extracted folder until the original setup has been restored.

## What has been tested

- The 64-frame driver completed a two-minute loop in Serato with zero reported callback dropouts and verified USB release on exit. In this test Serato used a separate 128-frame application buffer. [Playback evidence](one-time-setup-window.md#serato-playback-comparison)
- An earlier installer-assisted run demonstrated two Phase Essential decks in REL with both remotes on one platter. [Demo](demo-20261105.md)
- The setup window has a PF icon, a Windows progress bar while an action is running, and links to the repository and Peter French's site. [Icon source](https://peterfrench.dev/)

The beta has a **10-minute audio-session limit**. We are working to lower latency as far as we can while keeping playback reliable. 32 frames is still experimental and is outside this release. Timecode vinyl, independent two-platter control and longer sessions need further testing.

If the Serato interface freezes before the SL3 connects, try **Setup → Library + Display → Show Streaming Services** off and restart Serato. On the test PC that stopped repeated post-startup stalls, although some control and waveform lag remained. [Serato setting](https://support.serato.com/hc/en-us/articles/223364427-Library-Display)

## Source and build inputs

The corresponding-source archive includes the project tree and the three ASIO SDK 2.3.4 interface headers used in this build under `artifacts/references/asio-sdk-2.3.4/ASIOSDK`, with Steinberg's license text. The project and these interface headers are distributed under GPLv3. The setup ZIP includes its third-party notices. [ASIO SDK license](https://github.com/audiosdk/asio/blob/main/LICENSE.txt)

The audio build used Visual Studio 2019 x64 with Windows SDK 10.0.19041.0 and `scripts/build-native.ps1 -Configuration Release -WithAsioComponent -WithUnmeasuredAsioDiagnostic`. The installer uses the application's 64-frame playback-keepalive profile. The source includes the [activation package preparation](../scripts/prepare-asio-activation-deployment.py), [native entry](../scripts/build-on-demand-entry.ps1), [setup window](../scripts/build-setup-window.ps1) and [portable ZIP verification](../scripts/package-setup-window.py). The [sign-in watcher source](../scripts/native/serato-notice-startup/notice-startup.cpp) builds as a Windows x64 DLL with the C++17 MSVC toolchain and User32. A locally rebuilt watcher DLL must be reviewed and pinned in the watcher script before preparing a new setup bundle. The [setup engineering notes](one-time-setup-window.md) document the package and its local prerequisites.
