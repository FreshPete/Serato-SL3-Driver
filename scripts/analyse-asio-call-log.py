"""Decode a completed own-provider ETL and summarize arbitrary selected ASIO calls offline."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('trace_validation',ROOT/'scripts/validate-asio-private-trace.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
NAMES={1:'class_object',2:'init',3:'name',4:'version',5:'error_message',6:'start',7:'stop',8:'channels',9:'latencies',
       10:'buffer_size',11:'can_rate',12:'get_rate',13:'set_rate',14:'clocks',15:'set_clock',16:'create_buffers',17:'dispose_buffers',18:'control_panel'}
OUTER={'schema','pid','tid','timestampFileTime','payload'}
FIELDS={'schema','build','phase','op','object','call','result','a0','a1','qpc','frequency','elapsedQpc'}

def analyze(rows,marker):
    v.require(set(marker)=={'schema','pid','stopStatus','eventsLost','buffersLost','complete','hardwareStateAssessed'} and
              marker['schema']=='sl3.asio-owned-session.v1' and marker['hardwareStateAssessed'] is False,'Exact own-session marker required')
    v.integer(marker['pid'],1,2**32-1)
    for k in ['stopStatus','eventsLost','buffersLost']:v.integer(marker[k],0,2**32-1)
    complete=all(marker[k]==0 for k in ['stopStatus','eventsLost','buffersLost'])
    v.require(type(marker['complete']) is bool and marker['complete']==complete,'Consistent session completion required')
    v.require(len(rows)<=8192,'Provider record bound exceeded')
    pending={};closed=set();pairs=[];orphans=[];build=None;methods={};seen=set();stamps=[]
    for ordinal,row in enumerate(rows):
        v.require(set(row)==OUTER and row['schema']=='sl3.asio-etw-record.v1','Exact event envelope required')
        v.integer(row['pid'],marker['pid'],marker['pid']);v.integer(row['tid'],1,2**32-1)
        stamp=row['timestampFileTime'];v.require(type(stamp) is str and re.fullmatch('[0-9]{1,20}',stamp),'Bounded FILETIME string required')
        v.integer(int(stamp),1,2**64-1)
        stamps.append(int(stamp))
        p=row['payload'];v.require(type(p) is dict and set(p)==FIELDS and p['schema']=='sl3.asio-call.v1','Exact provider payload required')
        v.require(p['build'] in ['production','session_fixture'] and p['phase'] in ['begin','end','abandoned'],'Known build/phase required')
        build=p['build'] if build is None else build;v.require(p['build']==build,'Mixed build ordinals cannot be paired safely')
        v.integer(p['op'],1,18);v.integer(p['call'],1,4096)
        for k in ['object','qpc','frequency','elapsedQpc']:v.integer(p[k],0,2**64-1)
        for k in ['result','a0','a1']:v.integer(p[k],-2**63,2**63-1)
        v.require((p['op']==1)==(p['object']==0),'Activation/object identity differs')
        call=p['call'];seen.add(call)
        if p['phase']=='begin':
            v.require(call not in pending and call not in closed and p['result']==p['elapsedQpc']==0,'Duplicate or invalid begin')
            pending[call]=(ordinal,row)
        else:
            v.require(call not in closed,'Duplicate terminal');closed.add(call)
            if p['phase']=='abandoned':v.require(p['result']==0,'Abandoned call cannot claim a result')
            if call not in pending:orphans.append({'call':call,'phase':p['phase'],'operation':NAMES[p['op']]});continue
            first,begin=pending.pop(call);b=begin['payload']
            v.require(begin['tid']==row['tid'] and all(p[k]==b[k] for k in ['op','object','qpc','frequency','a0','a1']),'Pair identity/arguments/clock differs')
            error=p['phase']=='end' and ((p['op']==1 and p['result']<0) or (p['op']==2 and p['result']==0) or (p['op']>=6 and p['result']<0))
            pair={'call':call,'operation':NAMES[p['op']],'object':p['object'],'thread':row['tid'],'beginRecord':first,'terminalRecord':ordinal,
                  'phase':p['phase'],'rawResult':p['result'],'returnedError':error,'argument0':p['a0'],'argument1':p['a1'],
                  'elapsedQpc':p['elapsedQpc'],'frequency':p['frequency'],'hostTimingAvailable':p['qpc']>0 and p['frequency']>0 and p['elapsedQpc']>0}
            pairs.append(pair)
            method=methods.setdefault(NAMES[p['op']],{'paired':0,'abandoned':0,'returnedErrors':0,'rawResults':{}})
            method['paired']+=1;method['abandoned']+=p['phase']=='abandoned';method['returnedErrors']+=error
            if p['phase']=='end':method['rawResults'][str(p['result'])]=method['rawResults'].get(str(p['result']),0)+1
    gaps=sorted(set(range(min(seen),max(seen)+1))-seen) if seen else []
    abandoned=sum(p['phase']=='abandoned' for p in pairs)
    return {'schema':'sl3.asio-call-analysis.v1','scope':'Selected own-provider calls in one completed ETL; host identity unverified','build':build,'pid':marker['pid'],
            'recordCount':len(rows),'pairedCalls':len(pairs),'completedCalls':len(pairs)-abandoned,'abandonedCalls':abandoned,
            'eventFileTimeRange':{'first':str(min(stamps)),'last':str(max(stamps))} if stamps else None,
            'unterminatedBegins':sorted(pending),'orphanTerminals':orphans,'callIdGaps':gaps,'moduleCallBudgetReached':4096 in seen,
            'sessionMetadataComplete':complete,'sessionStopStatus':marker['stopStatus'],'reportedEventsLost':marker['eventsLost'],'reportedBuffersLost':marker['buffersLost'],
            'observedPairsComplete':bool(rows) and not pending and not orphans and not abandoned and not gaps,
            'methods':methods,'pairs':pairs,'actualEtwCaptureDecoded':False,'sourceHostIdentityVerified':False,'wholeHostSequenceVerified':False,
            'seratoCaptureVerified':False,'physicalAudioVerified':False,'currentSeratoAdmissionVerified':False,'twoDeckDvsVerified':False}

def sha(path):return hashlib.sha256(v.bounded(path,16*1024*1024)).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--etl',type=Path,required=True);p.add_argument('--session',type=Path,required=True)
    p.add_argument('--configuration',choices=['Release','Debug'],default='Release');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-pid',type=int,help='Require the PID recorded by the independent host observer')
    args=p.parse_args()
    etl=args.etl.absolute();session=args.session.absolute();folder=args.output.absolute()
    v.require(not folder.exists() and not folder.is_symlink() and not folder.is_junction() and folder.parent.is_dir(),'Fresh output directory required')
    marker=v.parse(v.bounded(session,65536));analyze([],marker)
    if args.expected_pid is not None:
        v.require(marker['pid']==args.expected_pid,'Session PID differs from expected observer PID')
    manifest=ROOT/f'artifacts/build/asio-trace-decoder/decoder-build-{args.configuration}.json';m=v.parse(v.bounded(manifest,1024*1024))
    v.require(m['schema']=='sl3.asio-etl-decoder-build.v1' and m['configuration']==args.configuration,'Known decoder build required')
    for source,digest in m['inputs'].items():v.require(sha(ROOT/source)==digest,'Decoder source drift')
    exe=manifest.parent/args.configuration/'sl3_asio_decode_trace.exe';v.require(sha(exe)==m['executableSha256'],'Decoder image drift')
    exe_digest=sha(exe);manifest_digest=sha(manifest)
    sources={name:sha(ROOT/name) for name in ['scripts/analyse-asio-call-log.py','scripts/validate-asio-private-trace.py']}
    etl_digest=sha(etl);marker_digest=sha(session);folder.mkdir();output=folder/'events.jsonl'
    child=subprocess.Popen([str(exe),'--decode',str(etl),str(output),str(marker['pid'])],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    timeout=False
    try:stdout,stderr=child.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        timeout=True;child.kill();stdout,stderr=child.communicate(timeout=5)
    for name,raw in [('stdout.json',stdout),('stderr.txt',stderr)]:
        with (folder/name).open('xb') as f:f.write(raw)
    run={'schema':'sl3.asio-etl-offline-run.v1','configuration':args.configuration,'decoderPid':child.pid,'decoderExitCode':child.returncode,'timedOut':timeout,
         'childExited':child.poll() is not None,'etlSha256':etl_digest,'sessionSha256':marker_digest,'decoderSha256':exe_digest,
         'buildManifestSha256':manifest_digest,'sourceSha256':sources,'deviceAccessByDecoder':False,'seratoExecutedByDecoder':False}
    with (folder/'decoder-run.json').open('x',encoding='utf-8') as f:json.dump(run,f,indent=2);f.write('\n')
    v.require(not timeout and child.returncode==0 and run['childExited'],'Decoder must retire successfully')
    v.require(sha(etl)==etl_digest and sha(session)==marker_digest,'Input evidence changed during decoding')
    v.require(sha(exe)==exe_digest and sha(manifest)==manifest_digest,'Decoder build changed during decoding')
    for source,digest in m['inputs'].items():v.require(sha(ROOT/source)==digest,'Decoder source changed during decoding')
    for name,digest in sources.items():v.require(sha(ROOT/name)==digest,'Analyzer source changed')
    envelope=v.parse(stdout);v.require(envelope=={'schema':'sl3.asio-etl-decode.v1','pid':marker['pid'],'decodedEvents':envelope.get('decodedEvents'),
                  'readerReportedLosses':0,'traceControllerStarted':False,'deviceAccess':False,'seratoExecuted':False} and
                  all(type(envelope[k]) is bool for k in ['traceControllerStarted','deviceAccess','seratoExecuted']),'Exact offline decoder scope required')
    v.integer(envelope['pid'],marker['pid'],marker['pid']);v.integer(envelope['decodedEvents'],0,8192);v.integer(envelope['readerReportedLosses'],0,0)
    v.require(output.is_file() and output.stat().st_size<=8*1024*1024,'Bounded decoded output')
    with output.open('rb') as f:raw=f.read(8*1024*1024+1)
    v.require(len(raw)<=8*1024*1024,'Bounded read')
    rows=[v.parse(line) for line in raw.splitlines()];v.require(len(rows)==envelope['decodedEvents'],'Complete decoder count required')
    result=analyze(rows,marker);result['actualEtwCaptureDecoded']=True
    result['provenance']={'etlSha256':etl_digest,'sessionSha256':marker_digest,'decodedJsonlSha256':hashlib.sha256(raw).hexdigest(),'decoderRunSha256':sha(folder/'decoder-run.json')}
    with (folder/'analysis.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:val for k,val in result.items() if k not in ['pairs','methods']},indent=2))

if __name__=='__main__':main()
