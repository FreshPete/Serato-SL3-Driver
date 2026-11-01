"""Actual selection-probe process tests: simulated positives, native safe negatives."""
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
    result=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=40)
    require(result.returncode==expected,f'Exit {result.returncode} expected {expected}: {result.stderr}')
    return result


def main():
    require(len(sys.argv)==5,'Four reviewed executable paths required')
    native,simulated,fixture,worker=[Path(x).resolve() for x in sys.argv[1:]];root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('selection_validation',root/'scripts/validate-selection-host-probe.py')
    validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
    folder=Path(tempfile.mkdtemp(prefix='selection-probe-software-',dir=root/'tests/results/local'))
    helper=folder/'absent-helper.dll';sha=hashlib.sha256(fixture.read_bytes()).hexdigest()
    options=['--worker',fixture,'--worker-sha256',sha,'--helper',helper,'--output']
    for mode in ('normal','selection-noop'):
        output=folder/mode;args=[simulated,'--select-control',*options,output,'--target','through:0:1']
        if mode!='normal':args+=['--fixture-mode',mode]
        execute(args,0);checked=validator.probe(output,sha,True)
        require(checked['outcome']['setters']==(mode=='normal'),'Changed/no-op result differs')
        saved=(output/'request.json').read_bytes();execute(args,1)
        require((output/'request.json').read_bytes()==saved,'Existing request was overwritten')
    for mode in ('fail-selection','mismatch-selection','bad-selection','throw-selection','hang-selection','selection-fail-close','selection-success-close','selection-unsupported','fail-controls'):
        output=folder/mode;execute([simulated,'--select-control',*options,output,'--target','through:0:1','--fixture-mode',mode],1)
        record=validator.read(output/'probe.json');require(record['successful'] is False and record['audio_start_attempts']==0,'Failure became successful/audio')
        wire=record['outcome_wire_hex']
        if mode in ('fail-selection','mismatch-selection','selection-fail-close','selection-success-close'):
            require(wire is not None,'Partial/complete outcome lost through failure')
            outcome=validator.decode_wire(wire,record['target'])
            require(outcome['deviceMayHaveChanged'] and outcome['initial'] is not None,'Partial observation/uncertainty lost')
            require((outcome['verified'] is not None)==(mode=='selection-success-close'),'Verification evidence differs')
        if mode in ('bad-selection','throw-selection','hang-selection'):
            require(wire is None and record['outcome_unknown'] is True and record['device_may_have_changed'] is True,'Missing outcome manufactured certainty')
        if mode in ('selection-unsupported','fail-controls'):require(record['selection_attempts']==0 and record['command_attempted'] is False,'Pre-operation refusal attempted setting')
        try:validator.probe(output,sha,True)
        except (ValueError,KeyError,TypeError):pass
        else:raise RuntimeError('Failed record accepted')
    for target in ('through:0:2','sensitivity:0:16','through:00:1','phono:0:1'):
        output=folder/('invalid-'+target.replace(':','-'))
        execute([native,'--select-control',*options,output,'--target',target],2);require(not output.exists(),'Invalid target created output')
    output=folder/'native-no-reviewed-baseline'
    execute([native,'--select-control',*options,output,'--target','through:0:1'],2)
    require(not output.exists(),'Native selection without reviewed baseline created output')
    for n,baseline in enumerate(('00'*21,'00'*23,'GG'*22,'AA'*22,'0 '*22)):
        output=folder/f'native-invalid-baseline-{n}'
        execute([native,'--select-control',*options,output,'--target','through:0:1','--baseline-controls',baseline],2)
        require(not output.exists(),'Invalid reviewed baseline created output')
    output=folder/'duplicate-reviewed-baseline'
    execute([simulated,'--select-control',*options,output,'--target','through:0:1','--baseline-controls','00'*22,'--baseline-controls','00'*22],2)
    require(not output.exists(),'Duplicate reviewed baseline created output')
    for label,baseline,expected in (('reviewed-match',bytes(range(17,39)).hex(),0),('reviewed-mismatch','00'*22,1)):
        output=folder/label
        execute([simulated,'--select-control',*options,output,'--target','through:0:1','--baseline-controls',baseline],expected)
        record=validator.read(output/'probe.json')
        if expected==0:validator.probe(output,sha,True)
        else:
            require(record['selection_attempts']==0 and record['command_attempted'] is False and record['baseline_raw_controls']==list(range(17,39)),
                    'Reviewed-table mismatch reached selection or lost actual observation')
            require(record['outcome_wire_hex'] is None and record['outcome_unknown'] is False and record['device_may_have_changed'] is False
                    and record['publication_pending'] is False and record['finished'] is True and record['final']['device_released'] is True,
                    'Reviewed-table refusal failed to preserve known-no-selection and final release')
    output=folder/'native-absent-helper'
    execute([native,'--select-control','--worker',worker,'--worker-sha256',hashlib.sha256(worker.read_bytes()).hexdigest(),
             '--helper',helper,'--output',output,'--target','through:0:1','--baseline-controls','00'*22],1)
    record=validator.read(output/'probe.json');require(record['selection_attempts']==0 and record['baseline_query_attempts']==0 and
            record['acquisition_verified'] is False and record['finished'] is True,'Native helper refusal did not retire without settings')
    print('Selection probe intent/no-overwrite, simulated change/no-op/partial/missing/close failures and native safe negatives passed; no physical USB')


if __name__=='__main__':main()
