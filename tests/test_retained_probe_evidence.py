"""Synthetic metadata/journal tests and no-device PowerShell plan checks only."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('retained_evidence', ROOT/'scripts/validate-retained-host-probe.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class RetainedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.sha = '1'*64
        self.root = {'schema': 'sl3.retained-host-probe.v1', 'phase': 'finished', 'simulated': True, 'worker_sha256': self.sha,
                     'acquisition_attempts': 1, 'requested_streams': 2, 'completed_streams': 2, 'buffer_recreations': 1,
                     'requested_stream_ms': 1000, 'bank_frames': 128, 'intervals': 8, 'worker_phase': 6,
                     'expected_rate_hz': 48000, 'reported_rate_hz': 48000, 'host_failure': 0, 'worker_failure': 0,
                     'stream_fault': 0, 'active_callbacks': 0, 'error': '', 'output_payload': 'zero PCM only',
                     'streams': [{'file': f'stream-{i}.json', 'successful': True, 'buffers_disposed': True} for i in (1, 2)]}
        for k in ('successful', 'finished', 'acquisition_verified', 'acquisition_io_retired', 'acquisition_device_held',
                  'io_retired', 'device_released', 'audio_thread_retired', 'worker_exited', 'private_job_empty'):
            self.root[k] = True
        for k in ('acquisition_device_released', 'acquisition_worker_exited', 'device_held', 'forced_termination',
                  'analogue_signal_verified', 'latency_measured', 'asio_com_registered'):
            self.root[k] = False
        self.stream = {'schema': 'sl3.host-probe.v1', 'phase': 'finished', 'simulated': True, 'stream_index': 1,
                       'expected_rate_hz': 48000, 'reported_rate_hz': 48000, 'initial_reported_rate_hz': 48000,
                       'intervals': 8, 'bank_frames': 128, 'requested_stream_ms': 1000, 'worker_phase': 1, 'audio_exit': 2,
                       'callbacks': 4, 'callbacks_started': 4, 'callbacks_completed': 4, 'input_blocks': 13,
                       'input_frames': 624, 'audio_input_frames': 576, 'published_output_frames': 528,
                       'output_submissions': 10, 'output_completions': 9, 'output_frames_submitted': 480,
                       'observed_stream_ms': 1000, 'native_error': 1168, 'error': '', 'output_payload': 'zero PCM only',
                       'callback_counter_frequency': 48000, 'timing_records_dropped': 0, 'last_frame': 384,
                       'callback_timings': [[i*128, i*2666666, 1000+i*128] for i in range(4)]}
        for k in ('host_failure', 'worker_failure', 'stream_fault', 'active_callbacks', 'pending_mask', 'retained_mask', 'completed_inspections', 'first_frame'):
            self.stream[k] = 0
        for k in ('successful', 'finished', 'retained_device', 'stream_started', 'device_held', 'io_retired', 'audio_thread_retired', 'buffers_disposed'):
            self.stream[k] = True
        for k in ('device_released', 'worker_exited', 'private_job_empty', 'forced_termination', 'single_open', 'inspect_only',
                  'inspection_succeeded', 'callback_contract_failed', 'analogue_signal_verified', 'latency_measured', 'asio_com_registered'):
            self.stream[k] = False

    def save(self, root=None, stream=None):
        (self.folder/'probe.json').write_text(json.dumps(root or self.root))
        for i in (1, 2):
            value = copy.deepcopy(stream or self.stream)
            value['stream_index'] = i
            (self.folder/f'stream-{i}.json').write_text(json.dumps(value))

    def validate(self):
        return validator.probe(self.folder, self.sha, 48000, True)

    def test_valid_queue_tails_and_native_error_preserved(self):
        self.save()
        result = self.validate()
        self.assertTrue(result['valid'])
        self.assertTrue(result['simulated'])
        self.assertEqual(result['streams'][0]['nativeError'], 1168)
        self.assertEqual(result['streams'][0]['outputSubmissions'], 10)
        self.assertEqual(result['streams'][0]['outputCompletions'], 9)

    def test_independent_ownership_and_failure_flags(self):
        for key, value in [('io_retired', False), ('device_released', False), ('audio_thread_retired', False),
                           ('worker_exited', False), ('device_held', True), ('host_failure', 3), ('completed_streams', 1),
                           ('acquisition_attempts', 2), ('buffer_recreations', 0)]:
            root = copy.deepcopy(self.root)
            root[key] = value
            self.save(root=root)
            with self.assertRaises(ValueError):
                self.validate()
        for key in ('device_released', 'worker_exited', 'forced_termination'):
            stream = copy.deepcopy(self.stream)
            stream[key] = True
            self.save(stream=stream)
            with self.assertRaises(ValueError):
                self.validate()

    def test_counter_type_order_and_timing_rejection(self):
        for key, value in [('input_frames', 1), ('published_output_frames', 1000), ('output_frames_submitted', 1000),
                           ('callbacks_completed', 3), ('observed_stream_ms', 999), ('callbacks', True),
                           ('host_failure', False), ('first_frame', 128), ('last_frame', 512)]:
            stream = copy.deepcopy(self.stream)
            stream[key] = value
            self.save(stream=stream)
            with self.assertRaises(ValueError):
                self.validate()

    def test_identity_paths_and_native_journal_required(self):
        for change in ({'simulated': False}, {'worker_sha256': '2'*64},
                       {'streams': [{'file': '../outside.json', 'successful': True, 'buffers_disposed': True}]*2}):
            root = copy.deepcopy(self.root)
            root.update(change)
            self.save(root=root)
            with self.assertRaises(ValueError):
                self.validate()
        self.root['simulated'] = self.stream['simulated'] = False
        self.save()
        with self.assertRaises(ValueError):
            validator.probe(self.folder, self.sha, 48000, False)

    def journal_rows(self):
        stages = ['worker.enter', 'helper_load.enter', 'helper_load.return', 'enumerate.enter', 'enumerate.return',
                  'configuration.enter', 'configuration.return', 'redirect_start.enter', 'redirect_start.return',
                  'system_handle.enter', 'system_handle.return'] + ['clock_getter.enter', 'clock_getter.return']*3 + [
                  'redirect_close.enter', 'redirect_close.return', 'helper_unload.enter', 'helper_unload.return']
        return [f'{1000+i}\t1234\t{s}\n' for i, s in enumerate(stages)]

    def test_exact_journal_lifetime_and_partial_suffix(self):
        path = self.folder/'worker-1.tsv'
        rows = self.journal_rows()
        path.write_text(''.join(rows))
        result = validator.journal(path)
        self.assertEqual((result['redirects'], result['clockGetters'], result['redirectCloses']), (1, 3, 1))
        for bad in (rows[:-1], rows+rows[7:9], rows[:11]+rows[13:], [rows[0]]+[r.replace('\t1234\t', '\t5678\t') for r in rows[1:]]):
            path.write_text(''.join(bad))
            with self.assertRaises(ValueError):
                validator.journal(path)
        path.write_text(''.join(rows).rstrip('\n'))
        with self.assertRaises(ValueError):
            validator.journal(path)

    def test_runner_plan_and_missing_run_gate_touch_no_device_or_files(self):
        target = self.folder/'no-output'
        script = ROOT/'scripts/test-retained-host-traced.ps1'
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(script), '-ExpectedRate', '44100', '-ResultDirectory', str(target)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertTrue(plan['planOnly'])
        self.assertFalse(plan['deviceAccess'])
        self.assertFalse(plan['automaticRetry'])
        self.assertEqual((plan['streams'], plan['intervals'], plan['redirectsRequested']), (2, 8, 1))
        self.assertFalse(target.exists())
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(script), '-Run', '-ResultDirectory', str(target)], capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Explicit ExpectedRate', result.stderr)
        self.assertFalse(target.exists())

    def test_duplex_prerequisite_packet_and_zero_buffer_gates(self):
        folder = self.folder/'duplex'
        folder.mkdir()
        data = {'duplex_succeeded': True, 'transfers_succeeded': True, 'buffer_cleanup_complete': True,
                'redirect_and_alternates_cleanup_succeeded': True, 'reported_rate_hz': 48000, 'output_payload': 'zero PCM only',
                'submitted_input_requests': 4, 'completed_input_requests': 4, 'submitted_output_requests': 4, 'completed_output_requests': 4, 'packets': []}
        for pair in range(4):
            (folder/f'registered-{pair*2+1}.bin').write_bytes(bytes(8064))
            for direction in ('IN', 'OUT'):
                for index in range(64):
                    data['packets'].append({'pair': pair, 'direction': direction, 'slot': pair*2+(direction == 'OUT'), 'packet': index,
                        'request_submitted': True, 'request_terminal': True, 'status': 0, 'completion_win32_error': 0, 'request_usbd_status': 0,
                        'returned_length': 108, 'requested_length': 108, 'offset': index*108, 'reported_request_bytes': 64*108})
        path = folder/'duplex.json'
        def validate(value):
            path.write_text(json.dumps(value))
            record = {'nativeCompletedUtc': '2026-10-30T01:00:00Z', 'nativeStartedUtc': '2026-10-30T01:01:00Z', 'nativeRecordSha256': validator.digest(path)}
            with patch.object(validator.physical, 'validate_run', return_value=(record, {})), patch.object(validator.physical.capture_validator, 'validate', return_value={'reportedRateHz': 48000}):
                return validator.prerequisites(self.folder, self.folder, self.sha, 48000)
        self.assertTrue(validate(data)['valid'])
        for key, value in [('status', 0xc0000012), ('request_terminal', False), ('packet', 1), ('slot', 7), ('status', False)]:
            bad = copy.deepcopy(data)
            bad['packets'][0][key] = value
            with self.assertRaises(ValueError):
                validate(bad)
        (folder/'registered-1.bin').write_bytes(b'\x01'+bytes(8063))
        with self.assertRaises(ValueError):
            validate(data)

    def test_sequence_plan_has_fresh_prerequisites_and_no_retry(self):
        target = self.folder/'sequence-not-created'
        script = ROOT/'scripts/test-retained-sequence.ps1'
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(script), '-ResultDirectory', str(target)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertTrue(plan['planOnly'])
        self.assertTrue(plan['stopOnFirstFailure'])
        self.assertFalse(plan['deviceAccess'])
        self.assertFalse(plan['rateChanges'])
        self.assertEqual(plan['retries'], 0)
        self.assertEqual(len(plan['steps']), 3)
        self.assertIn('two one-second', plan['steps'][2])
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
