"""Synthetic record/journal grammar only; a passing fixture is not a native run."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('broker_scope_evidence', ROOT/'scripts/validate-broker-scope-probe.py')
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
HASH = 'a'*64


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sl3-broker-scope-evidence-'); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.result = {'schema': 'sl3.broker-scope-probe.v1', 'simulated': True, 'successful': True, 'error': '', 'workerSha256': HASH,
                       'nativeDeviceAcquired': False, 'workerPid': 99, 'clientAttempts': 3, 'completedClients': 3, 'audioStarts': 0, 'rateSetters': 0,
                       'clients': [{'index': n, 'pid': 100+n, 'created100ns': 1000+n, 'rateHz': 48000, 'retired': True, 'terminationRequested': False} for n in range(3)]}
        for key in ['acquireAttempted', 'acquired', 'recordPublished', 'deviceReleasedVerified', 'ioRetiredVerified', 'workerProcessExited', 'workerJobEmpty']:
            self.result[key] = True
        for key in ['audioAllowed', 'timingProfileReadOrWritten', 'asioConfigurationPublished', 'workerTerminationRequested', 'helperLoadedInProbe',
                    'kernelQuiescenceVerified', 'usbReadyForNextAcquire', 'physicalAudioVerified', 'seratoAdmissionVerified']:
            self.result[key] = False
        self.write(); (self.folder/'worker-audit.txt').write_text('\n'.join(['acquire']+['rate']*7+['release'])+'\n')
        (self.folder/'broker-session.txt').write_bytes(('SL3-BROKER-SESSION-1\nendpoint=\\\\.\\pipe\\SL3Broker-'+('1'*32)+
            '\nserver_pid=88\nserver_created=999\nworker_sha256='+HASH+'\n').encode())

    def write(self):
        (self.folder/'result.json').write_text(json.dumps(self.result))
        for n, row in enumerate(self.result['clients']):
            data = {key: row[key] for key in ['index', 'pid', 'created100ns', 'rateHz']}
            data.update(schema='sl3.broker-scope-client.v1', workerPid=99, simulated=self.result['simulated'], detached=True, audioStarted=False, deviceReleased=False)
            (self.folder/f'client-{n}.json').write_text(json.dumps(data))

    def native(self):
        self.result['simulated'] = False; self.result['nativeDeviceAcquired'] = True; self.write()
        (self.folder/'worker-audit.txt').unlink()
        stages = ['worker.enter', 'helper_load.enter', 'helper_load.return', 'enumerate.enter', 'enumerate.return',
                  'configuration.enter', 'configuration.return', 'redirect_owner_acquire.enter', 'redirect_owner_acquire.return',
                  'redirect_start.enter', 'redirect_start.return', 'system_handle.enter', 'system_handle.return']+[
                  'clock_getter.enter', 'clock_getter.return']*7+['redirect_close.enter', 'redirect_close.return', 'helper_unload.enter', 'helper_unload.return']
        data = ''.join(f'{100+n}\t99\t{stage}\n' for n, stage in enumerate(stages)); (self.folder/'worker-startup.tsv').write_bytes(data.encode()); return data

    def test_simulated_records_keep_physical_provenance_false(self):
        result = v.validate(self.folder, HASH, True)
        self.assertTrue(result['valid']); self.assertFalse(result['physicalProvenanceVerified']); self.assertIsNone(result['nativeJournal'])

    def test_typed_native_grammar_is_not_physical_attestation(self):
        self.native(); result = v.validate(self.folder, HASH)
        self.assertEqual(result['nativeJournal']['workerPid'], 99); self.assertFalse(result['physicalProvenanceVerified'])

    def test_wrong_hash_kind_and_failed_result_refused(self):
        with self.assertRaises(ValueError): v.validate(self.folder, '0'*64, True)
        with self.assertRaises(ValueError): v.validate(self.folder, HASH)
        self.result['successful'] = False; self.write()
        with self.assertRaises(ValueError): v.validate(self.folder, HASH, True)

    def test_audio_readiness_timing_and_forced_retirement_flags_refused(self):
        original = copy.deepcopy(self.result)
        for key in ['audioAllowed', 'usbReadyForNextAcquire', 'physicalAudioVerified', 'timingProfileReadOrWritten', 'workerTerminationRequested']:
            self.result = copy.deepcopy(original); self.result[key] = True; self.write()
            with self.subTest(key=key), self.assertRaises(ValueError): v.validate(self.folder, HASH, True)

    def test_client_type_creation_rate_and_retirement_mismatches_refused(self):
        original = copy.deepcopy(self.result)
        for key, value in [('index', False), ('pid', True), ('created100ns', 0), ('rateHz', 44100), ('retired', False)]:
            self.result = copy.deepcopy(original); self.result['clients'][0][key] = value; self.write()
            with self.subTest(key=key), self.assertRaises(ValueError): v.validate(self.folder, HASH, True)

    def test_extra_configuration_and_wrong_audit_refused(self):
        extra = self.folder/'sl3-asio.conf'; extra.write_text('not a diagnostic')
        with self.assertRaises(ValueError): v.validate(self.folder, HASH, True)
        extra.unlink(); (self.folder/'worker-audit.txt').write_text('acquire\nrate\nbegin\nrelease\n')
        with self.assertRaises(ValueError): v.validate(self.folder, HASH, True)

    def test_missing_partial_wrong_worker_and_extra_audio_native_journal_refused(self):
        data = self.native(); path = self.folder/'worker-startup.tsv'
        for changed in [data.rstrip('\n'), data.replace('\t99\t', '\t98\t', 1), data.replace('clock_getter.return', 'clock_getter.enter', 1), data+'999\t99\taudio_start.enter\n']:
            path.write_bytes(changed.encode())
            with self.subTest(tail=changed[-40:]), self.assertRaises(ValueError): v.validate(self.folder, HASH)
        path.unlink()
        with self.assertRaises(ValueError): v.validate(self.folder, HASH)


if __name__ == '__main__':
    unittest.main()
