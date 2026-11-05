"""Export a completed, bounded software-output capture; never opens hardware."""
import argparse
import hashlib
import json
import wave
from pathlib import Path

SOURCE = "worker-dequeued-output-pcm"
MAX_BYTES = 48000 * 5 * 18


def export(capture: Path, destination: Path) -> dict:
    metadata_path = capture / "capture.json"
    if metadata_path.stat().st_size > 4096:
        raise ValueError("Oversized capture metadata")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if (metadata.get("schema") != 1 or metadata.get("source") != SOURCE
            or metadata.get("complete") is not True):
        raise ValueError("A completed software-output capture is required")
    rate, frames, first = (metadata.get(key) for key in ("rateHz", "frames", "firstFrame"))
    if (type(rate) is not int or rate not in (44100, 48000)
            or type(frames) is not int or not 0 < frames <= rate * 5
            or type(first) is not int or not 0 <= first <= (1 << 64) - 1 - frames):
        raise ValueError("Invalid rate, length or stream position")
    pcm_path = capture / "capture.pcm"
    if pcm_path.stat().st_size != frames * 18:
        raise ValueError("PCM length does not match metadata")
    with pcm_path.open("rb") as handle:
        pcm = handle.read(MAX_BYTES + 1)
    if len(pcm) != frames * 18 or hashlib.sha256(pcm).hexdigest() != metadata.get("pcmSha256"):
        raise ValueError("PCM hash/length mismatch")
    # Validate all source data before creating anything. A fresh directory and
    # final completion manifest prevent overwriting prior captures or presenting
    # a partial export as finished.
    destination.mkdir(parents=False, exist_ok=False)
    files = []
    for label, pair in (("channels-1-2", 0), ("deck-1-channels-3-4", 2), ("deck-2-channels-5-6", 4)):
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
                      "sha256": hashlib.sha256((destination / name).read_bytes()).hexdigest()})
    result = {"schema": 1, "source": SOURCE, "complete": True, "rateHz": rate,
              "frames": frames, "firstFrame": first, "pcmSha256": metadata["pcmSha256"],
              "analogOutputVerified": False, "usbCompletionVerified": False,
              "routing": "historical SL3 descriptor; logical pairs, not physical socket verification",
              "files": files}
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
