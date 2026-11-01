"""Actual held-rate probe process checks; simulated positives and native safe negatives only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def require(ok,reason):
    if not ok:raise RuntimeError(reason)

def execute(args,expected):
    result=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=45)
    require(result.returncode==expected,f'Exit {result.returncode} expected {expected}: {result.stderr}')
    return result

def main():
    require(len(sys.argv)==5,'Four reviewed executable paths required')
    native,simulated,fixture,worker=[Path(x).resolve() for x in sys.argv[1:]];root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('rate_probe_validator',root/'scripts/validate-rate-host-probe.py')
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    folder=Path(tempfile.mkdtemp(prefix='rate-probe-software-',dir=root/'tests/results/local'))
    helper=folder/'absent-helper.dll';sha=hashlib.sha256(fixture.read_bytes()).hexdigest()
    options=['--worker',fixture,'--worker-sha256',sha,'--helper',helper,'--output']
    for target in (44100,48000):
        output=folder/str(target);args=[simulated,'--select-rate',*options,output,'--target',str(target),'--expected-initial','48000']
        execute(args,0);checked=v.probe(output,sha,True);o=checked['outcome']['observation']
        require(o['setter_attempts']==int(target!=48000) and o['verified_rate_hz']==target,'Change/no-op result differs')
        require('utc' not in o and 'last_io_retired' not in o and 'redirect_closed' not in o,'Synthetic decoder envelope leaked into evidence')
        saved=(output/'request.json').read_bytes();execute(args,1);require((output/'request.json').read_bytes()==saved,'Existing request overwritten')
        original=v.read(output/'probe.json')
        for field,value in [('successful',False),('operation_verified',False),('outcome_unknown',True),('publication_pending',True),
                            ('device_may_have_changed',not bool(o['setter_attempts'])),('acquisition_attempts',2),('selection_attempts',0),
                            ('audio_start_attempts',1),('target_rate_hz',48000 if target==44100 else 44100)]:
            bad=dict(original);bad[field]=value;(output/'probe.json').write_text(json.dumps(bad),encoding='utf-8')
            try:v.probe(output,sha,True)
            except (ValueError,KeyError,TypeError):pass
            else:raise RuntimeError('Contradictory probe accepted: '+field)
        (output/'probe.json').write_text(json.dumps(original),encoding='utf-8');v.probe(output,sha,True)
    for mode in ('rate-mismatch','rate-transfer','rate-transfer-close','rate-success-close','rate-throw','rate-bad','rate-hang','normal','fail-acquire','invalid-clock'):
        output=folder/mode;execute([simulated,'--select-rate',*options,output,'--target','44100','--fixture-mode',mode],1)
        record=v.read(output/'probe.json');require(record['successful'] is False and record['audio_start_attempts']==0,'Fault became success/audio')
        if mode in ('rate-mismatch','rate-transfer','rate-transfer-close','rate-success-close'):
            require(record['outcome_wire_hex'] is not None,'Accepted rate outcome lost')
            o=v.decode_wire(record['outcome_wire_hex'],44100)['observation']
            require(o['device_may_have_changed'] and (o['verified_rate_hz']==44100)==(mode=='rate-success-close'),'Partial/complete clock evidence differs')
            if mode=='rate-mismatch':require(o['readback_rate_hz']==48000,'Actual wrong readback lost')
        if mode in ('rate-throw','rate-bad','rate-hang'):
            require(record['outcome_wire_hex'] is None and record['outcome_unknown'] is True and record['device_may_have_changed'] is True,'Unknown rate outcome invented certainty')
        if mode=='normal':require(record['rejected_before_operation'] is True and record['device_may_have_changed'] is False,'Unsupported adapter acquired setter uncertainty')
        try:v.probe(output,sha,True)
        except (ValueError,KeyError,TypeError):pass
        else:raise RuntimeError('Failed probe accepted: '+mode)
    output=folder/'initial-mismatch';execute([simulated,'--select-rate',*options,output,'--target','44100','--expected-initial','44100'],1)
    record=v.read(output/'probe.json');require(record['selection_attempts']==0 and record['command_attempted'] is False and
        record['device_may_have_changed'] is False and record['finished'] is True,'Reviewed initial mismatch reached setter or lost cleanup')
    for n,extra in enumerate([['--target','96000'],['--target','+48000'],['--target','44100'],
                              ['--target','44100','--expected-initial','048000'],
                              ['--target','44100','--expected-initial','48000','--fixture-mode','rate-normal'],
                              ['--target','44100','--expected-initial','48000','--expected-initial','48000']]):
        output=folder/f'native-invalid-{n}';execute([native,'--select-rate',*options,output,*extra],2);require(not output.exists(),'Invalid native command created output')
    output=folder/'native-absent-helper'
    execute([native,'--select-rate','--worker',worker,'--worker-sha256',hashlib.sha256(worker.read_bytes()).hexdigest(),
             '--helper',helper,'--output',output,'--target','44100','--expected-initial','48000'],1)
    record=v.read(output/'probe.json');require(record['selection_attempts']==0 and record['acquisition_verified'] is False and record['finished'] is True,
        'Native absent helper reached rate operation or failed to retire')
    print('Held-rate probe change/no-op, intent/no-overwrite, refusal/partial/unknown/close failures and native safe negatives passed; no physical USB')

if __name__=='__main__':main()
