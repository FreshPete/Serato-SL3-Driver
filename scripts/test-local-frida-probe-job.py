"""Prove inherited process limits and cleanup with owned Python children only."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time

API = runpy.run_path(str(Path(__file__).with_name('run-local-frida-owned-probe.py')))


def exercise():
    with tempfile.TemporaryDirectory(prefix='sl3-local-probe-job-') as temporary:
        root = Path(temporary); gate = root / 'go'; output = root / 'children.json'
        code = '''import json,pathlib,subprocess,sys,time
gate=pathlib.Path(sys.argv[1]);deadline=time.monotonic()+10
while not gate.exists() and time.monotonic()<deadline:time.sleep(.01)
children=[];error=None
try:
 for _ in range(4):
  children.append(subprocess.Popen([sys.executable,'-I','-B','-c','import time;time.sleep(20)'],creationflags=subprocess.DETACHED_PROCESS))
except OSError as e:error=e.winerror
pathlib.Path(sys.argv[2]).write_text(json.dumps({'children':len(children),'winerror':error,'pids':[child.pid for child in children]}))
time.sleep(20)
'''
        job = API['Job'](); child = None
        try:
            child = subprocess.Popen([sys.executable, '-I', '-B', '-c', code, str(gate), str(output)],
                                     creationflags=subprocess.DETACHED_PROCESS)
            job.assign(child); created = job.creation(child); gate.write_text('go')
            deadline = time.monotonic() + 8
            while not output.exists() and time.monotonic() < deadline: time.sleep(.02)
            result = json.loads(output.read_text())
            assert result['children'] == 3 and result['winerror'] == 1816, result
            before = job.accounting(); members = job.members()
            diagnostic = {'before': before, 'members': members, 'expected': [child.pid] + result['pids'],
                          'memberImages': job.member_images()}
            print(json.dumps(diagnostic))
            assert set(members) == {child.pid, *result['pids']} and len(members) == 4, members
            job.retire(); child.wait(timeout=5)
            deadline = time.monotonic() + 3
            while job.accounting()['active'] and time.monotonic() < deadline: time.sleep(.02)
            after = job.accounting(); assert after['active'] == 0, after
            return {'schema': 'sl3.local-frida-job-test.v1', 'passed': True, 'created': created,
                    'childResult': result, 'before': before, 'members': members, 'after': after,
                    'fridaImported': False, 'deviceOpened': False}
        finally:
            job.retire(); job.close()
            if child: child.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = exercise()
    with args.output.open('x', encoding='utf-8') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(result, indent=2))
