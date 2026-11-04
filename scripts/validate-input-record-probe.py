"""Validate a finite callback PCM prefix and optionally wrap it as WAV; no device access."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import wave


def require(value,text):
    if not value:raise ValueError(text)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def read(path,maximum):
    require(not path.is_symlink() and not path.is_junction() and 0<path.stat().st_size<=maximum,'Bounded ordinary input file required')
    raw=path.read_bytes();require(0<len(raw)<=maximum,'Input exceeded bound while reading');return raw


def integer(value,minimum=0):
    require(type(value) is int and minimum<=value<2**64,'Invalid integer field');return value


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON key');result[key]=value
    return result


def reject_constant(value):raise ValueError('Nonfinite JSON number')


def validate(folder,worker_sha,simulated=False,host_loopback=False):
    require(re.fullmatch('[0-9a-f]{64}',worker_sha or ''),'Reviewed lowercase worker hash required')
    raw=read(folder/'result.json',262144);result=json.loads(raw,object_pairs_hook=unique,parse_constant=reject_constant)
    require(not (host_loopback and simulated),'Host loopback requires a native record')
    schema='sl3.host-loopback-probe.v1' if host_loopback else 'sl3.input-record-probe.v1'
    require(result.get('schema')==schema and result.get('simulated') is simulated and result.get('successful') is True and result.get('error')=='','Successful expected-kind record required')
    require(result.get('workerSha256')==worker_sha,'Worker image binding differs')
    rate=integer(result.get('observedRateHz'),1);require(rate in (44100,48000) and integer(result.get('expectedRateHz'),1)==rate,'Clock contract differs')
    payload='bounded stereo markers' if host_loopback else 'zero PCM only'
    if host_loopback:
        require(rate==44100 and result.get('markerHz')==[997,1301] and
                integer(result.get('markerFirstFrame'))==8192 and integer(result.get('markerFrames'))==28665,
                'Host loopback marker contract differs')
    target=((rate*3+127)//128)*128
    for name,value in [('nominalRequestedMilliseconds',3000),('bankFrames',128),('channels',6),('sampleBytes',3),('intervals',8),('targetFrames',target),('recordedFrames',target),('recordedCallbacks',target//128),('recorderFault',0),('startupFramesDiscarded',0),('hostFailure',0),('pcmBytes',target*18)]:
        require(integer(result.get(name))==value,'Record geometry/status differs: '+name)
    for name in ['workerStarted','ioRetired','deviceReleased','audioThreadRetired','workerExited','workerJobEmpty','buffersDisposed','streamStarted','pcmSaved']:
        require(result.get(name) is True,'Missing successful retirement/recording evidence: '+name)
    for name in ['forcedTermination','timingProfileWritten','latencyMeasured','physicalMappingVerified','usbContinuityVerified','seratoAdmissionVerified']:
        require(result.get(name) is False,'Unsupported claim/activity: '+name)
    require(integer(result.get('workerInputFrames'))>=target and integer(result.get('outputSubmissions'),1)>0 and integer(result.get('outputCompletions'),1)>0 and
            result.get('audioOutputPayload')==payload,'Stream/output contract differs')
    require(integer(result.get('totalCallbacks'))==target//128+integer(result.get('trailingCallbacksNotRecorded')),'Finite prefix/suffix callback coverage differs')
    frequency=integer(result.get('counterFrequency'),1);require(integer(result.get('collectionElapsedMilliseconds'))<=6000,'Collection deadline exceeded')
    require(result['outputCompletions']<=result['outputSubmissions'],'Output completion/submission counters differ')
    rows=result.get('rows');require(type(rows) is list and len(rows)==target//128,'Complete prefix observations required')
    for n,row in enumerate(rows):
        require(type(row) is list and len(row)==4,'Malformed callback observation')
        frame,publication,ticks,bank=[integer(v) for v in row]
        require(frame==n*128 and ticks>0 and bank in (0,1),'Callback frame/bank origin differs')
        if n:require(publication>=rows[n-1][1] and ticks>=rows[n-1][2] and bank!=rows[n-1][3],'Callback clock/bank sequence differs')
    pcm=read(folder/'input.pcm',8*1024*1024)
    require(len(pcm)==target*18 and sha(pcm)==result.get('pcmSha256'),'PCM length/hash differs')
    journals=list(folder.glob('worker-*.tsv'));native_journal=None
    if simulated:
        require(not journals and result.get('startupJournalSha256')=='','Unexpected native journal in simulation')
    else:
        require(len(journals)==1 and journals[0].name=='worker-1.tsv','Exactly one native worker journal required')
        journal=read(journals[0],65536);require(journal.endswith(b'\n') and sha(journal)==result.get('startupJournalSha256'),'Native journal binding/completeness differs')
        parsed=[]
        for line in journal.decode('ascii').splitlines():
            match=re.fullmatch(r'([0-9]+)\t([0-9]+)\t([a-z_]+\.(?:enter|return))',line)
            require(match is not None,'Malformed native journal')
            tick,pid=int(match[1]),int(match[2]);require(0<tick<2**64 and 0<pid<2**32 and (not parsed or tick>=parsed[-1][0]),'Native journal time/PID invalid')
            parsed.append((tick,pid,match[3]))
        require(len({r[1] for r in parsed})==1,'Multiple native worker PIDs')
        stages=[r[2] for r in parsed];require(stages[:3]==['worker.enter','helper_load.enter','helper_load.return'],'Wrong native journal prefix')
        at=3
        while stages[at:at+2]==['enumerate.enter','enumerate.return']:at+=2
        require(at>3,'Native enumeration missing')
        expected=['configuration.enter','configuration.return','redirect_owner_acquire.enter','redirect_owner_acquire.return',
                  'redirect_start.enter','redirect_start.return','system_handle.enter','system_handle.return','clock_getter.enter','clock_getter.return']
        if host_loopback:
            expected.extend(['audio_controls.enter','audio_controls.return','clock_getter.enter','clock_getter.return',
                             'playback_keepalive.enter','playback_keepalive.return'])
        expected.extend(['redirect_close.enter','redirect_close.return','helper_unload.enter','helper_unload.return'])
        require(stages[at:]==expected,'Unexpected acquisition, control, stream or release journal')
        native_journal={'workerPid':parsed[0][1],'records':len(parsed),'sha256':sha(journal)}
    return {'valid':True,'schema':'sl3.input-record-validation.v1','simulated':simulated,'rateHz':rate,'frames':target,'channels':6,'sampleBytes':3,
            'recordedCallbacks':len(rows),'trailingCallbacksNotRecorded':result['trailingCallbacksNotRecorded'],'counterFrequency':frequency,
            'resultSha256':sha(raw),'nativeJournal':native_journal,'pcmSha256':sha(pcm),'physicalProvenanceVerified':False,'latencyMeasured':False,
            'scope':'Recorded finite callback-prefix/retirement consistency only; logical positions and software times do not prove USB continuity, physical mapping or round-trip latency.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path);parser.add_argument('--worker-sha256',required=True)
    parser.add_argument('--simulated',action='store_true');parser.add_argument('--wav-output',type=Path);args=parser.parse_args()
    result=validate(args.folder,args.worker_sha256,args.simulated)
    if args.wav_output:
        require(not args.wav_output.exists() and args.wav_output.parent.is_dir(),'Fresh WAV output in existing parent required')
        payload=read(args.folder/'input.pcm',8*1024*1024)
        require(sha(payload)==result['pcmSha256'] and sha(read(args.folder/'result.json',262144))==result['resultSha256'],'Input changed before WAV export')
        stream=io.BytesIO()
        with wave.open(stream,'wb') as wav:
            wav.setnchannels(6);wav.setsampwidth(3);wav.setframerate(result['rateHz']);wav.writeframes(payload)
        data=stream.getvalue()
        with args.wav_output.open('xb') as output:output.write(data)
        result['wavSha256']=sha(data);result['wavBytes']=len(data)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,UnicodeError) as error:
        print(json.dumps({'valid':False,'error':str(error)}));raise SystemExit(1)
