"""Compare completed, hash-bound native probe journals; never open hardware or infer readiness."""
import argparse
import hashlib
import json
from pathlib import Path

def require(value,message):
    if not value: raise ValueError(message)
def read(path,maximum=2_000_000):
    require(not path.is_symlink() and not path.is_junction() and 0<path.stat().st_size<=maximum,'Bounded regular evidence required')
    return path.read_bytes()
def digest(raw): return hashlib.sha256(raw).hexdigest()

def timeline(raw):
    rows=[]
    for line in raw.decode('utf-8').splitlines():
        cells=line.split('\t');require(len(cells)==3,'Three-column startup journal required')
        stamp,pid=int(cells[0]),int(cells[1])
        require(0<=stamp<=0xffffffffffffffff and 0<pid<=0xffffffff,'Bounded timestamp/process required')
        rows.append((stamp,pid,cells[2]))
    require(rows and len({row[1] for row in rows})==1,'One journal process required')
    require(all(a[0]<=b[0] for a,b in zip(rows,rows[1:])),'Journal clock moved backward')
    def point(name,required=False):
        values=[row[0] for row in rows if row[2]==name]
        require(len(values)<=1 and (not required or len(values)==1),'Unique required stage missing or repeated: '+name)
        return values[0] if values else None
    start=point('redirect_start.enter',True);returned=point('redirect_start.return');closed=point('redirect_close.return')
    require(returned is None or returned>=start,'Redirect return precedes entry')
    require(closed is None or (returned is not None and closed>=returned),'Redirect close without completed start')
    return {'redirectStartEnterMs':start,'redirectStartReturnMs':returned,'redirectCloseReturnMs':closed,
            'lastMarker':rows[-1][2]}

def completed(path,expected):
    data=read(path);require(digest(data)==expected,'Completed result identity differs')
    result=json.loads(data)
    require(result['schema'] in ('sl3.native-activation-control-run.v1','sl3.native-activation-silent-duplex-run.v1'),'Known native probe required')
    require(type(result['successful']) is bool,'Typed probe success required')
    journals=[(Path(name),value) for name,value in result['nativeJournalSha256'].items() if Path(name).name=='worker-startup.tsv']
    require(len(journals)==1,'One bound worker journal required')
    journal,expected_journal=journals[0];raw=read(journal);require(digest(raw)==expected_journal,'Worker journal identity differs')
    return {'resultSha256':expected,'workerJournalSha256':expected_journal,'successful':result['successful'],
            'bundleSha256':result['bundleSha256'],'nativeBuildSha256':result['nativeBuildSha256'],
            'streamStarted':result['audioStarted'],'timeline':timeline(raw)}

def summarize(runs,same_boot):
    require(type(same_boot) is bool,'Explicit same-boot context required')
    require(2<=len(runs)<=32,'Two to 32 completed probes required')
    for key in ('bundleSha256','nativeBuildSha256'):
        values={run[key] for run in runs}
        require(len(values)==1 and all(isinstance(v,str) and len(v)==64 and all(c in '0123456789abcdef' for c in v) for v in values),'One exact native build/bundle required')
    outcomes=[];previous=None
    for run in runs:
        row=dict(run);row['gapFromPreviousRedirectCloseMs']=None
        if same_boot and previous is not None:
            start=run['timeline']['redirectStartEnterMs'];closed=previous['timeline']['redirectCloseReturnMs']
            require(start>=previous['timeline']['redirectStartEnterMs'],'Run order/boot context differs')
            if closed is not None:
                require(start>=closed,'Acquisition overlaps preceding close')
                row['gapFromPreviousRedirectCloseMs']=start-closed
        outcomes.append(row);previous=run
    return {'schema':'sl3.native-reopen-cadence.v1','sameBootAssertedByCaller':same_boot,'bootIdentityIndependentlyVerified':False,
            'runs':outcomes,'streamingCauseIsolated':False,'readinessDelayEstablished':False,'automaticRetryRecommended':False,
            'deviceAccess':False,'vendorCodeExecuted':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result',action='append',type=Path,required=True)
    parser.add_argument('--result-sha256',action='append',required=True)
    parser.add_argument('--same-boot',action='store_true',help='Caller confirms all selected runs belong to the same Windows boot')
    args=parser.parse_args()
    require(len(args.result)==len(args.result_sha256),'Each result needs its expected hash')
    print(json.dumps(summarize([completed(p,h) for p,h in zip(args.result,args.result_sha256)],args.same_boot),indent=2))
