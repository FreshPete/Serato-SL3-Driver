"""Inspect completed first-party ASIO metadata logs offline. Never enables tracing or opens hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OPERATIONS=dict(enumerate(('class_object','init','name','version','error','start','stop','channels','latencies',
    'buffer_size','can_rate','get_rate','set_rate','clocks','set_clock','create_buffers','dispose_buffers','panel'),1))
DECODER_SOURCES={'diagnostics/asio-decode/CMakeLists.txt','diagnostics/asio-decode/decode.cpp',
                 'src/asio/call_trace.hpp','scripts/build-asio-trace-decoder.ps1'}


def require(value,text):
    if not value:raise ValueError(text)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate JSON field');result[key]=value
        return result
    def invalid(value):raise ValueError('Nonfinite JSON value')
    return json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=invalid)


def integer(value,low,high):
    require(type(value) is int and low<=value<=high,'Bounded exact integer required')


def marker_state(marker,pid):
    require(type(marker) is dict and set(marker)=={'schema','pid','stopStatus','eventsLost','buffersLost','complete','hardwareStateAssessed'},'Exact logger marker required')
    require(marker['schema']=='sl3.asio-owned-session.v1' and type(marker['pid']) is int and marker['pid']==pid,'Logger PID/schema differs')
    for name in ('stopStatus','eventsLost','buffersLost'):integer(marker[name],0,2**32-1)
    require(type(marker['complete']) is bool and marker['hardwareStateAssessed'] is False,'Typed logger completion required')
    require(marker['complete']==(marker['stopStatus']==marker['eventsLost']==marker['buffersLost']==0),'Logger completion contradicts its losses/status')
    return {'stopped':marker['stopStatus']==0,'complete':marker['complete'],
            'eventsLost':marker['eventsLost'],'buffersLost':marker['buffersLost']}


def summarize(rows,pid,marker,decoder):
    integer(pid,1,2**32-1)
    require(type(rows) is list and len(rows)<=8192,'One bounded trace file required')
    logger=marker_state(marker,pid)
    require(type(decoder) is dict and set(decoder)=={'schema','pid','decodedEvents','readerReportedLosses','traceControllerStarted','deviceAccess','seratoExecuted'},'Exact decoder result required')
    require(decoder['schema']=='sl3.asio-etl-decode.v1' and type(decoder['pid']) is int and decoder['pid']==pid,'Decoder PID/schema differs')
    integer(decoder['decodedEvents'],0,8192);integer(decoder['readerReportedLosses'],0,2**32-1)
    require(decoder['decodedEvents']==len(rows) and all(decoder[k] is False for k in ('traceControllerStarted','deviceAccess','seratoExecuted')),'Decoder count/scope differs')
    envelope={'schema','pid','tid','timestampFileTime','payload'}
    fields={'schema','build','phase','op','object','call','result','a0','a1','qpc','frequency','elapsedQpc'}
    begins={};terminals={};seen_build=set();clock_ok=True;maximum=0
    for row in rows:
        require(type(row) is dict and set(row)==envelope and row['schema']=='sl3.asio-etw-record.v1','Exact event envelope required')
        require(type(row['pid']) is int and row['pid']==pid,'Mixed process records refused');integer(row['tid'],1,2**32-1)
        stamp=row['timestampFileTime'];require(type(stamp) is str and re.fullmatch('[0-9]{1,20}',stamp) and 0<int(stamp)<2**64,'FILETIME text required')
        p=row['payload'];require(type(p) is dict and set(p)==fields and p['schema']=='sl3.asio-call.v1','Exact call payload required')
        require(p['build'] in ('production','session_fixture') and p['phase'] in ('begin','end','abandoned'),'Known build/phase required')
        seen_build.add(p['build']);require(len(seen_build)==1,'Mixed build/module records refused')
        integer(p['op'],1,18);integer(p['object'],0,2**64-1);integer(p['call'],1,4096)
        require((p['object']==0)==(p['op']==1),'Factory/device object identity differs')
        for name in ('qpc','frequency','elapsedQpc'):integer(p[name],0,2**64-1)
        for name in ('result','a0','a1'):integer(p[name],-2**63,2**63-1)
        maximum=max(maximum,p['call']);clock_ok=clock_ok and p['qpc']>0 and p['frequency']>0
        call=p['call']
        if p['phase']=='begin':
            require(call not in begins and call not in terminals,'Duplicate/reordered call ordinal; module boundary is ambiguous')
            require(p['result']==p['elapsedQpc']==0,'Begin cannot report a completed result');begins[call]=row
        else:
            require(call not in terminals,'Duplicate terminal; module boundary is ambiguous')
            if p['phase']=='abandoned':require(p['result']==0,'Abandoned call cannot report success')
            if call in begins:
                start=begins[call];b=start['payload']
                require(row['tid']==start['tid'] and all(p[k]==b[k] for k in ('op','object','a0','a1','qpc','frequency')),'Call pairing identity/clock differs')
                clock_ok=clock_ok and int(stamp)>=int(start['timestampFileTime']) and p['elapsedQpc']>0
            terminals[call]=row
    objects={};factory=[];abandoned=[];orphan=[];complete=0
    for call,row in sorted(terminals.items()):
        p=row['payload']
        if call not in begins:orphan.append(call);continue
        if p['phase']=='abandoned':abandoned.append(call);continue
        complete+=1;op=OPERATIONS[p['op']]
        if p['object']==0:
            factory.append({'call':call,'result':p['result']});continue
        obj=objects.setdefault(p['object'],{'object':p['object'],'completedCalls':{},'lastResults':{},
            'initSuccessObserved':False,'initRejectionObserved':False,'bufferCreationSuccessObserved':False,
            'startReturnSuccessObserved':False,'startFailureObserved':False,'stopReturnSuccessObserved':False,
            'disposeSuccessObserved':False,'nonSuccessReturns':[]})
        obj['completedCalls'][op]=obj['completedCalls'].get(op,0)+1;obj['lastResults'][op]=p['result']
        successful=p['result']==(1 if op=='init' else 0)
        flag={'init':'initSuccessObserved','create_buffers':'bufferCreationSuccessObserved','start':'startReturnSuccessObserved',
              'stop':'stopReturnSuccessObserved','dispose_buffers':'disposeSuccessObserved'}.get(op)
        if flag and successful:obj[flag]=True
        if op=='init' and p['result']==0:obj['initRejectionObserved']=True
        if op=='start' and not successful:obj['startFailureObserved']=True
        if op not in ('name','version','error') and not successful:
            obj['nonSuccessReturns'].append({'call':call,'operation':op,'result':p['result']})
    missing=sorted(set(begins)-set(terminals));budget=maximum>=4096
    unpaired=[]
    for call in sorted(set(missing+orphan+abandoned)):
        p=(begins.get(call) or terminals[call])['payload']
        unpaired.append({'call':call,'operation':OPERATIONS[p['op']],'object':p['object'],
                         'condition':'missing_terminal' if call in missing else 'orphan_terminal' if call in orphan else 'abandoned'})
    return {'schema':'sl3.asio-control-observation.v1','pid':pid,'buildKind':next(iter(seen_build),None),
        'decodedEvents':len(rows),'completeCallPairs':complete,'factoryReturns':factory,
        'objects':list(objects.values()),'missingTerminals':missing,'orphanTerminals':orphan,'abandonedCalls':abandoned,
        'unpairedCalls':unpaired,'maximumCallOrdinal':maximum,
        'logger':logger,'readerReportedLosses':decoder['readerReportedLosses'],'budgetReached':budget,
        'controlClockConsistent':clock_ok,'controlMetadataComplete':logger['complete'] and decoder['readerReportedLosses']==0 and
            not (missing or orphan or abandoned or budget) and clock_ok,
        'absenceOfCallsProvesDriverNotSelected':False,'callbackProgressRecorded':False,'physicalAudioVerified':False,
        'dvsVerified':False,'seratoProcessIdentityVerified':False,'loadedImageIdentityVerified':False,
        'analyzerStartsTracing':False,'analyzerOpensDevice':False}


def bounded(path,limit,empty=False):
    require(path.is_file() and not path.is_symlink() and not path.is_junction(),'Regular completed input required')
    for parent in path.parents:require(not parent.is_symlink() and not parent.is_junction(),'Reparse ancestor refused')
    with path.open('rb') as stream:raw=stream.read(limit+1)
    require((empty or len(raw)>0) and len(raw)<=limit,'Input exceeds file bound')
    return raw


def write_new(path,raw):
    with path.open('xb') as stream:stream.write(raw)


def inspect(directory,build_path,expected,output):
    source_sha=sha(Path(__file__).read_bytes())
    directory,build_path,output=(Path(p).absolute() for p in (directory,build_path,output))
    require(output.parent==ROOT/'analysis' and output.name.startswith('asio-observation-') and not output.exists(),'Fresh direct analysis/asio-observation-* output required')
    raw_marker=bounded(directory/'session.json',65536);marker=parse(raw_marker)
    require(type(marker) is dict,'Object logger marker required');integer(marker.get('pid'),1,2**32-1)
    logger=marker_state(marker,marker['pid']);require(logger['stopped'],'Logger must stop before offline inspection')
    raw_etl=bounded(directory/'private.etl',8*1024*1024)
    raw_build=bounded(build_path,1024*1024);require(sha(raw_build)==expected,'Decoder build identity changed');build=parse(raw_build)
    require(build['schema']=='sl3.asio-etl-decoder-build.v1' and build['configuration']=='Release' and
            build['planAndRefusalTestsPassed'] is True and set(build['inputs'])==DECODER_SOURCES,'Reviewed decoder build required')
    for name,value in build['inputs'].items():require(sha(bounded(ROOT/name,1024*1024))==value,'Decoder source changed')
    executable=build_path.parent/'Release/sl3_asio_decode_trace.exe';exe_raw=bounded(executable,16*1024*1024)
    require(sha(exe_raw)==build['executableSha256'],'Decoder executable changed')
    output.mkdir();write_new(output/'private.etl',raw_etl);write_new(output/'session.json',raw_marker)
    child=subprocess.run([str(executable),'--decode',str(output/'private.etl'),str(output/'events.jsonl'),str(marker['pid'])],
        capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    write_new(output/'decoder-stdout.json',child.stdout);write_new(output/'decoder-stderr.txt',child.stderr)
    require(child.returncode==0,'Completed ETL decoder refused; partial output preserved')
    decoded=parse(child.stdout);raw_rows=bounded(output/'events.jsonl',8*1024*1024,True)
    rows=[parse(line) for line in raw_rows.splitlines()]
    summary=summarize(rows,marker['pid'],marker,decoded)
    require(bounded(directory/'session.json',65536)==raw_marker and bounded(directory/'private.etl',8*1024*1024)==raw_etl,
            'Completed source changed during inspection')
    require(sha(bounded(executable,16*1024*1024))==build['executableSha256'],'Decoder changed during inspection')
    require(sha(Path(__file__).read_bytes())==source_sha and all(sha(bounded(ROOT/name,1024*1024))==value for name,value in build['inputs'].items()),
            'Inspector/decoder source changed during inspection')
    report={'schema':'sl3.completed-asio-observation.v1','summary':summary,'inputEtlSha256':sha(raw_etl),
        'inputMarkerSha256':sha(raw_marker),'decodedRowsSha256':sha(raw_rows),'decoderBuildSha256':expected,
        'decoderExecutableSha256':build['executableSha256'],'inspectorSourceSha256':source_sha,
        'actualCompletedEtlDecoded':True,'inputSourceModified':False,'applicationLaunched':False,
        'traceControllerStarted':False,'deviceOpened':False}
    write_new(output/'observation.json',(json.dumps(report,indent=2)+'\n').encode('utf-8'))
    return report


if __name__=='__main__':
    import sys
    if sys.argv[1:] in ([],['--plan']):
        print(json.dumps({'schema':'sl3.asio-observer-plan.v1','filesWritten':False,'traceControllerStarted':False,
                          'applicationLaunched':False,'deviceOpened':False}))
    else:
        parser=argparse.ArgumentParser(description=__doc__)
        for name in ('completed-directory','decoder-build','expected-decoder-build-sha256','output'):parser.add_argument('--'+name,required=True)
        args=parser.parse_args();print(json.dumps(inspect(args.completed_directory,args.decoder_build,
            args.expected_decoder_build_sha256,args.output),indent=2))
