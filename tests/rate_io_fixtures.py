"""Synthetic rate wire/recording fixtures. Never a device recording."""
import json

UTC='2026-10-30T23:00:07Z'
def frame(command,value=0):
    b=bytearray(64);b[:5]=bytes((command,0x1c,0xc5,0,1));b[5:7]=value.to_bytes(2,'big');return b.hex()

def recording(target=44100,initial=48000,pid=123,mismatch=False,short=False,late=False):
    changed=target!=initial
    steps=[(True,frame(0x30)),(False,frame(0x30,initial))]
    if changed and not short:steps += [(True,frame(0x31,target)),(False,frame(0x31,0xffff)),(True,frame(0x30)),(False,frame(0x30,initial if mismatch else target))]
    rows=[{'schema':'sl3.rate-io.v2','event':'header','pid':pid,'target_rate_hz':target,'utc':UTC}];decisions=[]
    for n,(output,raw) in enumerate(steps):
        tick=1000+5*n;count=63 if short and n==1 else 64;completed=4000 if late and n==len(steps)-1 else tick+2
        rows.append({'event':'begin','sequence':n,'output':output,'timeout_ms':100 if output else 300,'adapter_started_ms':tick,'frame_hex':raw if output else None})
        rows.append({'event':'end','sequence':n,'output':output,'adapter_completed_ms':completed-1,'io_return_success':True,'bytes':count,
            'frame_hex':None if output else raw[:2*count],'adapter_invoked':True,'api_attempted':True,'api_accepted':True,'native_terminal':True,
            'adapter_timeout_ms':100 if output else 300,'completion_error':0,'usbd_status':0,'submitted_utc':UTC,'completed_utc':UTC})
        name='deadline' if late and n==len(steps)-1 else 'transfer_failure' if short and n==1 else 'write_retired' if output else 'reply'
        decisions.append({'event':'decision','sequence':n,'output':output,'runner_started_ms':tick,'runner_completed_ms':completed,'transferred':True,'bytes':count,'decision':name})
    error=2 if late else 4 if short else 5 if mismatch else 0
    rows.append({'event':'transaction','started_ms':1000,'budget_ms':3000,'finished_ms':4001 if late else 1000+5*len(steps),'diagnostic_error':error})
    rows+=decisions
    return rows

def text(rows):return ''.join(json.dumps(row,separators=(',',':'))+'\n' for row in rows)

def summary(target=44100,initial=48000,mismatch=False,short=False,late=False):
    changed=target!=initial;error=2 if late else 4 if short else 5 if mismatch else 0
    writes,reads=(1,1) if short or not changed else (3,3)
    return {'schema':'sl3.rate-diagnostic.v2','phase':'finished','utc':UTC,'target_rate_hz':target,'diagnostic_error':error,
        'transaction_error':4 if late or short else 3 if mismatch else 0,'exchange_error':0,'initial_rate_hz':0 if short else initial,
        'verified_rate_hz':0 if error else target,'readback_rate_hz':initial if mismatch else target if changed and not error else 0,
        'write_attempts':writes,'read_attempts':reads,'setter_attempts':int(changed and not short),'control_transfer_attempts':writes+reads,
        'device_may_have_changed':changed and not short,'acknowledgement_received':changed and not short,'last_io_retired':True,'redirect_closed':False,
        'audio_submissions':0,'alternate_changes':0,'automatic_rollback':False,'error':'','rate_io_schema':'sl3.rate-io.v2','rate_io_file':'rate-io.jsonl'}
