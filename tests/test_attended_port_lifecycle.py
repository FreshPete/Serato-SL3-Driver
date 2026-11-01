"""Offline lifecycle message guards; no tracing, elevation or USB calls."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('attended_lifecycle',ROOT/'scripts/analyse-attended-port-lifecycle.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.messages=[(2324,'CWdmUsbDeviceAccess::Reset device power state D3'),
            (4,'PowerRequestCompletion -> D0'),
            (2324,'CUsbDkRedirection::CreateRedirectorHandle done for process 0x914'),
            (2324,'CUsbDkRedirectorStrategy::OnClose'),
            (2324,r'CUsbDkControlDevice::RemoveRedirect Waiting for detachment from USB\VID_1CC5&PID_0001:SL3.01.00'),
            (2324,r'CUsbDkControlDevice::RemoveRedirect Detached from USB\VID_1CC5&PID_0001:SL3.01.00'),
            (2324,'CUsbDkControlDevice::RemoveRedirect Finished successfully. New redirections list:')]

    def text(self,messages=None):
        return '\n'.join(f'[8]{pid:04X}.ABCD::2026-11-01T16:41:34.{index:07d} [UsbDk]{message}'
                         for index,(pid,message) in enumerate(messages or self.messages))

    def test_ordered_caller_linked_messages_do_not_admit_readiness(self):
        result=v.observations(self.text(),2324)
        self.assertEqual(result['decodedUsbDkRecords'],7)
        self.assertEqual(result['detachmentWaitTicks'],'1')
        self.assertFalse(result['readinessAdmission'])
        self.assertFalse(result['powerCallbackRequestIdentityVerified'])

    def test_missing_duplicate_wrong_caller_and_target_rejected(self):
        for fault in ('missing','duplicate','caller','target','owner','malformed'):
            messages=copy.deepcopy(self.messages)
            if fault=='missing':messages.pop(4)
            if fault=='duplicate':messages.append(messages[4])
            if fault=='caller':messages[4]=(999,messages[4][1])
            if fault=='target':messages[5]=(2324,messages[5][1].replace('SL3.01.00','OTHER'))
            if fault=='owner':messages[2]=(2324,messages[2][1].replace('0x914','0x915'))
            text=self.text(messages)
            if fault=='malformed':text=text.replace('::','INVALID')
            with self.subTest(fault=fault),self.assertRaises(ValueError):v.observations(text,2324)

    def test_reversed_stage_time_is_rejected(self):
        messages=copy.deepcopy(self.messages);messages[4],messages[5]=messages[5],messages[4]
        with self.assertRaisesRegex(ValueError,'order'):v.observations(self.text(messages),2324)

    def formats(self):
        text=[]
        for (guid,file),numbers in v.EXTRA.items():
            text.append(f'{guid} UsbDk // SRC={file} MJ= MN=')
            for number in numbers:text.append(f'#typev example {number} "message"\n{{\n}}')
        return '\n'.join(text)+'\n'

    def test_additional_formats_require_invariant_inventory_and_driver_guid(self):
        raw=self.formats().encode();image=b''.join(uuid.UUID(g).bytes_le for g,_ in v.EXTRA)
        with self.assertRaisesRegex(ValueError,'identity'):v.supplement(raw,image)
        with patch.object(v.source,'sha',return_value=v.source.TMF_SHA):
            self.assertEqual(v.supplement(raw,image).count(b'#typev'),3)
            self.assertEqual(v.supplement(raw+raw,image).count(b'#typev'),3)
            with self.assertRaisesRegex(ValueError,'architecture-dependent'):
                v.supplement(raw+raw.replace(b'"message"',b'"different"'),image)
            with self.assertRaisesRegex(ValueError,'inventory'):
                v.supplement(raw.replace(b'example 65',b'example 66'),image)
            with self.assertRaisesRegex(ValueError,'GUID absent'):v.supplement(raw,b'')


if __name__=='__main__':unittest.main()
