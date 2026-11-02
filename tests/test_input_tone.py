"""Known numeric tone/artefact fixtures only; no hardware, audio API or playback."""
import importlib.util
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from test_capture_pcm import fixture as pcm_fixture, packed

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/analyse-input-tone.py'
spec = importlib.util.spec_from_file_location('input_tone', SCRIPT)
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)


def fixture(rate=44100, frequency=1000, counts=None):
    record, _ = pcm_fixture(); record['reported_rate_hz'] = rate
    if counts is not None:
        require_counts = len(counts) == 256 and all(type(x) is int and 1 <= x <= 7 for x in counts)
        if not require_counts:
            raise ValueError('Synthetic fixture requires 256 bounded packet frame counts')
        record['frames'] = sum(counts)
        for packet, count in zip(record['packets'], counts):
            packet['length'] = count*18
    frames = []
    for n in range(record['frames']):
        angle = 2*math.pi*frequency*n/rate
        frames.append((round(1000+1_000_000*math.sin(angle)), round(-1200+250_000*math.sin(angle+.3)),
                       0, round(400_000*math.sin(angle+math.pi)), round(1_000_000*math.sin(2*math.pi*1700*n/rate)), 250_000))
    record_raw = json.dumps(record, sort_keys=True).encode(); audio = packed(frames)
    declared = {'schema': 'sl3.input-tone-declaration.v1', 'evidenceKind': 'synthetic', 'rateHz': rate,
                'toneHz': frequency, 'sourceDescription': 'Synthetic mathematical sine fixture; no audio emitted',
                'wiringDescription': 'No physical wiring: numeric channel fixture',
                'controlStateDescription': 'No device/control state: synthetic bytes only',
                'captureRecordSha256': v.digest(record_raw), 'pcmSha256': v.digest(audio)}
    return record_raw, audio, json.dumps(declared, sort_keys=True).encode()


