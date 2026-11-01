"""Synthetic rate probe/journal/native records; no USB or helper operations."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from tests.test_selection_probe_evidence import owner
from tests import rate_io_fixtures as io_fixtures

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('rate_probe_evidence_validator',ROOT/'scripts/validate-rate-host-probe.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
SHA='a'*64

def wire(target=44100,initial=48000,error=0):
    changed=target!=initial
    return struct.pack('<16I',0x52334c53,1,target,error,3 if error else 0,0,initial,0 if error else target,
        initial if error else target if changed else 0,3 if changed else 1,3 if changed else 1,int(changed),3 if changed else 0,0,0,0).hex()

def records(target=44100):
    r={'schema':'sl3.rate-host-probe.v1','phase':'finished','simulated':True,'worker_sha256':SHA,'device_protocol_version':3,
        'target_rate_hz':target,'expected_initial_rate_hz':48000,'successful':True,'finished':True,'acquisition_attempts':1,
        'acquisition_verified':True,'selection_attempts':1,'publication_pending':False,'command_attempted':True,'outcome_unknown':False,
        'device_may_have_changed':target!=48000,'rejected_before_operation':False,'operation_verified':True,'outcome_wire_hex':wire(target),
        'audio_start_attempts':0,'audio_buffers_created':False,'alternate_changes_requested':0,'control_setters':0,'automatic_rollback':False,
        'firmware_requests':0,'calibration_verified':False,'analogue_signal_verified':False,'asio_com_registered':False,'error':''}
    for name in ('acquisition','after_selection','final'):
        r[name]=owner(name=='final');r[name]['rate_hz']=48000 if name=='acquisition' else target
    q=copy.deepcopy(r);q.update(phase='preparing',successful=False,finished=False,acquisition_attempts=0,acquisition_verified=False,
        selection_attempts=0,command_attempted=False,device_may_have_changed=False,operation_verified=False,outcome_wire_hex=None)
    for name in ('acquisition','after_selection','final'):q[name]=owner(empty=True)
    return r,q

def stages():
    return ['worker.enter','helper_load.enter','helper_load.return','enumerate.enter','enumerate.return',
        'configuration.enter','configuration.return','redirect_owner_acquire.enter','redirect_owner_acquire.return',
        'redirect_start.enter','redirect_start.return','system_handle.enter','system_handle.return','clock_getter.enter','clock_getter.return',
        'rate_target_44100.enter','rate_selection.enter','rate_selection.return','redirect_close.enter','redirect_close.return',
        'helper_unload.enter','helper_unload.return']

class RateProbeEvidenceTests(unittest.TestCase):
    def validate(self,r,q,native=None,markers=None,recording=True):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            for name,value in (('probe.json',r),('request.json',q)):(folder/name).write_text(json.dumps(value),encoding='utf-8')
            if native is not None:
                path=folder/'worker-1.tsv.rate';path.mkdir();(path/'rate.json').write_text(json.dumps(native),encoding='utf-8')
                if recording:(path/'rate-io.jsonl').write_text(io_fixtures.text(io_fixtures.recording()),encoding='utf-8')
                (folder/'worker-1.tsv').write_text(''.join(f'{n}\t123\t{s}\n' for n,s in enumerate(markers or stages())),encoding='ascii')
            return v.probe(folder,SHA,native is None)

    def native(self):
        o=v.decode_wire(wire(),44100)['observation']
        return dict(o,schema='sl3.rate-diagnostic.v2',phase='finished',utc='2026-11-01T21:00:00Z',last_io_retired=True,
            redirect_closed=False,audio_submissions=0,alternate_changes=0,automatic_rollback=False,error='',rate_io_schema='sl3.rate-io.v2',rate_io_file='rate-io.jsonl')

    def test_change_noop_and_decoder_envelope_not_evidence(self):
        for target in (44100,48000):
            r,q=records(target);result=self.validate(r,q);o=result['outcome']['observation']
            self.assertTrue(result['valid']);self.assertEqual(o['setter_attempts'],int(target!=48000))
            self.assertFalse(result['rateRestorationVerified'])
            self.assertTrue({'utc','redirect_closed','last_io_retired','schema','phase'}.isdisjoint(o))

    def test_wire_bounds_target_reserved_and_order(self):
        for word in range(16):
            if word==13:continue
            bad=bytearray.fromhex(wire());struct.pack_into('<I',bad,word*4,0xffffffff)
            with self.subTest(word=word),self.assertRaises(ValueError):v.decode_wire(bad.hex(),44100)
        for text in ('',wire()[:-2],wire()+'00',wire().upper()):
            with self.assertRaises(ValueError):v.decode_wire(text,44100)
        with self.assertRaises(ValueError):v.decode_wire(wire(),48000)

    def test_failed_readback_is_preserved_but_not_probe_success(self):
        failed=wire(error=5);o=v.decode_wire(failed,44100)['observation']
        self.assertEqual(o['readback_rate_hz'],48000);self.assertEqual(o['verified_rate_hz'],0)
        r,q=records();r['outcome_wire_hex']=failed
        with self.assertRaises(ValueError):self.validate(r,q)

    def test_request_guard_and_pending_uncertainty(self):
        r,q=records()
        for key,value in [('target_rate_hz',48000),('expected_initial_rate_hz',44100),('acquisition_attempts',True),
                          ('selection_attempts',1),('command_attempted',True),('publication_pending',True),('outcome_wire_hex',wire())]:
            bad=copy.deepcopy(q);bad[key]=value
            with self.subTest(key=key),self.assertRaises((ValueError,TypeError)):self.validate(r,bad)
        for key,value in [('successful',False),('finished',False),('command_attempted',None),('outcome_unknown',True),
                          ('publication_pending',True),('device_may_have_changed',False),('rejected_before_operation',True),('control_setters',1)]:
            bad=copy.deepcopy(r);bad[key]=value
            with self.subTest(key=key),self.assertRaises((ValueError,TypeError)):self.validate(bad,q)

    def test_owner_clock_audio_and_retirement(self):
        r,q=records()
        for stage,key,value in [('acquisition','rate_hz',44100),('after_selection','rate_hz',48000),('after_selection','native_error',1),
                                ('after_selection','audio_input_frames',1),('after_selection','callbacks_started',1),
                                ('final','rate_hz',48000),('final','device_released',False),('final','io_retired',False),
                                ('final','worker_exited',False),('final','forced_termination',True)]:
            bad=copy.deepcopy(r);bad[stage][key]=value
            with self.subTest(stage=stage,key=key),self.assertRaises(ValueError):self.validate(bad,q)

    def test_synthetic_native_correlation_keeps_cleanup_separate(self):
        r,q=records();r['simulated']=q['simulated']=False;native=self.native()
        result=self.validate(r,q,native)
        self.assertTrue(result['valid']);self.assertFalse(result['nativeJournal']['individualRateTransfersJournalled'])
        for key,value in [('redirect_closed',True),('last_io_retired',False),('target_rate_hz',48000),('initial_rate_hz',44100),
                          ('setter_attempts',0),('readback_rate_hz',48000),('audio_submissions',1),('error','unexpected')]:
            bad=copy.deepcopy(native);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(r,q,bad)
        r['expected_initial_rate_hz']=q['expected_initial_rate_hz']=None
        with self.assertRaises(ValueError):self.validate(r,q,native)

    def test_current_native_gate_requires_replayable_recording_and_pid(self):
        r,q=records();r['simulated']=q['simulated']=False;native=self.native()
        for key in ('rate_io_schema','rate_io_file'):
            bad=copy.deepcopy(native);bad.pop(key)
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(r,q,bad)
        with self.assertRaises(OSError):self.validate(r,q,native,recording=False)
        rows=io_fixtures.recording();rows[0]['pid']=124
        with patch.object(io_fixtures,'recording',return_value=rows),self.assertRaises(ValueError):self.validate(r,q,native)
        rows=io_fixtures.recording()[:-1]
        with patch.object(io_fixtures,'recording',return_value=rows),self.assertRaises(ValueError):self.validate(r,q,native)

    def test_synthetic_native_journal_rejects_extra_or_wrong_operations(self):
        r,q=records();r['simulated']=q['simulated']=False
        for changed in (stages()+['redirect_start.enter'],[s for s in stages() if s!='rate_selection.return'],
                        [s.replace('rate_target_44100','rate_target_48000') for s in stages()],
                        [s.replace('rate_selection','audio_controls') for s in stages()]):
            with self.assertRaises(ValueError):self.validate(r,q,self.native(),changed)

if __name__=='__main__':unittest.main()
