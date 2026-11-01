"""Adversarial synthetic recording replay; no hardware or helper calls."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import os
import subprocess
from tests import rate_io_fixtures as f

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('rate_io_validation',ROOT/'scripts/validate-rate-io.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)

class RateIoEvidenceTests(unittest.TestCase):
    def validate(self,rows,summary=None,**options):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'rate-io.jsonl';path.write_text(f.text(rows),encoding='utf-8')
            return v.validate(path,summary,**options)

    def test_change_noop_mismatch_short_and_late_replay(self):
        for options in ({},{'target':48000},{'mismatch':True},{'short':True},{'late':True}):
            with self.subTest(options=options):
                result=self.validate(f.recording(**options),f.summary(**options),expected_pid=123)
                self.assertTrue(result['summaryMatched']);self.assertTrue(result['complete'])
                self.assertEqual(result['operationVerified'],not any(options.get(k) for k in ('mismatch','short','late')))
                self.assertNotIn('valid',result);self.assertFalse(result['rateRestorationVerified'])
        late=self.validate(f.recording(late=True),f.summary(late=True))['replayedObservation']
        self.assertEqual(late['readback_rate_hz'],0);self.assertTrue(late['acknowledgement_received'])

    def test_prefix_never_qualifies_summary(self):
        rows=f.recording()
        for length in range(1,len(rows)):
            with self.subTest(length=length):
                result=self.validate(rows[:length],allow_prefix=True);self.assertFalse(result['complete']);self.assertFalse(result['operationVerified'])
                self.assertIsNone(result['replayedObservation'])
                with self.assertRaises(ValueError):self.validate(rows[:length])
                with self.assertRaises(ValueError):self.validate(rows[:length],f.summary(),allow_prefix=True)

    def test_torn_suffix_duplicate_keys_and_row_limits(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'rate-io.jsonl';path.write_text(f.text(f.recording()[:2])+'{"event":',encoding='utf-8')
            result=v.validate(path,allow_prefix=True);self.assertFalse(result['complete']);self.assertGreater(result['tornSuffixBytes'],0)
            with self.assertRaises(ValueError):v.validate(path)
            path.write_text(f.text(f.recording()).replace('"pid":123','"pid":123,"pid":123'),encoding='utf-8')
            with self.assertRaises(ValueError):v.validate(path)
            path.write_bytes(b'x'*100000)
            with self.assertRaises(ValueError):v.validate(path,allow_prefix=True)

    def test_legacy_raw_v1_not_silently_replayed(self):
        rows=f.recording();rows[0]['schema']='sl3.rate-io.v1'
        with self.assertRaises(ValueError):self.validate(rows)

    def test_header_status_direction_and_sequence_types(self):
        rows=f.recording()
        for index,key,value in [(0,'pid',True),(0,'target_rate_hz',96000),(1,'sequence',True),(1,'timeout_ms',101),
            (2,'api_accepted',False),(2,'native_terminal',False),(2,'completion_error',995),(2,'adapter_timeout_ms',101),
            (3,'frame_hex','00'*64),(4,'bytes',63),(4,'output',True),(5,'sequence',0)]:
            bad=copy.deepcopy(rows);bad[index][key]=value
            with self.subTest(index=index,key=key),self.assertRaises(ValueError):self.validate(bad)
        with self.assertRaises(ValueError):self.validate(rows,expected_pid=124)

    def test_requests_acknowledgement_tags_and_notifications(self):
        rows=f.recording()
        for index,offset,value in [(1,0,0x31),(1,63,1),(5,5,0),(8,0,0x30),(4,1,0)]:
            bad=copy.deepcopy(rows);raw=bytearray.fromhex(bad[index]['frame_hex']);raw[offset]=value;bad[index]['frame_hex']=raw.hex()
            with self.subTest(index=index,offset=offset),self.assertRaises(ValueError):self.validate(bad)
        # Opaque acknowledgement payloads need not echo the selected rate.
        bad=copy.deepcopy(rows);raw=bytearray.fromhex(bad[8]['frame_hex']);raw[5:7]=b'\x12\x34';bad[8]['frame_hex']=raw.hex()
        self.assertTrue(self.validate(bad,f.summary())['operationVerified'])

    def test_acceptance_and_timeout_decisions_cannot_be_promoted(self):
        rows=f.recording(late=True);last=rows[-1]
        for key,value in [('decision','reply'),('runner_completed_ms',1027),('transferred',False),('output',True)]:
            bad=copy.deepcopy(rows);bad[-1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(bad)
        rows=f.recording();bad=copy.deepcopy(rows);bad[-1]['decision']='notification'
        with self.assertRaises(ValueError):self.validate(bad)

    @unittest.skipUnless(os.name=='nt','Windows writer fixture')
    def test_actual_cpp_writer_roundtrips_without_usb(self):
        executable=ROOT/'artifacts/build/native/Release/sl3_rate_selection_tests.exe'
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'rate-io.jsonl'
            result=subprocess.run([str(executable),'--emit-recording',str(path)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            summary=f.summary(target=44100,initial=44100);summary.update(read_attempts=4,control_transfer_attempts=5)
            checked=v.validate(path,summary);self.assertTrue(checked['operationVerified']);self.assertTrue(checked['summaryMatched'])
            self.assertEqual(checked['rawReturns'],5);self.assertEqual(checked['decisions'],5)
            saved=path.read_bytes();result=subprocess.run([str(executable),'--emit-recording',str(path)],capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertEqual(path.read_bytes(),saved)

    def test_pre_io_abort_is_not_verified_operation(self):
        for reason,budget in ((2,0),(3,3000)):
            rows=[f.recording()[0],{'event':'transaction','started_ms':1000,'budget_ms':budget,'finished_ms':1000,'diagnostic_error':reason}]
            result=self.validate(rows);self.assertTrue(result['complete']);self.assertFalse(result['operationVerified'])
            self.assertEqual(result['replayedObservation']['control_transfer_attempts'],0)

    def test_native_rejection_status_survives_failed_operation(self):
        rows=f.recording();end=rows[2];end.update(io_return_success=False,bytes=0,api_accepted=False,completion_error=31)
        decision=copy.deepcopy(rows[-6]);decision.update(transferred=False,bytes=0,decision='transfer_failure')
        transaction={'event':'transaction','started_ms':1000,'budget_ms':3000,'finished_ms':1003,'diagnostic_error':4}
        result=self.validate(rows[:3]+[transaction,decision]);self.assertFalse(result['operationVerified'])
        self.assertEqual(result['failedTransfers'][0]['completionError'],31)
        self.assertFalse(result['failedTransfers'][0]['apiAccepted'])

    def test_summary_field_types_counts_and_references(self):
        for key,value in [('target_rate_hz',48000),('verified_rate_hz',0),('readback_rate_hz',48000),('setter_attempts',True),
            ('acknowledgement_received',False),('control_transfer_attempts',7),('rate_io_schema','sl3.rate-io.v1'),('rate_io_file','../other')]:
            summary=f.summary();summary[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(f.recording(),summary)

if __name__=='__main__':unittest.main()
