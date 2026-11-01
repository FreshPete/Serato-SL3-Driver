"""Synthetic live-consumer contracts and real plan-only calls; no active capture."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('live_capture',ROOT/'scripts/validate-usb-state-capture.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
SESSION='SL3Startup-'+'a'*32


def records():
    header={'record':'header','schema':'sl3.usb-state-observer.v1','mode':'session','sourceSession':SESSION,'requestedSeconds':5,
            'pid':42,'tokenQueried':True,'elevated':True,'elevationType':2,'sourceImageEvidenceRequired':True,'opaqueValuesAsStrings':True}
    for key in ('deviceAccess','startsTraceSession','stopsSourceSession','readinessAdmission'):header[key]=False
    row={'record':'state','eventId':110,'task':13,'pid':4,'timestampFileTime':str(v.filetime('2026-10-31T00:00:01Z')),
         'device':'64','context':'128','startIndex':4000,'state':4224,'event':1000,'depth':0}
    summary={'record':'summary','successful':True,'propertyFailure':False,'readinessAdmission':False,'sourceLossCountersComplete':False,
             'lossScope':'header snapshot only','processTraceStatus':0,'closeTraceStatus':0,'deadlineExpired':False,
             'eventsSeen':3,'eventsLost':0,'buffersLost':0,'stateRecords':1}
    return [header,row,summary]


def save(path,data):path.write_text(json.dumps(data),encoding='utf-8')
def stream(path,rows):path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')


class LiveCaptureTests(unittest.TestCase):
    def test_real_optional_plans_create_no_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)/'not-created'
            for script,options in (('capture-controls-user-context.ps1',['-ContextDirectory',str(folder)]),
                                   ('capture-usb-startup.ps1',['-WithUsbDkLifecycle','-DurationSeconds','5','-OutputDirectory',str(folder)])):
                child=subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'scripts'/script),'-WithStateObserver',*options],capture_output=True,text=True,timeout=30)
                self.assertEqual(child.returncode,0,child.stderr);plan=json.loads(child.stdout)
                self.assertIs(plan['withStateObserver'],True);self.assertFalse(folder.exists())
                if script=='capture-usb-startup.ps1':
                    self.assertEqual(plan['logFormat'],'bin')
                    self.assertIs(plan['circularOverwriteAllowed'],False)
                    self.assertIs(plan['failAtFileCapacity'],True)
            child=subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'scripts/capture-usb-startup.ps1'),'-WithStateObserver',
                                  '-OutputDirectory',str(folder)],capture_output=True,text=True,timeout=15)
            self.assertNotEqual(child.returncode,0);self.assertFalse(folder.exists())

    def test_file_replay_scope_tokens_types_and_partial_records_never_admit_live(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'observer.ndjson';original=records();stream(path,original)
            self.assertEqual(len(v.observations(path,SESSION,5,42)[2]),1)
            for index,key,value in ((0,'mode','etl'),(0,'sourceSession','other'),(0,'elevated',False),(0,'elevationType',True),
                                    (0,'readinessAdmission',True),(1,'context',128),(2,'successful',False),(2,'stateRecords',0),
                                    (2,'sourceLossCountersComplete',True),(2,'processTraceStatus',4201),(2,'eventsLost',1)):
                bad=copy.deepcopy(original);bad[index][key]=value;stream(path,bad)
                with self.subTest(key=key),self.assertRaises(ValueError):v.observations(path,SESSION,5,42)
            stream(path,original[:-1])
            with self.assertRaises((ValueError,KeyError)):v.observations(path,SESSION,5,42)

    def test_synthetic_source_binding_cleanup_window_and_xml_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);output=folder/'state-observer.ndjson';stream(output,records())
            contract={'valid':True,'buildManifestSha256':'a'*64,'observerManifestSha256':'b'*64,'executableSha256':'c'*64,
                      'executable':str(ROOT/'artifacts/build/usb-state-observer/Release/sl3_usb_state_observer.exe')}
            image={'sha256':'d'*64,'signatureStatus':'Valid','loadedImageIdentityVerified':False}
            item={k:contract[k] for k in ('buildManifestSha256','observerManifestSha256','executableSha256')}
            item.update(consumerAttemptVerified=True,readinessAdmission=False,exitCode=0,outputSha256=v.sha(output),hubImageBefore=image,hubImageAfter=image,
                startedUtc='2026-10-31T00:00:00Z',completedUtc='2026-10-31T00:00:05Z',
                process={'pid':42,'alive':True,'tokenQueried':True,'elevated':True,'elevationType':2,'imagePath':contract['executable'],
                         'creationFileTimeUtc':str(v.filetime('2026-10-31T00:00:00.1000000Z'))})
            capture={'session':SESSION,'collectorPid':43,'producerSha256':v.sha(ROOT/'scripts/capture-usb-startup.ps1'),'status':'window completed',
                'plan':{'withStateObserver':True,'realTimeDelivery':True,'durationSeconds':5},'stateObserver':item,
                'startRequestedUtc':'2026-10-31T00:00:00Z','stoppedUtc':'2026-10-31T00:00:06Z',
                'commands':[{'arguments':['create','trace','-n',SESSION,'-rt','-ft','00:00:01'],'exitCode':0},
                            {'arguments':['delete','-n',SESSION],'exitCode':0}]}
            etl=folder/'synthetic.etl';etl.write_bytes(b'Synthetic ETL fixture; no native decoding or hardware validation')
            capture['files']=[{'name':etl.name,'bytes':etl.stat().st_size,'sha256':v.sha(etl)}]
            xml=folder/'events.xml'
            xml.write_text('<Events xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><Event><System><Provider '
                'Guid="{9e814aad-3204-11d2-9a82-006008a86939}"/><EventID>0</EventID></System><EventData>'
                f'<Data Name="SessionNameString">{SESSION}</Data><Data Name="EventsLost">0</Data><Data Name="BuffersLost">0</Data>'
                '</EventData></Event><Event><System><Provider Guid="{ac52ad17-cc01-4f85-8df5-4dce4333c99b}"/>'
                '<EventID>110</EventID><Task>13</Task><Execution ProcessID="4"/><TimeCreated SystemTime="2026-10-31T00:00:01Z"/>'
                '</System><EventData>'+''.join(f'<Data Name="{k}">{val}</Data>' for k,val in
                [('fid_UsbDevice','0x40'),('fid_Context','0x80'),('fid_StartIndex','4000'),('fid_State','4224'),('fid_Event','1000'),('fid_Depth','0')])+
                '</EventData></Event></Events>',encoding='utf-8')
            save(folder/'capture.json',capture)
            with patch.object(v,'preflight',return_value=contract):
                result=v.validate(folder,xml);self.assertTrue(result['sourceXmlMatchVerified']);self.assertFalse(result['readinessAdmission'])
            original_xml=xml.read_text()
            xml.write_text(original_xml.replace('Name="EventsLost">0<','Name="EventsLost">       0<').replace('Name="BuffersLost">0<','Name="BuffersLost">       0<'),encoding='utf-8')
            with patch.object(v,'preflight',return_value=contract):
                self.assertTrue(v.validate(folder,xml)['sourceXmlMatchVerified'])
            xml.write_text(original_xml.replace('Name="EventsLost">0<','Name="EventsLost">       1<'),encoding='utf-8')
            with patch.object(v,'preflight',return_value=contract),self.assertRaisesRegex(ValueError,'loss differs'):
                v.validate(folder,xml)
            xml.write_text(original_xml,encoding='utf-8')
            for kind in ('source','cleanup','hash','containment','window','image'):
                bad=copy.deepcopy(capture)
                if kind=='source':bad['plan']['realTimeDelivery']=False
                if kind=='cleanup':bad['commands'][-1]['exitCode']=1
                if kind=='hash':bad['stateObserver']['outputSha256']='0'*64
                if kind=='containment':bad['stateObserver']['containmentRequested']=True
                if kind=='window':bad['startRequestedUtc']='2026-10-31T00:00:02Z'
                if kind=='image':bad['stateObserver']['hubImageAfter']={**image,'sha256':'e'*64}
                save(folder/'capture.json',bad)
                with patch.object(v,'preflight',return_value=contract),self.subTest(kind=kind),self.assertRaises(ValueError):v.validate(folder,xml)
            save(folder/'capture.json',capture);xml.write_text(xml.read_text().replace('Name="fid_State">4224','Name="fid_State">4222'),encoding='utf-8')
            with patch.object(v,'preflight',return_value=contract),self.assertRaises(ValueError):v.validate(folder,xml)


if __name__=='__main__':unittest.main()
