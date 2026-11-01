# SL3 clock, control and sample contract

Updated 26 October 2026. Static analysis used the original x64 kernel and ASIO DLL; a bounded physical rate-getter test independently reported **44,100 Hz**. No rate setter, route change, status-enable, firmware request or audio transfer was executed.

Later checkpoints verify real capture/silent playback, both rates and the retained two-stream path; see [current status](../STATUS.md). Original control-table consumers now establish partial field meanings, the mV sensitivity scale and phono/through notification identities. A tested read-only C++ view is available; physical control/routing validation remains pending. [Recovered control contract](audio-controls-contract.md).

## Evidence and source identities

- Original kernel SHA-256 `e8e992a8ece1a57eab337d815a406b9f815954176c03db545fcf6d951ec615f5`, image base 0x10000.
- Original ASIO DLL SHA-256 `e3d88039547b70915b1a9bc9e3e3f7dba32aaa9bc3ce8fd51616565ea1734141`, image base 0x180000000.
- [Selected original decompilations and constants](evidence/rane-clock-audio-contract.json). New Ghidra leaf recovery: 0x115C0–0x11698 and 0x12480–0x1265B. Full local projects/output remain under ignored `analysis/`.
- [Physical rate query and final state](evidence/winusb-clock-query.json). Raw recording/transcripts remain under ignored `tests/results/local/winusb-clock-query-01`.

Decompilation is not vendor source or a runtime trace. The arithmetic and virtual-method assignments below were checked against PE instructions, pointer tables and constants. Hardware observations are identified separately.

## Clock and rate control

The ASIO method table at 0x1801B8CE8 agrees with the IASIO method sequence. `getChannels` (0x18000FEC0) returns six inputs/six outputs for an open device. `getClockSources` (0x180010C10) declares one source, reference 0, named **Internal**; `setClockSource` (0x180010C80) rejects other references. This declares the API clock model, not measured oscillator lock or drift. “Master” in the sample-rate setter's logs concerns client ownership of the shared driver, not proof of an external USB clock mode.

`canSampleRate`/`setSampleRate` compare against binary double constants **44100.0** and **48000.0** at 0x1801B93A8/B0. Kernel setter field 2 likewise accepts only 0xAC44/0xBB80 and updates the requested-rate field. A work item changes active buffering and invokes 0x11A90.

`0x11A90` sends command **0x31** with two big-endian rate bytes, waits for a two-byte reply, sends **0x30** with a zero payload, then verifies that its two-byte rate readback matches. Thus 0x30 is a distinct getter and 0x31 changes the rate. Accepted values do not establish the success or transient behaviour of an untested rate change.

### Physical getter test

One traced WinUSB binding at 23:12 UTC was followed by exactly one 64-byte interrupt OUT frame: `30 1C C5 00 01` followed by 59 zeros. Audio alternates remained zero. A synchronous 64-byte interrupt IN read returned prefix **`30 1C C5 00 01 AC 44`** at 23:13:04.916 UTC, establishing rate readback **44100**. No 0x31, 0x36, route or firmware command was sent. Transfer timeouts were 100 ms OUT / 300 ms IN, restored afterward; the process had a 20-second parent deadline and allowed at most four received frames, with no query retry.

Only the first two payload bytes of this reply are defined by the original driver's consumer. The remaining **57 bytes are uninterpreted**, not extra status or audio. The public evidence includes the defined prefix and a hash of the raw reply; its unused tail stays local. The codec now enforces that distinction.

The 60-second trace recorded **21,382 events, zero events/buffers lost**, 220 correlated SL3 events and two correlated bulk/interrupt dispatches. No correlated isochronous dispatch occurred. Cleanup restored original Rane/code 39, removed the development package/GUID/trust, and confirmed Secure Boot true. The temporary signing identity remains absent. This is a device-reported rate observation, not a sample-clock frequency measurement.

## Control and notification framing

Normal command frames contain command byte, literal tag **`1C C5 00 01`**, and 59 payload bytes. The original generic reply matcher checks the same command/tag and extracts only the requested reply length.

The newly recovered interrupt parser at **0x115C0** handles asynchronous frames with **different tags**:

| Command | Bytes 1–4 | Bytes consumed from payload | Original effect |
| --- | --- | --- | --- |
| 0x34 | `00 00 00 01` | 6 | Copy to shared block +0x398; increment +0x39E |
| 0x38 | `00 00 00 02` | 3 | Copy to +0x389; increment +0x38C |
| 0x39 | `00 00 00 03` | 4 | Copy to +0x390; increment +0x394 |

A decoder that demands the VID/PID reply tag for every frame will reject these original-driver notifications. Payload values and physical switch labels have not been observed on this unit; the Linux driver's names remain supporting hypotheses where a vendor-consumer link has not been traced.

The original API exports also clarify the control table:

- `sl3_get_audio_controls` (0x1800074F0) invokes control field 3/get. Kernel dispatcher 0x11E80 maps it to **0x32**, consuming **22 bytes**. It is not established as merely a three-byte phono-state query.
- `sl3_set_audio_controls` (0x1800075F0) constructs **index, count, value bytes** and invokes field 3/set. The kernel sends **0x33** and waits for two reply bytes. The meaning/allowed values of each table index must be verified before enabling writes. The Linux pair IDs may be offsets into this table; they are not yet a verified standalone routing ABI.
- Exported `sl3_get_overload_status` invokes field 4/get, which sends **0x35** and receives six bytes. The normal notification parser's corresponding six-byte consumer is recovered, but physical overload behaviour has not been exercised.
- **0x36** is sent with payload byte 1 during original D0 entry and with 0 from a separate mode-changing path. Its exact effect is still unknown. Do not call it “audio enable” or replay it just to obtain data.

