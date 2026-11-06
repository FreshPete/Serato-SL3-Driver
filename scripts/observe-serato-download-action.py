"""Bounded passive workspace startup capture; no installer or broker launch context."""
import argparse
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import queue
import runpy
import time
import winreg

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT/'analysis/serato-workspace-notice-20261105/app'
ARCHIVE_SHA='f7bfe219438f2f3e135325a4eea67eacf92c44a4990e0aa6d0ae02f5b63b918e'
BUNDLE=ROOT/'artifacts/build/deployment-bundles/phase-shutdown-diagnostic-20261105'
BUNDLE_SHA='898c4e5294aec6a67a7364ed9e47ff602f5228401fa10e8a1ca06d46e7cc8993'


def module(name):return runpy.run_path(str(ROOT/'scripts'/name))


def preflight():
    host=module('run-serato-startup-session.py');require=host['require'];sha=host['digest']
    s=module('inspect-sl3-session-readiness.py')['stage']()
    require(not s.elevated(),'Passive workspace capture requires an ordinary user token')
    require(not module('inspect-sl3-session-readiness.py')['running_serato']()['running'],'Close existing Serato before observation')
    module('prepare-asio-deployment.py')['verify'](BUNDLE,BUNDLE_SHA)
    plan=json.loads((BUNDLE/'deployment-plan.json').read_bytes())
    require(not Path(plan['installationDirectory']).exists(),'Temporary driver installation must be absent')
    for hive in (winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER):
        for entry in plan['registryEntries']:
            try:key=winreg.OpenKey(hive,entry['key'],0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY)
            except FileNotFoundError:continue
            key.Close();raise ValueError('Temporary driver registration must be absent')
    local=Path(os.environ['LOCALAPPDATA'])
    for path in (Path(plan['pointerPath']),local/'SL3Rebuild/phase-session.txt',
        local/'Serato/Serato DJ Pro/Drivers/SL3_Rebuild_Development_x64.exe',
        WORKSPACE/'bundles/8c7758f23375cee18a9cf3be4a3acc15.bin'):
        require(not path.exists(),'Unexpected session pointer or rebuilt installer: '+path.name)
    require(sha(WORKSPACE/'Serato DJ Pro.exe')==host['APP_SHA'] and sha(WORKSPACE/'userio_resources.bin')==ARCHIVE_SHA,
            'Expected existing original-image workspace and notice archive')
    installed=Path('C:/Program Files/Serato/Serato DJ Pro');images={}
    for path in WORKSPACE.rglob('*'):
        if path.is_file() and path.suffix.lower() in ('.dll','.exe'):
            relative=path.relative_to(WORKSPACE);original=installed/relative
            require(not path.is_symlink() and not path.is_junction() and original.is_file(),'Unreviewed workspace native file')
            identity=sha(path);require(identity==sha(original),'Workspace native file differs: '+str(relative))
            images[relative.as_posix()]=identity
    require(0<len(images)<=512,'Bounded original native inventory required')
    inspection=module('inspect-serato-download-action.py')['inspect'](WORKSPACE/'Serato DJ Pro.exe')
    return host,{'applicationSha256':host['APP_SHA'],'archiveSha256':ARCHIVE_SHA,'nativeImages':images,
        'observerSha256':inspection['observerSourceSha256'],'temporaryDriverAbsent':True,
        'rebuiltInstallerAbsent':True,'ordinaryToken':True}


def restrict_children(backend):
    class Basic(ctypes.Structure):
        _fields_=[('times',ctypes.c_int64*2),('flags',W.DWORD),('minimum',ctypes.c_size_t),
                  ('maximum',ctypes.c_size_t),('active',W.DWORD),('affinity',ctypes.c_size_t),
                  ('priority',W.DWORD),('scheduling',W.DWORD)]
    class Extended(ctypes.Structure):
        _fields_=[('basic',Basic),('io',ctypes.c_uint64*6),('limits',ctypes.c_size_t*4)]
    limits=Extended();limits.basic.flags=0x2000|0x8;limits.basic.active=1
    backend.checked(backend.k.SetInformationJobObject(backend.job,9,ctypes.byref(limits),ctypes.sizeof(limits)))
    observed=Extended()
    backend.checked(backend.k.QueryInformationJobObject(backend.job,9,ctypes.byref(observed),ctypes.sizeof(observed),None))
    backend.checked(observed.basic.flags==limits.basic.flags and observed.basic.active==1)
    return {'activeProcessLimit':1,'killOnJobClose':True,'silentBreakawayAllowed':False}


