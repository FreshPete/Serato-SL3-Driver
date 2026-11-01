import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('capture_evidence', Path(__file__).parents[1] / 'scripts/validate-usbdk-capture.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CaptureEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder / 'capture').mkdir()
        self.sha = '1' * 64
        self.capture = {'transport': 'UsbDk 1.0.22', 'capture_succeeded': True, 'transfers_succeeded': True,
                        'buffer_cleanup_complete': True, 'redirect_and_alternates_cleanup_succeeded': True,
                        'offline_playback_layout_validated': True, 'submitted_requests': 4, 'completed_requests': 4,
                        'planned_intervals': 256, 'planned_ms': 32, 'zero_packets': 0, 'audio_output_submissions': 0,
                        'reported_rate_hz': 48000, 'frames': 1536, 'started_utc': '2026-10-27T01:00:01Z',
                        'completed_utc': '2026-10-27T01:00:02Z', 'packets': []}
        packed = bytearray()
        for request in range(4):
            raw = bytearray([0x5a] * (64 * 126))
            for packet in range(64):
                data = bytes((request + packet + i) % 256 for i in range(108))
                raw[packet * 126:packet * 126 + 108] = data
                packed.extend(data)
                self.capture['packets'].append({'request': request, 'packet': packet, 'offset': packet * 126,
                    'length': 108, 'status': 0, 'request_attempted': True, 'request_submitted': True,
                    'request_terminal': True, 'completion_win32_error': 0, 'request_usbd_status': 0,
                    'submitted_utc': '2026-10-27T01:00:01.100Z', 'completed_utc': '2026-10-27T01:00:01.200Z'})
            (self.folder / f'capture/registered-{request}.bin').write_bytes(raw)
        (self.folder / 'capture/capture.pcm').write_bytes(packed)
        self.run = {'schema': 'sl3.usbdk.traced-run.v1', 'mode': 'Capture', 'completed': True, 'nativeExitCode': 0,
                    'error': None, 'secureBootBefore': True, 'secureBootAfter': True, 'traceExitCode': 0,
                    'traceCleanupConfirmed': True, 'traceStats': {'eventsLost': 0, 'buffersLost': 0, 'eventCount': 30},
                    'nativeSha256': self.sha, 'traceStartedUtc': '2026-10-27T01:00:00Z', 'traceStoppedUtc': '2026-10-27T01:01:00Z'}
        (self.folder / 'trace').mkdir()
        (self.folder / 'trace/capture.json').write_text(json.dumps({'status': 'window completed',
            'session': 'synthetic-session', 'startedUtc': self.run['traceStartedUtc'],
            'stoppedUtc': self.run['traceStoppedUtc']}), encoding='utf-8')
        self.xml = ('<Events><Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">'
                    '<System><Provider Guid="{9e814aad-3204-11d2-9a82-006008a86939}"/></System>'
                    '<EventData><Data Name="EventsLost">0</Data><Data Name="BuffersLost">0</Data>'
                    '<Data Name="SessionNameString">synthetic-session</Data></EventData></Event></Events>')
        (self.folder / 'events.xml').write_text(self.xml, encoding='utf-8')
        self.run['traceStats'] = module.trace_statistics(self.folder / 'events.xml')
        self.run['recoveryConfirmed'] = True
        for name, field in [('before-state.json', 'beforeStateSha256'), ('after-state.json', 'afterStateSha256')]:
            (self.folder / name).write_text('{"synthetic":true}', encoding='utf-8')
            self.run[field] = module.digest(self.folder / name)
        self.save()

    def save(self):
        record = self.folder / 'capture/capture.json'
        record.write_text(json.dumps(self.capture), encoding='utf-8')
        self.run['nativeRecordSha256'] = module.digest(record)
        (self.folder / 'run.json').write_text(json.dumps(self.run), encoding='utf-8')

    def validate(self):
        return module.validate(self.folder, self.sha)

    def test_valid_padding_and_identity(self):
        result = self.validate()
        self.assertTrue(result['valid'])
        self.assertEqual(result['frames'], 1536)
        self.assertEqual(len(result['files']), 11)

    def test_bad_native_identity(self):
        with self.assertRaisesRegex(ValueError, 'different native'):
            module.validate(self.folder, '2' * 64)

    def test_trace_loss_and_cleanup(self):
        for field in ['eventsLost', 'buffersLost']:
            self.run['traceStats'][field] = 1
            self.save()
            with self.assertRaisesRegex(ValueError, 'statistics or hash changed'):
                self.validate()
            self.run['traceStats'][field] = 0
        self.capture['redirect_and_alternates_cleanup_succeeded'] = False
        self.save()
        with self.assertRaisesRegex(ValueError, 'prerequisite'):
            self.validate()

    def test_duplicate_and_bad_packet(self):
        self.capture['packets'][-1] = self.capture['packets'][0].copy()
        self.save()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.validate()

    def test_wrong_pcm_and_mutated_record(self):
        pcm = self.folder / 'capture/capture.pcm'
        pcm.write_bytes(pcm.read_bytes() + b'padding')
        with self.assertRaisesRegex(ValueError, 'Packed PCM'):
            self.validate()
        self.capture['frames'] = 0
        (self.folder / 'capture/capture.json').write_text(json.dumps(self.capture), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'record hash changed'):
            self.validate()

    def test_outside_trace_and_packet_errors(self):
        self.run['traceStoppedUtc'] = '2026-10-27T01:00:01.500Z'
        self.save()
        with self.assertRaisesRegex(ValueError, 'inconsistent'):
            self.validate()
        self.run['traceStoppedUtc'] = '2026-10-27T01:01:00Z'
        for field, value in [('status', 0x100000000), ('length', 17), ('offset', 1), ('request_terminal', False)]:
            old = self.capture['packets'][0][field]
            self.capture['packets'][0][field] = value
            self.save()
            with self.assertRaises(ValueError):
                self.validate()
            self.capture['packets'][0][field] = old

    def test_trace_xml_and_session_integrity(self):
        xml = self.folder / 'events.xml'
        xml.write_text(self.xml.replace('>0</Data>', '>1</Data>', 1), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'statistics or hash changed'):
            self.validate()
        self.run['traceStats'] = module.trace_statistics(xml)
        self.save()
        with self.assertRaisesRegex(ValueError, 'lossy'):
            self.validate()
        for text in ['<Events/>', self.xml.replace('Name="EventsLost"', 'Name="Unknown"'),
                     self.xml.replace('9e814aad', '00000000')]:
            xml.write_text(text, encoding='utf-8')
            with self.assertRaises(ValueError):
                module.trace_statistics(xml)

    def test_recovery_snapshot_and_frame_count(self):
        self.run['recoveryConfirmed'] = False
        self.save()
        with self.assertRaisesRegex(ValueError, 'baseline recovery'):
            self.validate()
        self.run['recoveryConfirmed'] = True
        self.capture['reported_rate_hz'] = 44100
        self.save()
        with self.assertRaisesRegex(ValueError, 'not plausible'):
            self.validate()
        (self.folder / 'after-state.json').write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'snapshot hash changed'):
            self.validate()


class CircularRetentionTests(unittest.TestCase):
    def header(self, written):
        return {'LogFileMode':'0x2', 'BufferSize':'131072', 'MaxFileSize':'64', 'BuffersWritten':str(written),
                'EventsLost':'0', 'BuffersLost':'0'}

    def test_actual_attended_header_rejects_overwrite_despite_zero_loss(self):
        with self.assertRaisesRegex(ValueError, 'overwrote file capacity'):
            module.reject_circular_overwrite(self.header(919))

    def test_capacity_boundary_is_conservative_and_below_capacity_is_accepted(self):
        module.reject_circular_overwrite(self.header(511))
        with self.assertRaises(ValueError):
            module.reject_circular_overwrite(self.header(512))

    def test_known_circular_mode_requires_valid_geometry(self):
        for key in ('BufferSize','BuffersWritten','MaxFileSize'):
            header=self.header(100)
            del header[key]
            with self.assertRaisesRegex(ValueError, 'geometry'):
                module.reject_circular_overwrite(header)
        header=self.header(0);header['MaxFileSize']='0'
        with self.assertRaises(ValueError):
            module.reject_circular_overwrite(header)


if __name__ == '__main__':
    unittest.main()
