import json
from pathlib import Path, PureWindowsPath
import runpy
import tempfile
import unittest


API = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/read-installed-asio-start.py'))
ACTIVATION = ['controller.exe','1'*64,'input.conf','2'*64,'15000','5000','600000']
PREFIX = ('\n'.join(['SL3-ASIO-APPLICATION-1',*ACTIVATION])+'\n').encode()


class InstalledAsioStartTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)/'application-123-456'
        self.folder.mkdir()
        self.claim = self.folder.with_name(self.folder.name+'.claim')

    def ready(self, activation=ACTIVATION, config=b'published configuration', **extra):
        prefix = ('\n'.join(['SL3-ASIO-APPLICATION-1',*activation])+'\n').encode()
        digest = API['sha'](config)
        self.claim.write_bytes(prefix+digest.encode()+b'\n')
        (self.folder/'sl3-asio.conf').write_bytes(config)
        ready = {'schema':'sl3.broker-controller-ready.v1','readyIsSnapshot':True,'kind':'native',
                 'brokerSha256':activation[1],'configSha256':digest,'limitMs':600000,**extra}
        (self.folder/'ready.json').write_text(json.dumps(ready))

    def test_diagnostic_timing_is_bound_to_activation_and_published_worker(self):
        builder = runpy.run_path(str(API['ROOT']/'prepare-asio-deployment.py'))
        install = PureWindowsPath('C:/Program Files/SL3 Rebuild/on-demand-diagnostic-v1')
        worker_sha = 'a'*64

        def make_records(frames):
            return builder['activation_records'](install, 'b'*64, worker_sha,
                builder['APPLICATION_ACTIVATION_MODE'], playback_keepalive=True, buffer_frames=frames)

        records = make_records(64)
        for name, data in records.items():
            (self.folder.parent/name).write_bytes(data)
        path = self.folder.parent/'sl3-asio.conf'
        activation, digest = API['configuration'](path)
        profile = API['diagnostic_profile'](path,activation,digest)
        self.assertEqual(profile['configuredBufferFrames'],64)

        config = records['sl3-worker.conf'].replace(b'SL3-ASIO-CONFIG-1',b'SL3-ASIO-BROKER-CONFIG-1',1)
        self.ready(activation,config+b'broker=test\n',workerSha256=worker_sha,rateHz=44100)
        self.assertTrue(API['summarize'](self.folder,activation,profile)['diagnosticProfileMatchedReadiness'])
        self.ready(activation,config+b'broker=test\n',workerSha256=worker_sha,rateHz=48000)
        with self.assertRaisesRegex(ValueError,'diagnostic worker and rate'):
            API['summarize'](self.folder,activation,profile)
        other_worker = make_records(32)['sl3-worker.conf'].replace(b'SL3-ASIO-CONFIG-1',b'SL3-ASIO-BROKER-CONFIG-1',1)
        self.ready(activation,other_worker+b'broker=test\n',workerSha256=worker_sha,rateHz=44100)
        with self.assertRaisesRegex(ValueError,'Published worker configuration differs'):
            API['summarize'](self.folder,activation,profile)
        path.with_name('sl3-timing.conf').write_bytes(make_records(32)['sl3-timing.conf'])
        with self.assertRaisesRegex(ValueError,'timing hash chain differs'):
            API['diagnostic_profile'](path,activation,digest)

    def test_cut_off_receipt_and_ready_without_result_are_distinct(self):
        self.claim.write_bytes(PREFIX+b'1234')
        self.assertEqual(API['summarize'](self.folder,ACTIVATION)['outcome'],'activation_receipt_incomplete')
        self.ready()
        self.assertEqual(API['summarize'](self.folder,ACTIVATION)['outcome'],'completed_result_missing')

    def test_result_start_must_match_full_bound_process_identity(self):
        self.ready()
        final = {'schema':'sl3.broker-controller-result.v1','kind':'native','published':True,
                 'clientObservationsTruncated':False,'nativeDeviceAcquired':True,
                 'clientObservations':[{'pid':123,'creationFileTimeUtc':'455','admissionReplySent':True,'streamStartReplies':1}]}
        path = self.folder/'result.json'
        path.write_text(json.dumps(final))
        with self.assertRaisesRegex(ValueError,'bound host'):
            API['summarize'](self.folder,ACTIVATION)
        final['clientObservations'][0]['creationFileTimeUtc'] = '456'
        path.write_text(json.dumps(final))
        self.assertEqual(API['summarize'](self.folder,ACTIVATION)['streamStartReplies'],1)

    def test_unpublished_result_distinguishes_overlap_from_another_busy_error(self):
        self.claim.write_bytes(b'')
        intent = {'schema':'sl3.broker-controller-intent.v1','kind':'native','applicationBound':True,
                  'brokerSha256':ACTIVATION[1],'limitMs':600000}
        intent_path = self.folder/'intent.json'
        intent_path.write_text(json.dumps(intent))
        final = {'schema':'sl3.broker-controller-result.v1','kind':'native','published':False,
                 'acquireAttempted':True,'acquired':False,'snapshotValid':True,'failed':True,
                 'lastNativeError':170,'lastDeviceFailure':1,
                 'lastDiagnostic':'Acquire exclusive SL3 redirect owner failed, Win32=170'}
        final_path = self.folder/'result.json'
        final_path.write_text(json.dumps(final))
        self.assertEqual(API['summarize'](self.folder,ACTIVATION)['outcome'],'redirect_owner_busy')
        final['lastDiagnostic'] = 'Redirect exact SL3 failed, Win32=170'
        final_path.write_text(json.dumps(final))
        self.assertEqual(API['summarize'](self.folder,ACTIVATION)['outcome'],'broker_result_before_readiness')
        final['published'] = True
        final_path.write_text(json.dumps(final))
        self.assertEqual(API['summarize'](self.folder,ACTIVATION)['outcome'],'activation_receipt_incomplete')
        intent['brokerSha256'] = 'a'*64
        intent_path.write_text(json.dumps(intent))
        with self.assertRaisesRegex(ValueError,'Startup intent differs'):
            API['summarize'](self.folder,ACTIVATION)
