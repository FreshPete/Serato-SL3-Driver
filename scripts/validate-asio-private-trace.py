"""Strictly validate an unavailable-state first-party private ETW fixture; no ETW/device calls."""
import argparse
import hashlib
import json
from pathlib import Path
import re

EXPECTED = [(1,0),(3,0),(4,1),(2,0),(8,-1000),(10,-1000),(12,-1000),(5,0)]
ROOT=Path(__file__).resolve().parents[1]


def require(ok, why):
    if not ok:raise ValueError(why)


def parse(raw):
    def pairs(rows):
        out={}
        for k,v in rows:require(k not in out,'Duplicate JSON field');out[k]=v
        return out
    def invalid(value):raise ValueError('Nonfinite JSON: '+value)
    value=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=invalid)
    require(type(value) is dict,'Object required');return value


def integer(v,minimum,maximum):
    require(type(v) is int and minimum<=v<=maximum,'Bounded exact integer required')


def validate_rows(rows, summary, pid):
    integer(pid,1,2**32-1)
    require(set(summary)=={'schema','pid','decodedEvents','eventsLost','buffersLost','sessionStopped','dllUnloaded','ordinaryToken','unavailableProductionDll','deviceAccess','seratoExecuted'},'Exact capture summary required')
    require(summary['schema']=='sl3.asio-private-capture.v1' and type(summary['pid']) is int and summary['pid']==pid,'Capture PID/schema differs')
    for k in ['sessionStopped','dllUnloaded','ordinaryToken','unavailableProductionDll']:require(summary[k] is True,'Incomplete fixture lifecycle')
    for k in ['deviceAccess','seratoExecuted']:require(summary[k] is False,'Wrong fixture scope')
    for k in ['eventsLost','buffersLost']:integer(summary[k],0,0)
    integer(summary['decodedEvents'],16,16)
    require(len(rows)==summary['decodedEvents'],'Expected exact complete call sequence')
    previous_time=0;thread=None;pairs=[]
    outer={'schema','pid','tid','timestampFileTime','payload'}
    fields={'schema','build','phase','op','object','call','result','a0','a1','qpc','frequency','elapsedQpc'}
    for n,row in enumerate(rows):
        require(set(row)==outer and row['schema']=='sl3.asio-etw-record.v1','Exact decoded event envelope required')
        integer(row['pid'],pid,pid);integer(row['tid'],1,2**32-1)
        thread=row['tid'] if thread is None else thread
        require(row['tid']==thread,'Single-thread fixture expected')
        require(type(row['timestampFileTime']) is str and re.fullmatch('[0-9]{1,20}',row['timestampFileTime']),'FILETIME text required')
        stamp=int(row['timestampFileTime']);integer(stamp,1,2**64-1);require(stamp>=previous_time,'Event time regressed');previous_time=stamp
        p=row['payload'];require(type(p) is dict and set(p)==fields,'Exact payload fields required')
        require(p['schema']=='sl3.asio-call.v1' and p['build']=='production','Genuine production-build metadata required; not physical evidence')
        for k in ['op','object','call','qpc','frequency','elapsedQpc']:integer(p[k],0,2**64-1)
        for k in ['result','a0','a1']:integer(p[k],-2**63,2**63-1)
        ordinal=n//2;op,result=EXPECTED[ordinal]
        require(p['call']==ordinal+1 and p['op']==op and p['object']==(0 if ordinal==0 else 1),'Fixture operation/identity/order differs')
        require(p['a0']==p['a1']==0 and p['qpc']>0 and p['frequency']>0,'Fixture arguments/timing differ')
        if n%2==0:
            require(p['phase']=='begin' and p['result']==p['elapsedQpc']==0,'Begin is not a success result')
        else:
            start=rows[n-1]['payload'];require(p['phase']=='end' and p['result']==result,'Missing/failed expected terminal metadata')
            require(p['qpc']==start['qpc'] and p['frequency']==start['frequency'],'Pair clock identity differs')
            pairs.append({'operation':op,'result':result})
    return {'schema':'sl3.asio-private-trace-validation.v1','valid':True,'scope':'Own unavailable-state production DLL fixture only',
            'events':len(rows),'completePairs':len(pairs),'operationResults':pairs,'reportedLosses':0,'sessionStopped':True,
            'recordsConsistent':True,'actualEtwCaptureDecoded':False,'seratoCaptureVerified':False,'deviceAccess':False,'physicalAudioVerified':False,'currentSeratoAdmissionVerified':False,'twoDeckDvsVerified':False}


