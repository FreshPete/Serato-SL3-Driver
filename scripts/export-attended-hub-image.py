"""Verify version-3 schema and saved image rundown; never starts logging or USB."""
import hashlib
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    inspector=load('image_inspector',ROOT/'scripts/inspect-kernel-image-rundown.py')
    timing=load('exact_filetime',ROOT/'scripts/validate-usb-state-capture.py')
    require,sha=inspector.require,inspector.digest
    schema_path=ROOT/'analysis/installed-kernel-image-wmi-schema-02.json';schema=read(schema_path)
    require(schema['sourceSha256']==sha(ROOT/'scripts/inspect-kernel-image-schema.ps1'), 'Schema producer changed')
    qualifiers={q['name']:q['value'] for q in schema['baseQualifiers']}
    require(schema['baseClass']=='Image' and schema['payloadClass']=='Image_Load' and schema['payloadSuperClass']=='Image'
            and qualifiers['EventVersion']==3 and qualifiers['Guid'].lower()==inspector.IMAGE_GUID,'Wrong installed event class')
    declared={}
    for prop in schema['properties']:
        q={v['name']:v['value'] for v in prop['qualifiers']}
        if 'WmiDataId' in q:declared[prop['name']]=(prop['cimType'],q['WmiDataId'],bool(q.get('pointer',False)))
    expected={name:('UInt32',index,False) for index,name in enumerate([
        'ImageBase','ImageSize','ProcessId','ImageChecksum','TimeDateStamp','SignatureLevel','SignatureType',
        'Reserved0','DefaultBase','Reserved1','Reserved2','Reserved3','Reserved4','FileName'],1)}
    for name in ('ImageBase','ImageSize','DefaultBase'):expected[name]=('UInt32',expected[name][1],True)
    for name in ('SignatureLevel','SignatureType'):expected[name]=('UInt8',expected[name][1],False)
    expected['Reserved0']=('UInt16',8,False);expected['FileName']=('String',14,False)
    require(declared==expected and set(declared)==inspector.V3_FIELDS,'Installed payload fields/order/types differ')
    payload_q={q['name']:q['value'] for q in schema['payloadQualifiers']}
    require(payload_q['EventType']==[10,2,3,4],'Installed operation schema differs')
    reference=ROOT/'artifacts/references/perfview-image-rundown/KernelTraceEventParser.cs'
    require(sha(reference)=='2245ccc62b0d933190068a18344bc64749a2893bd9740a79706ba7fe5e86c778','Microsoft parser source changed')
    image=ROOT/'artifacts/references/windows-usbhub3/USBHUB3.SYS'
    metadata=inspector.image_metadata(image,r'\SystemRoot\System32\drivers\UsbHub3.sys')
    launch=read(ROOT/'analysis/attended-image-source-launch.json');context=Path(launch['context'])
    run=read(context/'run.json');prep=read(context/'preparation.json')
    require(run['successful'] is False and run['cleanup']['successful'] is True and run['cleanup']['collectorDeleted'] is True
            and run['after']['sourceActive'] is False and run['after']['win32Status']==4201,'Original failure/cleanup record differs')
    require(run['independentStopValidated'] is False and len(run['etlFiles'])==1,'Unexpected source outcome')
    etl=Path(run['etlFiles'][0]['path']);xml=ROOT/'analysis/attended-kernel-image-events.xml'
    saved=read(ROOT/'analysis/attended-kernel-image-rundown-v3.json')
    require(sha(etl)==run['etlFiles'][0]['sha256']==saved['sourceEtlSha256'] and
            sha(xml)==saved['decodedXmlSha256'] and saved['inspectorSha256']==sha(ROOT/'scripts/inspect-kernel-image-rundown.py'),
            'Saved trace/decoder input binding differs')
    result=inspector.inspect_xml(xml,metadata)
    require(result['comparison']['matchingRundownMetadata'] is True and result['sourceReportsNoLoss'] is True,
            'No matching loss-free hub rundown')
    require(len(result['kernelImages'])==259 and all(v['consistentRundownPair'] for v in result['kernelImages']),
            'Kernel rundown set is incomplete or inconsistent')
    target=next(v for v in result['kernelImages'] if v['canonicalKernelPath']==inspector.canonical_path(metadata['kernelPath']))
    require(target['consistentRundownPair'] and all(v['eventVersion']==3 for v in target['observations']), 'Target is not a version-3 pair')
    begin,end=result['headers'][0]['StartTime'],result['headers'][0]['EndTime']
    require(all(begin<=timing.filetime(v['time'])<=end for v in target['observations']), 'Target is outside its image-source window')
    ns=inspector.NS
    for _,event in ET.iterparse(xml,events=['end']):
        if event.tag=='{'+ns['e']+'}Event':
            header={d.get('Name'):(d.text or '').strip() for d in event.findall('e:EventData/e:Data',ns)}
            break
    mode=int(header['LogFileMode'],0)
    require(header['SessionNameString']==prep['sessionName'] and mode&0x02000000 and not mode&2,'Source name/mode differs')
    sources=[Path(__file__), ROOT/'scripts/inspect-kernel-image-rundown.py',ROOT/'scripts/test-kernel-image-rundown.py',
             ROOT/'scripts/inspect-kernel-image-schema.ps1',ROOT/'scripts/validate-usb-state-capture.py',schema_path,reference,
             context/'run.json',context/'preparation.json',ROOT/'analysis/attended-kernel-image-rundown-v3.json']
    output={'scope':'Actual saved image-window metadata, not the earlier USB window, loaded-memory hash or readiness',
            'sourceEtlSha256':sha(etl),'decodedXmlSha256':sha(xml),'schemaVersion':3,'kernelRundownPairs':259,
            'matchingHubRundownMetadata':True,'hub':metadata,
            'hubObservations':[{k:v for k,v in row.items() if k!='imageBase'} for row in target['observations']],
            'imageSourceWindow':{'startFileTime':str(begin),'endFileTime':str(end),'sessionName':header['SessionNameString']},
            'etlHeaderSystemLoggerModePresent':True,'etlHeaderMaximumFileMiB':int(header['MaxFileSize']),
            'originalSourceRunSuccessful':False,'collectorDeleted':True,'sourceAbsentAfterCleanup':True,
            'independentStopValidated':False,'loadedMemoryIdentityVerified':False,'usbWindowQualified':False,'readinessAdmission':False,
            'limits':['The requested segment size was not an ETW hard file limit: MaxFileSize is zero.',
                      'Reported signature level/type are event fields, not independent signature verification.',
                      'This source ran after the USB read; it cannot retroactively attest that interval or the earlier failed reopen.',
                      'The GUID-query failure and failed original run remain preserved.'],
            'sources':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sources}}
    require(result['kernelImageOperations']=={'DCStart':259,'DCEnd':259},'Kernel image count changed')
    (ROOT/'docs/evidence/attended-hub-image-20261031.json').write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
    print('Verified installed version-3 schema and 259 actual kernel rundown pairs; hub metadata matches; no USB readiness claim')


if __name__=='__main__':main()
