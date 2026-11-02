"""Bounded default-off and unavailable-log-directory checks on the isolated own DLL."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('private_trace',ROOT/'scripts/validate-asio-private-trace.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
def sha(path):return hashlib.sha256(v.bounded(path,16*1024*1024)).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration',choices=['Release','Debug'],default='Release')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();folder=args.output.absolute()
    v.require(folder.parent.resolve()==(ROOT/'tests/results/local').resolve() and folder.name.startswith('asio-private-trace-') and
              not folder.exists() and not folder.is_symlink() and not folder.is_junction(),'Fresh local fixture directory required')
    native=ROOT/f'artifacts/build/native/native-build-{args.configuration}.json'
    diagnostic=ROOT/f'artifacts/build/asio-private-trace/diagnostic-build-{args.configuration}.json'
    m=v.parse(v.bounded(native,1024*1024));b=v.parse(v.bounded(diagnostic,1024*1024))
    pins={}
    for inputs in [m['inputs'],b['inputs']]:
        for source,digest in inputs.items():v.require(sha(ROOT/source)==digest.lower(),'Build input drift: '+source)
    for path in ['scripts/test-asio-owned-fallback.py','scripts/validate-asio-private-trace.py']:pins[path]=sha(ROOT/path)
    dll=native.parent/args.configuration/'sl3_asio.dll';exe=diagnostic.parent/args.configuration/'sl3_asio_private_trace.exe'
    v.require(sha(dll)==m['asioComponent']['comDllSha256'].lower() and sha(exe)==b['executableSha256'],'Pinned images required')
    folder.mkdir();isolated=folder/'isolated';isolated.mkdir()
    with (isolated/'sl3_asio.dll').open('xb') as f:f.write(dll.read_bytes())
    results=[]
    for mode in ['--self-disabled','--self-refused']:
        output=folder/mode[2:]
        child=subprocess.Popen([str(exe),mode,str(output),str(isolated/'sl3_asio.dll')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        timeout=False
        try:stdout,stderr=child.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            timeout=True;child.kill();stdout,stderr=child.communicate(timeout=5)
        for name,raw in [('stdout.txt',stdout),('stderr.txt',stderr)]:
            with (folder/(mode[2:]+'-'+name)).open('xb') as f:f.write(raw)
        record={'mode':mode,'pid':child.pid,'exitCode':child.returncode,'timedOut':timeout,'childExited':child.poll() is not None}
        results.append(record)
        v.require(not timeout and child.returncode==0,'Fallback process must retire successfully')
        marker=output/'fallback.json';value=v.parse(v.bounded(marker,65536))
        expected={'schema':'sl3.asio-owned-fallback.v1','ordinaryResultsPreserved':True,'dllUnloaded':True,
                  'traceDirectoryCreated':False,'deviceAccess':False,'seratoExecuted':False}
        v.require(value==expected and all(type(value[k]) is bool for k in expected if k!='schema'),'Exact fallback result')
        record['resultSha256']=sha(marker);record['result']=value
    for path,digest in pins.items():v.require(sha(ROOT/path)==digest,'Runner changed')
    v.require(sha(isolated/'sl3_asio.dll')==sha(dll),'Isolated image changed')
    report={'schema':'sl3.asio-owned-fallback-tests.v1','configuration':args.configuration,'nativeManifestSha256':sha(native),
            'diagnosticManifestSha256':sha(diagnostic),'dllSha256':sha(dll),'toolSha256':sha(exe),'sourceSha256':pins,'results':results,
            'deviceAccess':False,'seratoExecuted':False}
    with (folder/'results.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
