# Serato 5.0.0 supported-device and ASIO contract

Current Serato retains a generic ASIO backend, but the SL3's discontinued stub lacks the descriptor/connection setup needed to reach a working audio path. A support-value edit alone is insufficient. New evidence also separates **driver-installation status** from the audio stream and from Windows driver admission. No application, account state, license check or registration was changed.

Target is installed Windows x64 5.0.0.1278, SHA256 `66e7af01ddfd151814f51bf44bd8472e5c94f54b3ce12119ef70b7cbab433265`. Addresses are preferred image VAs. Everything below is static evidence or an explicitly labeled prediction; no debugger call trace or supported-SL3 runtime experiment is claimed. [Discontinued route](serato-discontinued-path.md), [new bounded evidence](evidence/serato500-supported-contract.json).

## Descriptor and connection requirements

The aggregation worker `0x1421DB390` enters its connection loop for support value 1. It queries the descriptor interface at complete-object +0x10, using slots +0x10 (MIDI direction), +0x18 (has HID) and +0x28 (requires USB). Their nonzero results contribute component expectations. The following defaults come from the zeroed allocation, constructor, identity-only SL3 helper and getter implementations:

| Field | SL3 stub value | Implication for a support-1 counterfactual |
| --- | --- | --- |
| `supported_apps` | 2 for DJ/Lite | Currently selects discontinued handling |
| `midi_direction` | Empty string | Getter `0x1405C6EF0` returns **3**, not 0; contributes one expected MIDI component |
| `has_hid` | False | No HID component requested by this flag |
| `requires_usb` | False | No raw USB component requested by this flag |
| `use_legacy_portaudio` | **True** at complete +0x35C | Cannot assume this stub selects the newer generic JUCE path |
| `win_audio_api` | Empty at complete +0x360 | No concrete Windows audio API selected here |
| `win_audio_device_name` | Empty at complete +0x3A0 | No rebuilt ASIO device name selected here |

Getter direction values are `in` → 1, `out` → 2, `none` → 0, other/empty → 3. These are implementation enum values, not channel counts. The predicted MIDI expectation is one aggregation component; it does not mean one audio channel. Our rebuilt USB transport exposes no MIDI component to satisfy it. How current Serato routes a deliberately audio-only descriptor must be established rather than spoofing another controller.

Constructor `0x1405BEAD0` explicitly writes the legacy-audio flag to 1 after allocation helper `0x1405CE730` zeroes the 0x740-byte object. The helper allocates 0x750 bytes including a 0x10-byte shared-control prefix; these are different offsets from the descriptor's own +0x10 interface. Do not conflate them.

Parser references recover the field names and offsets. Its comparison near `0x1405C907F` uses literal **WDMKS**, not ASIO. That comparison alone is not an ASIO selection rule. Subsequent analysis recovers the [four-string audio gate and downstream legacy/newer backend choice](serato-audio-routing.md): empty audio fields enter the default OS branch, while explicit fields permit name or VID/PID selection with the legacy flag. No user-editable external descriptor override has been established.

## A separate DriverAPI factory

Readiness helper `0x1421DAD00` calls `0x140BFA030` and then virtual slots +0x50/+0x48/+0x58/+0x90 on its returned object. This object is **not the ControllerDescriptor**. Validated RTTI identifies the generic fallback as `serato::device::driver::DriverAPI`, vtable `0x142E86360`. Treating these four slots as descriptor audio/control capabilities would mislabel the path.

In this factory, VID 1CC5 has explicit product branches for **18, 1B, 20, 21, 22, 25 and 26** (hex). PID 0001 has no special match and reaches a generic DriverAPI constructor `0x140BFF9D0`, using the descriptor's driver-detection string. This is a conclusion about **this factory**, not proof that every SL3-specific operation has been removed from the whole application.

Generic DriverAPI +0x50 copies its registry-key string at +0x60 and calls `0x140BFFFD0`. Machine code establishes:

- An **empty key returns true** (`AL=1`).
- A nonempty key is opened under HKLM with `KEY_READ`; success determines the Boolean result.
- Slots +0x48 and +0x58 delegate to +0x50. Slot +0x90 returns false.

The SL3 identity-only stub leaves its driver-detection map empty. Its predicted generic readiness result is therefore true for those first three queries and false for +0x90, selecting deferred action 6 in the recovered branch. Action meanings beyond their concrete callback offsets are not guessed here.

