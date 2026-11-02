"""Run the pinned own-DLL unavailable-state fixture in a bounded private ETW session."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('private_trace_validator',ROOT/'scripts/validate-asio-private-trace.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration',choices=['Release','Debug'],default='Release');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();folder=args.output.absolute()
    v.require(folder.parent.resolve()==(ROOT/'tests/results/local').resolve() and folder.name.startswith('asio-private-trace-') and
              not folder.exists() and not folder.is_symlink() and not folder.is_junction(),'Fresh direct local fixture directory required')
    native=ROOT/f'artifacts/build/native/native-build-{args.configuration}.json';m=v.parse(native.read_bytes())
    build=ROOT/f'artifacts/build/asio-private-trace/diagnostic-build-{args.configuration}.json';b=v.parse(build.read_bytes())
    for inputs in [m['inputs'],b['inputs']]:
        for source,expected in inputs.items():v.require(sha(ROOT/source)==expected.lower(),'Build source differs: '+source)
    exe=build.parent/args.configuration/'sl3_asio_private_trace.exe';dll=native.parent/args.configuration/'sl3_asio.dll'
    v.require(sha(exe)==b['executableSha256'] and sha(dll)==m['asioComponent']['comDllSha256'].lower(),'Exact built images required')
    source_hashes={p:sha(ROOT/p) for p in ['scripts/test-asio-private-trace.py','scripts/validate-asio-private-trace.py']}
    folder.mkdir();isolated=folder/'isolated';isolated.mkdir()
    with (isolated/'sl3_asio.dll').open('xb') as f:f.write(dll.read_bytes())
    command=[str(exe),'--capture',str(folder/'capture'),str(isolated/'sl3_asio.dll')]
    child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    timed_out=False
    try:stdout,stderr=child.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        timed_out=True;child.kill();stdout,stderr=child.communicate(timeout=5)
    for name,raw in [('stdout.txt',stdout),('stderr.txt',stderr)]:
        with (folder/name).open('xb') as f:f.write(raw)
    captured=['capture/capture.json','capture/events.jsonl']
    if (folder/'capture').is_dir():captured += [p.relative_to(folder).as_posix() for p in (folder/'capture').glob('private.etl*') if p.is_file()]
    record={'schema':'sl3.asio-private-trace-run.v1','configuration':args.configuration,'pid':child.pid,'exitCode':child.returncode,
            'childExited':child.poll() is not None,'timedOut':timed_out,'toolSha256':sha(exe),'dllSha256':sha(dll),
            'nativeManifestSha256':sha(native),'diagnosticManifestSha256':sha(build),
            'sourceSha256':source_hashes,
            'files':{p:sha(folder/p) for p in captured if (folder/p).is_file()},'seratoExecuted':False,'deviceAccess':False}
    with (folder/'run.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,indent=2);f.write('\n')
    v.require(sha(isolated/'sl3_asio.dll')==record['dllSha256'],'Isolated input changed')
    for source,digest in source_hashes.items():v.require(sha(ROOT/source)==digest,'Runner source changed during capture')
    result=v.validate(folder)
    with (folder/'validation.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
