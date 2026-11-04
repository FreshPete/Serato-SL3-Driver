"""Port/child correlation guards; synthetic rows are not physical-device proof."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_port',ROOT/'scripts/analyse-sl3-release.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class PortTests(unittest.TestCase):
    def setUp(self):
        self.rows=[];self.states={};self.events={}
        def row(eid,second,data,pid=4):
            return {'eventId':eid,'pid':pid,'time':f'2026-11-01T14:00:{second:09.6f}+00:00','data':data}
        self.row=row
        def add(eid,second,data,pid=4):self.rows.append(row(eid,second,data,pid))
        add(6,0,{'fid_DeviceDescription':'Rane SL3','fid_HubDevice':'100','fid_UsbDevice':'101','fid_PortNumber':'4'})
        for cycle,done,child in [(1,2,102),(2.8,3.1,103)]:
            add(179,cycle,{'fid_UsbDevice':'100','fid_IoctlCode':str(v.timeline.CYCLE),'fid_idVendor':'7365','fid_idProduct':'1'},42)
            add(60,cycle+.01,{'fid_UsbDevice':'100','fid_PortNumber':'4'})
            add(61,done,{'fid_HubDevice':'100','fid_UsbDevice':str(child),'fid_PortNumber':'4','fid_NtStatus':'0'})
        add(43,2.1,{'fid_HubDevice':'100','fid_UsbDevice':'102','fid_PortNumber':'4','fid_DeviceDescription':'UsbDk device'})
        def state(second,context,device,name,event='OperationSuccess',pid=4):
            state_name='DsmStateEtw'+name;event_name='DsmEvent'+event
            state_value=next((k for k,val in self.states.items() if val==state_name),4000+len(self.states))
            event_value=next((k for k,val in self.events.items() if val==event_name),1000+len(self.events))
            self.states[state_value]=state_name;self.events[event_value]=event_name
            add(110,second,{'fid_Context':str(context),'fid_UsbDevice':str(device),'fid_StartIndex':'4000',
                           'fid_State':str(state_value),'fid_Event':str(event_value),'fid_Depth':'0'},pid)
        self.state=state
        state(1.1,201,101,'WaitingToBeDeleted')
        state(1.2,202,100,'RegisteringWithHSM',pid=42)
        state(2.9,202,102,'WaitingToBeDeleted')
        state(2.9,203,100,'RegisteringWithHSM')
        state(3.15,203,103,'StoppedEnumerated')
        state(13.15,203,103,'CheckIfDeviceCanBeDisabledOnDriverNotFound','TimerFired')
        state(13.15001,203,103,'DisablingDeviceInControllerOnStartTimeout','Yes')
        state(13.15002,203,103,'DisablingPortOnStartTimeout','UCXIoctlSuccess')
        state(13.15003,203,103,'Stopped','PortDisabled')
        self.rows.sort(key=lambda r:v.clock(r['time']))

    def analyse(self):return v.correlate(self.rows,42,'2026-11-01T14:00:03+00:00',self.states,self.events)

    def test_explicit_port_child_links_and_no_readiness_claim(self):
        result=self.analyse()
        self.assertTrue(result['postReleaseContextMappedToSl3Port']);self.assertEqual(result['port'],4)
        self.assertEqual(result['lastSuccessfulEntryToTimerTicks'],'100000000')
        self.assertFalse(result['readinessAdmission']);self.assertFalse(result['successiveAcquisitionVerified'])

    def test_shared_hub_cookie_does_not_select_other_port_context(self):
        self.state(3,999,100,'RegisteringWithHSM');self.state(13,999,9999,'Stopped','PortDisabled')
        self.assertEqual(self.analyse()['contextRows']['postRelease'],6)

    def test_probe_can_retire_after_last_successful_entry(self):
        completed='2026-11-01T14:00:04+00:00'
        result=v.correlate(self.rows,42,completed,self.states,self.events)
        self.assertIsNone(result['firstStoppedEnumeratedAfterProbeTicks'])
        self.assertEqual(result['postProbePendingStartFileTime'],str(v.clock(completed)))
        self.assertFalse(result['readinessAdmission'])

    def test_retirement_at_timeout_has_no_pending_window(self):
        with self.assertRaisesRegex(ValueError,'No successful stopped-enumerated window'):
            v.correlate(self.rows,42,'2026-11-01T14:00:13.15+00:00',self.states,self.events)

    def test_duplicate_rundown_or_child_context_rejected(self):
        original=copy.deepcopy(self.rows)
        self.rows.append(copy.deepcopy(self.rows[0]))
        with self.assertRaises(ValueError):self.analyse()
        self.rows=original;self.state(3.2,204,103,'StoppedEnumerated')
        with self.assertRaisesRegex(ValueError,'ambiguous DSM'):self.analyse()

    def test_another_port_enumeration_cannot_map_target_context(self):
        for r in self.rows:
            if r['eventId']==61 and r['data']['fid_UsbDevice']=='103':r['data']['fid_PortNumber']='5'
        with self.assertRaisesRegex(ValueError,'exact SL3 port'):self.analyse()

    def test_null_enumerated_child_cannot_be_used_as_identity(self):
        next(r for r in self.rows if r['eventId']==61)['data']['fid_UsbDevice']='0'
        with self.assertRaisesRegex(ValueError,'null'):self.analyse()

    def test_wrong_worker_vendor_status_or_start_port_rejected(self):
        original=copy.deepcopy(self.rows)
        for fault in ('worker','vendor','status','start'):
            self.rows=copy.deepcopy(original)
            if fault=='worker':next(r for r in self.rows if r['eventId']==179)['pid']=99
            if fault=='vendor':next(r for r in self.rows if r['eventId']==179)['data']['fid_idVendor']='1'
            if fault=='status':next(r for r in self.rows if r['eventId']==61)['data']['fid_NtStatus']='1'
            if fault=='start':next(r for r in self.rows if r['eventId']==60)['data']['fid_PortNumber']='5'
            with self.subTest(fault=fault),self.assertRaises(ValueError):self.analyse()

    def test_context_contamination_and_unknown_state_rejected(self):
        original=copy.deepcopy(self.rows)
        self.state(4,203,9999,'StoppedEnumerated')
        with self.assertRaisesRegex(ValueError,'unrelated child'):self.analyse()
        self.rows=original;next(r for r in self.rows if r['eventId']==110)['data']['fid_State']='99999'
        with self.assertRaisesRegex(ValueError,'Unknown state'):self.analyse()

    def test_missing_port_disabled_tail_rejected(self):
        self.rows=[r for r in self.rows if r['eventId']!=110 or self.states[int(r['data']['fid_State'])]!='DsmStateEtwStopped']
        with self.assertRaisesRegex(ValueError,'timeout/port-disable'):self.analyse()


if __name__=='__main__':unittest.main()
