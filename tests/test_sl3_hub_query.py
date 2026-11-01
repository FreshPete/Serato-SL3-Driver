"""Cached hub response and plan guards; never opens USB hardware."""
import ctypes as c
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hub_query',ROOT/'scripts/query-sl3-hub-port.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class HubQueryTests(unittest.TestCase):
    def buffer(self):
        raw=(c.c_ubyte*387)();info=v.Connection.from_buffer(raw)
        info.index=4;info.status=1;info.descriptor.length=18;info.descriptor.type=1
        info.descriptor.vendor=0x1cc5;info.descriptor.product=1;info.address=1
        return bytes(raw)

    def test_packed_layout_and_descriptor_response(self):
        v.layout();result=v.decode(self.buffer(),35,4)
        self.assertTrue(result['targetDescriptorMatches']);self.assertFalse(result['readinessAdmission'])
        self.assertEqual(result['connectionStatusName'],'DeviceConnected')

    def test_absent_device_is_observation_not_readiness(self):
        raw=bytearray(387);raw[0]=4
        result=v.decode(bytes(raw),35,4)
        self.assertFalse(result['targetDescriptorMatches']);self.assertEqual(result['connectionStatusName'],'NoDeviceConnected')
        self.assertFalse(result['readinessAdmission'])

    def test_truncated_wrong_index_unknown_status_descriptor_and_hub_flag(self):
        for fault in ('length','index','status','descriptor','hub'):
            raw=bytearray(self.buffer());returned=35
            if fault=='length':returned=34
            if fault=='index':raw[0]=5
            if fault=='status':raw[31]=255
            if fault=='descriptor':raw[5]=2
            if fault=='hub':raw[24]=2
            with self.subTest(fault=fault),self.assertRaises(ValueError):v.decode(bytes(raw),returned,4)

    def test_plan_limits_and_invalid_target(self):
        p=v.plan(r'USB\ROOT_HUB30\test',4)
        self.assertEqual(p['queryIoctl'],'0x220448');self.assertEqual(p['createFileDesiredAccess'],0)
        self.assertEqual(p['connectionQueriesRequested'],1);self.assertEqual(p['sl3OpensRequested'],0)
        for hub,port in [(r'USB\VID_1CC5&PID_0001\device',4),(r'USB\ROOT_HUB30\test',0),
                         (r'USB\ROOT_HUB30\test',True),(r'USB\ROOT_HUB30\test',256)]:
            with self.assertRaises(ValueError):v.plan(hub,port)

    def test_rejected_response_bytes_preserved_without_admission(self):
        raw=bytearray(self.buffer());raw[31]=255;raw[-1]=173
        saved=v.response_evidence(bytes(raw),35)
        self.assertEqual(bytes.fromhex(saved['bufferHex']),bytes(raw))
        self.assertEqual(saved['unvalidatedHeader']['status'],255)
        self.assertEqual(saved['unvalidatedDescriptorHex'],bytes(raw[4:22]).hex())
        self.assertEqual(saved['bytesReturned'],35)
        with self.assertRaisesRegex(ValueError,'Unknown hub connection status: 255'):
            v.decode(bytes(raw),35,4)
        for returned in (0,34,388):
            saved=v.response_evidence(bytes(raw),returned)
            self.assertEqual(saved['bytesReturned'],returned)
            self.assertEqual(saved['returnedLengthWithinBuffer'],returned<=387)
            with self.assertRaises(ValueError):v.decode(bytes(raw),returned,4)

    def test_elevated_role_refused_before_dll_access(self):
        with patch.object(v,'own_token',return_value={'queried':True,'elevated':True}),patch.object(v.c,'WinDLL') as dll:
            with self.assertRaisesRegex(ValueError,'normal user'):v.run(v.plan(r'USB\ROOT_HUB30\test',4))
            dll.assert_not_called()

    def test_actual_plan_only_cli(self):
        run=subprocess.run([sys.executable,str(ROOT/'scripts/query-sl3-hub-port.py'),
                            '--hub-instance',r'USB\ROOT_HUB30\test','--port','4'],capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stderr)
        result=json.loads(run.stdout);self.assertNotIn('producerToken',result);self.assertFalse(result['requestsElevation'])


if __name__=='__main__':unittest.main()
