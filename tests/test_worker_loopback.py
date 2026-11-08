import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

import numpy as np


ANALYSE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/analyse-worker-loopback.py"))["analyse"]


def packed_pair(samples, start_channel):
    packed = np.zeros((len(samples), 6, 3), dtype=np.uint8)
    for byte in range(3):
        packed[:, start_channel:start_channel + 2, byte] = (samples >> (8 * byte)) & 0xff
    return packed.tobytes()


class WorkerLoopbackTest(unittest.TestCase):
    def test_offsets_use_stream_positions_and_late_gap_remains_visible(self):
        rate, frames = 44100, 44100 * 5
        output_first, input_first = 1000, 1064
        source = np.random.default_rng(21).integers(-100000, 100000, size=(frames, 2), dtype=np.int32)
        returned = np.zeros_like(source)
        for channel, offset, sign in ((0, 199, 1), (1, 201, -1)):
            shift = offset - (input_first - output_first)
            returned[shift:, channel] = source[:-shift, channel] * sign
        returned[rate * 2:rate * 2 + rate // 10, 1] = 0

        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory)
            pcm = packed_pair(source, 2)
            incoming = packed_pair(returned, 0)
            (capture / "capture.pcm").write_bytes(pcm)
            (capture / "input.pcm").write_bytes(incoming)
            (capture / "capture.json").write_text(json.dumps({
                "schema": 1, "source": "worker-dequeued-output-pcm", "complete": True,
                "rateHz": rate, "frames": frames, "firstFrame": output_first,
                "pcmSha256": hashlib.sha256(pcm).hexdigest(),
                "input": {"source": "worker-published-input-pcm", "frames": frames,
                          "firstFrame": input_first, "pcmSha256": hashlib.sha256(incoming).hexdigest()},
            }), encoding="utf-8")
            result = ANALYSE(capture, 3, 1)
            self.assertTrue(result["consistentStereoMatch"])
            left, right = result["channels"]
            self.assertEqual((left["offsetFrames"], right["offsetFrames"]), (199, 201))
            self.assertEqual(left["lowAgreementWindowFirstFrames"], [])
            self.assertGreaterEqual(len(right["lowAgreementWindowFirstFrames"]), 4)
            self.assertLess(right["peakCorrelation"], -0.99)
            self.assertFalse(ANALYSE(capture, 3, 5)["consistentStereoMatch"])


if __name__ == "__main__":
    unittest.main()
