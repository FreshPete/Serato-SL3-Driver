"""Synthetic phase comparisons; differences never grant hardware readiness."""
import copy
from datetime import datetime,timedelta,timezone
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('port_phases',ROOT/'scripts/analyse-hub-port-phases.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


def stamp(second):return (datetime(2026,11,1,14,0,tzinfo=timezone.utc)+timedelta(seconds=second)).isoformat()


class PhaseTests(unittest.TestCase):
    def setUp(self):
        self.samples=[]
        for second in (1,1.25,1.5,1.75,12,12.25,12.5,12.75):self.add(second)

    def add(self,second,duration=.01):
        self.samples.append({'record':'sample','sequence':len(self.samples)+1,'entryUtc':stamp(second),
            'completedUtc':stamp(second+duration),'devnode':{'complete':True,'present':True,'problemCode':39},
            'query':{'queryStartedUtc':stamp(second),'queryFinishedUtc':stamp(second+duration),
                     'completedUtc':stamp(second+duration),'successful':True,'error':None,'handleClosed':True,
                     'readinessAdmission':False,'queryElapsedNanoseconds':'100',
                     'connection':{'connectionStatus':1,'currentConfiguration':0,'readinessAdmission':False}}})

    def compare(self):return v.compare(self.samples,*[v.clock(stamp(n)) for n in (1,11,11.1,0,18)])

    def test_identical_complete_snapshots_disprove_stateless_distinction(self):
        result=self.compare()
        self.assertTrue(result['ambiguousCompleteFingerprintObserved']);self.assertEqual(result['commonCompleteFingerprints'],1)
        self.assertEqual(result['candidateDisjointFields'],[]);self.assertEqual(result['phaseSamples'],{'pending':4,'stopped':4})
        self.assertFalse(result['readinessAdmission']);self.assertFalse(result['statelessReadinessFromTheseFieldsSupported'])

    def test_query_host_duration_is_not_a_readiness_feature(self):
        for sample in self.samples[4:]:sample['query']['queryElapsedNanoseconds']='999999'
        self.assertTrue(self.compare()['ambiguousCompleteFingerprintObserved'])

    def test_disjoint_field_only_marks_candidate(self):
        for sample in self.samples[4:]:sample['devnode']['problemCode']=0
        result=self.compare();self.assertEqual(result['candidateDisjointFields'],['devnode.problemCode'])
        self.assertFalse(result['readinessAdmission']);self.assertFalse(result['successiveAcquisitionVerified'])
        self.assertEqual(result['valuesByPhase']['stopped']['devnode.problemCode'],[0])

    def test_query_crossing_phase_boundary_is_excluded(self):
        self.add(10.999,duration=.002)
        self.samples.sort(key=lambda s:v.clock(s['entryUtc']))
        for n,sample in enumerate(self.samples,1):sample['sequence']=n
        result=self.compare();self.assertEqual(result['excludedBoundaryOrOtherPhaseSamples'],1)
        self.assertEqual(result['phaseSamples']['pending'],4)

    def test_insufficient_phase_coverage_refused(self):
        self.samples.pop()
        with self.assertRaisesRegex(ValueError,'Insufficient'):self.compare()

    def test_enumeration_gap_does_not_count_toward_phase_coverage(self):
        self.add(13)
        sample=self.samples[-1]
        sample['devnode']=None
        raw=bytes(31)+b'\x09'+bytes(355)
        sample['query'].update(successful=False,error='Hub response connection index differs',
                               queryWin32Error=0,bytesReturned=35,responseEvidence=v.port_query.response_evidence(raw,35))
        del sample['query']['connection']
        result=self.compare()
        self.assertEqual(result['excludedEnumerationGaps'],1)
        self.assertEqual(result['phaseSamples']['stopped'],4)
        sample['query']['handleClosed']=False
        with self.assertRaisesRegex(ValueError,'Incomplete'):self.compare()

    def test_partial_snapshot_or_changed_field_inventory_refused(self):
        original=copy.deepcopy(self.samples)
        for fault in ('close','node','inventory','sequence','overlap','clock'):
            self.samples=copy.deepcopy(original);sample=self.samples[1]
            if fault=='close':sample['query']['handleClosed']=False
            if fault=='node':sample['devnode']['complete']=False
            if fault=='inventory':sample['devnode']['extra']=1
            if fault=='sequence':sample['sequence']=1
            if fault=='overlap':sample['entryUtc']=self.samples[0]['entryUtc']
            if fault=='clock':sample['query']['queryFinishedUtc']=stamp(99)
            with self.subTest(fault=fault),self.assertRaises(ValueError):self.compare()


if __name__=='__main__':unittest.main()