class ToneTests(unittest.TestCase):
    def test_known_amplitude_dc_phase_and_six_channel_order(self):
        for rate in [44100, 48000]:
            with self.subTest(rate=rate):
                result = v.analyse(*fixture(rate)); channels = result['fullCaptureFit']['channels']
                self.assertEqual([x['streamChannel'] for x in channels], list(range(6)))
                self.assertAlmostEqual(channels[0]['sineAmplitudeCode'], 1_000_000, delta=1)
                self.assertAlmostEqual(channels[0]['fittedDcCode'], 1000, delta=1)
                self.assertAlmostEqual(channels[1]['sineAmplitudeCode'], 250_000, delta=1)
                self.assertAlmostEqual(channels[1]['fittedDcCode'], -1200, delta=1)
                self.assertAlmostEqual(channels[1]['phaseAtRetainedFrameZeroRadians'], .3, delta=.00001)
                self.assertGreater(channels[0]['explainedCentredEnergyFraction'], .999999)
                self.assertLess(channels[0]['residualRmsCode'], .5)

    def test_inverted_channel_phase_is_not_reported_as_latency(self):
        result = v.analyse(*fixture()); c = result['fullCaptureFit']['channels'][3]
        self.assertAlmostEqual(abs(c['phaseAtRetainedFrameZeroRadians']), math.pi, delta=.00001)
        self.assertFalse(result['latencyMeasured']); self.assertFalse(result['timingProfileGenerated'])

    def test_silence_and_constant_dc_have_no_explained_energy_claim(self):
        result = v.analyse(*fixture()); channels = result['fullCaptureFit']['channels']
        self.assertIsNone(channels[2]['explainedCentredEnergyFraction'])
        self.assertIsNone(channels[2]['sinePeakDbfs'])
        self.assertIsNone(channels[5]['explainedCentredEnergyFraction'])
        self.assertAlmostEqual(channels[5]['fittedDcCode'], 250_000, delta=.000001)
        json.dumps(result, allow_nan=False)

    def test_wrong_frequency_stays_in_residual(self):
        channels = v.analyse(*fixture())['fullCaptureFit']['channels']
        self.assertLess(channels[4]['explainedCentredEnergyFraction'], .01)
        self.assertGreater(channels[4]['residualRmsCode'], 600_000)

    def test_deterministic_noise_energy_is_visible(self):
        record, audio, decl = fixture(); frames = v.pcm.decode(audio); noise = random.Random(42)
        changed = packed([tuple(value+round(noise.gauss(0, 100)) for value in frame) for frame in frames])
        declared = json.loads(decl); declared['pcmSha256'] = v.digest(changed)
        c = v.analyse(record, changed, json.dumps(declared).encode())['fullCaptureFit']['channels'][0]
        self.assertAlmostEqual(c['sineAmplitudeCode'], 1_000_000, delta=20)
        self.assertGreater(c['residualRmsCode'], 80); self.assertLess(c['residualRmsCode'], 120)

    def test_startup_artefact_is_retained_in_full_and_first_request(self):
        record, audio, decl = fixture(); frames = v.pcm.decode(audio)
        frames[0] = (8388607,)*6; changed = packed(frames)
        declared = json.loads(decl); declared['pcmSha256'] = v.digest(changed)
        result = v.analyse(record, changed, json.dumps(declared).encode())
        self.assertEqual(result['fullCaptureStatistics']['channels'][0]['maximumCode'], 8388607)
        self.assertEqual(result['fullCaptureStatistics']['channels'][0]['railSamples'], 1)
        self.assertGreater(result['fullCaptureFit']['channels'][0]['residualRmsCode'], 100_000)
        self.assertGreater(result['requestWindowFits'][0]['channels'][0]['residualRmsCode'], 100_000)
        self.assertLess(result['requestWindowFits'][1]['channels'][0]['residualRmsCode'], .5)
        self.assertEqual(result['pcmSha256'], v.digest(changed)); self.assertEqual(result['samplesDiscarded'], 0)

    def test_predetermined_request_windows_cover_all_frames_once(self):
        result = v.analyse(*fixture()); windows = result['requestWindowFits']
        self.assertEqual([x['request'] for x in windows], [0, 1, 2, 3])
        self.assertEqual(windows[0]['firstRetainedFrame'], 0)
        self.assertEqual(windows[-1]['endRetainedFrameExclusive'], result['fullCaptureFit']['frames'])
        for a, b in zip(windows, windows[1:]):
            self.assertEqual(a['endRetainedFrameExclusive'], b['firstRetainedFrame'])
        self.assertEqual(sum(x['frames'] for x in windows), result['fullCaptureFit']['frames'])

    def test_short_windows_are_ineligible_without_silent_trimming(self):
        result = v.analyse(*fixture(frequency=120))
        self.assertTrue(result['fullCaptureFit']['eligible'])
        self.assertTrue(all(not x['eligible'] and 'channels' not in x for x in result['requestWindowFits']))
        self.assertEqual(result['samplesDiscarded'], 0)

    def test_variable_packet_lengths_define_request_windows(self):
        counts = [5]*64+[6]*64+[7]*64+[5, 6]*32
        result = v.analyse(*fixture(counts=counts)); windows = result['requestWindowFits']
        self.assertEqual([x['firstRetainedFrame'] for x in windows], [0, 320, 704, 1152])
        self.assertEqual([x['endRetainedFrameExclusive'] for x in windows], [320, 704, 1152, 1504])
        self.assertEqual(result['fullCaptureFit']['frames'], 1504)
        self.assertTrue(all(x['eligible'] for x in windows))
        self.assertFalse(result['usbContinuityVerified'])

    def test_too_few_full_capture_cycles_refused(self):
        with self.assertRaises(ValueError):
            v.analyse(*fixture(frequency=10))

    def test_nonfinite_boolean_zero_and_aliasing_tones_refused(self):
        record, audio, decl = fixture()
        for frequency in [float('nan'), float('inf'), True, 0, -100, 22050, 10**1000]:
            declared = json.loads(decl); declared['toneHz'] = frequency
            with self.subTest(frequency=frequency), self.assertRaises(ValueError):
                v.analyse(record, audio, json.dumps(declared).encode())

    def test_declaration_hashes_and_rate_must_bind_input(self):
        record, audio, decl = fixture()
        for key, value in [('captureRecordSha256', '0'*64), ('pcmSha256', '0'*64), ('rateHz', 48000)]:
            declared = json.loads(decl); declared[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                v.analyse(record, audio, json.dumps(declared).encode())

    def test_missing_unknown_and_duplicate_declaration_fields_refused(self):
        record, audio, decl = fixture(); declared = json.loads(decl)
        for changed in [dict(declared, hiddenOverride=True), {k: val for k, val in declared.items() if k != 'wiringDescription'}]:
            with self.assertRaises(ValueError):
                v.analyse(record, audio, json.dumps(changed).encode())
        with self.assertRaises(ValueError):
            v.analyse(record, audio, decl[:-1]+b',"toneHz":1000}')

    def test_descriptions_and_provenance_required(self):
        record, audio, decl = fixture()
        for key, value in [('sourceDescription', ''), ('wiringDescription', '\n'), ('controlStateDescription', 'x'*513),
                           ('evidenceKind', 'physical_validated')]:
            declared = json.loads(decl); declared[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                v.analyse(record, audio, json.dumps(declared).encode())

    def test_operator_declaration_does_not_verify_physical_signal(self):
        record, audio, decl = fixture(); declared = json.loads(decl); declared['evidenceKind'] = 'operator_declared'
        result = v.analyse(record, audio, json.dumps(declared).encode())
        for key in ['analogueSignalVerified', 'physicalJackMappingVerified', 'physicalClockVerified', 'usbContinuityVerified',
                    'latencyMeasured', 'timingProfileGenerated', 'playbackRequested', 'deviceAccess']:
            self.assertIs(result[key], False)

    def test_existing_capture_faults_are_refused_before_fit(self):
        record, audio, decl = fixture(); changed = json.loads(record); changed['packets'][0]['status'] = 1
        raw = json.dumps(changed).encode(); declared = json.loads(decl); declared['captureRecordSha256'] = v.digest(raw)
        with self.assertRaises(ValueError):
            v.analyse(raw, audio, json.dumps(declared).encode())

    def test_bounded_inputs(self):
        record, audio, decl = fixture()
        for args in [(record, audio[:-1], decl), (record, audio, bytes(16385)), (bytes(1048577), audio, decl)]:
            with self.subTest(lengths=list(map(len, args))), self.assertRaises(ValueError):
                v.analyse(*args)

    def test_actual_cli_preserves_inputs_and_refuses_output_reuse(self):
        with tempfile.TemporaryDirectory(prefix='sl3-input-tone-') as directory:
            folder = Path(directory); record, audio, decl = fixture()
            for name, data in [('capture.json', record), ('capture.pcm', audio), ('declaration.json', decl)]:
                (folder/name).write_bytes(data)
            output = folder/'analysis'; args = [sys.executable, str(SCRIPT), '--capture', str(folder), '--declaration',
                                               str(folder/'declaration.json'), '--output', str(output)]
            run = subprocess.run(args, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            before = (output/'analysis.json').read_bytes(); result = json.loads(before)
            self.assertEqual(result['pcmSha256'], v.digest(audio)); self.assertFalse(result['playbackRequested'])
            self.assertEqual(subprocess.run(args, capture_output=True, timeout=10).returncode, 1)
            self.assertEqual((output/'analysis.json').read_bytes(), before)
            self.assertEqual((folder/'capture.pcm').read_bytes(), audio)

    def test_actual_cli_bad_declaration_writes_no_output(self):
        with tempfile.TemporaryDirectory(prefix='sl3-input-tone-refuse-') as directory:
            folder = Path(directory); record, audio, decl = fixture(); declared = json.loads(decl); declared['pcmSha256'] = '0'*64
            (folder/'capture.json').write_bytes(record); (folder/'capture.pcm').write_bytes(audio)
            (folder/'declaration.json').write_text(json.dumps(declared)); output = folder/'refused'
            run = subprocess.run([sys.executable, str(SCRIPT), '--capture', str(folder), '--declaration',
                                  str(folder/'declaration.json'), '--output', str(output)], capture_output=True, timeout=10)
            self.assertEqual(run.returncode, 1); self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
