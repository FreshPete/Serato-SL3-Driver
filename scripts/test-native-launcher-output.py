"""Observe native relay output before its owned child exits; no SL3 access."""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import tempfile
import threading


def exercise(executable):
    cases=[]
    with tempfile.TemporaryDirectory(prefix='sl3-output-') as temporary:
        gate=Path(temporary)/'finish.txt'
        child=subprocess.Popen([str(executable),'--relay',str(gate)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        observations=queue.Queue()
        def first_line(name,stream):observations.put((name,stream.readline()))
        readers=[threading.Thread(target=first_line,args=(name,stream),daemon=True)
                 for name,stream in (('stdout',child.stdout),('stderr',child.stderr))]
        for reader in readers:reader.start()
        try:
            first=dict(observations.get(timeout=8) for _ in readers)
            assert first['stdout']==b'child-first\r\n'
            assert first['stderr']==b'child-error-first\r\n'
            assert child.poll() is None,'Relay exited before its output was observed'
        finally:
            gate.write_text('finish',encoding='utf-8')
            for reader in readers:reader.join(timeout=8)
            output,error=child.communicate(timeout=20)
        assert child.returncode==7 and output==b'child-last\r\n'
        assert error==b'child-error-last\r\n'
        cases.append({'name':'stdout-and-stderr-visible-before-child-exit','passed':True,
                      'childExitCodePreserved':7,'outputNotDuplicated':True})
    overflow=subprocess.run([str(executable),'--overflow'],capture_output=True,timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert overflow.returncode==1
    assert overflow.stdout==b'x'*(4*1024*1024)
    assert b'overflow-child-finished' in overflow.stderr and b'Helper wait/output failed' in overflow.stderr
    cases.append({'name':'output-cap-refuses-success-and-continues-draining','passed':True,
                  'stdoutBytes':len(overflow.stdout),'childFinished':True})
    unattached=subprocess.run([str(executable),'--no-console'],capture_output=True,timeout=20,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    assert unattached.returncode==9 and unattached.stdout==b'' and unattached.stderr==b''
    cases.append({'name':'unattached-installer-streams-drained-with-child-exit-preserved','passed':True,
                  'childExitCodePreserved':9})
    return {'schema':'sl3.native-launcher-output-tests.v1','cases':cases,
            'fixtureSha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
            'applicationStarted':False,'elevationRequested':False,'deviceOpened':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=exercise(args.fixture.absolute())
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))
