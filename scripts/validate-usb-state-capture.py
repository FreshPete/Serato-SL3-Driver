"""Read-only consistency checks for an optional live consumer of an owned trace."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'artifacts/build/native/native-build-Release.json'


def require(ok,reason):
    if not ok:raise ValueError(reason)


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def uint(value):return type(value) is int and 0<=value<2**32


def preflight():
    controls=read(BUILD)['hostProbe']['controls'];current=controls['stateObserverReferences']
    require(len(controls['scriptInputs'])==18,'Incomplete live-capture script set')
    for name,expected in controls['scriptInputs'].items():require(sha(ROOT/'scripts'/name)==expected.lower(),'Capture dependency changed: '+name)
    manifest=ROOT/'artifacts/build/usb-state-observer/observer-build-Release.json';build=read(manifest)
    exe=ROOT/'artifacts/build/usb-state-observer/Release/sl3_usb_state_observer.exe'
    require(sha(manifest)==current['manifestSha256'].lower() and sha(exe)==current['executableSha256'].lower()==build['executableSha256'].lower(),
            'Observer differs from reviewed native build reference')
    require(build['inputs']==current['inputs'] and len(build['inputs'])==5,'Observer input inventory differs')
    for name,expected in build['inputs'].items():require(sha(ROOT/name)==expected.lower(),'Observer input changed: '+name)
    test=Path(build['testRecord']);require(sha(test)==build['testRecordSha256'].lower()==current['testRecordSha256'].lower(),'Observer replay evidence changed')
    checked=read(test)
    require(checked['all585StateRowsMatchXmlIncluding100nsTimestamps'] is True and checked['noOverwriteVerified'] is True and
            checked['executableSha256']==sha(exe) and checked['livePositiveValidated'] is False and checked['summary']['successful'] is True and
            sha(Path(checked['outputDirectory'])/'replay.ndjson')==checked['replaySha256'],'Observer actual replay gate missing')
    return {'valid':True,'buildManifestSha256':sha(BUILD),'observerManifestSha256':sha(manifest),'executable':str(exe),'executableSha256':sha(exe)}


def filetime(value):
    match=re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(?:\+00:00|Z)',value)
    require(match is not None,'Expected UTC trace time');whole=datetime.fromisoformat(match[1]).replace(tzinfo=timezone.utc)-datetime(1601,1,1,tzinfo=timezone.utc)
    fraction=int((match[2] or '').ljust(9,'0'));require(fraction%100==0,'Timestamp exceeds 100 ns precision')
    return (whole.days*86400+whole.seconds)*10_000_000+fraction//100


def observations(path,session,seconds,pid):
    require(0<path.stat().st_size<=16*1024*1024,'Empty/oversized observer output')
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()];require(2<=len(rows)<=50002,'Observer record count outside bound')
    header,summary=rows[0],rows[-1]
    require(header['record']=='header' and header['schema']=='sl3.usb-state-observer.v1' and header['mode']=='session' and
            header['sourceSession']==session and header['requestedSeconds']==seconds and header['pid']==pid and
            header['tokenQueried'] is True and header['elevated'] is True and type(header['elevationType']) is int and header['elevationType'] in (1,2),
            'Live observer source/token/header differs')
    require(all(header[k] is False for k in ('deviceAccess','startsTraceSession','stopsSourceSession','readinessAdmission')) and
            header['sourceImageEvidenceRequired'] is True and header['opaqueValuesAsStrings'] is True,'Observer scope differs')
    require(summary['record']=='summary' and summary['successful'] is True and summary['propertyFailure'] is False and
            summary['readinessAdmission'] is False and summary['sourceLossCountersComplete'] is False and summary['lossScope']=='header snapshot only',
            'Incomplete/failed or overclaimed live consumer')
    require(uint(summary['processTraceStatus']) and (summary['processTraceStatus']==0 or
            summary['processTraceStatus']==1223 and summary['deadlineExpired'] is True) and
            uint(summary['closeTraceStatus']) and summary['closeTraceStatus'] in (0,7007),'Consumer processing/closure failed')
    require(uint(summary['eventsLost']) and uint(summary['buffersLost']) and summary['eventsLost']==summary['buffersLost']==0 and uint(summary['eventsSeen']) and summary['eventsSeen']>0,
            'Lossy/empty live header observation')
    states=rows[1:-1];require(type(summary['stateRecords']) is int and summary['stateRecords']==len(states)>0,'No actual live state rows')
    fields=('eventId','task','pid','timestampFileTime','device','context','startIndex','state','event','depth');opaque={'timestampFileTime','device','context'}
    values=[]
    for row in states:
        require(row['record']=='state' and row['eventId'] in (110,111),'Unexpected observation record')
        require(all(type(row[k]) is str and re.fullmatch('0|[1-9][0-9]{0,19}',row[k]) and int(row[k])<2**64 if k in opaque
                    else uint(row[k]) for k in fields),'Invalid state values/types')
        values.append(tuple(int(row[k]) for k in fields))
    return header,summary,values


def validate(folder,xml=None):
    contract=preflight();capture=read(folder/'capture.json');item=capture['stateObserver'];session=capture['session']
    require(capture['plan']['withStateObserver'] is True and capture['plan']['realTimeDelivery'] is True and
            capture['status']=='window completed' and re.fullmatch('SL3Startup-[0-9a-f]{32}',session),'Not a completed real-time source')
    require(capture['producerSha256'].lower()==sha(ROOT/'scripts/capture-usb-startup.ps1'),'Capture source changed')
    require(item['buildManifestSha256'].lower()==contract['buildManifestSha256'] and item['observerManifestSha256'].lower()==contract['observerManifestSha256'] and
            item['executableSha256'].lower()==contract['executableSha256'],'Capture observer build binding differs')
    require(item['consumerAttemptVerified'] is True and item['readinessAdmission'] is False and item['exitCode']==0 and
            type(item['exitCode']) is int and item.get('containmentRequested',False) is False,'Observer did not retire normally')
    process=item['process'];require(process['alive'] is True and process['tokenQueried'] is True and process['elevated'] is True and
            type(process['elevationType']) is int and process['elevationType'] in (1,2) and type(process['pid']) is int and process['pid']>0 and
            process['imagePath'].casefold()==contract['executable'].casefold() and
            re.fullmatch('[1-9][0-9]{16,17}',process['creationFileTimeUtc']),'Observer process snapshot differs')
    require(process['pid']!=capture['collectorPid'] and filetime(item['startedUtc'])<=int(process['creationFileTimeUtc'])<=filetime(item['completedUtc'])<=filetime(capture['stoppedUtc']),
            'Observer role/time window differs')
    create=[x for x in capture['commands'] if x['arguments'][:2]==['create','trace'] and type(x['exitCode']) is int and x['exitCode']==0]
    require(len(create)==1 and '-rt' in create[0]['arguments'] and '-ft' in create[0]['arguments'],'Real-time source creation not recorded')
    require(sum(x['arguments']==['delete','-n',session] and type(x['exitCode']) is int and x['exitCode']==0 for x in capture['commands'])==1,
            'Owned source cleanup not confirmed')
    etls=list(folder.glob('*.etl'));recorded=capture['files']
    require(len(etls)==len(recorded)==1 and recorded[0]['name']==etls[0].name and type(recorded[0]['bytes']) is int and
            recorded[0]['bytes']==etls[0].stat().st_size and 0<recorded[0]['bytes']<=64*1024*1024 and
            recorded[0]['sha256'].lower()==sha(etls[0]),'Combined source ETL binding missing/changed')
    path=folder/'state-observer.ndjson';require(sha(path)==item['outputSha256'].lower(),'Observer output binding changed')
    header,summary,values=observations(path,session,capture['plan']['durationSeconds'],process['pid'])
    require(process['elevationType']==header['elevationType'],'Native/process token observations differ')
    start,end=filetime(capture['startRequestedUtc']),filetime(capture['stoppedUtc'])
    require(all(start<=v[3]<=end for v in values),'Live state outside source window')
    before,after=item['hubImageBefore'],item['hubImageAfter']
    require(before==after and before['signatureStatus']=='Valid' and before['loadedImageIdentityVerified'] is False and re.fullmatch('[0-9A-Fa-f]{64}',before['sha256']),
            'Observed installed hub image changed/invalid')
    matched=False;coverage=None
    if xml is not None:
        require(0<xml.stat().st_size<=512*1024*1024,'Source XML size outside bound')
        ns='{http://schemas.microsoft.com/win/2004/08/events/event}';expected=[];source_header=None
        event_count=0
        for _,event in ET.iterparse(xml,events=['end']):
            if event.tag!=ns+'Event':continue
            event_count+=1;require(event_count<=2000000,'Source XML event count exceeds bound')
            system=event.find(ns+'System');provider=system.find(ns+'Provider');event_id=int(system.findtext(ns+'EventID'))
            if source_header is None:
                require(provider.get('Guid','').lower()=='{9e814aad-3204-11d2-9a82-006008a86939}','Missing source XML system header')
                source_header={d.get('Name'):(d.text or '') for d in event.findall(ns+'EventData/'+ns+'Data')}
                require(source_header.get('SessionNameString')==session and source_header.get('EventsLost','').strip()==source_header.get('BuffersLost','').strip()=='0',
                        'Source XML session/loss differs')
            if provider.get('Guid','').lower()=='{ac52ad17-cc01-4f85-8df5-4dce4333c99b}' and event_id in (110,111):
                data={d.get('Name'):(d.text or '') for d in event.findall(ns+'EventData/'+ns+'Data')}
                expected.append((event_id,int(system.findtext(ns+'Task')),int(system.find(ns+'Execution').get('ProcessID')),
                    filetime(system.find(ns+'TimeCreated').get('SystemTime')),*[int(data[k],0) for k in
                    ('fid_UsbDevice','fid_Context','fid_StartIndex','fid_State','fid_Event','fid_Depth')]))
            event.clear()
        require(source_header is not None and not Counter(values)-Counter(expected),'Live rows do not match full source XML')
        matched=True;coverage={'liveRows':len(values),'sourceStateRows':len(expected),'allSourceStateRowsObserved':Counter(values)==Counter(expected),'xmlSha256':sha(xml)}
    return {'valid':True,'scope':'Recorded live consumer/source consistency; no readiness, physical identity, audio or Serato acceptance',
            'session':session,'producerPid':process['pid'],'stateRows':len(values),'outputSha256':sha(path),
            'sourceXmlMatchVerified':matched,'coverage':coverage,'headerLossCountersComplete':False,
            'loadedHubImageIdentityVerified':False,'readinessAdmission':False}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight',action='store_true');mode.add_argument('--capture',type=Path);parser.add_argument('--xml',type=Path)
    args=parser.parse_args()
    try:print(json.dumps(preflight() if args.preflight else validate(args.capture,args.xml),indent=2))
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as error:
        print(json.dumps({'valid':False,'error':str(error)}));raise SystemExit(1)
