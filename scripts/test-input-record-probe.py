"""Actual simulated finite-prefix recording and native-kind refusal; no physical USB."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

ROOT=Path(__file__).resolve().parents[1]

def require(ok,text):
    if not ok:raise ValueError(text)


def main():
    native,simulated,fixture=[Path(x).resolve() for x in sys.argv[1:]];cases=[]
    parent=ROOT/'tests/results/local';parent.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='input-record-software-',dir=parent))
    def call(name,args,code):
        child=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=20)
        (folder/(name+'-stdout.txt')).write_text(child.stdout,encoding='utf-8')
        (folder/(name+'-stderr.txt')).write_text(child.stderr,encoding='utf-8')
        require(child.returncode==code,f'{name}: {child.returncode}: {child.stderr[-700:]}')
        cases.append({'name':name,'passed':True});return child
    for exe,kind in [(native,False),(simulated,True)]:
        for suffix,args in [('default',[]),('plan',['--plan'])]:
            value=json.loads(call(exe.name+'-'+suffix,[exe,*args],0).stdout)
            require(value['planOnly'] is True and value['deviceAccess'] is False and value['simulated'] is kind and value['audioOutputPayload']=='zero PCM only','Inert plan/kind differs')
        for n,args in enumerate([['--run'],['--plan','--helper','x'],['--unknown']]):call(exe.name+'-invalid-'+str(n),[exe,*args],2)
    digest=hashlib.sha256(fixture.read_bytes()).hexdigest()
    def command(exe,output,rate):return [exe,'--run','--worker',fixture,'--worker-sha256',digest,'--helper',folder/'unused-helper.dll','--output',output,'--expected-rate',str(rate)]
    output=folder/'positive'
    call('simulated-positive',command(simulated,output,48000),0)
    spec=importlib.util.spec_from_file_location('input_record_test_validator',ROOT/'scripts/validate-input-record-probe.py')
    validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
    value=validator.validate(output,digest,True);require(value['frames']==144000,'Exact three-second nominal prefix')
    pcm=(output/'input.pcm').read_bytes()
    # Independent expected packed bytes from the test backend's fixed 8x6-frame packets.
    expected=bytes(((f//48)*17+((f%48)//6)*13+(f%6)*18+c*3+k)&255 for f in range(144000) for c in range(6) for k in range(3))
    require(pcm==expected,'Every input sample/channel byte must match the actual simulated worker prefix')
    wav=folder/'recorded.wav'
    call('offline-wave-export',[sys.executable,ROOT/'scripts/validate-input-record-probe.py',output,'--worker-sha256',digest,'--simulated','--wav-output',wav],0)
    with wave.open(str(wav),'rb') as data:require(data.getnchannels()==6 and data.getsampwidth()==3 and data.getframerate()==48000 and data.readframes(144001)==pcm,'WAV must preserve every PCM byte')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    call('existing-output-refused',command(simulated,output,48000),1)
    require({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}==hashes,'Existing recording changed')
    clock=folder/'simulated-clock.txt';clock.write_text('44100\n',encoding='ascii')
    slow_rate=folder/'positive-44100'
    call('simulated-positive-44100',[*command(simulated,slow_rate,44100),'--fixture-clock',clock],0)
    rate_value=validator.validate(slow_rate,digest,True);require(rate_value['frames']==132352,'44.1 kHz whole-bank rounding')
    require((slow_rate/'input.pcm').read_bytes()==expected[:132352*18],'44.1 kHz prefix bytes differ')
    no_fixture=folder/'native-fixture-refusal'
    call('native-fixture-flag-refused',[*command(native,no_fixture,44100),'--fixture-clock',clock],2)
    require(not no_fixture.exists(),'Native fixture argument created output')
    rejected=folder/'native-kind-refusal';call('native-kind-refusal',command(native,rejected,48000),70)
    result=json.loads((rejected/'failure.json').read_text());require(result['schema']=='sl3.input-record-unretired.v1' and result['simulated'] is False and result['successful'] is False and not result['streamStarted'] and not result['pcmSaved'] and result['processContainmentRequired'] and not (rejected/'input.pcm').exists() and not (rejected/'result.json').exists(),'Unknown-kind cleanup must not become a native recording or false retirement claim')
    mismatch=folder/'wrong-rate';call('rate-mismatch',command(simulated,mismatch,44100),1)
    result=json.loads((mismatch/'result.json').read_text());require(not result['successful'] and not result['streamStarted'] and result['recordedFrames']==0 and result['outputSubmissions']==0,'Rate mismatch must not start audio')
    bad=folder/'bad-rate';call('invalid-rate',command(simulated,bad,96000),2);require(not bad.exists(),'Invalid rate created output')
    sources=[Path(__file__),ROOT/'scripts/validate-input-record-probe.py']
    value={'schema':'sl3.input-record-software-tests.v1','cases':cases,'inputFrames':144000,'simulatedPrefixBytesVerified':len(pcm),'validation':value,
           'nativeExecutableSha256':hashlib.sha256(native.read_bytes()).hexdigest(),'simulatedExecutableSha256':hashlib.sha256(simulated.read_bytes()).hexdigest(),'fixtureExecutableSha256':digest,'sourceSha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'nativePhysicalRun':False,'files':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}}
    index=folder/'index.json';index.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    (ROOT/'artifacts/build/input-record-tests-last.json').write_text(json.dumps({'directory':str(folder),'indexSha256':hashlib.sha256(index.read_bytes()).hexdigest()},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'cases':len(cases),'directory':str(folder),'nativePhysicalRun':False}))


if __name__=='__main__':main()