Firmware-related branches and EP0 request helper 0x11B80 remain excluded. The Linux implementation was reviewed as a comparison, not used as proof of command effects or copied into the prototype. [Comparison repository](https://github.com/nvgeele/snd-rane-sl3).

Further original analysis now maps `sl3_driver_timer` through IOCTL 0x220010/get selector 0x44 to interrupt command 0x37 with eight challenge/reply bytes and a real response comparison in historical Serato. A [bounded native control codec](native-control-frames.md) implements the known frame/reply widths and notification budget. Only its existing rate getter is connected at runtime; no new query, setter, response emulation or hardware operation has run.

## Sample container and layout

The original ASIO `getChannelInfo` method at **0x180010D90** writes sample type **17** at instruction **0x180010DDC**, for channel indexes 0–5. That is the SDK's packed **ASIOSTInt24LSB** representation. Kernel conversion at 0x1301C independently walks six values per frame, advances three bytes per value, preserves the low 24 bits and deinterleaves input into per-channel buffers. These observations support **six interleaved little-endian 3-byte signed PCM containers**, or **18 bytes per complete channel frame**, on USB input. This is consistent with the [Steinberg-authored SDK sample-type declarations](https://github.com/kxproject/kx-audio-driver/blob/master/asio_sdk/asio.h).

Channel indexes are logical 0–5. Jack/deck order, effective converter bits and analogue scaling still require an audio fixture; a 24-bit container is not proof of 24 meaningful converter bits. `sl3_protocol.py` decodes whole packets only, using signed 24-bit boundaries and rejecting partial 18-byte frames or packets over 126 bytes. It does not flatten a registered USB buffer across unused packet padding.

## USB timing and output coupling

The original request builder 0x12B74 submits isochronous URBs with **8 × millisecond-count packets**. Each IN packet reserves **126 bytes**; offsets increase by 126, independent of the actual returned lengths. The descriptor's high-speed interval 1 corresponds to 125 µs; eight intervals form 1 ms. [Microsoft USB timing and URB semantics](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/transfer-data-to-isochronous-endpoints).

Completion path **0x13968 → 0x1301C** uses each returned IN packet's actual length, rounds it to whole 18-byte frames, and builds the corresponding OUT packet offset/size and total OUT length from that sequence. It schedules the output relative to the input frame plus a delay. This establishes input-length-driven output pacing in the original implementation; it is substantially stronger evidence than a claim of implicit feedback based only on descriptors. The original fallback for zero/oversize packets substitutes 108 bytes and sets diagnostic bits. A first diagnostic capture should report such failures, not silently copy that recovery.

The endpoint maximum accommodates seven channel frames (126 bytes). Arithmetic expectations are averages, not measured packet patterns: 44.1 kHz corresponds to 5.5125 channel frames per 125 µs interval; 48 kHz corresponds to 6. Actual packet lengths/status and timing must be recorded.

### Playback constraint to resolve

Microsoft's documented [`WinUsb_WriteIsochPipe`](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_writeisochpipe) and [`Asap` variant](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_writeisochpipeasap) accept a buffer offset/total length, without a caller-supplied per-packet descriptor array, and document packetization using maximum bytes per interval. The original driver's variable packet-offset sequence is therefore **not yet shown to be representable** by these APIs. Full 126-byte packets in every interval would correspond to 56,000 six-channel frames/s, not either supported rate.

This is an identified API/contract gap, not a demonstrated WinUSB hardware write failure: no isochronous OUT write has been attempted. Do not pad playback to the endpoint maximum or promise a full-duplex WinUSB ASIO implementation until the gap is resolved. A suitable signed transport exposing per-packet scheduling may be needed; a new kernel binary still has the separate signing constraint.

## Bounded capture-first test specification

The next data experiment should be **IN-only**, with no rate/route/status-enable setter and no audio OUT submission:

1. Bind under tracing, read the current rate once, and verify the exact device/pipe fixture.
2. Select the already-verified audio alternates; register small IN buffers for 0x82. Use maximum-packet stride 126 and groups of eight intervals, with total scheduled capture bounded to tens of milliseconds and a hard wall-clock deadline.
3. Keep all buffers/OVERLAPPED objects alive through completion or cancellation. On the first error, cancel outstanding operations and drain completions before unregistering/freeing memory. Record every packet's status, offset and actual length.
4. Decode only successful packet slices `[Offset:Offset+Length]`; record zero lengths, reject lengths over 126 or nonmultiples of 18, and preserve raw evidence locally. Do not interpret unused 126-byte slot padding as samples.
5. Restore alternate settings, close handles, clean up binding/trust, and compare descriptors and security state. A successful capture proves only data arrival and container/timing observations. Physical channel mapping and sample-clock measurement require controlled analogue input later.

[`WinUsb_ReadIsochPipeAsap`](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_readisochpipeasap) supplies per-packet result descriptors and supports this capture-first investigation. No such audio read has been run yet. A missing/invalid stream should stop the experiment, not trigger guessed command replay.
