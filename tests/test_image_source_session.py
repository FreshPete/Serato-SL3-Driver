import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

spec = importlib.util.spec_from_file_location('image_source_session', Path(__file__).parents[1]/'scripts/inspect-image-source-session.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ImageSourceSessionTests(unittest.TestCase):
    def setUp(self):
        self.name = 'SL3Image-'+'a'*32
        self.guid = uuid.UUID('d485072b-6f31-4c20-87d5-c418cc7966b5')
        self.raw = module.request_buffer(self.name, self.guid)
        struct.pack_into('<I', self.raw, 64, 0x02000001)
        struct.pack_into('<I', self.raw, 40, 1)
        struct.pack_into('<IIII', self.raw, 88, 3, 12, 2, 1)

    def parse(self, raw=None):
        return module.parse_properties(bytes(self.raw if raw is None else raw), self.name, self.guid)

    def test_effective_modes_and_loss_fields_preserved(self):
        p = self.parse()
        self.assertTrue(p['systemLoggerModePresent'])
        self.assertEqual((p['eventsLost'], p['buffersWritten'], p['logBuffersLost'], p['realTimeBuffersLost']), (3,12,2,1))
        self.assertEqual(p['clockType'], 1)
        struct.pack_into('<I', self.raw, 64, 1)
        self.assertFalse(self.parse()['systemLoggerModePresent'])

    def test_foreign_identity_rejected(self):
        foreign=uuid.UUID('7948d849-b7d7-43fe-8972-c5bc65246153')
        self.raw[24:40] = foreign.bytes_le
        with self.assertRaisesRegex(module.SessionIdentityMismatch, 'GUID differs') as caught:
            self.parse()
        self.assertEqual(caught.exception.properties['sessionGuid'],str(foreign))
        self.assertIs(caught.exception.properties['sessionGuidMatchesExpected'],False)

    def test_foreign_name_rejected(self):
        self.raw[120:122] = 'X'.encode('utf-16-le')
        with self.assertRaisesRegex(ValueError, 'name differs'):
            self.parse()

    def test_offsets_overlap_and_missing_terminator_rejected(self):
        for offset in (0, 119, 121, len(self.raw), len(self.raw)+2):
            raw = copy.copy(self.raw)
            struct.pack_into('<I', raw, 116, offset)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.parse(raw)
        struct.pack_into('<I', self.raw, 112, 120)
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            self.parse()
        raw = module.request_buffer(self.name, self.guid)
        raw[120:120+module.STRING_BYTES] = b'A\0'*(module.STRING_BYTES//2)
        with self.assertRaisesRegex(ValueError, 'Unterminated'):
            self.parse(raw)

    def test_truncated_and_oversized_buffers_rejected(self):
        for raw in (bytes(119), bytes(module.BUFFER_BYTES+1)):
            with self.assertRaisesRegex(ValueError, 'extent'):
                self.parse(raw)
        for size in (0, 119, len(self.raw)+1):
            struct.pack_into('<I', self.raw, 0, size)
            with self.assertRaisesRegex(ValueError, 'buffer size'):
                self.parse()

    def test_global_and_malformed_source_identities_rejected(self):
        for name in ('NT Kernel Logger', 'SL3Image-../outside', self.name+' '):
            with self.assertRaises(ValueError):
                module.request_buffer(name, self.guid)
        for guid in ('00000000-0000-0000-0000-000000000000', '9e814aad-3204-11d2-9a82-006008a86939', 'bad'):
            with self.assertRaises(ValueError):
                module.request_buffer(self.name, guid)


@unittest.skipUnless(os.name=='nt','Native query boundary is simulated on Windows')
class QueryOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.name='SL3Image-'+'c'*32
        self.guid=uuid.UUID('7b9e532e-3e57-4c98-899d-27ae4bf3f495')
        self.raw=module.request_buffer(self.name,self.guid)
        struct.pack_into('<I',self.raw,64,0x02000001)
        struct.pack_into('<I',self.raw,40,1)
        self.calls=[]

    def call(self,status=0,cli=False):
        outer=self
        class Control:
            def __call__(self,handle,name,buffer,code):
                outer.calls.append((handle,name,code))
                module.C.memmove(buffer,bytes(outer.raw),len(outer.raw))
                return status
        api=SimpleNamespace(ControlTraceW=Control())
        with mock.patch.object(module.C,'WinDLL',return_value=api) as library:
            if cli:
                with tempfile.TemporaryDirectory(prefix='sl3-query-cli-') as directory:
                    output=Path(directory)/'result.json'
                    arguments=['inspect-image-source-session.py','--session-name',self.name,'--session-guid',str(self.guid),'--output',str(output)]
                    with mock.patch.object(module.sys,'argv',arguments),redirect_stdout(io.StringIO()):
                        code=module.main()
                    value=json.loads(output.read_text(encoding='utf-8'))
                    result=(code,value)
            else:
                result=module.query(self.name,self.guid)
            library.assert_called_once_with('advapi32.dll',winmode=0x800)
        self.assertEqual(self.calls,[(0,self.name,0)])
        return result

    def test_guid_rejection_is_saved_and_cli_stays_failed(self):
        foreign=uuid.UUID('e9b07e44-ff50-4e4e-a0f1-839391bbd1f9')
        self.raw[24:40]=foreign.bytes_le
        code,value=self.call(cli=True)
        self.assertEqual(code,1)
        self.assertIs(value['diagnosticAccepted'],False)
        self.assertIs(value['sourceActive'],True)
        self.assertEqual(value['properties']['sessionGuid'],str(foreign))
        self.assertEqual(value['properties']['maximumFileSizeMiB'],0)
        self.assertIn(str(self.guid),value['validationError'])
        self.assertIn(str(foreign),value['validationError'])
        self.assertFalse(value['sourceStarted'] or value['sourceStopped'] or value['readinessAdmission'])

    def test_access_error_retains_status_and_unknown_activity(self):
        code,value=self.call(status=5,cli=True)
        self.assertEqual(code,1)
        self.assertEqual(value['win32Status'],5)
        self.assertIsNone(value['sourceActive'])
        self.assertIsNone(value['properties'])
        self.assertFalse(value['diagnosticAccepted'])

    def test_malformed_properties_keep_native_success_separate_from_validation(self):
        struct.pack_into('<I',self.raw,0,119)
        value=self.call()
        self.assertEqual(value['win32Status'],0)
        self.assertTrue(value['sourceActive'])
        self.assertFalse(value['diagnosticAccepted'])
        self.assertIsNone(value['properties'])
        self.assertIn('buffer size',value['validationError'])

    def test_absence_is_accepted_without_claiming_identity_or_start(self):
        value=self.call(status=4201)
        self.assertTrue(value['diagnosticAccepted'])
        self.assertFalse(value['sourceActive'])
        self.assertIsNone(value['properties'])

    def test_valid_identity_preserves_observed_maximum_without_readiness(self):
        struct.pack_into('<I',self.raw,60,64)
        value=self.call()
        self.assertTrue(value['diagnosticAccepted'])
        self.assertEqual(value['properties']['maximumFileSizeMiB'],64)
        self.assertTrue(value['properties']['sessionGuidMatchesExpected'])
        self.assertFalse(value['readinessAdmission'])


if __name__ == '__main__':
    unittest.main()
