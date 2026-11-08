import hashlib
import json
import runpy
import tempfile
import unittest
import wave
from pathlib import Path

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/export-output-capture.py"))


class OutputExportTest(unittest.TestCase):
    def prepare(self, root, **changes):
        capture = root / "capture"
        capture.mkdir()
        # Distinct channels and signed extrema; no float conversion allowed.
        frame = b"\x00\x00\x80\xff\xff\x7f\x01\x02\x03\x04\x05\x06\xfd\xfe\xff\x00\x00\x00"
        pcm = frame * 7
        (capture / "capture.pcm").write_bytes(pcm)
        metadata = {"schema": 1, "source": MODULE["SOURCE"], "complete": True,
                    "rateHz": 44100, "frames": 7, "firstFrame": 12345,
                    "pcmSha256": hashlib.sha256(pcm).hexdigest()}
        metadata.update(changes)
        (capture / "capture.json").write_text(json.dumps(metadata), encoding="utf-8")
        return capture, frame

    def test_stereo_pairs_preserve_signed_24bit_bytes_and_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capture, frame = self.prepare(root)
            destination = root / "wav"
            result = MODULE["export"](capture, destination)
            for index, item in enumerate(result["files"]):
                with wave.open(str(destination / item["file"]), "rb") as wav:
                    self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()), (2, 3, 44100, 7))
                    self.assertEqual(wav.readframes(8), frame[index * 6:index * 6 + 6] * 7)
                self.assertEqual(item["longestIdenticalStereoFrames"], 7)
                self.assertEqual(item["longestDigitalSilenceFrames"], 0)
            self.assertFalse(result["analogOutputVerified"])
            self.assertFalse(result["usbCompletionVerified"])
            self.assertTrue((destination / "export.json").is_file())
            with self.assertRaises(FileExistsError):
                MODULE["export"](capture, destination)

    def test_silence_and_held_samples_are_distinguished(self):
        silent = b"\0" * 6
        left_only = b"\x01" + b"\0" * 5
        right_only = b"\0" * 3 + b"\x01\0\0"
        stereo = bytearray(silent * 2 + left_only * 4 + right_only + silent * 3)
        self.assertEqual(MODULE["stereo_runs"](stereo), {
            "longestDigitalSilenceFrames": 3, "longestIdenticalStereoFrames": 4,
        })

    def test_unfinished_unbounded_wrong_rate_and_bad_hash_are_refused_before_writes(self):
        cases = ({"complete": False}, {"rateHz": 96000}, {"frames": 44100 * 5 + 1},
                 {"frames": True}, {"firstFrame": -1}, {"firstFrame": (1 << 64) - 1},
                 {"source": "analog-loopback"}, {"pcmSha256": "0" * 64}, {"frames": 8})
        for changes in cases:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                capture, _ = self.prepare(root, **changes)
                with self.assertRaises(ValueError):
                    MODULE["export"](capture, root / "wav")
                self.assertFalse((root / "wav").exists())


if __name__ == "__main__":
    unittest.main()
