"""Export a completed, bounded worker audio capture; never opens hardware."""
import argparse
import hashlib
import json
import struct
import wave
from itertools import groupby
from pathlib import Path

SOURCE = "worker-dequeued-output-pcm"
INPUT_SOURCE = "worker-published-input-pcm"
MAX_BYTES = 48000 * 5 * 18
SILENT_STEREO_FRAME = (b"\0" * 3, b"\0" * 3)


def stereo_runs(stereo: bytearray) -> dict:
    longest_silent = longest_constant = 0
    for frame, copies in groupby(struct.iter_unpack("3s3s", stereo)):
        length = sum(1 for _ in copies)
        longest_constant = max(longest_constant, length)
        if frame == SILENT_STEREO_FRAME:
            longest_silent = max(longest_silent, length)
    return {"longestDigitalSilenceFrames": longest_silent,
            "longestIdenticalStereoFrames": longest_constant}


def read_pcm(path, metadata, rate):
    frames, first = (metadata.get(key) for key in ("frames", "firstFrame"))
    if (type(frames) is not int or not 0 < frames <= rate * 5
            or type(first) is not int or not 0 <= first <= (1 << 64) - 1 - frames):
        raise ValueError("Invalid length or stream position")
    if path.stat().st_size != frames * 18:
        raise ValueError("PCM length does not match metadata")
    with path.open("rb") as handle:
        pcm = handle.read(MAX_BYTES + 1)
    if len(pcm) != frames * 18 or hashlib.sha256(pcm).hexdigest() != metadata.get("pcmSha256"):
        raise ValueError("PCM hash/length mismatch")
    return pcm


def write_pairs(pcm, destination, rate, labels):
    frames = len(pcm) // 18
    files = []
    for index, label in enumerate(labels):
        pair = index * 2
        stereo = bytearray(frames * 6)
        for frame in range(frames):
            start = frame * 18 + pair * 3
            stereo[frame * 6:frame * 6 + 6] = pcm[start:start + 6]
        name = label + ".wav"
        with (destination / name).open("xb") as output:
            with wave.open(output, "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(3)
                wav.setframerate(rate)
                wav.writeframes(stereo)
        files.append({"file": name, "logicalChannels": [pair + 1, pair + 2],
                      "sha256": hashlib.sha256((destination / name).read_bytes()).hexdigest(),
                      **stereo_runs(stereo)})
    return files


def read_capture(capture: Path):
    metadata_path = capture / "capture.json"
    if metadata_path.stat().st_size > 4096:
        raise ValueError("Oversized capture metadata")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if (metadata.get("schema") != 1 or metadata.get("source") != SOURCE
            or metadata.get("complete") is not True):
        raise ValueError("A completed software-output capture is required")
    rate = metadata.get("rateHz")
    if type(rate) is not int or rate not in (44100, 48000):
        raise ValueError("Invalid capture sample rate")
    pcm = read_pcm(capture / "capture.pcm", metadata, rate)
    frames = metadata["frames"]
    input_pcm = None
    if "input" in metadata:
        input_record = metadata["input"]
        if (not isinstance(input_record, dict) or input_record.get("source") != INPUT_SOURCE
                or input_record.get("frames") != frames or frames != rate * 5):
            raise ValueError("Expected a complete paired input capture")
        input_pcm = read_pcm(capture / "input.pcm", input_record, rate)
    return metadata, pcm, input_pcm


def export(capture: Path, destination: Path) -> dict:
    metadata, pcm, input_pcm = read_capture(capture)
    rate, frames, first = (metadata[key] for key in ("rateHz", "frames", "firstFrame"))
    # Validate both streams before publishing any files.
    destination.mkdir(parents=False, exist_ok=False)
    files = write_pairs(pcm, destination, rate, ("channels-1-2", "deck-1-channels-3-4", "deck-2-channels-5-6"))
    result = {"schema": 1, "source": SOURCE, "complete": True, "rateHz": rate,
              "frames": frames, "firstFrame": first, "pcmSha256": metadata["pcmSha256"],
              "analogOutputVerified": False, "usbCompletionVerified": False,
              "routing": "historical SL3 descriptor; logical pairs, not physical socket verification",
              "files": files}
    if input_pcm is not None:
        result["input"] = {**metadata["input"], "files": write_pairs(input_pcm, destination, rate,
            ("input-channels-1-2", "input-channels-3-4", "input-channels-5-6"))}
    with (destination / "export.json").open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.capture, args.destination), indent=2))
