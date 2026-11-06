"""Terminate only owned simulated ASIO hosts; observe exact controller/worker process objects."""
from contextlib import contextmanager,ExitStack
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
def require(value,text):
    if not value:raise ValueError(text)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    build_path=Path(sys.argv[1]).absolute();expected_build=sys.argv[2];reference=Path(sys.argv[3]).absolute();expected_reference=sys.argv[4]
    require(sha(build_path)==expected_build and sha(reference)==expected_reference,'Reviewed build/reference identities required')
    build=json.loads(build_path.read_bytes());prior=json.loads(reference.read_bytes())
    require(build['schema']=='sl3.activation-interruption-host-build.v1' and build['configuration']=='Release' and build['planAndRefusalTestsPassed'] is True,'Owned diagnostic Release build required')
    require(prior['schema']=='sl3.activation-asio-run.v1' and prior['nativeDeviceAccess'] is False,'Owned simulated fixture reference required')
    for pins in (build['inputs'],prior['sourceSha256']):require(all(sha(ROOT/name)==value for name,value in pins.items()),'Build/reference source changed')
    images={Path(name).name:Path(name) for name in prior['imageSha256']}
    names={'sl3_activation_asio_tests.exe','sl3_activation_session_fixture.dll','sl3_broker_controller_unmeasured_simulated.exe','sl3_device_session_fixture.exe','UsbDkHelper.dll10'}
    require(set(images)==names and all(sha(Path(name))==value for name,value in prior['imageSha256'].items()),'Exact simulated fixture image contract required')
    host=build_path.parent/'Release/sl3_activation_interruption_host.exe';require(sha(host)==build['executableSha256'],'Owned host executable changed')
    native_build=images['sl3_activation_session_fixture.dll'].parent.parent/'native-build-Release.json';native=json.loads(native_build.read_bytes())
    require(native['coreTestsPassed'] is True and all(sha(ROOT/name)==value.lower() for name,value in native['inputs'].items()),'Native activation source provenance changed')
    require(native['unmeasuredAsioDiagnostic']['simulatedBrokerSha256'].lower()==sha(images['sl3_broker_controller_unmeasured_simulated.exe']) and
            native['deviceSession']['fixtureSha256'].lower()==sha(images['sl3_device_session_fixture.exe']),'Simulated controller/worker must match tested native build')
    s=runpy.run_path(str(ROOT/'scripts/asio-install-journal.py'))['stage_module']();require(not s.elevated(),'Ordinary-token diagnostic required')
    own_sources=[Path(__file__),ROOT/'scripts/serato-session-stop.py',ROOT/'scripts/asio-file-stage.py',ROOT/'scripts/asio-install-journal.py']
    source_pins={p.relative_to(ROOT).as_posix():sha(p) for p in own_sources}
    identity=uuid.uuid4().hex;folder=ROOT/'analysis'/('activation-interruption-'+identity);folder.mkdir();outcomes=[]
    wait=s.api('kernel32.dll','WaitForSingleObject',W.DWORD,[W.HANDLE,W.DWORD])
    @contextmanager
    def live_process(pid,image,created=None):
        require(type(pid) is int and 0<pid<=0xffffffff,'Bounded process identity required')
        with ExitStack() as held:
            handle=held.enter_context(s.Handle(s.api('kernel32.dll','OpenProcess',W.HANDLE,[W.DWORD,W.BOOL,W.DWORD])(0x101000,False,pid)))
            require(wait(handle,0)==258,'Selected process must be alive before test action')
            times=[W.FILETIME() for _ in range(4)]
            s.check(s.api('kernel32.dll','GetProcessTimes',W.BOOL,[W.HANDLE]+[ctypes.POINTER(W.FILETIME)]*4)(handle,*(ctypes.byref(t) for t in times)))
            timestamp=str((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)
            require(created is None or timestamp==created,'Exact controller creation identity differs')
            buffer=ctypes.create_unicode_buffer(32768);length=W.DWORD(len(buffer))
            s.check(s.api('kernel32.dll','QueryFullProcessImageNameW',W.BOOL,[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)])(handle,0,buffer,ctypes.byref(length)))
            expected_file=held.enter_context(s.open_file(image));actual_file=held.enter_context(s.open_file(Path(buffer.value)))
            require(s.information(expected_file,False)['identity']==s.information(actual_file,False)['identity'],'Exact observed process image differs')
            yield handle,{'pid':pid,'created':timestamp,'imageSha256':sha(image)}
    def exited(handle):
        require(wait(handle,10000)==0,'Owned descendant did not exit within ten seconds')
        code=W.DWORD();s.check(s.api('kernel32.dll','GetExitCodeProcess',W.BOOL,[W.HANDLE,ctypes.POINTER(W.DWORD)])(handle,ctypes.byref(code)))
        return int(code.value)
    for mode,forced in [('normal',False),('stream',True),('blocked',True)]:
        root=folder/mode;root.mkdir();owners=root/'owners';owners.mkdir();markers=root/'host';markers.mkdir()
        worker=images['sl3_device_session_fixture.exe'];helper=images['UsbDkHelper.dll10'];controller=images['sl3_broker_controller_unmeasured_simulated.exe']
        timing=root/'timing.conf';timing.write_text('SL3-ASIO-DIAGNOSTIC-TIMING-1\nworker_sha256='+sha(worker)+'\nhelper_sha256='+sha(helper)+'\nrate_hz=44100\nbuffer_frames=128\n',encoding='utf-8')
        config=root/'worker.conf';config.write_text('SL3-ASIO-CONFIG-1\nworker='+str(worker)+'\nworker_sha256='+sha(worker)+'\nhelper='+str(helper)+'\ntiming_record='+str(timing)+'\ntiming_record_sha256='+sha(timing)+'\n',encoding='utf-8')
        entry=root/'activation.conf';entry.write_text('SL3-ASIO-ACTIVATION-1\ncontroller='+str(controller)+'\ncontroller_sha256='+sha(controller)+'\ninput='+str(config)+'\ninput_sha256='+sha(config)+'\nstartup_timeout_ms=15000\nstartup_failure_grace_ms=5000\nlifetime_ms=60000\n',encoding='utf-8')
        env=dict(os.environ);env.pop('SL3_ASIO_PRIVATE_TRACE',None)
        child=subprocess.Popen([str(host),'--run','blocked' if mode=='blocked' else 'stream',str(images['sl3_activation_session_fixture.dll']),str(entry),str(owners),str(markers)],
            env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            began=time.monotonic();ready_file=markers/'host-ready.json'
            while not ready_file.is_file():
                require(child.poll() is None,'Owned host exited before readiness');require(time.monotonic()-began<15,'Owned host readiness deadline');time.sleep(.01)
            ready=json.loads(ready_file.read_bytes());require(ready['pid']==child.pid and ready['simulatedOnly'] is True and ready['nativeDeviceAccess'] is False,'Exact ready host scope required')
            require(ready['callbackBlocked']==(mode=='blocked') and (ready['callbacksEntered']>=1 if mode=='blocked' else ready['callbacksCompleted']>=8),'Actual simulated callback progress/block required')
            session=owners/'session-1';published=json.loads((session/'ready.json').read_bytes())
            binding=dict(line.split('=',1) for line in (session/'broker-session.txt').read_text().splitlines()[1:])
            require(published['kind']=='simulated' and int(binding['server_pid'])==published['controllerPid'],'Expected simulated controller publication')
            with live_process(child.pid,host) as (_,host_identity), \
                 live_process(published['controllerPid'],controller,binding['server_created']) as (controller_handle,controller_identity), \
                 live_process(published['workerPid'],worker) as (worker_handle,worker_identity):
                if forced:child.kill()  # Exact retained Popen process handle; never a name/PID lookup.
                else:(markers/'stop').write_bytes(b'owned normal stop\n')
                stdout,stderr=child.communicate(timeout=20)
                (root/'host-stdout.txt').write_bytes(stdout);(root/'host-stderr.txt').write_bytes(stderr)
                require(child.returncode==(1 if forced else 0),'Expected exact normal/forced host exit')
                controller_code=exited(controller_handle);worker_code=exited(worker_handle)
            result_file=session/'result.json';host_result=markers/'host-result.json'
            if forced:
                require(not result_file.exists() and not host_result.exists(),'Abrupt host death must not be represented as normal retirement')
                retirement=None
            else:
                retirement=json.loads(result_file.read_bytes());require(retirement['successful'] is True and retirement['kind']=='simulated' and
                    all(retirement[k] is True for k in ('ioRetiredVerified','deviceReleasedVerified','processExited','jobEmpty')) and
                    retirement['terminationRequested'] is False and retirement['nativeDeviceAcquired'] is False,'Normal typed simulated retirement required')
                require(json.loads(host_result.read_bytes())['successful'] is True,'Normal host result required')
            outcome={'scenario':mode,'host':host_identity,'controller':controller_identity,'worker':worker_identity,
                'hostTerminationRequested':forced,'hostExited':child.poll() is not None,'controllerExited':True,'workerExited':True,
                'controllerExitCode':controller_code,'workerExitCode':worker_code,'callbacksEnteredAtReady':ready['callbacksEntered'],
                'callbacksCompletedAtReady':ready['callbacksCompleted'],'callbackBlockedAtReady':ready['callbackBlocked'],
                'normalRetirementRecorded':retirement is not None,'normalControllerResultSha256':sha(result_file) if retirement else None,
                'hostResultSha256':sha(host_result) if host_result.exists() else None,'nativeDeviceAccess':False,'physicalUsbReleaseVerified':False}
            outcomes.append(outcome);(root/'outcome.json').write_text(json.dumps(outcome,indent=2)+'\n',encoding='utf-8')
            print(json.dumps({'scenario':mode,'passed':True,'controllerExited':True,'workerExited':True}),flush=True)
        finally:
            if child.poll() is None:child.kill();child.communicate(timeout=5)
    require(all(sha(ROOT/name)==value for name,value in source_pins.items()) and all(sha(ROOT/name)==value for name,value in build['inputs'].items()) and
            all(sha(Path(name))==value for name,value in prior['imageSha256'].items()) and sha(host)==build['executableSha256'],'Interruption test inputs changed')
    report={'schema':'sl3.activation-interruption-tests.v1','passed':True,'outcomes':outcomes,'sourceSha256':source_pins,
        'diagnosticBuildSha256':expected_build,'diagnosticHostSha256':build['executableSha256'],'referenceRunSha256':expected_reference,
        'nativeBuildManifestSha256':sha(native_build),'nativeInputsStillMatch':True,'ownedHostsTerminated':2,
        'normalBaselinePassed':True,'actualOwnedProcessTerminationTested':True,'seratoLaunched':False,'nativeDeviceAccess':False,
        'registryModified':False,'persistentEnvironmentModified':False,'physicalUsbReleaseVerified':False}
    path=folder/'result.json';path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'passed':True,'scenarios':len(outcomes),'report':str(path)},indent=2))


if __name__=='__main__':main()