def bounded(path,limit):
    require(path.is_file() and not path.is_symlink() and not path.is_junction(),'Regular fixture file required')
    with path.open('rb') as f:raw=f.read(limit+1)
    require(0<len(raw)<=limit,'File size bound');return raw


def validate(folder):
    journal=bounded(folder/'run.json',1024*1024);run=parse(journal)
    require(run['schema']=='sl3.asio-private-trace-run.v1' and run['childExited'] is True and
            type(run['exitCode']) is int and run['exitCode']==0 and run['timedOut'] is False,'Actual successful retired child required')
    require(run['configuration'] in ['Release','Debug'] and run['seratoExecuted'] is False and run['deviceAccess'] is False,'Original fixture scope required')
    sources=['scripts/test-asio-private-trace.py','scripts/validate-asio-private-trace.py']
    require(set(run['sourceSha256'])==set(sources),'Exact runner/validator sources required')
    for p in sources:require(hashlib.sha256(bounded(ROOT/p,1024*1024)).hexdigest()==run['sourceSha256'][p],'Runner source differs')
    native=ROOT/f"artifacts/build/native/native-build-{run['configuration']}.json"
    diagnostic=ROOT/f"artifacts/build/asio-private-trace/diagnostic-build-{run['configuration']}.json"
    require(hashlib.sha256(bounded(native,1024*1024)).hexdigest()==run['nativeManifestSha256'] and
            hashlib.sha256(bounded(diagnostic,1024*1024)).hexdigest()==run['diagnosticManifestSha256'],'Recorded build identities differ')
    m=parse(bounded(native,1024*1024));b=parse(bounded(diagnostic,1024*1024))
    for inputs in [m['inputs'],b['inputs']]:
        for source,digest in inputs.items():require(hashlib.sha256(bounded(ROOT/source,16*1024*1024)).hexdigest()==digest.lower(),'Current source drift')
    require(run['dllSha256']==m['asioComponent']['comDllSha256'].lower() and run['toolSha256']==b['executableSha256'],'Known compiled images required')
    require({p.name for p in (folder/'isolated').iterdir()}=={'sl3_asio.dll'},'Exact isolated DLL directory without configuration required')
    for image,digest in [(ROOT/f"artifacts/build/native/{run['configuration']}/sl3_asio.dll",run['dllSha256']),
                         (ROOT/f"artifacts/build/asio-private-trace/{run['configuration']}/sl3_asio_private_trace.exe",run['toolSha256']),
                         (folder/'isolated/sl3_asio.dll',run['dllSha256'])]:
        require(hashlib.sha256(bounded(image,16*1024*1024)).hexdigest()==digest,'Actual image changed')
    etls=[p for p in run['files'] if re.fullmatch(r'capture/private\.etl(?:_[0-9]+)?',p)]
    require(len(etls)==1 and set(run['files'])=={'capture/capture.json','capture/events.jsonl',etls[0]},'Exact result and raw ETL pins required')
    for name,digest in run['files'].items():
        require(hashlib.sha256(bounded(folder/name,8*1024*1024)).hexdigest()==digest,'Recorded capture file differs')
    rows=[parse(line) for line in bounded(folder/'capture/events.jsonl',1024*1024).splitlines()]
    result=validate_rows(rows,parse(bounded(folder/'capture/capture.json',65536)),run['pid'])
    result['runRecordSha256']=hashlib.sha256(journal).hexdigest();result['actualEtwCaptureDecoded']=True
    result['firstPartyRunnerProvenanceVerified']=True;return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    args=parser.parse_args();print(json.dumps(validate(args.folder),indent=2))
