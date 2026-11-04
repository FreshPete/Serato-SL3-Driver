"""Report the generated tone in a saved SL3 loopback recording."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy


def analyse(folder, challenge):
    scripts = Path(__file__).resolve().parent
    timer = runpy.run_path(str(scripts/'validate-driver-timer.py'))
    with (folder/'timer.json').open('rb') as stream:
        checked = timer['validate'](stream.read(8193), challenge, True, False, True)
    length = checked['loopbackPcmBytes']
    with (folder/'loopback.pcm').open('rb') as stream:
        audio = stream.read(length + 1)
    if len(audio) != length:
        raise ValueError('Saved loopback PCM length differs')
    rate = checked['rateHz']
    tone = runpy.run_path(str(scripts/'analyse-input-tone.py'))
    frames = tone['decode_recording'](audio)
    windows = []
    step = rate // 20
    for first in range(0, len(frames), step):
        fit = tone['fit'](frames, rate, 997, first, min(first + step, len(frames)))
        windows.append(fit)
    return {'schema': 'sl3.timer-loopback-analysis.v1', 'recordSha256': checked['recordSha256'],
            'pcmSha256': hashlib.sha256(audio).hexdigest(), 'rateHz': rate, 'frames': len(frames),
            'toneHz': 997, 'windows': windows, 'physicalWiringVerified': False, 'latencyMeasured': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--challenge', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyse(args.folder, args.challenge)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
