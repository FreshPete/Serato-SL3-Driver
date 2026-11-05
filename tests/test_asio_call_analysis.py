import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('analysis',ROOT/'scripts/analyse-asio-call-log.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

def marker():return {'schema':'sl3.asio-owned-session.v1','pid':42,'stopStatus':0,'eventsLost':0,'buffersLost':0,'complete':True,'hardwareStateAssessed':False}
def event(call,op,phase,tid=7,result=0):
    return {'schema':'sl3.asio-etw-record.v1','pid':42,'tid':tid,'timestampFileTime':'1000000',
            'payload':{'schema':'sl3.asio-call.v1','build':'production','phase':phase,'op':op,'object':0 if op==1 else 1,'call':call,
                       'result':result,'a0':0,'a1':0,'qpc':100,'frequency':1000,'elapsedQpc':0 if phase=='begin' else 20}}

class CallAnalysisTests(unittest.TestCase):
    def test_interleaved_threads_and_api_failure_are_valid_evidence(self):
        rows=[event(8,16,'begin',7),event(9,6,'begin',8),event(9,6,'end',8,-1000),event(8,16,'end',7)]
        r=a.analyze(rows,marker())
        self.assertEqual(r['completedCalls'],2);self.assertTrue(r['observedPairsComplete'])
        self.assertEqual(r['methods']['start']['returnedErrors'],1)
        self.assertEqual(r['pairs'][0]['beginRecord'],1)
        self.assertEqual(r['eventFileTimeRange'], {'first':'1000000','last':'1000000'})
        for key in ['actualEtwCaptureDecoded','sourceHostIdentityVerified','wholeHostSequenceVerified','seratoCaptureVerified','physicalAudioVerified','currentSeratoAdmissionVerified','twoDeckDvsVerified']:
            self.assertIs(r[key],False)

    def test_missing_abandoned_and_orphan_calls_are_incomplete(self):
        rows=[event(2,2,'begin'),event(2,2,'abandoned'),event(4,6,'end'),event(5,7,'begin')]
        r=a.analyze(rows,marker());self.assertFalse(r['observedPairsComplete'])
        self.assertEqual(r['abandonedCalls'],1);self.assertEqual(r['unterminatedBegins'],[5])
        self.assertEqual(r['orphanTerminals'][0]['call'],4);self.assertEqual(r['callIdGaps'],[3])

    def test_empty_and_budget_limited_logs_cannot_prove_whole_host(self):
        self.assertFalse(a.analyze([],marker())['observedPairsComplete'])
        rows=[event(4096,7,'begin'),event(4096,7,'end')];r=a.analyze(rows,marker())
        self.assertTrue(r['moduleCallBudgetReached']);self.assertFalse(r['wholeHostSequenceVerified'])

    def test_failed_stop_and_loss_are_preserved_not_hidden(self):
        for key in ['stopStatus','eventsLost','buffersLost']:
            m=marker();m[key]=1;m['complete']=False;r=a.analyze([event(1,1,'begin'),event(1,1,'end')],m)
            self.assertFalse(r['sessionMetadataComplete'])
        m=marker();m['eventsLost']=1
        with self.assertRaises(ValueError):a.analyze([],m)

    def test_duplicate_mixed_build_and_pair_mismatch_are_refused(self):
        original=[event(1,6,'begin'),event(1,6,'end')]
        mutations=[lambda r:r.append(copy.deepcopy(r[1])),lambda r:r.append(copy.deepcopy(r[0])),
                   lambda r:r[1]['payload'].__setitem__('build','session_fixture'),lambda r:r[1].__setitem__('tid',8),
                   lambda r:r[1]['payload'].__setitem__('a0',1),lambda r:r[1]['payload'].__setitem__('qpc',200)]
        for mutate in mutations:
            rows=copy.deepcopy(original);mutate(rows)
            with self.assertRaises(ValueError):a.analyze(rows,marker())

    def test_schema_types_bounds_and_wrong_pid_are_refused(self):
        mutations=[lambda r:r.__setitem__('pid',True),lambda r:r.__setitem__('pid',43),lambda r:r.__setitem__('extra',0),
                   lambda r:r['payload'].__setitem__('op',19),lambda r:r['payload'].__setitem__('call',4097),
                   lambda r:r['payload'].__setitem__('call',1.0),lambda r:r['payload'].__setitem__('frequency',True),
                   lambda r:r['payload'].__setitem__('result',2**63),lambda r:r['payload'].__setitem__('result',1)]
        for mutate in mutations:
            row=event(1,6,'begin');mutate(row)
            with self.assertRaises(ValueError):a.analyze([row],marker())
        with self.assertRaises(ValueError):a.analyze([event(1,1,'begin')]*8193,marker())

    def test_zero_clock_and_zero_elapsed_are_not_measured_timing(self):
        rows=[event(1,12,'begin'),event(1,12,'end')]
        for row in rows:row['payload']['qpc']=row['payload']['frequency']=row['payload']['elapsedQpc']=0
        r=a.analyze(rows,marker());self.assertTrue(r['observedPairsComplete']);self.assertFalse(r['pairs'][0]['hostTimingAvailable'])

    def test_result_domains_keep_version_and_void_separate_from_errors(self):
        rows=[]
        for call,op,result in [(1,1,-2147467259),(2,2,0),(3,4,-1),(4,5,0),(5,8,-1000)]:
            rows.extend([event(call,op,'begin'),event(call,op,'end',result=result)])
        r=a.analyze(rows,marker());self.assertEqual([p['returnedError'] for p in r['pairs']],[True,True,False,False,True])

    def test_marker_boolean_numbers_and_physical_claims_are_refused(self):
        for key,value in [('pid',True),('complete',1),('eventsLost',False),('hardwareStateAssessed',True),('extra',0)]:
            m=marker();m[key]=value
            with self.assertRaises(ValueError):a.analyze([],m)

if __name__=='__main__':unittest.main()
