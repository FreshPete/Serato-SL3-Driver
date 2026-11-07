"""Observe exact journal-bound process identities after a completed activation probe; no USB access."""
import argparse
from contextlib import ExitStack
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import re
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parents[1]
def require(condition,message):
    if not condition: raise ValueError(message)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def inspect(path,expected,bundle,bundle_sha):
    require(sha(path)==expected,'Exact completed result required')
    raw=json.loads(path.read_bytes())
    require(raw['schema'] in ('sl3.native-activation-control-run.v1','sl3.native-activation-silent-duplex-run.v1',
                              'sl3.native-activation-application-reopen-run.v1'),'Known owned probe result required')
    require(raw['bundleSha256']==bundle_sha,'Result must bind selected reviewed bundle')
    base=runpy.run_path(str(ROOT/'scripts/prepare-asio-deployment.py'))
    manifest,payload=base['capture_bundle'](bundle,bundle_sha);base['verify_payloads'](manifest,payload)
    s=runpy.run_path(str(ROOT/'scripts/asio-install-journal.py'))['stage_module']()
    owners=s.known_folder('f1b32785-6fba-4fcf-9d55-7b8e7f157091')/'SL3RebuildActivated'
    wait=s.api('kernel32.dll','WaitForSingleObject',W.DWORD,[W.HANDLE,W.DWORD])
    outcomes=[]
    for name in raw['observedNewSessions']:
        session=Path(name)
        pattern=(r'application-[1-9][0-9]{0,9}-[1-9][0-9]{0,19}' if raw['schema']=='sl3.native-activation-application-reopen-run.v1'
                 else r'session-[0-9a-f]{32}')
        require(session.parent==owners and re.fullmatch(pattern,session.name),'Exact user activation session required')
        require(not session.is_symlink() and not session.is_junction() and not owners.is_symlink() and not owners.is_junction(),'Redirected session refused')
        result={'sessionIdentity':session.name,'records':{},'processObservations':[]}
        for key in ('result.json','ready.json','worker-startup.tsv','controller-startup.tsv'):
            file=session/key
            if not file.exists(): continue
            require(not file.is_symlink() and not file.is_junction() and 0<file.stat().st_size<=2_000_000,'Bounded regular journal required')
            require(raw['nativeJournalSha256'].get(str(file))==sha(file),'Journal differs from completed probe snapshot')
            if key.endswith('.json'): result['records'][key]=json.loads(file.read_bytes());continue
            rows=[line.split('\t') for line in file.read_text().splitlines()]
            require(all(len(row)==3 for row in rows),'Typed startup journal rows required')
            pids={int(row[1]) for row in rows};require(len(pids)==1,'Exactly one journal process required')
            pid=pids.pop();require(0<pid<=0xffffffff,'Bounded journal PID required')
            image=bundle/('sl3_usbdk.exe' if key.startswith('worker') else 'sl3_broker_controller.exe')
            observation={'journal':key,'recordedPid':pid,'lastMarker':rows[-1][2]}
            handle=s.api('kernel32.dll','OpenProcess',W.HANDLE,[W.DWORD,W.BOOL,W.DWORD])(0x101000,False,pid)
            if not handle:
                error=ctypes.get_last_error();require(error==87,'Cannot observe recorded process')
                observation['state']='pid_absent';observation['recordedProcessExitProved']=False
            else:
                with ExitStack() as held:
                    held.enter_context(s.Handle(handle))
                    times=[W.FILETIME() for _ in range(4)]
                    s.check(s.api('kernel32.dll','GetProcessTimes',W.BOOL,[W.HANDLE]+[ctypes.POINTER(W.FILETIME)]*4)(handle,*(ctypes.byref(t) for t in times)))
                    buffer=ctypes.create_unicode_buffer(32768);length=W.DWORD(len(buffer))
                    s.check(s.api('kernel32.dll','QueryFullProcessImageNameW',W.BOOL,[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)])(handle,0,buffer,ctypes.byref(length)))
                    wanted=held.enter_context(s.open_file(image));actual=held.enter_context(s.open_file(Path(buffer.value)))
                    same=s.information(wanted,False)['identity']==s.information(actual,False)['identity']
                    observation['imageIdentityMatches']=same
                    observation['created']=str((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)
                    # A journal PID alone cannot rule out PID reuse. Compare creation to
                    # any process identity retained by the actual probe, if available.
                    old=raw.get('worker' if key.startswith('worker') else 'controller')
                    observation['creationBoundByProbe']=bool(old and old['pid']==pid and old['created']==observation['created'])
                    observation['imageSha256']=sha(image) if same else None
                    status=wait(handle,0);require(status in (0,258),'Process wait failed')
                    observation['state']='signaled' if status==0 else 'not_signaled'
                    code=W.DWORD();s.check(s.api('kernel32.dll','GetExitCodeProcess',W.BOOL,[W.HANDLE,ctypes.POINTER(W.DWORD)])(handle,ctypes.byref(code)))
                    observation['reportedExitCode']=int(code.value)
            result['processObservations'].append(observation)
        outcomes.append(result)
    return {'schema':'sl3.native-activation-failure-observation.v1','completedResultSha256':expected,'probeSuccessful':raw['successful'],
            'bundleSha256':bundle_sha,'sessions':outcomes,'readOnly':True,'deviceOpened':False,'processTerminated':False,
            'pointInTimeObservation':True,'journalPidAloneProvesHistoricalProcess':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result',type=Path);parser.add_argument('--expected-result-sha256')
    parser.add_argument('--bundle',type=Path);parser.add_argument('--bundle-sha256')
    args=parser.parse_args()
    if args.result is None: print(json.dumps({'readOnly':True,'deviceOpened':False,'observationAttempted':False}))
    else:
        require(args.expected_result_sha256 and args.bundle and args.bundle_sha256,'All reviewed result/bundle identities required')
        print(json.dumps(inspect(args.result.absolute(),args.expected_result_sha256,args.bundle.absolute(),args.bundle_sha256),indent=2))
