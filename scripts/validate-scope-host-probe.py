"""Read-only checks for the metadata-only facade-scope diagnostic."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re


def require(ok,message):
    if not ok:raise ValueError(message)


def validate(folder,worker_sha,simulated=False):
    path=folder/'probe.json';require(0<path.stat().st_size<=65536,'Invalid scope record size')
    raw=path.read_bytes();r=json.loads(raw)
    require(re.fullmatch('[0-9a-f]{64}',worker_sha) and r['worker_sha256']==worker_sha,'Worker identity differs')
    require(r['schema']=='sl3.facade-scope-probe.v1' and r['phase']=='finished' and r['finished'] is True and
            r['successful'] is True and r['error']==r['failed_phase']=='' and r['simulated'] is simulated,'Scope result failed or kind differs')
    times=[datetime.fromisoformat(r[k].replace('Z','+00:00')) for k in ('started_utc','completed_utc')]
    require(all(t.tzinfo is not None for t in times) and times[0]<=times[1],'Invalid scope UTC bounds')
    require(type(r['probe_pid']) is int and r['probe_pid']>0 and type(r['object_attempts']) is int and r['object_attempts']==3,'Wrong process/object count')
    for key in ('audio_start_attempts','rate_setters','firmware_requests'):
        require(type(r[key]) is int and r[key]==0,'Forbidden scope operation: '+key)
    for key in ('buffers_created','timing_calibration_verified','serato_admission_verified'):
        require(r[key] is False,'Unproved scope claim: '+key)
    require(type(r['objects']) is list and len(r['objects'])==3,'Wrong completed metadata count')
    rates=[]
    for i,row in enumerate(r['objects']):
        rate=row['rate_hz'];require(type(rate) is int and rate in (44100,48000),'Invalid getter rate')
        require(all(type(row[k]) is int for k in ('index','inputs','outputs')),'Invalid metadata integer type')
        require(row=={'index':i,'rate_hz':rate,'inputs':6,'outputs':6,'packed_24':True,'channels_inactive':True,'latency_unavailable':True} and
                all(row[k] is True for k in ('packed_24','channels_inactive','latency_unavailable')),'Invalid no-audio metadata')
        rates.append(rate)
    require(len(set(rates))==1,'Clock changed across diagnostic objects')
    final=r['final']
    for key in ('io_retired','device_released','audio_retired','process_started','process_exited','private_job_empty'):
        require(final[key] is True,'Incomplete final retirement: '+key)
    require(final['device_held'] is False and final['termination_requested'] is False,'Retained or forced final release')
    for key in ('failure','audio_callbacks','input_submissions','output_submissions'):
        require(type(final[key]) is int and final[key]==0,'Failure or audio activity: '+key)
    journals=list(folder.glob('worker-*.tsv'))
    native_journal=None
    if simulated:require(not journals,'Simulated result contains native journal')
    else:
        require(len(journals)==1 and journals[0].name=='worker-1.tsv','Expected one native worker journal')
        data=journals[0].read_bytes();require(0<len(data)<=65536 and data.endswith(b'\n'),'Incomplete native journal')
        rows=[line.split('\t') for line in data.decode('ascii').splitlines()]
        require(all(len(row)==3 and row[0].isdigit() and row[1].isdigit() for row in rows),'Malformed native scope journal')
        require(len({row[1] for row in rows})==1 and 0<int(rows[0][1])<2**32 and
                all(int(row[0])<2**64 for row in rows) and [int(row[0]) for row in rows]==sorted(int(row[0]) for row in rows),'Invalid journal worker/times')
        stages=[row[2] for row in rows];at=3
        require(stages[:3]==['worker.enter','helper_load.enter','helper_load.return'],'Invalid journal prefix')
        while stages[at:at+2]==['enumerate.enter','enumerate.return']:at+=2
        require(at>3,'No recorded enumeration')
        expected=['configuration.enter','configuration.return','redirect_owner_acquire.enter','redirect_owner_acquire.return',
                  'redirect_start.enter','redirect_start.return','system_handle.enter','system_handle.return']+[
                  'clock_getter.enter','clock_getter.return']*3+['redirect_close.enter','redirect_close.return','helper_unload.enter','helper_unload.return']
        require(stages[at:]==expected,'Expected one acquisition, three clock getters and one release only')
        native_journal={'name':journals[0].name,'workerPid':int(rows[0][1]),'records':len(rows),'sha256':hashlib.sha256(data).hexdigest()}
    return {'valid':True,'simulated':simulated,'rateHz':rates[0],'metadataObjects':3,'recordSha256':hashlib.sha256(raw).hexdigest(),
            'probeRecordSha256':hashlib.sha256(raw).hexdigest(),'nativeJournal':native_journal,
            'scope':'Recorded facade/clock/ownership consistency only; not COM, audio, latency, Serato or reopen readiness'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path);parser.add_argument('--worker-sha256',required=True)
    parser.add_argument('--simulated',action='store_true');args=parser.parse_args()
    try:print(json.dumps(validate(args.folder,args.worker_sha256,args.simulated),indent=2))
    except (ValueError,OSError,KeyError,TypeError,UnicodeError) as error:
        print(json.dumps({'valid':False,'error':str(error)}));raise SystemExit(1)
