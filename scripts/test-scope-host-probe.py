"""Actual probe CLI with simulated worker and pre-device native refusal guards."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('scope_validator',ROOT/'scripts/validate-scope-host-probe.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


def main():
    native,simulated,worker=[Path(p).resolve() for p in sys.argv[1:]]
    sha=hashlib.sha256(worker.read_bytes()).hexdigest()
    def run(executable,*args):
        return subprocess.run([str(executable),*map(str,args)],capture_output=True,text=True,timeout=25)
    for exe,kind in ((native,False),(simulated,True)):
        plan=run(exe,'--plan');assert plan.returncode==0,plan.stderr
        data=json.loads(plan.stdout);assert data['plan_only'] is True and data['simulated'] is kind
        assert data['acquisitions']==1 and data['clock_reads']==3 and data['audio_starts']==data['rate_setters']==0
    with tempfile.TemporaryDirectory(prefix='sl3-facade-scope-') as directory:
        root=Path(directory);good=root/'good';audit=root/'audit.txt'
        def command(output,mode='normal'):
            return ['--run','--worker',worker,'--worker-sha256',sha,'--output',output,'--fixture-mode',mode]
        completed=run(simulated,*command(good,'audit:'+str(audit)));assert completed.returncode==0,completed.stderr
        checked=v.validate(good,sha,True);assert checked['valid'] and checked['metadataObjects']==3
        assert audit.read_text().splitlines()==['acquire','rate','rate','rate','release']
        original=(good/'probe.json').read_bytes();record=json.loads(original)
        assert run(simulated,*command(good)).returncode==2 and (good/'probe.json').read_bytes()==original
        for mode,attempts,objects in (('fail-acquire',1,0),('fail-rate-refresh',2,1)):
            output=root/mode;failed=run(simulated,*command(output,mode));assert failed.returncode==1,failed.stderr
            r=json.loads((output/'probe.json').read_text());assert r['successful'] is False and r['finished'] is True
            assert r['object_attempts']==attempts and len(r['objects'])==objects and r['error']
            assert r['final']['device_released'] is True and r['final']['process_exited'] is True and r['final']['private_job_empty'] is True
            try:v.validate(output,sha,True);raise AssertionError('Failed scope accepted')
            except ValueError:pass
        absent=root/'never-created'
        for exe,args in ((simulated,command(absent)+['--run']),
                         (native,command(absent)), # Native refuses any fixture flag.
                         (simulated,['--plan','--worker',worker]),
                         (simulated,['--run','--worker',worker,'--worker-sha256','0'*64,'--output',absent]),
                         (native,['--run','--worker',worker,'--worker-sha256',sha,'--output',absent,'--helper',root/'missing.dll'])):
            assert run(exe,*args).returncode==2 and not absent.exists()
        synthetic=root/'journal-validator';synthetic.mkdir();record['simulated']=False
        (synthetic/'probe.json').write_text(json.dumps(record))
        stages=['worker.enter','helper_load.enter','helper_load.return','enumerate.enter','enumerate.return',
                'configuration.enter','configuration.return','redirect_owner_acquire.enter','redirect_owner_acquire.return',
                'redirect_start.enter','redirect_start.return','system_handle.enter','system_handle.return']+[
                'clock_getter.enter','clock_getter.return']*3+['redirect_close.enter','redirect_close.return','helper_unload.enter','helper_unload.return']
        journal=''.join(f'{i+100}\t123\t{s}\n' for i,s in enumerate(stages));path=synthetic/'worker-1.tsv';path.write_bytes(journal.encode())
        assert v.validate(synthetic,sha)['valid'] # Synthetic grammar test only; not a native run.
        for broken in (journal.rstrip('\n'),journal+'999\t123\taudio_start.enter\n',journal.replace('101\t123','101\t124'),
                       journal.replace('clock_getter.return','clock_getter.enter',1)):
            path.write_bytes(broken.encode())
            try:v.validate(synthetic,sha);raise AssertionError('Malformed journal accepted')
            except ValueError:pass
        path.write_bytes(journal.encode())
        for key,value in (('successful',False),('rate_setters',1),('buffers_created',True)):
            bad=copy.deepcopy(record);bad[key]=value;(synthetic/'probe.json').write_text(json.dumps(bad))
            try:v.validate(synthetic,sha);raise AssertionError('Invalid scope flags accepted')
            except ValueError:pass
    print('Scope plan, three simulated metadata objects, one-acquire audit, failure cleanup, CLI guards and strict journal validation passed; no SL3 access')


if __name__=='__main__':main()
