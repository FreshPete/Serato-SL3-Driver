# Windows beta 2 setup

Use this build with Windows 11 x64 and Serato DJ Pro 5.0.0.1278 in its standard install folder. Install the signed UsbDk 1.0.22 x64 prerequisite separately. [UsbDk release](https://github.com/daynix/UsbDk/releases/tag/v1.00-22)

1. Close Serato. If beta 1 is installed, use its setup window to restore the original setup first.
2. Extract the entire beta 2 ZIP to a local folder. Open **SL3_Compatibility_Setup.exe**.
3. Choose **Check setup**, then **Install** and approve the Windows prompt.
4. Once setup reports it is installed, open Serato from your usual shortcut. Keep the extracted setup folder for recovery.

The watcher runs when you sign in to Windows. It registers the SL3 descriptor in memory for the supported Serato build. The installed Serato executable and resource archive stay intact. The driver uses the standard 64-frame setting and runs for the life of the Serato session.

To remove it or before updating Serato, close Serato, reopen the same setup window and choose **Check setup → Restore original setup**.

On the test PC, the watcher started after a fresh Windows sign-in. Two consecutive launches from the regular shortcut opened the SL3 and released it on exit. A two-minute playback check and a two-deck Phase REL check also passed. The Phase remotes shared one platter. The left-deck analogue-through test verified the physical route using an independent diagnostic. [Through test](physical-through-20261113.md)

[Download beta 2](https://github.com/FreshPete/Serato-SL3-Driver/releases/download/v0.1.0-beta.2/SL3-Compatibility-Setup-v0.1.0-beta.2-win-x64.zip) · [Report an issue](https://github.com/FreshPete/Serato-SL3-Driver/issues)
