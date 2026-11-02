"""Synthetic prefix/journal grammar and mutation checks; not a physical recording."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('input_record_evidence',ROOT/'scripts/validate-input-record-probe.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
HASH='a'*64


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='sl3-input-record-evidence-')
        self.folder=Path(temp.name).resolve()
        self.assertEqual(self.folder.parent,Path(tempfile.gettempdir()).resolve())
        self.assertTrue(self.folder.name.startswith('sl3-input-record-evidence-'))
        self.addCleanup(temp.cleanup);self.fixture(48000)

    def fixture(self,rate):
        frames=((rate*3+127)//128)*128;pcm=b'\x01\x02\x03'*(frames*6);(self.folder/'input.pcm').write_bytes(pcm)
        self.result={'schema':'sl3.input-record-probe.v1','simulated':True,'successful':True,'error':'','workerSha256':HASH,
                     'observedRateHz':rate,'expectedRateHz':rate,'nominalRequestedMilliseconds':3000,'bankFrames':128,'channels':6,'sampleBytes':3,'intervals':8,
                     'targetFrames':frames,'recordedFrames':frames,'recordedCallbacks':frames//128,'recorderFault':0,'startupFramesDiscarded':0,'hostFailure':0,
                     'pcmBytes':len(pcm),'workerInputFrames':frames+128,'outputSubmissions':300,'outputCompletions':299,'audioOutputPayload':'zero PCM only',
                     'totalCallbacks':frames//128+2,'trailingCallbacksNotRecorded':2,'counterFrequency':1000000,'collectionElapsedMilliseconds':5,
                     'pcmSha256':hashlib.sha256(pcm).hexdigest(),'startupJournalSha256':'','rows':[[n*128,n*1000,10000+n*1000,n%2] for n in range(frames//128)]}
        for name in ['workerStarted','ioRetired','deviceReleased','audioThreadRetired','workerExited','workerJobEmpty','buffersDisposed','streamStarted','pcmSaved']:self.result[name]=True
        for name in ['forcedTermination','timingProfileWritten','latencyMeasured','physicalMappingVerified','usbContinuityVerified','seratoAdmissionVerified']:self.result[name]=False
        self.save()

    def save(self): (self.folder/'result.json').write_text(json.dumps(self.result),encoding='utf-8')
    def check(self,simulated=True):return v.validate(self.folder,HASH,simulated)

    def test_both_rates_have_complete_prefix_and_no_physical_promotion(self):
        for rate,frames in [(44100,132352),(48000,144000)]:
            self.fixture(rate);result=self.check();self.assertEqual(result['frames'],frames);self.assertFalse(result['physicalProvenanceVerified']);self.assertFalse(result['latencyMeasured'])

    def test_geometry_counter_and_deadline_changes_refused(self):
        original=copy.deepcopy(self.result)
        for key,value in [('recordedFrames',True),('recordedCallbacks',1124),('targetFrames',0),('channels',2),('sampleBytes',4),('intervals',64),('hostFailure',1),('counterFrequency',0),('totalCallbacks',1),('startupFramesDiscarded',1),('collectionElapsedMilliseconds',6001),('outputCompletions',301),('expectedRateHz',44100)]:
            self.result=copy.deepcopy(original);self.result[key]=value;self.save()
            with self.subTest(key=key),self.assertRaises(ValueError):self.check()

    def test_failure_termination_and_unsupported_claims_refused(self):
        original=copy.deepcopy(self.result)
        for key in ['successful','workerJobEmpty','audioThreadRetired','buffersDisposed','pcmSaved','forcedTermination','timingProfileWritten','latencyMeasured','physicalMappingVerified','usbContinuityVerified','seratoAdmissionVerified']:
            self.result=copy.deepcopy(original);self.result[key]=not self.result[key];self.save()
            with self.subTest(key=key),self.assertRaises(ValueError):self.check()

    def test_callback_gaps_timestamps_and_repeated_bank_refused(self):
        original=copy.deepcopy(self.result)
        for column,value in [(0,129),(1,0),(2,0),(3,0)]:
            self.result=copy.deepcopy(original);self.result['rows'][1][column]=value;self.save()
            # A repeated publication timestamp is legitimate; use regression for its negative case.
            if column==1:self.result['rows'][0][1]=1;self.save()
            with self.subTest(column=column),self.assertRaises(ValueError):self.check()

    def test_pcm_tampering_partial_and_extra_bytes_refused(self):
        path=self.folder/'input.pcm';raw=path.read_bytes()
        for value in [raw[:-1],b'X'+raw[1:],raw+b'X',b'']:
            path.write_bytes(value)
            with self.subTest(length=len(value)),self.assertRaises(ValueError):self.check()

    def test_wrong_kind_worker_hash_and_strict_json_refused(self):
        with self.assertRaises(ValueError):self.check(False)
        with self.assertRaises(ValueError):v.validate(self.folder,'b'*64,True)
        path=self.folder/'result.json';raw=json.dumps(self.result)
        for value in ['{"schema":"duplicate",'+raw[1:],raw[:-1]+',"unknown":NaN}']:
            path.write_text(value)
            with self.assertRaises(ValueError):self.check()

    def native(self):
        stages=['worker.enter','helper_load.enter','helper_load.return','enumerate.enter','enumerate.return',
                'configuration.enter','configuration.return','redirect_owner_acquire.enter','redirect_owner_acquire.return','redirect_start.enter','redirect_start.return',
                'system_handle.enter','system_handle.return','clock_getter.enter','clock_getter.return','redirect_close.enter','redirect_close.return','helper_unload.enter','helper_unload.return']
        raw=''.join(f'{n+1}\t99\t{stage}\n' for n,stage in enumerate(stages)).encode();path=self.folder/'worker-1.tsv';path.write_bytes(raw)
        self.result['simulated']=False;self.result['startupJournalSha256']=hashlib.sha256(raw).hexdigest();self.save();return path,raw

    def test_synthetic_native_grammar_is_not_physical_attestation(self):
        self.native();result=self.check(False);self.assertEqual(result['nativeJournal']['workerPid'],99);self.assertFalse(result['physicalProvenanceVerified'])

    def test_native_missing_second_acquisition_setter_and_partial_journal_refused(self):
        path,raw=self.native()
        for value in [raw[:-1],raw.replace(b'clock_getter.return',b'rate_selection.return'),raw+raw,raw.replace(b'\t99\t',b'\t98\t',1)]:
            path.write_bytes(value);self.result['startupJournalSha256']=hashlib.sha256(value).hexdigest();self.save()
            with self.assertRaises(ValueError):self.check(False)
        path.unlink()
        with self.assertRaises(ValueError):self.check(False)

    def test_simulation_cannot_contain_native_journal(self):
        (self.folder/'worker-1.tsv').write_bytes(b'native fixture')
        with self.assertRaises(ValueError):self.check()


if __name__=='__main__':unittest.main()
