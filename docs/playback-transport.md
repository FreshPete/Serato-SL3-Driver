# Playback layout and Windows transport selection

The new native playback layout core builds and passes offline tests. It preserves observed packet boundaries and packs six signed 24-bit channels without padding. **No audio OUT transfer has been submitted.** A promising separate transport is the Microsoft-signed Windows 10 binary in UsbDk 1.0.22; its signature has been checked, but neither installation nor an SL3 test has occurred.

## Why a WinUSB wrapper is insufficient

The original SL3 driver derives output packet lengths from input completions. The public WinUSB write API accepts no packet-size array. A pinned review of libusb commit `6a1aff0b39c724657fd92b2d2bf82eb532344570` confirms that its WinUSB backend rejects a short nonfinal OUT packet followed by more data. Its libusbK branch instead supplies cumulative caller-defined packet offsets. Thus changing the user-mode wrapper to libusb does not remove the WinUSB backend constraint. [Reviewed source, lines 4000–4130](https://github.com/libusb/libusb/blob/6a1aff0b39c724657fd92b2d2bf82eb532344570/libusb/os/windows_winusb.c#L4000).

At six channels × three bytes, nominal arithmetic gives 90/108-byte packets for a simple 44.1 kHz schedule and 108-byte packets for 48 kHz. These are **synthetic examples**, not measured packet patterns on this device. Filling every interval with 126 bytes would change the rate to 56,000 channel frames/s. Splitting a millisecond into independently queued short WinUSB writes has not been shown to preserve the required interval schedule and is not implemented as a workaround.

## Candidate binaries inspected without installation

| Candidate | Exact binary inspected | Signature observation | Consequence |
| --- | --- | --- | --- |
| libusbK release 3.1.0.0 | Bundled amd64 `libusbK.sys`, file version **3.0.7.0**, timestamped 27 April 2014 | Authenticode valid; SignTool `/all /kp` passes one legacy cross-signature | Supports caller packet offsets, but this result does not establish acceptance by this host's enforced 2026 CI policy |
| UsbDk release 1.0.22 | MSI stream `UsbDk.sys10`, file version **1.0.22.0** | Primary Red Hat signature is not kernel-usage-valid; nested **signature index 1** chains to Microsoft Windows Hardware Compatibility Publisher and passes `/ds 1 /kp` | Stronger candidate for normal-security testing; no load, SL3 redirection or audio result yet |

Both sources were downloaded from their maintainers' releases and extracted as archives. The UsbDk MSI, helper DLL, controller and Zadig were **not executed**. Zadig 2.9 was acquired during investigation but does not establish the signature of a transport we have tested. The libusbK binary and source archives were inspected separately; their release version must not be substituted for the older SYS version. [libusbK release](https://github.com/mcuee/libusbk/releases/tag/V3.1.0.0), [UsbDk release](https://github.com/daynix/UsbDk/releases/tag/v1.00-22), [signature evidence](evidence/playback-transport.json), [download provenance](evidence/downloads.jsonl).

UsbDk's first-signature-only check initially reported a failure. Enumerating **all signatures**, then explicitly selecting index 1, resolves that ambiguity. The all-signatures invocation still exits 1 because its primary signature fails, although one signature verifies. Do not describe this binary as unsigned or infer that the single aggregate exit code invalidates its Microsoft signature. Conversely, successful offline verification does not prove a successful enforced-policy load. The original Rane driver already demonstrated that distinction. [Microsoft's current driver trust policy](https://support.microsoft.com/en-us/windows/hardware/drivers/the-windows-driver-policy).

## UsbDk packet contract and remaining gap

Pinned release source commit `84752c30037956149d53b498005b5368616f9257` declares a packet-size array in each transfer request. `CIsochronousUrb::FillOffsetsArray` accumulates those sizes into URB offsets and total transfer length. `Create` uses ASAP scheduling. This can express the SL3's variable packet lengths, but the public request does not expose the original driver's explicit input-frame-plus-delay start frame. Full-duplex alignment, latency, underrun behaviour and device acceptance therefore remain test questions. [Request ABI](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDk/UsbDkData.h), [URB construction](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDk/Urb.cpp).

UsbDk is a system USB filter, rather than a replacement INF restricted to the SL3. Its helper supports exclusive redirection of a selected device and returning it on close. An installation test must account for this larger scope, trace startup, restrict redirection to the exact SL3 and preserve a clear uninstall path. No installer or elevation prompt was started while the owner is away. [Helper contract](https://github.com/daynix/UsbDk/blob/84752c30037956149d53b498005b5368616f9257/UsbDkHelper/UsbDkHelper.h).

## Original implementation added

`src/core/playback.cpp` accepts 8–1024 successful, nonempty interval lengths in groups of eight and an exact matching number of six-channel frames. It rejects malformed lengths, under/oversupply and out-of-range samples. It emits cumulative offsets, unchanged lengths and tightly packed PCM. It performs no USB calls, clocks, resampling, rate changes or guessed error substitution.

The `winusb_maximum_packet_shape` field is a **necessary shape check only**. False rules out the reviewed contiguous maximum-packet layout; true does not prove all WinUSB API requirements or hardware behaviour. No backend is selected by this boolean.

After a future successful capture, the capture diagnostic also repacks its decoded frames offline against the observed length sequence and reports whether the layout validates. It still records `audio_output_submissions: 0`. This supplies an immediately reviewable packet contract without sending the captured signal back to the device.

Both Release and Debug pass four CTest entries. Playback tests cover synthetic 44.1/48 kHz arithmetic fixtures, varied packet boundaries, exact PCM/channel/frame round trips including signed extrema, maximum-packet shape classification, malformed intervals, under/oversupply and invalid samples. They do not prove physical playback.

## Next steps

1. Finish a bounded UsbDk adapter and plan-only/install preflight tooling offline, with fixed dependency hashes and explicit completion ownership.
2. On the owner's return, run the already-prepared WinUSB IN-only capture first. Actual packet lengths and statuses will replace arithmetic assumptions.
3. Separately test the unchanged Microsoft-signed UsbDk package loading under normal policy, with tracing and targeted recovery; verify that it can enumerate and temporarily redirect this exact SL3 before streaming.
4. Establish a capture/clock baseline through that backend, then bounded silent output preserving actual lengths. Audible output and analogue channel mapping require a controlled physical setup. Do not advance directly to ASIO/DVS success claims.
