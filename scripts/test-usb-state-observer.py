"""Actual passive observer executable checks against a saved ETL; no USB test."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

import pefile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('observer_timeline',ROOT/'scripts/export-reopen-usb-timeline.py')
timeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(timeline)
require=timeline.require


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def filetime(value):
    match=re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\.(\d{1,9})\+00:00',value)
    require(match is not None,'Expected explicit UTC trace time')
    whole=datetime.fromisoformat(match[1]).replace(tzinfo=timezone.utc)-datetime(1601,1,1,tzinfo=timezone.utc)
    nanos=int(match[2].ljust(9,'0'));require(nanos%100==0,'Timestamp exceeds FILETIME precision')
    return (whole.days*86400+whole.seconds)*10_000_000+nanos//100


def execute(args,expected=None):
    result=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=15)
    if expected is not None:require(result.returncode==expected,f'Exit {result.returncode} expected {expected}: {result.stderr}')
    return result


def main():
    require(len(sys.argv)==3,'Expected executable and new verification-record paths')
    exe,record_path=[Path(x).resolve() for x in sys.argv[1:]]
    require(not record_path.exists(),'Do not overwrite a verification record')
    old=timeline.read(ROOT/'docs/evidence/reopen-usb-timeline-20261030.json')
    source=ROOT/'tests/results/local/inspect-reopen-staged-20261030-02';xml=source/'events.xml';etls=list((source/'trace').glob('*.etl'))
    require(sha(xml)==old['xmlSha256'] and len(etls)==1 and sha(etls[0])==old['etlSha256'],'Saved trace binding differs')
    folder=Path(tempfile.mkdtemp(prefix='usb-state-observer-software-',dir=ROOT/'tests/results/local'))
    plan=json.loads(execute([exe,'--plan'],0).stdout)
    require(plan['planOnly'] is True and all(plan[k] is False for k in ('deviceAccess','startsTraceSession','stopsSourceSession','selfElevates','readinessAdmission','liveConsumerPhysicallyValidated')),'Unsafe passive observer plan')
    output=folder/'replay.ndjson';execute([exe,'--etl',etls[0],'--output',output],0)
    records=[json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
    header,summary=records[0],records[-1];actual=records[1:-1]
    require(header['schema']=='sl3.usb-state-observer.v1' and header['mode']=='etl' and header['record']=='header' and
            header['sourceSession'] is None and header['requestedSeconds']==0 and
            header['tokenQueried'] is True and type(header['elevated']) is bool and type(header['elevationType']) is int and
            header['elevationType'] in (1,2,3) and type(header['pid']) is int and header['pid']>0,'Missing actual producer token/header evidence')
    require(summary['record']=='summary' and summary['successful'] is True and summary['propertyFailure'] is False and
            summary['deadlineExpired'] is False and summary['readinessAdmission'] is False and
            summary['sourceLossCountersComplete'] is True and summary['lossScope']=='completed source-file header' and
            summary['eventsSeen']==old['traceStats']['eventCount'] and summary['eventsLost']==summary['buffersLost']==0 and
            summary['processTraceStatus']==summary['closeTraceStatus']==0,'Incomplete/lossy passive replay')
    rows,total=timeline.parse(xml);expected=[]
    for row in rows:
        if row['eventId'] not in (110,111):continue
        data=row['data']
        expected.append((row['eventId'],row['task'],row['pid'],filetime(row['time']),*[timeline.number(data[k]) for k in
                         ('fid_UsbDevice','fid_Context','fid_StartIndex','fid_State','fid_Event','fid_Depth')]))
    fields=('eventId','task','pid','timestampFileTime','device','context','startIndex','state','event','depth')
    opaque={'timestampFileTime','device','context'}
    require(header['opaqueValuesAsStrings'] is True and all(row['record']=='state' and
            all((type(row[k]) is str and re.fullmatch(r'0|[1-9][0-9]{0,19}',row[k]) and int(row[k])<2**64) if k in opaque
                else type(row[k]) is int for k in fields) for row in actual),'Malformed or precision-losing native state row')
    require(Counter(tuple(int(row[k]) if k in opaque else row[k] for k in fields) for row in actual)==Counter(expected) and
            len(actual)==summary['stateRecords']==585 and total==summary['eventsSeen'],'Native ETL observations differ from hash-bound XML')
    saved=sha(output);execute([exe,'--etl',etls[0],'--output',output],1);require(sha(output)==saved,'Replay output was overwritten')
    negative=[]
    cases=[('missing-file',['--etl',folder/'absent.etl']),('invalid-session',['--session','not-owned','--seconds','1']),
           ('duration-zero',['--session','SL3Startup-'+uuid.uuid4().hex,'--seconds','0']),
           ('duration-long',['--session','SL3Startup-'+uuid.uuid4().hex,'--seconds','61']),
           ('missing-session',['--session','SL3Startup-'+uuid.uuid4().hex,'--seconds','1'])]
    for name,args in cases:
        target=folder/(name+'.ndjson');result=execute([exe,*args,'--output',target],1)
        status=None
        if name=='missing-session' and target.exists():
            failed=[json.loads(line) for line in target.read_text().splitlines()]
            require(failed[-1]['record']=='summary' and failed[-1]['successful'] is False and failed[-1]['eventsSeen']==0 and
                    failed[-1]['processTraceStatus']==4201 and failed[-1]['readinessAdmission'] is False,'Missing session manufactured a successful observation')
            status=failed[-1]['processTraceStatus']
        else:require(not target.exists(),'Rejected arguments created output')
        negative.append({'case':name,'exitCode':result.returncode,'outputCreated':target.exists(),'processTraceStatus':status})
    bad=folder/'malformed.etl';bad.write_bytes(b'not an ETL file'*5);target=folder/'bad.ndjson'
    result=execute([exe,'--etl',bad,'--output',target],1)
    if target.exists():
        saved_rows=[json.loads(line) for line in target.read_text().splitlines()]
        require(saved_rows[-1]['record']=='summary' and saved_rows[-1]['successful'] is False,'Malformed ETL claimed successful read')
    negative.append({'case':'malformed-etl','exitCode':result.returncode,'outputCreated':target.exists()})
    pe=pefile.PE(str(exe));imports={x.name.decode('ascii') for item in pe.DIRECTORY_ENTRY_IMPORT for x in item.imports if x.name}
    require({'OpenTraceW','ProcessTrace','CloseTrace','TdhGetProperty','TdhGetPropertySize'}<=imports,'Native passive consumer imports missing')
    require(not imports&{'StartTraceW','ControlTraceW','EnableTraceEx2','DeviceIoControl','CreateServiceW','ShellExecuteExW'},'Observer directly imports a source-session/device/elevation control API')
    record={'scope':'Actual native ETL replay and passive negative cases; not a live subscription or device readiness test',
            'executableSha256':sha(exe),'testScriptSha256':sha(Path(__file__)),'etlSha256':sha(etls[0]),'xmlSha256':sha(xml),
            'outputDirectory':str(folder),'replaySha256':sha(output),'producer':header,'summary':summary,
            'all585StateRowsMatchXmlIncluding100nsTimestamps':True,'noOverwriteVerified':True,'negativeCases':negative,
            'consumerImports':sorted(imports),'livePositiveValidated':False,'readinessAdmission':False}
    record_path.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print('Actual passive replay: 14,368 events, all 585 state rows/timestamps match XML, no loss; negative/no-overwrite cases pass')


if __name__=='__main__':main()
