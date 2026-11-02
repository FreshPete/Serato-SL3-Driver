"""Synthetic recorder/journal plus surrounding trace composition; no physical trace."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_input_record_evidence as recording

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('record_trace_component',ROOT/'scripts/validate-controls-host-probe.py')
validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)

class RecordedTraceTests(unittest.TestCase):
    def setUp(self):
        self.source=recording.EvidenceTests();self.source.setUp();self.addCleanup(self.source.doCleanups)
        self.folder=self.source.folder;self.sha=recording.HASH

    def test_trace_hash_window_recovery_and_loss_gates(self):
        probe = self.folder/'probe'
        probe.mkdir()
        for name in ('result.json','input.pcm'):
            (probe/name).write_bytes((self.folder/name).read_bytes())
        self.source.folder=probe;self.source.native()
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
        record = {'schema': 'sl3.input-record.traced-run.v1', 'completed': True, 'error': None, 'withUsbDkLifecycle': False, 'withUsbIdentity': False,'expectedRateHz':48000,
                  'probeExitCode': 0, 'traceExitCode': 0, 'workerSha256': self.sha, 'probeSha256': 'b'*64,
                  'runnerInputs': {name: validator.digest(ROOT/'scripts'/name) for name in validator.RUNNER_INPUTS+('validate-input-record-probe.py',)},
                  'beforeStateSha256': validator.digest(self.folder/'before-state.json'),
                  'afterStateSha256': validator.digest(self.folder/'after-state.json'), 'traceStats': stats,
                  'traceRecordSha256': validator.digest(trace/'capture.json'), 'etlSha256': validator.digest(trace/'one.etl'),
                  'probeRecordSha256': validator.digest(probe/'result.json'),
                  'probeValidationSha256': validator.digest(self.folder/'probe-validation.json'),
                  'probeStartedUtc': '2026-10-30T01:00:05Z', 'probeCompletedUtc': '2026-10-30T01:00:07Z'}
        for key in ('traceCleanupConfirmed', 'secureBootBefore', 'secureBootAfter', 'recoveryConfirmed'):
            record[key] = True
        for key in ('driverChanges', 'securityChanges', 'asioRegistration', 'automaticRetry'):
            record[key] = False
        with patch.object(validator.physical.capture_validator, 'trace_statistics', return_value=stats):
            (self.folder/'run.json').write_text(json.dumps(record))
            self.assertTrue(validator.traced(self.folder, self.sha, 'b'*64,input_record=True)['valid'])
            for key, value in [('expectedRateHz',44100),('expectedRateHz',True),('schema','sl3.controls-host.traced-run.v1'),('probeCompletedUtc', '2026-10-30T01:02:00Z'), ('etlSha256', 'c'*64),
                               ('probeValidationSha256', 'c'*64), ('secureBootAfter', False), ('driverChanges', True)]:
                bad = copy.deepcopy(record)
                bad[key] = value
                (self.folder/'run.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    validator.traced(self.folder, self.sha, 'b'*64,input_record=True)
            (self.folder/'run.json').write_text(json.dumps(record))
            stats['eventsLost'] = 1
            with self.assertRaises(ValueError):
                validator.traced(self.folder, self.sha, 'b'*64,input_record=True)
