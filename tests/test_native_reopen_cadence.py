"""Interpretation boundaries only; synthetic journals, no native program or USB."""
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

API=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/summarize-native-reopen-cadence.py'))
def identities(runs):return [dict(r,bundleSha256='1'*64,nativeBuildSha256='2'*64) for r in runs]

class CadenceTests(unittest.TestCase):
    def test_completed_and_stalled_boundaries(self):
        completed=API['timeline'](b'10\t42\tredirect_start.enter\n12\t42\tredirect_start.return\n15\t42\tredirect_close.return\n')
        stalled=API['timeline'](b'20\t43\thelper_load.return\n21\t43\tredirect_start.enter\n')
        self.assertEqual(completed['redirectCloseReturnMs'],15)
        self.assertIsNone(stalled['redirectStartReturnMs'])
        self.assertIsNone(stalled['redirectCloseReturnMs'])

    def test_malformed_or_ambiguous_journals_refused(self):
        cases=[b'10\t42\tother\n',b'10\t42\tredirect_start.enter\n11\t42\tredirect_start.enter\n',
               b'10\t42\tredirect_start.enter\n9\t42\tother\n',b'10\t42\tredirect_start.enter\n11\t43\tother\n',
               b'10\t42\tredirect_start.enter\n11\t42\tredirect_close.return\n',b'10\t0\tredirect_start.enter\n']
        for raw in cases:
            with self.subTest(raw=raw),self.assertRaises(ValueError):API['timeline'](raw)

    def test_gaps_require_explicit_same_boot_and_do_not_imply_cause(self):
        runs=[{'timeline':{'redirectStartEnterMs':1,'redirectCloseReturnMs':5},'successful':True},
              {'timeline':{'redirectStartEnterMs':22,'redirectCloseReturnMs':25},'successful':True},
              {'timeline':{'redirectStartEnterMs':34,'redirectCloseReturnMs':None},'successful':False}]
        runs=identities(runs);result=API['summarize'](runs,True)
        self.assertEqual([r['gapFromPreviousRedirectCloseMs'] for r in result['runs']],[None,17,9])
        self.assertFalse(result['streamingCauseIsolated']);self.assertFalse(result['readinessDelayEstablished'])
        self.assertFalse(result['bootIdentityIndependentlyVerified'])
        self.assertTrue(all(r['gapFromPreviousRedirectCloseMs'] is None for r in API['summarize'](runs,False)['runs']))

    def test_overlapping_or_reordered_runs_refused(self):
        for second in (0,4):
            with self.assertRaises(ValueError):
                API['summarize'](identities([{'timeline':{'redirectStartEnterMs':1,'redirectCloseReturnMs':5}},
                                  {'timeline':{'redirectStartEnterMs':second,'redirectCloseReturnMs':None}}]),True)

    def test_mixed_native_builds_refused(self):
        runs=identities([{},{}]);runs[1]['bundleSha256']='3'*64
        with self.assertRaises(ValueError):API['summarize'](runs,True)

    def test_changed_completed_result_or_journal_refused(self):
        with tempfile.TemporaryDirectory(prefix='sl3-cadence-') as temp:
            root=Path(temp);journal=root/'worker-startup.tsv';journal.write_bytes(b'10\t42\tredirect_start.enter\n')
            record={'schema':'sl3.native-activation-control-run.v1','successful':False,'audioStarted':False,
                    'bundleSha256':'1'*64,'nativeBuildSha256':'2'*64,
                    'nativeJournalSha256':{str(journal):hashlib.sha256(journal.read_bytes()).hexdigest()}}
            path=root/'result.json';path.write_text(json.dumps(record),encoding='utf-8');sha=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertFalse(API['completed'](path,sha)['successful'])
            with self.assertRaises(ValueError):API['completed'](path,'0'*64)
            journal.write_bytes(b'11\t42\tredirect_start.enter\n')
            with self.assertRaises(ValueError):API['completed'](path,sha)

if __name__=='__main__':unittest.main()