The [subsequent notification trace](serato-driver-notification.md) now binds action 6 to DeviceManager observer slot +0x38, UserIO message 0x52 and keyed state/object handling in its receiver. This identifies the local notification route without assigning the unresolved virtual operation a name. It is not an ASIO open, a new proven driver gate, or an observed support-1 SL3 session.

Ghidra infers `void` returns for the registry checker/wrapper and drops the relevant Boolean in its pseudocode. The exported machine-code excerpts preserve `mov al,1` and the nonempty-key `sete`/return. That is why a plausible decompilation alone is insufficient.

An empty-key success or existing registry entry says nothing about code 39, an admitted kernel image, an open stream or functioning DVS. It is not an identified licensing/authentication operation. No registry entry was fabricated to satisfy it.

## Generic ASIO is present

Validated RTTI locates `juce::ASIOAudioIODeviceType`, vtable `0x1431DD8D0`, and `juce::ASIOAudioIODevice`. Recovered functions establish:

| Operation | Function and observed behaviour |
| --- | --- |
| Scan | `0x142212470`: reads HKLM `software\asio`, enumerates keys and applies driver-name filtering |
| Driver information | `0x142209DD0`: reads `clsid`, checks COM `CLSID` / `InprocServer32` registration, then reads `description` with a name fallback |
| Device creation | `0x14220D200`: resolves the chosen device name in the scanned list and constructs the ASIO device using its associated CLSID |
| Construction | `0x142208150`: initializes COM and calls setup helper `0x142210950` |
| Initial setup | `0x142210950`: queries channels/buffers/rate/latencies, prepares dummy buffers, invokes ASIO start, delays, then invokes stop |

The type's destructor occupies the final slot here; assuming the first slot is always a destructor would miss the registry scanner. [Validated audio RTTI](evidence/serato500-audio-rtti.json).

These behaviours correspond to the published JUCE ASIO implementation, which helps interpret the recovered names and setup pattern. The installed fork/version has not been identified as identical to current upstream. [JUCE's own ASIO source](https://github.com/juce-framework/JUCE/blob/master/modules/juce_audio_devices/native/juce_ASIO_windows.cpp), [JUCE device-type interface](https://docs.juce.com/master/classjuce_1_1AudioIODeviceType.html).

This gives the rebuilt ASIO adapter a concrete future host contract: consistent x64 COM/ASIO registration and display naming, real six-channel/sample-format reporting, finite init/create/start/stop/dispose behaviour, and correct handling of the host's initial start/stop probe. Device construction can already exercise driver operations; application enumeration must not be assumed physically passive.

Presence of this backend does **not** prove that the SL3 descriptor reaches it, that a new DLL will initialize, or that DVS channel/deck mapping is available. The original vendor ASIO registration also remains independent of its blocked kernel driver.

## Implementation consequences and remaining work

Continue transport validation independently, then expose verified audio through an original ASIO adapter and test it with a controlled host. Preserve the original Rane registration and use a distinct rebuilt identity. Do not register a placeholder that claims to stream while its transport is missing.

For current Serato, trace the descriptor's legacy/backend choice and channel/deck/control consumer before implementing a local integration. Recover the actual audio-only connection requirements and DVS input/output mapping. Keep original SL3 identity and legitimate product/account checks; impersonating a supported controller or suppressing the discontinued dialog does not meet this goal.

Evidence can be reproduced with `.venv/Scripts/python.exe scripts/export-serato-supported-evidence.py`, using retained focused reports and the exact original PE. The exporter checks its hash, validates RTTI locators, verifies the seven Rane factory branches against disassembly and emits bounded excerpts. No broad application patch or live driver call is involved.

Further investigation now recovers [DVS capability, decoder calibration and endpoint containers](serato-dvs-contract.md). It adds independent application requirements without changing the original executable or legitimate product/account checks.

The subsequent [component-profile comparison](serato-component-profiles.md) verifies the exact MIDI getter and its nonzero contribution in the descriptor-count branch. Across 197 current descriptors, fifteen explicitly declare `none`; fourteen of those declare HID, and the remaining native Pro virtual-audio profile declares no DVS capability. DS1/Flux resource omissions still project to the getter's nonzero fallback, not to no MIDI. None is an established template for a USB-only current SL3/DVS integration.
