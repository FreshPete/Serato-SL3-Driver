"""Synthetic controls evidence and plan-only guards; never executes a USB test."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('controls_validator', ROOT/'scripts/validate-controls-host-probe.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ControlsEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.sha = 'a'*64
        self.owner = {'rate_hz': 48000, 'worker_phase': 1, 'native_error': 1168}
        for key in ('io_retired', 'audio_thread_retired', 'process_started', 'device_held'):
            self.owner[key] = True
        for key in ('running', 'forced_termination', 'device_released', 'worker_exited', 'private_job_empty'):
            self.owner[key] = False
        for key in ('host_failure', 'active_callbacks', 'callbacks_started', 'callbacks_completed', 'worker_failure', 'stream_fault',
                    'audio_input_submissions', 'audio_input_frames', 'audio_input_blocks', 'audio_owner_input_frames', 'published_output_frames',
                    'audio_output_submissions', 'audio_output_completions', 'audio_output_frames_submitted', 'pending_mask', 'retained_mask'):
            self.owner[key] = 0
        final = copy.deepcopy(self.owner)
        final.update(worker_phase=6, device_held=False, device_released=True, worker_exited=True, private_job_empty=True)
        raw = list(range(17, 39))
        self.data = {'schema': 'sl3.controls-host-probe.v1', 'phase': 'finished', 'simulated': True,
                     'worker_sha256': self.sha, 'device_protocol_version': 3, 'successful': True, 'finished': True,
                     'acquisition_verified': True, 'sample_present': True, 'acquisition_attempts': 1, 'query_attempts': 1,
                     'received_frames': 4, 'error': '', 'raw_controls': raw, 'inputs': [],
                     'audio_start_attempts': 0, 'audio_buffers_created': False, 'alternate_changes_requested': 0,
                     'rate_changes': 0, 'control_setters': 0, 'firmware_requests': 0, 'calibration_verified': False,
                     'analogue_signal_verified': False, 'asio_com_registered': False,
                     'acquisition': copy.deepcopy(self.owner), 'after_query': copy.deepcopy(self.owner), 'final': final}
        for i, (p, s, t) in enumerate(((0, 3, 8), (1, 9, 14), (2, 15, 20))):
            self.data['inputs'].append({'group': i, 'phono_raw': raw[p], 'phono_nonzero': True, 'sensitivity_code': raw[s],
                                        'original_ui_sensitivity_tenths_mv': None, 'through_raw': raw[t], 'through_nonzero': True})

    def save(self, data=None, folder=None):
        path = (folder or self.folder)/'probe.json'
        path.write_text(json.dumps(data or self.data))

    def validate(self):
        return validator.probe(self.folder, self.sha, True)

    def test_raw_unknown_values_and_native_error_preserved(self):
        self.save()
        result = self.validate()
        self.assertTrue(result['valid'])
        self.assertEqual(result['rawControls'], list(range(17, 39)))
        self.assertIsNone(result['inputs'][0]['original_ui_sensitivity_tenths_mv'])

    def test_ownership_and_no_audio_guards(self):
        for stage, key, value in [('acquisition', 'device_released', True), ('after_query', 'io_retired', False),
                                  ('after_query', 'audio_input_frames', 1), ('after_query', 'callbacks_started', 1),
                                  ('final', 'worker_exited', False), ('final', 'pending_mask', 1), ('final', 'forced_termination', True)]:
            data = copy.deepcopy(self.data)
            data[stage][key] = value
            self.save(data)
            with self.assertRaises(ValueError):
                self.validate()
        for key, value in [('sample_present', False), ('successful', False), ('device_protocol_version', True),
                           ('query_attempts', 2), ('control_setters', 1), ('audio_buffers_created', True)]:
            data = copy.deepcopy(self.data)
            data[key] = value
            self.save(data)
            with self.assertRaises(ValueError):
                self.validate()

    def test_payload_types_width_count_and_interpretation(self):
        for key, value in [('raw_controls', [1]*21), ('raw_controls', [True]*22), ('raw_controls', [256]*22),
                           ('received_frames', 0), ('received_frames', 5), ('received_frames', True)]:
            data = copy.deepcopy(self.data)
            data[key] = value
            self.save(data)
            with self.assertRaises(ValueError):
                self.validate()
        data = copy.deepcopy(self.data)
        data['inputs'][0]['original_ui_sensitivity_tenths_mv'] = 125
        self.save(data)
        with self.assertRaises(ValueError):
            self.validate()
        data = copy.deepcopy(self.data)
        data['inputs'][0]['phono_nonzero'] = 1
        self.save(data)
        with self.assertRaises(ValueError):
            self.validate()

    def native(self, folder):
        data = copy.deepcopy(self.data)
        data['simulated'] = False
        self.save(data, folder)
        stages = ['worker.enter', 'helper_load.enter', 'helper_load.return', 'enumerate.enter', 'enumerate.return',
                  'configuration.enter', 'configuration.return', 'redirect_start.enter', 'redirect_start.return',
                  'system_handle.enter', 'system_handle.return', 'clock_getter.enter', 'clock_getter.return',
                  'audio_controls.enter', 'audio_controls_write.enter', 'audio_controls_write.return'] + [
                  'audio_controls_read.enter', 'audio_controls_read.return']*4 + [
                  'audio_controls.return', 'redirect_close.enter', 'redirect_close.return', 'helper_unload.enter', 'helper_unload.return']
        raw = ''.join(f'{100+i}\t1234\t{stage}\n' for i, stage in enumerate(stages))
        (folder/'worker-1.tsv').write_text(raw)
        return raw

    def test_native_journal_exact_operations_and_complete_suffix(self):
        raw = self.native(self.folder)
        result = validator.probe(self.folder, self.sha)
        self.assertEqual(result['nativeJournal']['controlsReads'], 4)
        for bad in (raw.rstrip('\n'), raw+'999\t1234\tclock_getter.enter\n', raw.replace('1234', '4321', 1),
                    raw.replace('audio_controls_write.return', 'audio_controls_write.enter'), raw.replace('101\t', '99\t', 1)):
            (self.folder/'worker-1.tsv').write_text(bad)
            with self.assertRaises(ValueError):
                validator.probe(self.folder, self.sha)

    def test_guard_markers_require_complete_ordered_pair(self):
        raw = self.native(self.folder)
        path = self.folder/'worker-1.tsv'
        # Same tick is legal; insert at the configuration/start boundary.
        anchor = '107\t1234\tredirect_start.enter\n'
        for name in ('redirect_owner_acquire', 'redirect_owner.acquire'):
            pair = f'106\t1234\t{name}.enter\n106\t1234\t{name}.return\n'
            path.write_text(raw.replace(anchor, pair+anchor))
            result = validator.probe(self.folder, self.sha)
            self.assertEqual(result['nativeJournal']['redirectOwnerAcquireMarkers'],
                             [name+'.enter', name+'.return'])
            for bad in (pair.splitlines(True)[0], ''.join(reversed(pair.splitlines(True))),
                        pair+pair, pair.replace(name+'.return', 'other.acquire.return')):
                path.write_text(raw.replace(anchor, bad+anchor))
                with self.assertRaises(ValueError):
                    validator.probe(self.folder, self.sha)

    def test_wrapper_plan_has_no_device_or_directory_actions(self):
        target = self.folder/'not-created'
        run = subprocess.run(['pwsh', '-NoProfile', '-File', str(ROOT/'scripts/test-controls-host-traced.ps1'),
                              '-ResultDirectory', str(target)], capture_output=True, text=True, timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        plan = json.loads(run.stdout)
        self.assertTrue(plan['planOnly'])
        self.assertFalse(plan['deviceAccess'])
        self.assertEqual(plan['audioStartAttempts'], 0)
        self.assertEqual(plan['controlSetters'], 0)
        self.assertFalse(target.exists())

    def test_existing_live_output_rejected_before_elevation_or_device(self):
        run = subprocess.run(['pwsh', '-NoProfile', '-File', str(ROOT/'scripts/test-controls-host-traced.ps1'), '-Run',
                              '-ResultDirectory', str(self.folder)], capture_output=True, text=True, timeout=20)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('Choose a fresh evidence directory', run.stderr)
        self.assertFalse((self.folder/'run.json').exists())

    def test_trace_hash_window_recovery_and_loss_gates(self):
        probe = self.folder/'probe'
        probe.mkdir()
        self.native(probe)
        validation = {'valid': True}
        (self.folder/'probe-validation.json').write_text(json.dumps(validation))
        trace = self.folder/'trace'
        trace.mkdir()
        (trace/'one.etl').write_bytes(b'synthetic')
        (self.folder/'events.xml').write_text('<synthetic-parser-input/>')
        state = {'secureBoot': True, 'deviceGuard': {}, 'hvciRegistry': {}, 'devices': [{'device': {
            'InstanceId': r'USB\VID_1CC5&PID_0001\SL3.01.00'}, 'properties': []}], 'asio': {}, 'application': {}}
        for name in ('before-state.json', 'after-state.json'):
            (self.folder/name).write_text(json.dumps(state))
        capture = {'status': 'window completed', 'session': 'SL3Startup-'+'a'*32, 'plan': {'withUsbDkLifecycle': False},
                   'startedUtc': '2026-10-30T01:00:00Z', 'stoppedUtc': '2026-10-30T01:01:00Z',
                   'commands': [{'arguments': ['delete', '-n', 'SL3Startup-'+'a'*32], 'exitCode': 0}]}
        (trace/'capture.json').write_text(json.dumps(capture))
        stats = {'eventsLost': 0, 'buffersLost': 0, 'eventCount': 10, 'session': capture['session'],
                 'xmlSha256': validator.digest(self.folder/'events.xml')}
        record = {'schema': 'sl3.controls-host.traced-run.v1', 'completed': True, 'error': None, 'withUsbDkLifecycle': False, 'withUsbIdentity': False,
                  'probeExitCode': 0, 'traceExitCode': 0, 'workerSha256': self.sha, 'probeSha256': 'b'*64,
                  'runnerInputs': {name: validator.digest(ROOT/'scripts'/name) for name in validator.RUNNER_INPUTS},
                  'beforeStateSha256': validator.digest(self.folder/'before-state.json'),
                  'afterStateSha256': validator.digest(self.folder/'after-state.json'), 'traceStats': stats,
                  'traceRecordSha256': validator.digest(trace/'capture.json'), 'etlSha256': validator.digest(trace/'one.etl'),
                  'probeRecordSha256': validator.digest(probe/'probe.json'),
                  'probeValidationSha256': validator.digest(self.folder/'probe-validation.json'),
                  'probeStartedUtc': '2026-10-30T01:00:05Z', 'probeCompletedUtc': '2026-10-30T01:00:07Z'}
        for key in ('traceCleanupConfirmed', 'secureBootBefore', 'secureBootAfter', 'recoveryConfirmed'):
            record[key] = True
        for key in ('driverChanges', 'securityChanges', 'asioRegistration', 'automaticRetry'):
            record[key] = False
        with patch.object(validator.physical.capture_validator, 'trace_statistics', return_value=stats):
            (self.folder/'run.json').write_text(json.dumps(record))
            self.assertTrue(validator.traced(self.folder, self.sha, 'b'*64)['valid'])
            for key, value in [('probeCompletedUtc', '2026-10-30T01:02:00Z'), ('etlSha256', 'c'*64),
                               ('probeValidationSha256', 'c'*64), ('secureBootAfter', False), ('driverChanges', True)]:
                bad = copy.deepcopy(record)
                bad[key] = value
                (self.folder/'run.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    validator.traced(self.folder, self.sha, 'b'*64)
            (self.folder/'run.json').write_text(json.dumps(record))
            stats['eventsLost'] = 1
            with self.assertRaises(ValueError):
                validator.traced(self.folder, self.sha, 'b'*64)

    def test_combined_trace_plans_create_no_directory(self):
        for script in ('test-controls-host-traced.ps1', 'capture-usb-startup.ps1'):
            target = self.folder/script
            parameter = '-ResultDirectory' if script.startswith('test-') else '-OutputDirectory'
            run = subprocess.run(['pwsh', '-NoProfile', '-File', str(ROOT/'scripts'/script), '-WithUsbDkLifecycle',
                                  parameter, str(target)], capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr)
            plan = json.loads(run.stdout)
            self.assertTrue(plan['withUsbDkLifecycle'])
            self.assertFalse(target.exists())
            if script.startswith('capture-'):
                self.assertEqual(plan['lifecycle']['flags'], '0x650')
                self.assertFalse(plan['lifecycle']['emissionVerified'])

    def lifecycle_fixture(self):
        spec = importlib.util.spec_from_file_location('lifecycle_fixture', ROOT/'scripts/prepare-usbdk-lifecycle-trace.py')
        preparer = importlib.util.module_from_spec(spec);spec.loader.exec_module(preparer)
        plan, tmf = preparer.check()
        folder = self.folder/'lifecycle-decoder';folder.mkdir()
        (folder/'plan.json').write_text(json.dumps(plan))
        (folder/'lifecycle.tmf').write_bytes(tmf)
        session = 'SL3Startup-'+'a'*32
        capture = {'session': session, 'plan': {'withUsbDkLifecycle': True, 'lifecycle': {
            'provider': plan['providerGuid'], 'flags': plan['flags'], 'level': plan['level'],
            'driverSha256': plan['driverSha256'], 'selectedTmfSha256': plan['selectedTmfSha256'], 'emissionVerified': False}},
            'lifecycleDecoder': {'sourceSha256': validator.digest(ROOT/'scripts/prepare-usbdk-lifecycle-trace.py'),
                                 'planSha256': validator.digest(folder/'plan.json'), 'tmfSha256': validator.digest(folder/'lifecycle.tmf')},
            'commands': [{'arguments': ['update', 'trace', '-n', session, '-p', '{'+plan['providerGuid']+'}', '0x650', '4'], 'exitCode': 0},
                         {'arguments': ['start', '-n', session], 'exitCode': 0}]}
        return capture

    def test_lifecycle_decoder_provider_order_and_mode_binding(self):
        capture = self.lifecycle_fixture()
        result = validator.lifecycle_trace(self.folder, capture, True)
        self.assertTrue(result['providerConfigured'])
        self.assertFalse(result['emissionVerified'])
        self.assertFalse(result['decodedMessagesVerified'])
        for bad in (False, 1, None):
            with self.subTest(requested=bad), self.assertRaises(ValueError):
                validator.lifecycle_trace(self.folder, capture, bad)
        for kind in ('reordered', 'failed', 'flags', 'claimed-emission', 'hash'):
            bad = copy.deepcopy(capture)
            if kind == 'reordered':bad['commands'].reverse()
            if kind == 'failed':bad['commands'][0]['exitCode'] = 1
            if kind == 'flags':bad['commands'][0]['arguments'][6] = '0x640'
            if kind == 'claimed-emission':bad['plan']['lifecycle']['emissionVerified'] = True
            if kind == 'hash':bad['lifecycleDecoder']['tmfSha256'] = 'a'*64
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validator.lifecycle_trace(self.folder, bad, True)

    def test_lifecycle_prepared_bytes_and_plan_are_rechecked(self):
        capture = self.lifecycle_fixture()
        tmf = self.folder/'lifecycle-decoder/lifecycle.tmf'
        original = tmf.read_bytes();tmf.write_bytes(original+b'changed')
        with self.assertRaises(ValueError):validator.lifecycle_trace(self.folder, capture, True)
        tmf.write_bytes(original)
        path = self.folder/'lifecycle-decoder/plan.json'
        data = json.loads(path.read_text());data['flags'] = '0x640';path.write_text(json.dumps(data))
        capture['lifecycleDecoder']['planSha256'] = validator.digest(path)
        with self.assertRaises(ValueError):validator.lifecycle_trace(self.folder, capture, True)


if __name__ == '__main__':
    unittest.main()
