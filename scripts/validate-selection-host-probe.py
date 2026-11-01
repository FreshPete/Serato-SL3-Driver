"""Offline setting-probe consistency; not physical trace/recovery acceptance."""
import argparse
import importlib.util
from pathlib import Path
import re
import struct

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('selection_controls',ROOT/'scripts/validate-controls-host-probe.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
require,read,digest=base.require,base.read,base.digest


def target(value):
    require(type(value) is dict and set(value)=={'setting','group','value'},'Invalid target fields')
    require(value['setting'] in ('sensitivity','through') and base.uint(value['group'],3)
            and base.uint(value['value'],16 if value['setting']=='sensitivity' else 2),'Invalid target range/type')
    return (0 if value['setting']=='sensitivity' else 1,value['group'],value['value'])


def decode_wire(text,expected):
    kind,group,value=target(expected)
    require(type(text) is str and re.fullmatch('[0-9a-f]{264}',text) is not None,'Invalid selection wire size/hex')
    raw=bytes.fromhex(text);w=struct.unpack('<16I',raw[:64])
    require(w[:5]==(0x53334c53,1,kind,group,value) and not w[13] and not w[14] and not w[12]&~31,
            'Wrong wire version/target/reserved fields')
    error,selection_error,exchange,phase,writes,reads,setters,flags=w[5:13]
    require(error<=7 and error!=2 and selection_error<=4 and exchange<=6 and phase<=7,'Invalid outcome enums')
    require(writes<=3 and reads<=12 and setters<=1 and reads<=4*writes and bool(flags&1)==(setters==1),'Inconsistent transfer/uncertainty counts')
    tables=[]
    for n,bit in enumerate((2,4,8)):
        data=raw[64+22*n:86+22*n]
        require(bool(flags&bit) or not any(data),'Noncanonical absent table')
        tables.append(list(data) if flags&bit else None)
    initial,observed,verified=tables;ack=list(raw[130:]) if flags&16 else None
    require(ack is not None or not any(raw[130:]),'Noncanonical absent receipt')
    field=((3,9,15) if kind==0 else (8,14,20))[group]
    require((initial is not None)==(observed is not None),'Initial/observed presence differs')
    require(writes<2 or (setters==1 and initial is not None),'Setter lacks initial observation')
    require(not setters or (writes>=2 and initial is not None and initial[field]!=value),'Invalid setter initial/target')
    require(writes!=3 or ack is not None,'Verification request lacks receipt')
    require(ack is None or (setters==1 and writes>=2 and reads>=2),'Receipt without setter/read')
    require(initial is None or (writes>=1 and reads>=1),'Observation without transfer')
    require(initial is None or (ack is not None and writes==3) or initial==observed,'Unverified observation changed before readback')
    if error==0:
        require(phase==6 and selection_error==exchange==0 and initial is not None and observed is not None and verified==observed
                and verified[field]==value,'Inconsistent verified result')
        require((writes==3 and reads>=3 and ack is not None) if setters else
                (writes==1 and reads>=1 and ack is None and initial==verified),'Invalid success transfer sequence')
    else:
        require(phase==7 and verified is None and selection_error!=0 and (initial is None or initial[field]!=value),'Failed outcome claims verification/no-op')
        if error==7:
            require(selection_error==3 and exchange==0 and writes==3 and reads>=3 and ack is not None and observed is not None
                    and observed[field]!=value,'Invalid readback mismatch evidence')
        elif error==6:
            require((selection_error==2 and exchange!=0) or (selection_error==4 and exchange==0),'Invalid protocol failure')
        else:require(selection_error==4 and exchange==0,'Invalid aborted I/O failure')
        if error==1:require(writes==reads==setters==0 and initial is None,'Invalid budget attempted I/O')
    return {'error':error,'selectionError':selection_error,'exchangeError':exchange,'phase':phase,
            'writes':writes,'reads':reads,'setters':setters,'deviceMayHaveChanged':bool(flags&1),
            'initial':initial,'observed':observed,'verified':verified,'acknowledgement':ack,'nativeError':w[15]}


def journal(path,requested,received,outcome):
    require(0<path.stat().st_size<=65536,'Empty/oversized selection journal')
    raw=path.read_bytes();require(raw.endswith(b'\n'),'Incomplete selection journal')
    rows=[]
    for line in raw.decode('ascii').splitlines():
        match=re.fullmatch(r'([0-9]+)\t([0-9]+)\t([a-z_]+\.(?:enter|return))',line)
        require(match is not None,'Malformed selection journal')
        tick,pid=int(match[1]),int(match[2]);require(base.uint(tick) and 0<pid<2**32 and (not rows or tick>=rows[-1][0]),'Invalid journal clock/PID')
        rows.append((tick,pid,match[3]))
    require(len({r[1] for r in rows})==1,'Multiple selection workers')
    stages=[r[2] for r in rows];kind,group,value=target(requested)
    names=('zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve','thirteen','fourteen','fifteen')
    prefix=['worker.enter','control_target_'+requested['setting']+'.enter','control_group_'+names[group]+'.enter',
            'control_value_'+names[value]+'.enter','helper_load.enter','helper_load.return']
    require(stages[:len(prefix)]==prefix,'Journal target/helper prefix differs');at=len(prefix)
    start=at
    while stages[at:at+2]==['enumerate.enter','enumerate.return']:at+=2
    require(at>start,'Missing selection enumeration')
    expected=['configuration.enter','configuration.return','redirect_start.enter','redirect_start.return','system_handle.enter','system_handle.return',
              'clock_getter.enter','clock_getter.return','audio_controls.enter','audio_controls_write.enter','audio_controls_write.return']+[
              'audio_controls_read.enter','audio_controls_read.return']*received+['audio_controls.return','audio_control_selection.enter']
    require(stages[at:at+len(expected)]==expected,'Expected one acquire/clock/baseline before selection');at+=len(expected)
    total=0
    for operation in range(outcome['writes']):
        setter=outcome['setters']==1 and operation==1
        stem='audio_control_selection_set' if setter else 'audio_controls_write'
        require(stages[at:at+2]==[stem+'.enter',stem+'.return'],'Selection request order differs');at+=2
        count=0
        while stages[at:at+2]==['audio_controls_read.enter','audio_controls_read.return']:count+=1;at+=2
        require(1<=count<=4,'Selection reply/notification count differs');total+=count
    require(total==outcome['reads'],'Selection journal/read count differs')
    tail=['audio_control_selection_'+('possible_write' if outcome['deviceMayHaveChanged'] else 'no_write')+'.return',
          'audio_control_selection_verified.return','audio_control_selection.return','redirect_close.enter','redirect_close.return',
          'helper_unload.enter','helper_unload.return']
    require(stages[at:]==tail,'Selection result/release suffix differs')
    return {'sha256':digest(path),'records':len(rows),'workerPid':rows[0][1],'redirects':1,'baselineReads':received,
            'selectionReads':total,'selectionWrites':outcome['writes'],'setters':outcome['setters'],'closes':1}


def probe(folder,worker_sha,simulated=False):
    require(type(simulated) is bool,'Expected explicit simulated/native kind')
    require(re.fullmatch('[0-9a-fA-F]{64}',worker_sha) is not None,'Invalid expected worker hash')
    require(all(0<(folder/name).stat().st_size<=65536 for name in ('probe.json','request.json')),'Empty/oversized selection record')
    data=read(folder/'probe.json');request=read(folder/'request.json');requested=data['target'];target(requested)
    for record in (data,request):
        require(record['schema']=='sl3.selection-host-probe.v2' and record['simulated'] is simulated and
                type(record['worker_sha256']) is str and record['worker_sha256'].lower()==worker_sha.lower() and
                type(record['device_protocol_version']) is int and record['device_protocol_version']==3,'Kind/version/worker differs')
        require(record['target']==requested and target(record['target'])==target(requested),'Request/result target differs')
        for name in ('audio_start_attempts','alternate_changes_requested','rate_changes','firmware_requests'):
            require(base.uint(record[name]) and record[name]==0,'Unexpected audio/rate/firmware operation')
        base.flags(record,no=('audio_buffers_created','calibration_verified','analogue_signal_verified','asio_com_registered'))
        reviewed=record['reviewed_baseline_raw_controls']
        require((reviewed is None and simulated) or (type(reviewed) is list and len(reviewed)==22 and all(base.uint(x,256) for x in reviewed)),
                'Native selection needs an exact reviewed baseline')
    require(request['reviewed_baseline_raw_controls']==data['reviewed_baseline_raw_controls'],'Reviewed baseline changed after launch')
    require(request['phase']=='preparing' and all(type(request[k]) is int and request[k]==0 for k in
            ('acquisition_attempts','baseline_query_attempts','selection_attempts')),'Initial request already claims operation')
    base.flags(request,no=('successful','finished','acquisition_verified','publication_pending','command_attempted','outcome_unknown','device_may_have_changed','operation_verified'))
    require(request['outcome_wire_hex'] is None and request['baseline_raw_controls'] is None and request['baseline_received_frames'] is None and request['error']=='','Initial request invents evidence')
    for name in ('acquisition','after_baseline','after_selection','final'):
        require(type(request[name]) is dict and type(data[name]) is dict and request[name].keys()==data[name].keys(),'Initial owner fields differ')
        for key,value in request[name].items():
            if type(data[name][key]) is bool:require(type(value) is bool and value is (key in ('io_retired','device_released','audio_thread_retired')),'Initial request already claims live owner/activity')
            else:require(type(value) is int and value==0,'Initial request already claims owner observation')
    require(data['phase']=='finished' and data['error']=='','Unfinished/failed selection probe')
    base.flags(data,yes=('successful','finished','acquisition_verified','command_attempted','operation_verified'),no=('publication_pending','outcome_unknown'))
    require(all(type(data[k]) is int and data[k]==1 for k in ('acquisition_attempts','baseline_query_attempts','selection_attempts')),'Expected one acquisition/baseline/selection')
    baseline=data['baseline_raw_controls'];received=data['baseline_received_frames']
    require(type(baseline) is list and len(baseline)==22 and all(base.uint(x,256) for x in baseline) and base.uint(received) and 1<=received<=4,'Invalid baseline')
    require(data['reviewed_baseline_raw_controls'] is None or data['reviewed_baseline_raw_controls']==baseline,'Fresh table differs from reviewed baseline')
    outcome=decode_wire(data['outcome_wire_hex'],requested)
    require(outcome['error']==0 and outcome['verified'] is not None and data['device_may_have_changed'] is outcome['deviceMayHaveChanged'],'Unverified/contradictory operation')
    require(not outcome['setters'] or outcome['initial']==baseline,'Setter initial table differs from recorded baseline')
    for name,released in (('acquisition',False),('after_baseline',False),('after_selection',False),('final',True)):base.owner(data[name],released)
    require(len({data[name]['rate_hz'] for name in ('acquisition','after_baseline','after_selection','final')})==1,'Cached clock identity differs')
    require(data['after_selection']['native_error']==outcome['nativeError'],'Owner/operation native error differs')
    journals=list(folder.glob('worker-*.tsv'))
    if simulated:require(not journals,'Simulated probe contains native journal');native=None
    else:
        require(len(journals)==1 and journals[0].name=='worker-1.tsv','Expected one native selection journal')
        native=journal(journals[0],requested,received,outcome)
    return {'valid':True,'scope':'Recorded selection/result/ownership consistency only; physical trace, security/recovery and analogue validation are separate',
            'simulated':simulated,'workerSha256':worker_sha.lower(),'target':requested,'outcome':outcome,
            'probeRecordSha256':digest(folder/'probe.json'),'requestRecordSha256':digest(folder/'request.json'),'nativeJournal':native}


def main():
    import json
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--probe',type=Path,required=True)
    parser.add_argument('--worker-sha256',required=True);parser.add_argument('--expect-simulated',action='store_true');args=parser.parse_args()
    print(json.dumps(probe(args.probe,args.worker_sha256,args.expect_simulated),indent=2))


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,UnicodeError) as error:
        import json
        print(json.dumps({'valid':False,'error':str(error)}));raise SystemExit(1)
