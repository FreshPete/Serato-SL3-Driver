"""Synthetic worker-queue recording lifecycle, with no USB device acquisition."""
import runpy
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

export = runpy.run_path(str(Path(__file__).with_name("export-output-capture.py")))["export"]


def main():
    executable = sys.argv[1]
    with tempfile.TemporaryDirectory(prefix="sl3-output-capture-") as temporary:
        root = Path(temporary)
        for mode in ("success", "rate-44100", "loopback", "loopback-missing-input", "partial", "invalid-arm", "write-failure"):
            directory = root / mode
            subprocess.run([executable, str(directory), mode], check=True, timeout=10)
            if mode not in ("success", "rate-44100", "loopback"):
                assert not (directory / "capture.json").exists()
                assert not (directory / "input.pcm").exists()
                if mode == "write-failure":
                    assert (directory / "capture.pcm").read_bytes() == b"preserve"
                else:
                    assert not (directory / "capture.pcm").exists()
                continue
            destination = root / ("wav-" + mode)
            result = export(directory, destination)
            rate = 44100 if mode in ("rate-44100", "loopback") else 48000
            assert result["rateHz"] == rate and result["frames"] == rate * 5
            assert result["firstFrame"] == 0
            for index, item in enumerate(result["files"]):
                with wave.open(str(destination / item["file"]), "rb") as wav:
                    frame = bytes((index * 2 + 1, 0x80, 0xff, index * 2 + 2, 0x80, 0xff))
                    assert wav.readframes(rate * 5) == frame * (rate * 5)
            if mode == "loopback":
                returned = result["input"]
                assert returned["source"] == "worker-published-input-pcm"
                assert returned["firstFrame"] == 0 and returned["frames"] == rate * 5
                with wave.open(str(destination / returned["files"][0]["file"]), "rb") as wav:
                    assert wav.readframes(rate * 5) == b"\x41\x80\xff\x02\x80\xff" * (rate * 5)
                input_path = directory / "input.pcm"
                with input_path.open("r+b") as tamper:
                    tamper.write(b"\0")
                refused = root / "tampered-input-export"
                try:
                    export(directory, refused)
                except ValueError:
                    assert not refused.exists()
                else:
                    raise AssertionError("A mismatched input hash was accepted")
            else:
                assert "input" not in result and not (directory / "input.pcm").exists()
            before = (directory / "capture.json").read_bytes()
            subprocess.run([executable, str(directory), "existing"], check=True, timeout=10)
            assert (directory / "capture.json").read_bytes() == before
    print("Synthetic six-channel queue capture/export and failure retirement passed; no hardware opened")


if __name__ == "__main__":
    main()
