"""Exact window and image-lifetime rules; synthetic examples are not hardware proof."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('image_window',ROOT/'scripts/validate-controls-image-window.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class ImageWindowTests(unittest.TestCase):
    def setUp(self):
        self.expected={'kernelPath':r'\SystemRoot\System32\drivers\UsbHub3.sys','sizeOfImage':733184,
                       'timeDateStamp':180548141,'imageChecksum':781464,'diskSha256':'a'*64}
        self.rows=[dict(self.expected,operation=op,time=at) for op,at in
                   [('DCStart','2026-11-01T14:00:00Z'),('DCEnd','2026-11-01T14:01:00Z')]]
        self.report={'sourceReportsNoLoss':True,'headers':[{'EventsLost':0,'BuffersLost':0,
                     'StartTime':v.clock.filetime('2026-11-01T14:00:00Z'),
                     'EndTime':v.clock.filetime('2026-11-01T14:01:00Z')}],
                     'comparison':{'targetPresent':True,'matchingRundownMetadata':True,'expected':self.expected},
                     'kernelImages':[{'canonicalKernelPath':self.expected['kernelPath'].casefold(),
                                      'consistentRundownPair':True,'observations':self.rows}]}
        self.trace={'startedUtc':'2026-11-01T14:00:05Z','stoppedUtc':'2026-11-01T14:00:25Z','status':'window completed'}
        self.run={'probeStartedUtc':'2026-11-01T14:00:06Z','probeCompletedUtc':'2026-11-01T14:00:07Z'}

    def test_full_window_metadata_scope(self):
        result=v.qualify(self.report,self.trace,self.run)
        self.assertTrue(result['imageMetadataCoversUsbWindow']);self.assertEqual(result['postReleaseTicks'],'180000000')
        for key in ('readinessAdmission','physicalDeviceIdentityVerified','loadedMemoryIdentityVerified'):
            self.assertFalse(result[key])

    def test_scope_sixty_second_usb_window_needs_the_longer_image_window(self):
        self.trace['stoppedUtc']='2026-11-01T14:01:05Z'
        self.run['probeCompletedUtc']='2026-11-01T14:00:35Z'
        self.report['headers'][0]['EndTime']=v.clock.filetime('2026-11-01T14:02:00Z')
        self.rows[1]['time']='2026-11-01T14:02:00Z'
        result=v.qualify(self.report,self.trace,self.run)
        self.assertTrue(result['imageMetadataCoversUsbWindow'])
        self.assertEqual(result['postReleaseTicks'],'300000000')
        self.rows[1]['time']='2026-11-01T14:01:00Z'
        with self.assertRaisesRegex(ValueError,'encompass'):v.qualify(self.report,self.trace,self.run)

    def test_earlier_trace_and_only_partial_overlap_rejected(self):
        for key,at in [('startedUtc','2026-10-31T14:00:05Z'),('stoppedUtc','2026-11-01T14:01:00.0000001Z')]:
            trace=copy.deepcopy(self.trace);trace[key]=at
            with self.subTest(key=key),self.assertRaises(ValueError):v.qualify(self.report,trace,self.run)

    def test_exact_twelve_second_boundary(self):
        self.trace['stoppedUtc']='2026-11-01T14:00:19Z';v.qualify(self.report,self.trace,self.run)
        self.trace['stoppedUtc']='2026-11-01T14:00:18.9999999Z'
        with self.assertRaisesRegex(ValueError,'twelve-second'):v.qualify(self.report,self.trace,self.run)

    def test_probe_outside_trace_or_failed_trace_rejected(self):
        for key,value in [('probeStartedUtc','2026-11-01T14:00:04.9999999Z'),
                          ('probeCompletedUtc','2026-11-01T14:00:25.0000001Z')]:
            run=copy.deepcopy(self.run);run[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.qualify(self.report,self.trace,run)
        self.trace['status']='failed'
        with self.assertRaises(ValueError):v.qualify(self.report,self.trace,self.run)

    def test_loss_reload_mismatch_and_late_rundown_rejected(self):
        original=copy.deepcopy(self.report)
        for mutation in ('loss','header','duplicate','reload','checksum','late_start','early_end','missing','wrong_target'):
            report=copy.deepcopy(original);target=report['kernelImages'][0]
            if mutation=='loss':report['sourceReportsNoLoss']=False
            if mutation=='header':report['headers'][0]['EventsLost']=1
            if mutation=='duplicate':report['headers']*=2
            if mutation=='reload':target['observations'][0]['operation']='Load'
            if mutation=='checksum':target['observations'][1]['imageChecksum']+=1
            if mutation=='late_start':target['observations'][0]['time']='2026-11-01T14:00:05.0000001Z'
            if mutation=='early_end':target['observations'][1]['time']='2026-11-01T14:00:24.9999999Z'
            if mutation=='missing':report['kernelImages']=[]
            if mutation=='wrong_target':report['comparison']['expected']['kernelPath']=r'\SystemRoot\other.sys'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):v.qualify(report,self.trace,self.run)

    def test_real_saved_logging_cannot_qualify_previous_controls_capture(self):
        report=ROOT/'analysis/native-guid-rundown-20261101-job1/rundown.json'
        context=ROOT/'tests/results/local/user-controls-attended-20261031-120514'
        if not report.exists() or not context.exists():self.skipTest('Local archived evidence unavailable')
        read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
        with self.assertRaisesRegex(ValueError,'does not encompass'):
            v.qualify(read(report),read(context/'trace/capture.json'),read(context/'run.json'))


if __name__=='__main__':unittest.main()
