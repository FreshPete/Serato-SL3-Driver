# Beta 2 build inputs

This release uses the r7 setup and sign-in watcher with the unchanged 64-frame audio bundle from beta 1. The audio sources are retained from beta 1. The corresponding-source archive includes the same ASIO SDK interface headers and licence text.

The watcher scripts in the source tree are the versions in the tested setup ZIP. The generated setup inputs in this directory bind the exact watcher payload and its startup plan. The CMake files for the setup entry and window use relative source paths so they can be configured from an extracted source archive. Build them with Visual Studio 2019 x64 and Windows SDK 10.0.19041.0. The native watcher DLL projects are under scripts/native/serato-descriptor-pair and scripts/native/serato-notice-startup. A locally rebuilt DLL has a new hash and may have different export offsets. Review those identities and regenerate the watcher plan and payload before preparing new setup binaries.

The setup ZIP bundles the CPython runtime and pefile with their licence notices. The official ASIO SDK binaries and the Serato and Rane installers are absent. The signed UsbDk filter is a separate prerequisite.
