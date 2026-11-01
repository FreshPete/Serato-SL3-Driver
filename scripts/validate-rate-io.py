"""Replay bounded rate I/O records. Consistency only; never permission or physical attestation."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re


def require(ok,message):
    if not ok:raise ValueError(message)

def uint(value,bits=64):return type(value) is int and 0<=value<2**bits

def utc(text):
    require(type(text) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})',text),'Invalid recording UTC')
    return datetime.fromisoformat(text.replace('Z','+00:00'))

def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON key');result[key]=value
    return result

def keys(row,names):require(type(row) is dict and set(row)==set(names.split()),'Unexpected recording fields')
def hex_frame(value,count):
    require(type(value) is str and len(value)==2*count and re.fullmatch('[0-9a-f]*',value) is not None,'Invalid raw frame')
    return bytes.fromhex(value)

def parse(path,allow_prefix=False):
    with Path(path).open('rb') as stream:raw=stream.read(47*2048+1)
    require(0<len(raw)<=47*2048,'Empty/oversized recording')
    tail=0
    if not raw.endswith(b'\n'):
        require(allow_prefix,'Torn recording suffix');last=raw.rfind(b'\n');require(last>=0,'No complete header');tail=len(raw)-last-1;body=raw[:last+1]
    else:body=raw
    lines=body.splitlines(keepends=True);require(1<=len(lines)<=47 and all(len(line)<=2048 for line in lines),'Recording row bound exceeded')
    rows=[json.loads(line.decode('utf-8'),object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON'))) for line in lines]
    header=rows[0];keys(header,'schema event pid target_rate_hz utc')
    require(header['schema']=='sl3.rate-io.v2' and header['event']=='header' and uint(header['pid'],32) and header['pid']>0 and
        type(header['target_rate_hz']) is int and header['target_rate_hz'] in (44100,48000),'Wrong recording header/version')
    utc(header['utc']);pairs=[];pending=None;transaction=None;decisions=[]
    for row in rows[1:]:
        event=row.get('event') if type(row) is dict else None
        if event=='begin':
            keys(row,'event sequence output timeout_ms adapter_started_ms frame_hex')
            require(transaction is None and pending is None and len(pairs)<15 and type(row['output']) is bool and
                uint(row['sequence'],32) and row['sequence']==len(pairs) and uint(row['timeout_ms'],32) and
                1<=row['timeout_ms']<=(100 if row['output'] else 300) and uint(row['adapter_started_ms']),'Invalid recording begin/order')
            if row['output']:hex_frame(row['frame_hex'],64)
            else:require(row['frame_hex'] is None,'Input intent invents returned bytes')
            pending=row
        elif event=='end':
            keys(row,'event sequence output adapter_completed_ms io_return_success bytes frame_hex adapter_invoked api_attempted api_accepted native_terminal adapter_timeout_ms completion_error usbd_status submitted_utc completed_utc')
            require(pending is not None and transaction is None and uint(row['sequence'],32) and row['sequence']==pending['sequence'] and
                type(row['output']) is bool and row['output'] is pending['output'],'End lacks matching begin')
            for key in ('adapter_completed_ms','bytes','usbd_status'):require(uint(row[key]),'Invalid end integer')
            for key in ('adapter_timeout_ms','completion_error'):require(uint(row[key],32),'Invalid native status/timeout')
            for key in ('io_return_success','adapter_invoked','api_attempted','api_accepted','native_terminal'):require(type(row[key]) is bool,'Invalid native flag')
            require(row['adapter_invoked'] is True and row['native_terminal'] is row['api_attempted'] and
                (not row['api_accepted'] or row['api_attempted']),'Native retirement/submission facts differ')
            require(row['adapter_timeout_ms']<=pending['timeout_ms'],'Native wait exceeded requested timeout')
            if row['api_attempted']:
                require(row['adapter_timeout_ms']>0 and utc(header['utc'])<=utc(row['submitted_utc'])<=utc(row['completed_utc']),'Invalid native submission/completion order')
                require(row['api_accepted'] or row['completion_error']>0,'Rejected API call lacks native failure')
            else:
                require(not row['api_accepted'] and row['submitted_utc'] is None and row['completed_utc'] is None and
                    row['adapter_timeout_ms']==row['completion_error']==row['usbd_status']==row['bytes']==0,'Unsubmitted request invents native facts')
            require(not row['io_return_success'] or (row['api_accepted'] and not row['completion_error'] and not row['usbd_status']),'Successful I/O contradicts native status')
            if row['output']:require(row['frame_hex'] is None,'Output completion invents received frame')
            else:hex_frame(row['frame_hex'],min(row['bytes'],64))
            pairs.append((pending,row));pending=None
        elif event=='transaction':
            keys(row,'event started_ms budget_ms finished_ms diagnostic_error')
            require(pending is None and transaction is None and uint(row['started_ms']) and uint(row['finished_ms']) and
                uint(row['budget_ms'],32) and type(row['diagnostic_error']) is int and row['diagnostic_error'] in (0,2,3,4,5),'Invalid transaction metadata/order')
            transaction=row
        elif event=='decision':
            keys(row,'event sequence output runner_started_ms runner_completed_ms transferred bytes decision')
            require(transaction is not None and uint(row['sequence'],32) and row['sequence']==len(decisions)<len(pairs) and
                type(row['output']) is bool and type(row['transferred']) is bool and uint(row['runner_started_ms']) and
                uint(row['runner_completed_ms']) and uint(row['bytes']) and row['decision'] in
                ('write_retired','notification','reply','exchange_failure','cancelled','deadline','transfer_failure'),'Invalid decision/order')
            decisions.append(row)
        else:raise ValueError('Unknown recording event')
    complete=not tail and pending is None and transaction is not None and len(decisions)==len(pairs)
    require(allow_prefix or complete,'Incomplete recording')
    return header,pairs,transaction,decisions,complete,tail,hashlib.sha256(raw).hexdigest()

def exchange(frame,command,received):
    if frame[0]==command:
        if frame[1:5]!=bytes((0x1c,0xc5,0,1)):return 'exchange_failure',2,0
        value=int.from_bytes(frame[5:7],'big')
        if command==0x30 and value not in (44100,48000):return 'exchange_failure',4,0
        return 'reply',0,value
    tag={0x34:1,0x38:2,0x39:3}.get(frame[0])
    if tag is None:return 'exchange_failure',3,0
    if frame[1:5]!=bytes((0,0,0,tag)):return 'exchange_failure',2,0
    if received>=4:return 'exchange_failure',5,0
    return 'notification',0,0

def replay(header,pairs,transaction,decisions):
    target=header['target_rate_hz'];start=transaction['started_ms'];budget=transaction['budget_ms'];finish=transaction['finished_ms']
    phase='inspect_ready';initial=verified=readback=writes=reads=setters=received=0;ack=False;error=txn=detail=0
    previous=None
    for index,((begin,end),decision) in enumerate(zip(pairs,decisions)):
        require(phase not in ('complete','failed'),'I/O after terminal transaction')
        output=phase.endswith('_ready');require(begin['output'] is output,'Request direction contradicts transaction')
        a,b=decision['runner_started_ms'],decision['runner_completed_ms']
        require(start<=a and a-start<budget and (previous is None or previous<=a),'I/O begins outside deadline/order')
        require(begin['timeout_ms']==min(100 if output else 300,budget-(a-start)),'Requested wait differs from runner budget')
        require(decision['output'] is output and decision['transferred'] is end['io_return_success'] and decision['bytes']==end['bytes'],'Decision differs from retired adapter return')
        if output:
            command=0x31 if phase=='set_ready' else 0x30;frame=bytearray(64);frame[:5]=bytes((command,0x1c,0xc5,0,1))
            if command==0x31:frame[5:7]=target.to_bytes(2,'big');setters+=1
            require(hex_frame(begin['frame_hex'],64)==frame,'Unexpected control request/payload')
            writes+=1;received=0;phase=phase.replace('_ready','_wait')
        else:reads+=1
        require(writes<=3 and reads<=12 and setters<=1,'Transaction bounds exceeded')
        name=decision['decision'];expired=b<a or b<start or b-start>=budget
        if name not in ('deadline','cancelled'):
            require(not expired and a<=begin['adapter_started_ms']<=end['adapter_completed_ms']<=b,'Accepted/failed transfer has invalid timing')
        if name=='cancelled':error,txn,phase=3,4,'failed'
        elif name=='deadline':require(expired,'Deadline decision has no expired clock');error,txn,phase=2,4,'failed'
        elif name=='transfer_failure':
            require(not end['io_return_success'] or end['bytes']!=64,'Transfer failure contradicts returned I/O');error,txn,phase=4,4,'failed'
        else:
            require(end['io_return_success'] and end['bytes']==64,'Accepted exchange lacks complete successful I/O')
            if output:require(name=='write_retired','Write cannot consume a reply')
            else:
                received+=1;kind,code,value=exchange(hex_frame(end['frame_hex'],64),command,received)
                require(name==kind,'Recorded frame acceptance differs from replay')
                if code:error,txn,detail,phase=5,2,code,'failed'
                elif kind=='reply':
                    if phase=='inspect_wait':
                        initial=value
                        if value==target:verified=value;phase='complete'
                        else:phase='set_ready'
                    elif phase=='set_wait':ack=True;phase='verify_ready'
                    else:
                        require(phase=='verify_wait','Reply outside expected verification');readback=value
                        if value==target:verified=value;phase='complete'
                        else:error,txn,phase=5,3,'failed'
        previous=b
    if phase not in ('complete','failed'):
        error=transaction['diagnostic_error'];txn=4
        require(error in (2,3,5),'Unfinished exchange has no abort reason')
        if error==2:require(finish<start or finish-start>=budget,'Pre-I/O deadline did not expire')
        if error==5:require(len(pairs)==15,'Operation-bound abort lacks full attempt budget')
    require(error==transaction['diagnostic_error'],'Final error differs from replay')
    require(previous is None or error==2 or previous<=finish,'Transaction finish precedes last return')
    return {'target_rate_hz':target,'diagnostic_error':error,'transaction_error':txn,'exchange_error':detail,
        'initial_rate_hz':initial,'verified_rate_hz':verified,'readback_rate_hz':readback,'write_attempts':writes,'read_attempts':reads,
        'setter_attempts':setters,'control_transfer_attempts':writes+reads,'device_may_have_changed':bool(setters),'acknowledgement_received':ack}

def validate(path,summary=None,expected_pid=None,allow_prefix=False):
    header,pairs,transaction,decisions,complete,tail,sha=parse(path,allow_prefix)
    require(expected_pid is None or (type(expected_pid) is int and expected_pid==header['pid']),'Recording worker PID differs')
    submissions=[e['submitted_utc'] for _,e in pairs if e['submitted_utc'] is not None]
    completions=[e['completed_utc'] for _,e in pairs if e['completed_utc'] is not None]
    result={'validRecordingConsistency':True,'scope':'Software record consistency only; no independent USB/clock, cleanup, recovery or audio attestation',
        'complete':complete,'createdUtc':header['utc'],'firstSubmittedUtc':min(submissions,key=utc) if submissions else None,
        'lastCompletedUtc':max(completions,key=utc) if completions else None,'recordingSha256':sha,'workerPid':header['pid'],'targetRateHz':header['target_rate_hz'],
        'rawReturns':len(pairs),'decisions':len(decisions),'tornSuffixBytes':tail,'operationVerified':False,'summaryMatched':False,
        'rateRestorationVerified':False,'replayedObservation':None,
        'failedTransfers':[{'sequence':b['sequence'],'output':b['output'],'completionError':e['completion_error'],'usbdStatus':e['usbd_status'],
            'apiAttempted':e['api_attempted'],'apiAccepted':e['api_accepted'],'bytes':e['bytes']} for b,e in pairs
            if not e['io_return_success'] or e['bytes']!=64 or e['completion_error'] or e['usbd_status']]}
    if complete:
        observation=replay(header,pairs,transaction,decisions);result['replayedObservation']=observation
        result['operationVerified']=observation['diagnostic_error']==0
        if summary is not None:
            require(summary.get('rate_io_schema')=='sl3.rate-io.v2' and summary.get('rate_io_file')=='rate-io.jsonl','Missing canonical recording reference')
            for key,value in observation.items():require(type(summary.get(key)) is type(value) and summary[key]==value,'Recording/summary differs: '+key)
            require(utc(header['utc'])<=utc(summary['utc']),'Summary predates recording creation')
            require(transaction['budget_ms']==3000,'Unexpected native transaction budget')
            for _,end in pairs:
                if end['completed_utc'] is not None:require(utc(end['completed_utc'])<=utc(summary['utc']),'Native I/O follows summary')
            result['summaryMatched']=True
    else:require(summary is None,'An incomplete prefix cannot qualify a completed summary')
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--record',type=Path,required=True)
    parser.add_argument('--summary',type=Path);parser.add_argument('--expected-pid',type=int);parser.add_argument('--allow-prefix',action='store_true');args=parser.parse_args()
    summary=json.loads(args.summary.read_text(encoding='utf-8-sig')) if args.summary else None
    print(json.dumps(validate(args.record,summary,args.expected_pid,args.allow_prefix),indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,UnicodeError) as error:
        print(json.dumps({'validRecordingConsistency':False,'error':str(error)}));raise SystemExit(1)
