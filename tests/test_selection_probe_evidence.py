import copy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('selection_probe_validation',ROOT/'scripts/validate-selection-host-probe.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
TARGET={'setting':'through','group':0,'value':1};SHA='a'*64


def wire():
    initial=bytes(22);observed=bytearray(22);observed[8]=1
    return (struct.pack('<16I',0x53334c53,1,1,0,1,0,0,0,6,3,3,1,31,0,0,1168)+initial+observed+observed+b'\xe7\xa1').hex()


def owner(released=False,empty=False):
    zero=('host_failure active_callbacks callbacks_started callbacks_completed worker_failure stream_fault native_error '
          'audio_input_submissions audio_input_frames audio_input_blocks audio_owner_input_frames published_output_frames '
          'audio_output_submissions audio_output_completions audio_output_frames_submitted pending_mask retained_mask').split()
    r={k:0 for k in zero};r.update(rate_hz=0 if empty else 44100,running=False,io_retired=True,
       device_released=released or empty,device_held=not released and not empty,audio_thread_retired=True,
       process_started=not empty,worker_exited=released and not empty,private_job_empty=released and not empty,
       forced_termination=False,worker_phase=0 if empty else 6 if released else 1)
    return r


def records():
    r={'schema':'sl3.selection-host-probe.v2','phase':'finished','simulated':True,'worker_sha256':SHA,'device_protocol_version':3,
       'target':copy.deepcopy(TARGET),'successful':True,'finished':True,'acquisition_attempts':1,'acquisition_verified':True,
       'baseline_query_attempts':1,'selection_attempts':1,'publication_pending':False,'command_attempted':True,'outcome_unknown':False,
       'device_may_have_changed':True,'operation_verified':True,'baseline_received_frames':1,'baseline_raw_controls':[0]*22,
       'outcome_wire_hex':wire(),'reviewed_baseline_raw_controls':None,'audio_start_attempts':0,'audio_buffers_created':False,'alternate_changes_requested':0,'rate_changes':0,
       'firmware_requests':0,'calibration_verified':False,'analogue_signal_verified':False,'asio_com_registered':False,'error':''}
    for name in ('acquisition','after_baseline','after_selection','final'):r[name]=owner(name=='final')
    r['after_selection']['native_error']=r['final']['native_error']=1168
    request=copy.deepcopy(r);request.update(phase='preparing',successful=False,finished=False,acquisition_attempts=0,acquisition_verified=False,
        baseline_query_attempts=0,selection_attempts=0,command_attempted=False,outcome_unknown=False,device_may_have_changed=False,
        operation_verified=False,baseline_received_frames=None,baseline_raw_controls=None,outcome_wire_hex=None)
    for name in ('acquisition','after_baseline','after_selection','final'):request[name]=owner(empty=True)
    return r,request


class SelectionEvidenceTests(unittest.TestCase):
    def validate(self,result,request):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            for name,value in (('probe.json',result),('request.json',request)):(folder/name).write_text(json.dumps(value),encoding='utf-8')
            return v.probe(folder,SHA,True)

    def test_actual_wire_layout_and_complete_record(self):
        decoded=v.decode_wire(wire(),TARGET);self.assertEqual(decoded['nativeError'],1168);self.assertEqual(decoded['verified'][8],1)
        r,q=records();self.assertTrue(self.validate(r,q)['valid'])
        r['reviewed_baseline_raw_controls']=q['reviewed_baseline_raw_controls']=[0]*22
        self.assertTrue(self.validate(r,q)['valid'])

    def test_wire_target_enum_reserved_and_optional_mutations(self):
        raw=bytes.fromhex(wire())
        for word,value in ((0,0),(1,2),(2,0),(3,1),(4,0),(5,2),(6,4),(7,1),(8,7),(9,4),(10,13),(11,0),(12,63),(13,1),(14,1)):
            bad=bytearray(raw);struct.pack_into('<I',bad,word*4,value)
            with self.subTest(word=word),self.assertRaises(ValueError):v.decode_wire(bad.hex(),TARGET)
        for text in ('',raw.hex()[:-2],raw.hex()+'00',raw.hex().upper()):
            with self.assertRaises(ValueError):v.decode_wire(text,TARGET)

    def test_missing_reply_uncertainty_and_failed_cleanup_never_pass(self):
        r,q=records()
        for patch in ({'outcome_wire_hex':None,'outcome_unknown':True},{'publication_pending':True,'command_attempted':None},
                      {'device_may_have_changed':False},{'operation_verified':False},{'successful':False},{'finished':False}):
            bad=copy.deepcopy(r);bad.update(patch)
            with self.assertRaises((ValueError,TypeError)):self.validate(bad,q)
        for key,value in (('device_released',False),('forced_termination',True),('private_job_empty',False),('io_retired',False),('audio_input_frames',1)):
            bad=copy.deepcopy(r);bad['final'][key]=value
            with self.assertRaises(ValueError):self.validate(bad,q)
        bad=copy.deepcopy(r);bad['after_selection']=None
        with self.assertRaises(ValueError):self.validate(bad,q)

    def test_request_precedes_activity_and_matches_baseline_target(self):
        r,q=records()
        mutations=[('target',{'setting':'through','group':0,'value':0}),('worker_sha256','b'*64),('command_attempted',True),('baseline_raw_controls',[0]*22)]
        for key,value in mutations:
            bad=copy.deepcopy(q);bad[key]=value
            with self.assertRaises(ValueError):self.validate(r,bad)
        bad=copy.deepcopy(q);bad['acquisition']['process_started']=True
        with self.assertRaises(ValueError):self.validate(r,bad)
        for key in ('process_started','io_retired'):
            bad=copy.deepcopy(q);bad['acquisition'][key]=0
            with self.assertRaises(ValueError):self.validate(r,bad)
        bad=copy.deepcopy(r);bad['baseline_raw_controls'][21]=1
        with self.assertRaises(ValueError):self.validate(bad,q)
        for key in ('acquisition_attempts','selection_attempts','device_protocol_version'):
            bad=copy.deepcopy(r);bad[key]=True
            with self.assertRaises(ValueError):self.validate(bad,q)
        for reviewed in ([0]*21,[0]*21+[256],[0]*21+[True],'00'*22,[1]*22,[0]*21+[1]):
            bad,initial=copy.deepcopy(r),copy.deepcopy(q)
            bad['reviewed_baseline_raw_controls']=initial['reviewed_baseline_raw_controls']=reviewed
            with self.assertRaises(ValueError):self.validate(bad,initial)
        bad=copy.deepcopy(q);bad['reviewed_baseline_raw_controls']=[0]*22
        with self.assertRaises(ValueError):self.validate(r,bad)
        for schema in ('sl3.selection-host-probe.v1','sl3.selection-host-probe.v3'):
            bad,initial=copy.deepcopy(r),copy.deepcopy(q);bad['schema']=initial['schema']=schema
            with self.assertRaises(ValueError):self.validate(bad,initial)
        bad,initial=copy.deepcopy(r),copy.deepcopy(q);bad['simulated']=initial['simulated']=False
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            for name,value in (('probe.json',bad),('request.json',initial)):(folder/name).write_text(json.dumps(value),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'exact reviewed baseline'):v.probe(folder,SHA,False)

    def test_partial_failure_wire_preserves_observation_and_uncertainty(self):
        raw=bytearray(bytes.fromhex(wire()));struct.pack_into('<4I',raw,5*4,5,4,0,7)
        struct.pack_into('<4I',raw,9*4,2,1,1,7);raw[86:130]=bytes(44);raw[130:]=bytes(2)
        decoded=v.decode_wire(raw.hex(),TARGET)
        self.assertTrue(decoded['deviceMayHaveChanged']);self.assertEqual(decoded['initial'],[0]*22);self.assertIsNone(decoded['verified'])
        raw[108]=1
        with self.assertRaises(ValueError):v.decode_wire(raw.hex(),TARGET)

    def test_native_journal_target_order_counts_and_single_close(self):
        stages=['worker.enter','control_target_through.enter','control_group_zero.enter','control_value_one.enter','helper_load.enter','helper_load.return',
                'enumerate.enter','enumerate.return','configuration.enter','configuration.return','redirect_start.enter','redirect_start.return',
                'system_handle.enter','system_handle.return','clock_getter.enter','clock_getter.return','audio_controls.enter',
                'audio_controls_write.enter','audio_controls_write.return','audio_controls_read.enter','audio_controls_read.return','audio_controls.return',
                'audio_control_selection.enter']
        for stem in ('audio_controls_write','audio_control_selection_set','audio_controls_write'):
            stages += [stem+'.enter',stem+'.return','audio_controls_read.enter','audio_controls_read.return']
        stages += ['audio_control_selection_possible_write.return','audio_control_selection_verified.return','audio_control_selection.return',
                   'redirect_close.enter','redirect_close.return','helper_unload.enter','helper_unload.return']
        outcome=v.decode_wire(wire(),TARGET)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'worker-1.tsv'
            def save(values):path.write_text(''.join(f'{n+100}\t42\t{value}\n' for n,value in enumerate(values)),encoding='ascii')
            save(stages);self.assertEqual(v.journal(path,TARGET,1,outcome)['setters'],1)
            for values in (stages[:-1],stages+['redirect_close.enter'],stages[:2]+['control_group_one.enter']+stages[3:],stages[:23]+stages[27:]):
                save(values)
                with self.assertRaises(ValueError):v.journal(path,TARGET,1,outcome)


if __name__=='__main__':unittest.main()
