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

def run(args, silent_duplex=False, application_reopen=False, prepare_only=False):
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
    expected_mode=base['APPLICATION_ACTIVATION_MODE'] if application_reopen else base['ACTIVATION_MODE']
    require(manifest.get('activationMode')==expected_mode,'Production bundle must match the selected activation mode')
    native_sha=json.loads(payload['provenance.json'])['identitySeed']['buildManifestSha256']
    native=api['sources'](native_path,native_sha)
    require(hashlib.sha256(payload['sl3_asio.dll']).hexdigest()==native['unmeasuredAsioDiagnostic']['dllSha256'].lower(),'Production ASIO mismatch')
    require(hashlib.sha256(payload['sl3_broker_controller.exe']).hexdigest()==native['unmeasuredAsioDiagnostic']['brokerSha256'].lower(),'Controller mismatch')
    readiness=module('inspect-sl3-session-readiness.py')
    platform=readiness['platform_state'](); driver=readiness['driver_state'](); serato=readiness['running_serato']()
    require(platform['nativeX64'] and not platform['elevated'] and not serato['running'],'Ordinary x64 host with Serato stopped required')
    require(driver['running'] and driver['reviewedImageOnDisk'],'Running reviewed UsbDk dependency required')
    if application_reopen and not prepare_only:
        require(readiness['sl3_presence']()['matchingPresentIdentities']==1,'One present SL3 required for an attended reopen test')
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
    probe='application-reopen' if application_reopen else ('silent-duplex' if silent_duplex else 'control')
    folder=ROOT/'analysis'/('native-activation-'+probe+'-'+uuid.uuid4().hex);folder.mkdir()
    copied=folder/'driver';copied.mkdir();markers=folder/'host';markers.mkdir()
    (copied/'sl3_asio.dll').write_bytes(payload['sl3_asio.dll'])
    records=base['activation_records'](copied,hashlib.sha256(payload['sl3_broker_controller.exe']).hexdigest(),
        hashlib.sha256(payload['sl3_usbdk.exe']).hexdigest(),expected_mode,bundle)
    # A new private diagnostic record, never an override of the installed candidate.
    records['sl3-asio.conf']=records['sl3-asio.conf'].replace(b'lifetime_ms=600000\n',b'lifetime_ms=60000\n')
    for name,data in records.items(): (copied/name).write_bytes(data)
    (copied/'fixture.manifest').write_text('<?xml version="1.0" encoding="utf-8"?><assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0"><assemblyIdentity type="win32" name="SL3.Owned.NativeControl" version="1.0.0.0" processorArchitecture="amd64"/><file name="sl3_asio.dll"><comClass clsid="{5A551CD0-F83E-48EB-8B9D-8614E07852FE}" threadingModel="Both"/></file></assembly>',encoding='utf-8')
    api['inspect'](native_path.parent/'Release/sl3_driver_configuration_tests.exe',native['asioComponent']['activationConfigurationInspectorSha256'].lower(),copied/'sl3-asio.conf')
    if prepare_only:
        report={'schema':'sl3.native-application-reopen-preparation.v1','prepared':True,'mode':expected_mode,
                'bundleSha256':args.bundle_sha256,'nativeBuildSha256':native_sha,'hostBuildSha256':sha(build_path),
                'driverFiles':{name:sha(copied/name) for name in sorted(p.name for p in copied.iterdir())},
                'nativeParserAccepted':True,'initializationAttempted':False,'audioStarted':False,
                'installationPerformed':False,'seratoLaunched':False}
        write(folder/'preparation.json',report)
        print(json.dumps({'prepared':str(folder),'initializationAttempted':False,'nativeParserAccepted':True}))
        return 0
    report={'schema':'sl3.native-activation-'+probe+'-run.v1','successful':False,
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
    def await_record(path,seconds):
        deadline=time.monotonic()+seconds
        while not path.is_file():
            require(child.poll() is None,'Host exited before '+path.name)
            require(time.monotonic()<deadline,'Observation deadline for '+path.name)
            time.sleep(.02)
        return json.loads(path.read_bytes())

    def ready_client(path,seconds):
        ready=await_record(path/'host-ready.json',seconds)
        require(ready['pid']==child.pid and ready['initialized'] is True and ready['accepted'] is True and ready['audioStarted'] is False,
                'Native initialization/channel/clock contract failed')
        return ready

    try:
        env=dict(os.environ);env.pop('SL3_ASIO_PRIVATE_TRACE',None)
        option='--run-native-application-reopen' if application_reopen else ('--run-native-silent-duplex' if silent_duplex else '--run-native-control')
        child=subprocess.Popen([str(host),option,str(copied/'sl3_asio.dll'),str(markers)],env=env,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        first=markers/'open-1' if application_reopen else markers
        report['hostReady']=ready_client(first,26)
        after=set(owners.iterdir()) if owners.exists() else set();fresh=after-before
        if application_reopen:
            with live_process(child.pid,host) as (_,identity):
                session=owners/('application-'+str(child.pid)+'-'+identity['created'])
            require(fresh=={session,session.with_suffix('.claim')},'Exact host-bound owner and startup claim required')
        else:
            require(len(fresh)==1,'Exactly one new production activation owner required');session=fresh.pop()
        require(not session.is_symlink() and not session.is_junction(),'Redirected owner refused')
        report['session']=str(session)
        if application_reopen:
            require(json.loads((session/'intent.json').read_bytes())['applicationBound'] is True,'Application-bound controller required')
            report['claimSha256']=sha(session.with_suffix('.claim'))
        ready_path=session/'ready.json';ready_hash=sha(ready_path)
        published=json.loads(ready_path.read_bytes())
        binding=dict(line.split('=',1) for line in (session/'broker-session.txt').read_text().splitlines()[1:])
        require(published['kind']=='native' and int(binding['server_pid'])==published['controllerPid'],'Native controller binding required')
        with live_process(published['controllerPid'],bundle/'sl3_broker_controller.exe',binding['server_created']) as (controller,controller_identity), \
             live_process(published['workerPid'],bundle/'sl3_usbdk.exe') as (worker,worker_identity):
            report['controller']=controller_identity;report['worker']=worker_identity
            (first/'release').write_bytes(b'one-shot release\n')
            if application_reopen:
                outcomes=report['opens']=[await_record(first/'host-result.json',12)]
                second=markers/'open-2'
                report['secondHostReady']=ready_client(second,12)
                require(wait(controller,0)==258 and wait(worker,0)==258,'Original controller and worker must survive first ASIO release')
                (second/'release').write_bytes(b'second open on the retained owner\n')
                outcomes.append(await_record(second/'host-result.json',12))
                require(wait(controller,0)==258 and wait(worker,0)==258,'Original controller and worker must survive both releases')
                require(sha(ready_path)==ready_hash and set(owners.iterdir())-before==fresh,
                        'A second owner or changed publication cannot count as a retained reopen')
                journal=(session/'worker-startup.tsv').read_text().splitlines()
                events=[line.rsplit('\t',1)[-1] for line in journal]
                require(events.count('redirect_start.return')==1 and 'redirect_close.enter' not in events,
                        'One physical acquisition must cover both ASIO opens')
                report['oneAcquisitionObserved']=True
                (markers/'finish').write_bytes(b'host may exit\n')
            stdout,stderr=child.communicate(timeout=20)
            (folder/'stdout.txt').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
            report['hostExitCode']=child.returncode
            report['controllerExited']=wait(controller,10000)==0;report['workerExited']=wait(worker,0)==0
        report['hostResult']=report['opens'][-1] if application_reopen else json.loads((markers/'host-result.json').read_bytes())
        retirement=json.loads((session/'result.json').read_bytes());report['retirement']=retirement
        require(child.returncode==0 and report['hostResult']['successful'] is True,'ASIO release failed')
        if silent_duplex:
            require(all(result['successful'] is True and result['released'] is True and result['unloadable'] is True and
                        result['silentOutputOnly'] is True and result['callbacksCompleted']>=500 and result['durationMs']==3000
                        for result in report.get('opens',[report['hostResult']])), 'Silent duplex progress contract failed')
            report['audioStarted']=report['hostResult']['audioStarted'];report['buffersCreated']=report['hostResult']['buffersCreated']
        require(report['controllerExited'] and report['workerExited'],'Owned native processes did not retire')
        require(retirement['kind']=='native' and retirement['successful'] is True and retirement['nativeDeviceAcquired'] is True and
                retirement['terminationRequested'] is False and retirement['lifetimeExpired'] is False and
                all(retirement[k] is True for k in ('ioRetiredVerified','deviceReleasedVerified','processExited','jobEmpty')),'Native retirement not proved')
        if application_reopen:
            require(retirement['reason']=='application_exit' and retirement['applicationExitObserved'] is True,
                    'Controller retirement must follow the exact host exit')
        require(sha(original)==readiness['ORIGINAL_ARCHIVE_SHA'] and not readiness['running_serato']()['running'],'Original application state changed')
        report['successful']=True
    except Exception as error:
        report['error']=str(error)
    finally:
        if child is not None and child.poll() is None:
            if application_reopen:
                (markers/'abort').write_bytes(b'observer cleanup\n')
            elif not (markers/'release').exists():
                (markers/'release').write_bytes(b'observer cleanup\n')
            try: stdout,stderr=child.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill();report['hostForcedTermination']=True;stdout,stderr=child.communicate(timeout=5)
            (folder/'stdout.txt').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
        elif child is not None and not (folder/'stdout.txt').exists():
            stdout,stderr=child.communicate(timeout=5)
            (folder/'stdout.txt').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
        if child is not None: report['hostExitCode']=child.returncode
        fresh={p for p in ((set(owners.iterdir()) if owners.exists() else set())-before)
               if p.is_dir() and not p.is_symlink() and not p.is_junction()}
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
