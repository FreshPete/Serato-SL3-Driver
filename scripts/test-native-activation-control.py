"""Explicit one-shot production ASIO initialization; no buffers, streams or installation."""
import argparse
from contextlib import ExitStack, contextmanager
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import time
import uuid
import winreg

ROOT = Path(__file__).resolve().parents[1]
def require(value, message):
    if not value: raise ValueError(message)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def module(name): return runpy.run_path(str(ROOT/'scripts'/name))
def write(path, value):
    with path.open('x', encoding='utf-8') as stream: json.dump(value, stream, indent=2)

def run(args, silent_duplex=False):
    api = module('prepare-asio-activation-config.py'); base = api['BASE']
    build_path=Path(args.host_build).absolute()
    require(sha(build_path)==args.host_build_sha256,'Exact diagnostic build required')
    build=json.loads(build_path.read_bytes())
    kind='native-silent-duplex' if silent_duplex else 'native-control'
    require(build['schema']=='sl3.'+kind+'-host-build.v1' and build['configuration']=='Release' and build['planAndRefusalTestsPassed'] is True,'Reviewed Release diagnostic required')
    for name,value in build['inputs'].items(): require(sha(ROOT/name)==value,'Diagnostic source changed: '+name)
    host=build_path.parent/('Release/sl3_native_silent_duplex_host.exe' if silent_duplex else 'Release/sl3_native_control_host.exe')
    require(sha(host)==build['executableSha256'],'Diagnostic executable changed')
    bundle=Path(args.bundle).absolute(); native_path=Path(args.native_build).absolute()
    manifest,payload=base['capture_bundle'](bundle,args.bundle_sha256);base['verify_payloads'](manifest,payload)
    require(manifest.get('activationMode')=='asio-init-v1','Lazy production bundle required')
    native_sha=json.loads(payload['provenance.json'])['identitySeed']['buildManifestSha256']
    native=api['sources'](native_path,native_sha)
    require(hashlib.sha256(payload['sl3_asio.dll']).hexdigest()==native['unmeasuredAsioDiagnostic']['dllSha256'].lower(),'Production ASIO mismatch')
    require(hashlib.sha256(payload['sl3_broker_controller.exe']).hexdigest()==native['unmeasuredAsioDiagnostic']['brokerSha256'].lower(),'Controller mismatch')
    readiness=module('inspect-sl3-session-readiness.py')
    platform=readiness['platform_state'](); driver=readiness['driver_state'](); serato=readiness['running_serato']()
    require(platform['nativeX64'] and not platform['elevated'] and not serato['running'],'Ordinary x64 host with Serato stopped required')
    require(driver['running'] and driver['reviewedImageOnDisk'],'Running reviewed UsbDk dependency required')
    app=Path('C:/Program Files/Serato/Serato DJ Pro')
    original=app/'userio_resources.bin'
    require(sha(original)==readiness['ORIGINAL_ARCHIVE_SHA'],'Original Serato resource state required')
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for key in ('SOFTWARE\\ASIO\\SL3 Rebuild Development','SOFTWARE\\Classes\\CLSID\\{5A551CD0-F83E-48EB-8B9D-8614E07852FE}'):
            try:
                with winreg.OpenKey(hive,key,0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY): raise ValueError('Existing project registration refused')
            except FileNotFoundError: pass
    s=readiness['stage'](); wait=s.api('kernel32.dll','WaitForSingleObject',W.DWORD,[W.HANDLE,W.DWORD])
    owners=s.known_folder('f1b32785-6fba-4fcf-9d55-7b8e7f157091')/'SL3RebuildActivated'
    before=set(owners.iterdir()) if owners.exists() else set()
    for previous in before:
        old=previous/'ready.json'
        if not old.exists(): continue
        pid=json.loads(old.read_bytes())['controllerPid']
        require(type(pid) is int and 0<pid<=0xffffffff,'Prior owner PID must be bounded')
        handle=s.api('kernel32.dll','OpenProcess',W.HANDLE,[W.DWORD,W.BOOL,W.DWORD])(0x100000,False,pid)
        if handle:
            with s.Handle(handle): require(wait(handle,0)==0,'Existing activation owner may still be alive')
        else: require(ctypes.get_last_error()==87,'Cannot establish previous activation owner absence')
    folder=ROOT/'analysis'/('native-activation-'+('silent-duplex-' if silent_duplex else 'control-')+uuid.uuid4().hex);folder.mkdir()
    copied=folder/'driver';copied.mkdir();markers=folder/'host';markers.mkdir()
    (copied/'sl3_asio.dll').write_bytes(payload['sl3_asio.dll'])
    records=api['records'](copied,bundle,hashlib.sha256(payload['sl3_broker_controller.exe']).hexdigest(),hashlib.sha256(payload['sl3_usbdk.exe']).hexdigest())
    # A new private diagnostic record, never an override of the installed candidate.
    records['sl3-asio.conf']=records['sl3-asio.conf'].replace(b'lifetime_ms=600000\n',b'lifetime_ms=60000\n')
    for name,data in records.items(): (copied/name).write_bytes(data)
    (copied/'fixture.manifest').write_text('<?xml version="1.0" encoding="utf-8"?><assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0"><assemblyIdentity type="win32" name="SL3.Owned.NativeControl" version="1.0.0.0" processorArchitecture="amd64"/><file name="sl3_asio.dll"><comClass clsid="{5A551CD0-F83E-48EB-8B9D-8614E07852FE}" threadingModel="Both"/></file></assembly>',encoding='utf-8')
    api['inspect'](native_path.parent/'Release/sl3_driver_configuration_tests.exe',native['asioComponent']['activationConfigurationInspectorSha256'].lower(),copied/'sl3-asio.conf')
    report={'schema':'sl3.native-activation-'+('silent-duplex' if silent_duplex else 'control')+'-run.v1','successful':False,
            'audioStarted':None if silent_duplex else False,'buffersCreated':None if silent_duplex else False,
            'silentDuplexRequested':silent_duplex,
            'installationPerformed':False,'seratoLaunched':False,'platform':platform,'driver':driver,
            'hostBuildSha256':sha(build_path),'nativeBuildSha256':native_sha,'bundleSha256':args.bundle_sha256,
            'sourceSha256':{str(Path(__file__).relative_to(ROOT)).replace('\\','/'):sha(Path(__file__))},
            'hostSha256':sha(host),'activationRecordSha256':sha(copied/'sl3-asio.conf'),
            'usbReadyForNextAcquire':False,'physicalAudioValidated':False}
    if silent_duplex: report['sourceSha256']['scripts/test-native-activation-silent.py']=sha(ROOT/'scripts/test-native-activation-silent.py')
    print(json.dumps({'prepared':str(folder),'startingOneNativeInitialization':True}),flush=True)
    @contextmanager
    def live_process(pid,image,created=None):
        require(type(pid) is int and 0<pid<=0xffffffff,'Bounded process identity required')
        with ExitStack() as held:
            handle=held.enter_context(s.Handle(s.api('kernel32.dll','OpenProcess',W.HANDLE,[W.DWORD,W.BOOL,W.DWORD])(0x101000,False,pid)))
            require(wait(handle,0)==258,'Observed descendant must still be alive')
            times=[W.FILETIME() for _ in range(4)]
            s.check(s.api('kernel32.dll','GetProcessTimes',W.BOOL,[W.HANDLE]+[ctypes.POINTER(W.FILETIME)]*4)(handle,*(ctypes.byref(t) for t in times)))
            timestamp=str((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)
            require(created is None or timestamp==created,'Exact controller creation differs')
            buffer=ctypes.create_unicode_buffer(32768);length=W.DWORD(len(buffer))
            s.check(s.api('kernel32.dll','QueryFullProcessImageNameW',W.BOOL,[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)])(handle,0,buffer,ctypes.byref(length)))
            expected_file=held.enter_context(s.open_file(image));actual_file=held.enter_context(s.open_file(Path(buffer.value)))
            require(s.information(expected_file,False)['identity']==s.information(actual_file,False)['identity'],'Observed process image differs')
            yield handle,{'pid':pid,'created':timestamp,'imageSha256':sha(image)}
    child=None
    try:
        env=dict(os.environ);env.pop('SL3_ASIO_PRIVATE_TRACE',None)
        child=subprocess.Popen([str(host),'--run-native-silent-duplex' if silent_duplex else '--run-native-control',str(copied/'sl3_asio.dll'),str(markers)],env=env,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        began=time.monotonic();ready_file=markers/'host-ready.json'
        while not ready_file.exists():
            require(child.poll() is None,'Host exited before initialization report')
            require(time.monotonic()-began<26,'Initialization observation deadline');time.sleep(.02)
        ready=json.loads(ready_file.read_bytes());report['hostReady']=ready
        require(ready['pid']==child.pid and ready['initialized'] is True and ready['accepted'] is True and ready['audioStarted'] is False,'Native initialization/channel/clock contract failed')
        after=set(owners.iterdir()) if owners.exists() else set();fresh=after-before
        require(len(fresh)==1,'Exactly one new production activation owner required');session=fresh.pop()
        require(not session.is_symlink() and not session.is_junction(),'Redirected owner refused')
        report['session']=str(session)
        published=json.loads((session/'ready.json').read_bytes())
        binding=dict(line.split('=',1) for line in (session/'broker-session.txt').read_text().splitlines()[1:])
        require(published['kind']=='native' and int(binding['server_pid'])==published['controllerPid'],'Native controller binding required')
        with live_process(published['controllerPid'],bundle/'sl3_broker_controller.exe',binding['server_created']) as (controller,controller_identity), \
             live_process(published['workerPid'],bundle/'sl3_usbdk.exe') as (worker,worker_identity):
            report['controller']=controller_identity;report['worker']=worker_identity
            (markers/'release').write_bytes(b'one-shot release\n')
            stdout,stderr=child.communicate(timeout=20)
            (folder/'stdout.txt').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
            report['hostExitCode']=child.returncode
            report['controllerExited']=wait(controller,10000)==0;report['workerExited']=wait(worker,0)==0
        report['hostResult']=json.loads((markers/'host-result.json').read_bytes())
        retirement=json.loads((session/'result.json').read_bytes());report['retirement']=retirement
        require(child.returncode==0 and report['hostResult']['successful'] is True,'ASIO release failed')
        if silent_duplex:
            require(report['hostResult']['silentOutputOnly'] is True and report['hostResult']['callbacksCompleted']>=500 and report['hostResult']['durationMs']==3000,'Silent duplex progress contract failed')
            report['audioStarted']=report['hostResult']['audioStarted'];report['buffersCreated']=report['hostResult']['buffersCreated']
        require(report['controllerExited'] and report['workerExited'],'Owned native processes did not retire')
        require(retirement['kind']=='native' and retirement['successful'] is True and retirement['nativeDeviceAcquired'] is True and
                retirement['terminationRequested'] is False and retirement['lifetimeExpired'] is False and
                all(retirement[k] is True for k in ('ioRetiredVerified','deviceReleasedVerified','processExited','jobEmpty')),'Native retirement not proved')
        require(sha(original)==readiness['ORIGINAL_ARCHIVE_SHA'] and not readiness['running_serato']()['running'],'Original application state changed')
        report['successful']=True
    except Exception as error:
        report['error']=str(error)
    finally:
        if child is not None and child.poll() is None:
            if not (markers/'release').exists(): (markers/'release').write_bytes(b'observer cleanup\n')
            try: stdout,stderr=child.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill();report['hostForcedTermination']=True;stdout,stderr=child.communicate(timeout=5)
            (folder/'stdout.txt').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
        elif child is not None and not (folder/'stdout.txt').exists():
            stdout,stderr=child.communicate(timeout=5)
            (folder/'stdout.txt').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
        if child is not None: report['hostExitCode']=child.returncode
        fresh=(set(owners.iterdir()) if owners.exists() else set())-before
        report['observedNewSessions']=[str(p) for p in sorted(fresh)]
        report['nativeJournalSha256']={str(p):sha(p) for root in fresh for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
        write(folder/'result.json',report)
    print(json.dumps({'result':str(folder/'result.json'),'successful':report['successful'],'error':report.get('error')}),flush=True)
    return 0 if report['successful'] else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-native-control',action='store_true')
    for name in ('host-build','host-build-sha256','bundle','bundle-sha256','native-build'): parser.add_argument('--'+name)
    args=parser.parse_args()
    if not args.run_native_control:
        print(json.dumps({'schema':'sl3.native-control-wrapper-plan.v1','initializationAttempted':False,'installationPerformed':False}))
    else:
        require(all(getattr(args,n.replace('-','_')) for n in ('host-build','host-build-sha256','bundle','bundle-sha256','native-build')),'All reviewed identities required')
        raise SystemExit(run(args))
