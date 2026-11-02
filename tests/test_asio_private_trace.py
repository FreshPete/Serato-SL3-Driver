"""Synthetic record checks stay distinct from actual private ETW capture provenance."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('private_trace',ROOT/'scripts/validate-asio-private-trace.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


def fixture():
    summary={'schema':'sl3.asio-private-capture.v1','pid':42,'decodedEvents':16,'eventsLost':0,'buffersLost':0,
             'sessionStopped':True,'dllUnloaded':True,'ordinaryToken':True,'unavailableProductionDll':True,'deviceAccess':False,'seratoExecuted':False}
    rows=[]
    for n,(op,result) in enumerate(v.EXPECTED):
        for phase in ['begin','end']:
            p={'schema':'sl3.asio-call.v1','build':'production','phase':phase,'op':op,'object':0 if n==0 else 1,
               'call':n+1,'result':0 if phase=='begin' else result,'a0':0,'a1':0,'qpc':100+n*100,
               'frequency':10000000,'elapsedQpc':0 if phase=='begin' else 20}
            rows.append({'schema':'sl3.asio-etw-record.v1','pid':42,'tid':19,'timestampFileTime':str(1000+len(rows)),'payload':p})
    return rows,summary


class TraceValidationTests(unittest.TestCase):
    def test_owned_marker_requires_exact_retirement_and_loss_fields(self):
        marker={'schema':'sl3.asio-owned-session.v1','pid':42,'stopStatus':0,'eventsLost':0,'buffersLost':0,
                'complete':True,'hardwareStateAssessed':False}
        v.validate_owned_marker(marker,42)
        for key,value in [('pid',True),('pid',43),('stopStatus',5),('stopStatus',False),('eventsLost',1),
                          ('buffersLost',1),('complete',False),('hardwareStateAssessed',True),('schema','other')]:
            bad=dict(marker);bad[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):v.validate_owned_marker(bad,42)
        bad=dict(marker);bad['extra']=0
        with self.assertRaises(ValueError):v.validate_owned_marker(bad,42)

    def test_consistent_model_cannot_become_actual_capture(self):
        rows,summary=fixture();r=v.validate_rows(rows,summary,42)
        self.assertTrue(r['recordsConsistent']);self.assertEqual(r['completePairs'],8)
        for k in ['actualEtwCaptureDecoded','seratoCaptureVerified','physicalAudioVerified','currentSeratoAdmissionVerified','twoDeckDvsVerified']:
            self.assertIs(r[k],False)

    def test_loss_elevation_scope_and_incomplete_retirement_refused(self):
        for key,value in [('eventsLost',1),('buffersLost',1),('ordinaryToken',False),('sessionStopped',False),('dllUnloaded',False),
                          ('unavailableProductionDll',False),('deviceAccess',True),('seratoExecuted',True),('decodedEvents',15)]:
            rows,s=fixture();s[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.validate_rows(rows,s,42)

    def test_missing_duplicate_wrong_result_and_abandoned_events_refused(self):
        for mutate in [lambda r:r.pop(),lambda r:r.__setitem__(1,copy.deepcopy(r[0])),
                       lambda r:r[7]['payload'].__setitem__('result',1),lambda r:r[1]['payload'].__setitem__('phase','abandoned')]:
            rows,s=fixture();mutate(rows)
            with self.assertRaises(ValueError):v.validate_rows(rows,s,42)

    def test_identity_build_and_operation_drift_refused(self):
        for path,key,value in [('envelope','pid',43),('envelope','tid',20),('payload','build','session_fixture'),
                               ('payload','object',2),('payload','call',9),('payload','op',18),('payload','a0',1)]:
            rows,s=fixture();target=rows[5] if path=='envelope' else rows[5]['payload'];target[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.validate_rows(rows,s,42)

    def test_boolean_numbers_nonfinite_duplicates_and_extra_fields_refused(self):
        for key in ['pid','tid']:
            rows,s=fixture();rows[0][key]=True
            with self.assertRaises(ValueError):v.validate_rows(rows,s,42)
        for key in ['result','qpc','frequency','call','op']:
            rows,s=fixture();rows[1]['payload'][key]=False
            with self.assertRaises(ValueError):v.validate_rows(rows,s,42)
        for raw in [b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b'[]']:
            with self.assertRaises(ValueError):v.parse(raw)
        rows,s=fixture();rows[0]['payload']['unproved']=True
        with self.assertRaises(ValueError):v.validate_rows(rows,s,42)

    def test_pair_clock_and_event_time_corruption_refused(self):
        for mutate in [lambda r:r[1]['payload'].__setitem__('qpc',101),lambda r:r[1]['payload'].__setitem__('frequency',0),
                       lambda r:r[2].__setitem__('timestampFileTime','1'),lambda r:r[1]['payload'].__setitem__('elapsedQpc',-1)]:
            rows,s=fixture();mutate(rows)
            with self.assertRaises(ValueError):v.validate_rows(rows,s,42)


if __name__=='__main__':unittest.main()
