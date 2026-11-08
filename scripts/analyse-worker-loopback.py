"""Compare a completed worker output capture to its paired physical return candidate."""
import argparse
import json
from pathlib import Path
import runpy

import numpy as np


read_capture = runpy.run_path(str(Path(__file__).with_name("export-output-capture.py")))["read_capture"]


def stereo(pcm, pair):
    samples = np.frombuffer(pcm, dtype=np.uint8).reshape(-1, 6, 3)[:, pair - 1:pair + 1].astype(np.int32)
    codes = samples[..., 0] | samples[..., 1] << 8 | samples[..., 2] << 16
    return ((codes ^ 0x800000) - 0x800000) / float(1 << 23)


def match_channel(sent, returned, output_first, input_first, rate):
    first = max(output_first, input_first)
    output_start, input_start = first - output_first, first - input_first
    search = rate // 10
    length = rate // 2
    template = sent[output_start:output_start + length]
    observation = returned[input_start:input_start + length + search]
    if len(template) != length or len(observation) != length + search:
        raise ValueError("Insufficient shared frame range for loopback search")
    template = template - template.mean()
    template_energy = np.dot(template, template)
    if template_energy <= 1e-12:
        return {"offsetFrames": None, "reason": "no-output-reference"}

    # Normalized correlation at each candidate shift, with DC removed from
    # each return window. Zero pad so the FFT performs linear convolution.
    size = 1 << (length + len(observation) - 2).bit_length()
    product = np.fft.rfft(observation, size) * np.fft.rfft(template[::-1], size)
    numerator = np.fft.irfft(product, size)[length - 1:length + search]
    sums = np.concatenate(([0.0], np.cumsum(observation)))
    squares = np.concatenate(([0.0], np.cumsum(observation * observation)))
    energy = squares[length:] - squares[:-length] - (sums[length:] - sums[:-length]) ** 2 / length
    denom = np.sqrt(template_energy * np.maximum(energy, 0))
    scores = np.divide(numerator, denom, out=np.zeros_like(numerator), where=denom > 1e-12)
    magnitude = np.abs(scores)
    peak = int(np.argmax(magnitude))
    runner_up = max(np.max(magnitude[:max(peak - 4, 0)], initial=0),
                    np.max(magnitude[peak + 5:], initial=0))
    result = {"offsetFrames": None, "peakCorrelation": float(scores[peak]),
              "peakMargin": float(magnitude[peak] - runner_up)}
    if magnitude[peak] < 0.8 or result["peakMargin"] < 0.02:
        return {**result, "reason": "weak-or-ambiguous-match"}

    # The found offset maps output frame n to input frame n + offset. Check
    # the rest of the common range without searching away short mismatches.
    input_start += peak
    width = rate // 50
    windows = min(len(sent) - output_start, len(returned) - input_start) // width
    x = sent[output_start:output_start + windows * width].reshape(-1, width)
    y = returned[input_start:input_start + windows * width].reshape(-1, width)
    x, y = x - x.mean(axis=1, keepdims=True), y - y.mean(axis=1, keepdims=True)
    norm = np.linalg.norm(x, axis=1) * np.linalg.norm(y, axis=1)
    agreement = np.divide((x * y).sum(axis=1), norm, out=np.zeros(windows), where=norm > 1e-12)
    agreement *= np.sign(scores[peak])
    return {**result, "offsetFrames": peak, "offsetMs": peak * 1000 / rate,
            "windowFrames": width, "windowsChecked": windows,
            "lowAgreementWindowFirstFrames": [first + int(index) * width for index in np.flatnonzero(agreement < 0.75)]}


def analyse(capture, output_pair, input_pair):
    metadata, sent, returned = read_capture(capture)
    if returned is None:
        raise ValueError("Paired input and output capture required")
    rate = metadata["rateHz"]
    rows = [match_channel(x, y, metadata["firstFrame"], metadata["input"]["firstFrame"], rate)
            for x, y in zip(stereo(sent, output_pair).T, stereo(returned, input_pair).T)]
    offsets = [row["offsetFrames"] for row in rows]
    matched = None not in offsets and abs(offsets[0] - offsets[1]) <= 8
    return {"schema": "sl3.worker-loopback-analysis.v1", "rateHz": rate,
            "outputPair": [output_pair, output_pair + 1], "inputPair": [input_pair, input_pair + 1],
            "outputPcmSha256": metadata["pcmSha256"], "inputPcmSha256": metadata["input"]["pcmSha256"],
            "consistentStereoMatch": matched, "channels": rows,
            "scope": "Worker output-to-input frame offset. Verify wiring and use a nonrepeating stereo test signal."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output-pair", type=int, choices=(1, 3, 5), required=True)
    parser.add_argument("--input-pair", type=int, choices=(1, 3, 5), required=True)
    args = parser.parse_args()
    print(json.dumps(analyse(args.capture, args.output_pair, args.input_pair), indent=2))