def capture(output):
    if (ROOT/'analysis/frida-runtime-security-hold.json').exists():
        raise ValueError('Frida helper security hold is unresolved; preserve Defender protection and use offline inspection')
    host,inputs=preflight();require=host['require'];sha=host['digest']
    output=Path(output).absolute()
    require(output.parent.resolve()==(ROOT/'analysis').resolve() and output.name.startswith('serato-passive-action-') and
            not output.exists(),'Fresh project-local passive action output required')
    output.mkdir();(output/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n',encoding='utf-8')
    import frida
    script=(ROOT/'scripts/serato-sl3-action-observer.js').read_text(encoding='utf-8')
    require(sha(ROOT/'scripts/serato-sl3-action-observer.js')==inputs['observerSha256'],'Observer changed after inspection')
    incoming=queue.Queue(maxsize=128);overflow=False
    def receive(message,data=None):
        nonlocal overflow
        try:incoming.put_nowait(message)
        except queue.Full:overflow=True
    events=[];report={'schema':'sl3.passive-action-capture.v1','inputsSha256':sha(output/'inputs.json'),
        'observerInvokesCallbacks':False,'observerReadsAudio':False,'observerOpensDevice':False,
        'applicationUsbBehaviourMeasured':False,'installerRequestedByHost':False,
        'elevationRequested':False,'error':None,'captureSeconds':20}
    backend=host['WindowsProcess'](WORKSPACE/'Serato DJ Pro.exe',frida)
    deadline=host['HardDeadline'](75)
    try:
        backend.start(script,receive);report['jobPolicy']=restrict_children(backend)
        ready=False;until=time.monotonic()+5
        def collect(timeout):
            require(not overflow,'Passive event queue exceeded its bound')
            try:message=incoming.get(timeout=timeout)
            except queue.Empty:return None
            require(message.get('type')=='send','Passive observer error: '+str(message.get('description','unexpected message'))[:512])
            payload=message.get('payload');require(isinstance(payload,dict),'Missing passive payload')
            fields=host['action_observation'](payload);require(fields is not None,'Unexpected passive event')
            require(fields['ordinal']==len(events)+1,'Passive event sequence differs')
            events.append({'event':payload['event'],'hostMonotonicSeconds':time.monotonic(),**fields})
            return payload['event']
        while time.monotonic()<until:
            if collect(.1)=='action_observer_ready':ready=True;break
        require(ready,'Passive observer did not become ready')
        backend.resume();until=time.monotonic()+20
        while time.monotonic()<until:
            require(not backend.wait(0),'Owned workspace application exited during capture')
            collect(.1)
        report['captureCompleted']=True
    except Exception as error:
        report['error']=str(error)[:512];report['captureCompleted']=False
    finally:
        try:
            backend.detach();report['observerDetachedBeforeClose']=True
        except Exception as error:
            report['observerDetachError']=str(error)[:512]
            report['observerDetachedBeforeClose']=False
        try:report['process']=backend.cleanup()
        except Exception as error:report['cleanupError']=str(error)[:512]
        deadline.close()
        (output/'events.json').write_text(json.dumps(events,indent=2)+'\n',encoding='utf-8')
        report['eventsSha256']=sha(output/'events.json')
        report['eventCounts']={name:sum(e['event']==name for e in events) for name in sorted({e['event'] for e in events})}
        report['workspaceInputsUnchanged']=sha(WORKSPACE/'Serato DJ Pro.exe')==inputs['applicationSha256'] and sha(WORKSPACE/'userio_resources.bin')==ARCHIVE_SHA
        report['workspaceNativeImagesUnchanged']=all(sha(WORKSPACE/name)==identity for name,identity in inputs['nativeImages'].items())
        process=report.get('process',{})
        report['normalExitObserved']=(process.get('processExited') is True and process.get('jobEmpty') is True and
            process.get('observerForcedTermination') is False and process.get('exitCode')==0)
        (output/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path)
    args=parser.parse_args()
    result=capture(args.run) if args.run else preflight()[1]
    print(json.dumps(result,indent=2))
    if args.run:raise SystemExit(0 if result.get('captureCompleted') and result.get('normalExitObserved') and
        result.get('observerDetachedBeforeClose') and result.get('workspaceInputsUnchanged') and
        result.get('workspaceNativeImagesUnchanged') and not result.get('error') else 1)
