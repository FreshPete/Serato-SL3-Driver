"""Three-second mathematical fixtures only; no device, playback or physical claim."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np
import test_input_record_evidence as recording

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/analyse-input-tone.py'
spec = importlib.util.spec_from_file_location('recorded_tone', SCRIPT)
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)


class RecordedToneTests(unittest.TestCase):
    def setUp(self):
        self.source = recording.EvidenceTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.folder = self.source.folder

    def fixture(self, rate=48000, frequency=1000, spike=False):
        self.source.fixture(rate)
        count = self.source.result['recordedFrames']
        phase = np.arange(count)*2*np.pi*frequency/rate
        frames = np.rint(np.column_stack((1000+1e6*np.sin(phase),
            -1200+250000*np.sin(phase+.3), np.zeros(count),
            400000*np.sin(phase+np.pi),
            1e6*np.sin(np.arange(count)*2*np.pi*1700/rate), np.full(count,250000)))).astype(np.int32)
        if spike: frames[0,:] = 8388607
        unsigned = frames.reshape(-1) & 0xffffff
        audio = np.column_stack((unsigned & 255, (unsigned >> 8) & 255,
                                 (unsigned >> 16) & 255)).astype(np.uint8).tobytes()
        (self.folder/'input.pcm').write_bytes(audio)
        self.source.result['pcmSha256'] = v.digest(audio); self.source.save()
        return self.declaration(frequency)

    def declaration(self, frequency=1000, kind='synthetic'):
        return json.dumps({'schema':'sl3.recorded-input-tone-declaration.v1',
            'evidenceKind':kind,'rateHz':self.source.result['observedRateHz'], 'toneHz':frequency,
            'sourceDescription':'Mathematical sine fixture only; no audio emitted',
            'wiringDescription':'No physical wiring; numeric six-channel fixture',
            'controlStateDescription':'No device or control operation',
            'recordingRecordSha256':v.digest((self.folder/'result.json').read_bytes()),
            'pcmSha256':v.digest((self.folder/'input.pcm').read_bytes()),
            'workerSha256':recording.HASH}).encode()

    def analyse(self, declaration, simulated=True):
        return v.analyse_recording(self.folder, declaration, recording.HASH, simulated)

    def test_signed_decoder_extrema_and_partial_frame_refusal(self):
        values = [-8388608,-1,0,1,8388607,123]
        audio = b''.join(n.to_bytes(3,'little',signed=True) for n in values)
        self.assertEqual(v.decode_recording(audio).tolist(), [values])
        for bad in [b'', audio[:-1], audio+b'X', bytearray(audio)]:
            with self.subTest(length=len(bad)), self.assertRaises(ValueError): v.decode_recording(bad)

    def test_both_rates_fit_and_partition_every_callback(self):
        for rate, count in [(44100,132352),(48000,144000)]:
            with self.subTest(rate=rate):
                result = self.analyse(self.fixture(rate))
                full = result['fullRecordedPrefixFit']; channels = full['channels']
                self.assertEqual(full['frames'],count)
                self.assertAlmostEqual(channels[0]['sineAmplitudeCode'],1e6,delta=1)
                self.assertAlmostEqual(channels[0]['fittedDcCode'],1000,delta=1)
                self.assertAlmostEqual(channels[1]['phaseAtRetainedFrameZeroRadians'],.3,delta=.00001)
                self.assertLess(channels[0]['residualRmsCode'],.5)
                self.assertIsNone(channels[2]['explainedCentredEnergyFraction'])
                self.assertIsNone(channels[5]['explainedCentredEnergyFraction'])
                self.assertLess(channels[4]['explainedCentredEnergyFraction'],.01)
                self.assertGreater(channels[4]['residualRmsCode'],600000)
                windows = result['callbackWindowFits']
                boundaries = [(i*(count//128)//4)*128 for i in range(5)]
                self.assertEqual([w['firstRetainedFrame'] for w in windows],boundaries[:-1])
                self.assertEqual([w['endRetainedFrameExclusive'] for w in windows],boundaries[1:])
                self.assertEqual(sum(w['frames'] for w in windows),count)
                self.assertEqual(result['trailingCallbacksOutsideRecordedPrefix'],2)
                self.assertEqual(result['samplesDiscardedFromRecordedPrefix'],0)
                self.assertTrue(result['recordingSimulated'])
                for key in ['analogueSignalVerified','physicalJackMappingVerified','physicalClockVerified',
                            'usbContinuityVerified','latencyMeasured','timingProfileGenerated','playbackRequested']:
                    self.assertFalse(result[key])

    def test_startup_spike_retained_in_statistics_full_fit_and_first_window(self):
        result = self.analyse(self.fixture(spike=True))
        c = result['fullRecordedPrefixStatistics']['channels'][0]
        self.assertEqual(c['maximumCode'],8388607); self.assertEqual(c['railSamples'],1)
        self.assertGreater(result['fullRecordedPrefixFit']['channels'][0]['residualRmsCode'],1000)
        self.assertGreater(result['callbackWindowFits'][0]['channels'][0]['residualRmsCode'],1000)
        self.assertLess(result['callbackWindowFits'][1]['channels'][0]['residualRmsCode'],.5)

    def test_three_cycles_full_prefix_does_not_make_short_windows_eligible(self):
        result = self.analyse(self.fixture(frequency=1))
        self.assertTrue(result['fullRecordedPrefixFit']['eligible'])
        self.assertTrue(all(not w['eligible'] and 'channels' not in w for w in result['callbackWindowFits']))

    def test_full_scale_alternation_keeps_exact_energy_beyond_int64_sum(self):
        # 144000 * 2**46 exceeds signed int64; the half-code DC is retained.
        frame_a = b'\x00\x00\x80'*6
        frame_b = b'\xff\xff\x7f'*6
        audio = (frame_a+frame_b)*72000
        (self.folder/'input.pcm').write_bytes(audio)
        self.source.result['pcmSha256'] = v.digest(audio); self.source.save()
        result = self.analyse(self.declaration())
        for channel in result['fullRecordedPrefixStatistics']['channels']:
            self.assertEqual(channel['meanCode'],-.5)
            self.assertEqual(channel['acRmsCode'],8388607.5)
            self.assertEqual(channel['railSamples'],144000)

    def test_declaration_contract_and_simulation_cannot_be_promoted(self):
        original = json.loads(self.declaration())
        for key,value in [('schema','sl3.input-tone-declaration.v1'),('workerSha256','b'*64),
                          ('recordingRecordSha256','b'*64),('pcmSha256','b'*64),('rateHz',44100),
                          ('evidenceKind','operator_declared'),('unknown',True),('toneHz',True)]:
            changed = dict(original); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):self.analyse(json.dumps(changed).encode())

    def test_synthetic_native_grammar_and_operator_statement_do_not_verify_physics(self):
        self.source.native()
        result = self.analyse(self.declaration(kind='operator_declared'),False)
        self.assertFalse(result['recordingSimulated'])
        self.assertFalse(result['recordingValidation']['physicalProvenanceVerified'])
        self.assertFalse(result['analogueSignalVerified']);self.assertFalse(result['latencyMeasured'])

    def test_mutation_during_fit_is_refused(self):
        declared = self.declaration(); original = v.fit; mutated = False
        def change(*args):
            nonlocal mutated
            value = original(*args)
            if not mutated:
                path = self.folder/'input.pcm'; raw = path.read_bytes()
                path.write_bytes(b'X'+raw[1:]); mutated = True
            return value
        with patch.object(v,'fit',side_effect=change), self.assertRaises(ValueError):self.analyse(declared)

    def test_cli_preserves_sources_refuses_overwrite_and_missing_worker(self):
        declaration = self.folder/'declaration.json'; declaration.write_bytes(self.fixture())
        before = {p.name:v.digest(p.read_bytes()) for p in self.folder.iterdir() if p.is_file()}
        output = self.folder/'tone-output'
        args = [sys.executable,str(SCRIPT),'--recording',str(self.folder),'--simulated',
                '--declaration',str(declaration),'--output',str(output)]
        missing = subprocess.run(args,capture_output=True,timeout=30)
        self.assertNotEqual(missing.returncode,0);self.assertFalse(output.exists())
        args += ['--worker-sha256',recording.HASH]
        good = subprocess.run(args,capture_output=True,timeout=30)
        self.assertEqual(good.returncode,0,good.stderr.decode())
        report = output/'analysis.json'; saved = report.read_bytes()
        self.assertEqual(json.loads(saved)['schema'],'sl3.recorded-input-tone-analysis.v1')
        self.assertNotEqual(subprocess.run(args,capture_output=True,timeout=30).returncode,0)
        self.assertEqual(report.read_bytes(),saved)
        self.assertEqual(before,{name:v.digest((self.folder/name).read_bytes()) for name in before})


if __name__ == '__main__': unittest.main()
