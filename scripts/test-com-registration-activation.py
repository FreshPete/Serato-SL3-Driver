"""Real COM resolution in an owned process-local HKCR fixture; no live registration or USB."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import uuid
import winreg

ROOT=Path(__file__).resolve().parents[1]
def require(value,text):
    if not value:raise ValueError(text)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    build_path=Path(sys.argv[1]).absolute();reference=Path(sys.argv[3]).absolute()
    require(sha(build_path)==sys.argv[2] and sha(reference)==sys.argv[4],'Exact reviewed build and fixture reference required')
    build=json.loads(build_path.read_bytes());prior=json.loads(reference.read_bytes())
    require(build['schema']=='sl3.com-registration-host-build.v1' and build['configuration']=='Release' and build['planAndRefusalTestsPassed'],'Reviewed COM host build required')
    require(prior['schema']=='sl3.activation-asio-run.v1' and prior['nativeDeviceAccess'] is False,'Simulated ASIO reference required')
    for pins in (build['inputs'],prior['sourceSha256']):require(all(sha(ROOT/p)==v for p,v in pins.items()),'Current build/reference sources required')
    require(all(sha(p)==v for p,v in prior['imageSha256'].items()),'Exact tested simulated binaries required')
    images={Path(p).name:Path(p) for p in prior['imageSha256']}
    require(set(images)=={'sl3_activation_asio_tests.exe','sl3_activation_session_fixture.dll','sl3_broker_controller_unmeasured_simulated.exe','sl3_device_session_fixture.exe','UsbDkHelper.dll10'},'Closed simulated image set required')
    host=build_path.parent/'Release/sl3_com_registration_host.exe';require(sha(host)==build['executableSha256'],'COM host image changed')
    s=runpy.run_path(str(ROOT/'scripts/asio-install-journal.py'))['stage_module']();require(not s.elevated(),'Ordinary-token fixture required')
    r=runpy.run_path(str(ROOT/'scripts/asio-registry.py'));b=runpy.run_path(str(ROOT/'scripts/prepare-asio-deployment.py'))
    source_pins={p:sha(ROOT/p) for p in ['scripts/test-com-registration-activation.py','scripts/asio-registry.py','scripts/prepare-asio-deployment.py','scripts/asio-file-stage.py','scripts/asio-install-journal.py']}
    identity=uuid.uuid4().hex;namespace='Software\\SL3RebuildComActivationTests\\'+identity
    folder=ROOT/'analysis'/('com-registration-'+identity);folder.mkdir();dll_dir=folder/'registered fixture é';dll_dir.mkdir()
    dll=dll_dir/'sl3_asio.dll';dll.write_bytes(images['sl3_activation_session_fixture.dll'].read_bytes());require(sha(dll)==sha(images['sl3_activation_session_fixture.dll']),'Byte-identical copied fixture required')
    records=b['registry_entries'](dll_dir,identity*2);access=winreg.KEY_ALL_ACCESS|winreg.KEY_WOW64_64KEY
    (dll_dir/'fixture.manifest').write_text('<?xml version="1.0" encoding="utf-8"?><assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0"><assemblyIdentity type="win32" name="SL3.Owned.ComFixture" version="1.0.0.0" processorArchitecture="amd64"/><file name="sl3_asio.dll"><comClass clsid="'+b['CLSID']+'" threadingModel="Both"/></file></assembly>',encoding='utf-8')
    def live():
        return {h:[r['snapshot'](root,x['key']) for x in records] for h,root in [('machine',winreg.HKEY_LOCAL_MACHINE),('user',winreg.HKEY_CURRENT_USER)]}
    before=live();outcomes=[]
    production_bundle=Path(sys.argv[5]).absolute();production_expected=sys.argv[6]
    production_manifest,production_payload=b['capture_bundle'](production_bundle,production_expected);b['verify_payloads'](production_manifest,production_payload)
    require(production_manifest['schema']=='sl3.deployment-bundle.v2','Reviewed on-demand production package required')
    production_dir=folder/'production enumeration é';production_dir.mkdir()
    for name,raw in production_payload.items():(production_dir/name).write_bytes(raw)
    (production_dir/'fixture.manifest').write_bytes((dll_dir/'fixture.manifest').read_bytes())
    def scenario(name,mode,selected_dll=None):
        selected_dll=selected_dll or dll
        here=folder/name;here.mkdir();owners=here/'owners';owners.mkdir()
        worker=images['sl3_device_session_fixture.exe'];helper=images['UsbDkHelper.dll10'];controller=images['sl3_broker_controller_unmeasured_simulated.exe']
        timing=here/'timing.conf';timing.write_text('SL3-ASIO-DIAGNOSTIC-TIMING-1\nworker_sha256='+sha(worker)+'\nhelper_sha256='+sha(helper)+'\nrate_hz=44100\nbuffer_frames=128\n',encoding='utf-8')
        config=here/'worker.conf';config.write_text('SL3-ASIO-CONFIG-1\nworker='+str(worker)+'\nworker_sha256='+sha(worker)+'\nhelper='+str(helper)+'\ntiming_record='+str(timing)+'\ntiming_record_sha256='+sha(timing)+'\n',encoding='utf-8')
        entry=here/'activation.conf';entry.write_text('SL3-ASIO-ACTIVATION-1\ncontroller='+str(controller)+'\ncontroller_sha256='+sha(controller)+'\ninput='+str(config)+'\ninput_sha256='+sha(config)+'\nstartup_timeout_ms=15000\nstartup_failure_grace_ms=5000\nlifetime_ms=60000\n',encoding='utf-8')
        env=dict(os.environ);env.pop('SL3_ASIO_PRIVATE_TRACE',None)
        child=subprocess.run([str(host),'--run',mode,namespace+'\\SOFTWARE\\Classes',str(selected_dll),str(entry),str(owners)],env=env,capture_output=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
        (here/'stdout.txt').write_bytes(child.stdout);(here/'stderr.txt').write_bytes(child.stderr)
        require(child.returncode==0,'COM fixture failed: '+child.stderr.decode('utf-8',errors='replace'))
        result=json.loads(child.stdout);require(result['schema']=='sl3.com-registration-result.v1' and result['nativeDeviceAccess'] is False,'Typed COM result required')
        retirements=[]
        if mode=='manifest':
            require(result['coCreateInstances']==2 and result['callbacksCompleted']>=16 and result['simulatedOnly'] is True,'Two registered instances must make actual callback progress')
            require(sorted(p.name for p in owners.iterdir())==['session-1','session-2'],'Exactly two lazy owners required')
            for session in sorted(owners.iterdir()):
                record=json.loads((session/'result.json').read_bytes());require(record['kind']=='simulated' and record['successful'] is True and record['nativeDeviceAcquired'] is False and record['terminationRequested'] is False and all(record[k] is True for k in ('ioRetiredVerified','deviceReleasedVerified','processExited','jobEmpty')),'Normal typed simulated retirement required')
                retirements.append({'session':session.name,'resultSha256':sha(session/'result.json'),'ioRetiredVerified':True,'processExited':True,'jobEmpty':True})
        elif mode=='production-enumeration':
            require(result['productionEnumerationOnly'] is True and result['coCreateInstances']==2 and result['callbacksCompleted']==0 and result['simulatedOnly'] is False and not list(owners.iterdir()),'Production COM enumeration must remain idle')
        else:require(result['classNotRegistered'] is True and result['fixtureLoaded'] is False and not list(owners.iterdir()),'Absent registration must remain idle')
        outcomes.append({'scenario':name,'passed':True,'hostResult':result,'retirements':retirements});print(json.dumps({'scenario':name,'passed':True}),flush=True)
    def cleanup(path):
        require(path==namespace or path.startswith(namespace+'\\'),'Exact private cleanup boundary')
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path,0,access) as key:children=[winreg.EnumKey(key,n) for n in range(winreg.QueryInfoKey(key)[0])]
        for child in children:cleanup(path+'\\'+child)
        winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER,path,winreg.KEY_WOW64_64KEY,0)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,'Software\\SL3RebuildComActivationTests',0,access):pass
    with r['create_new'](winreg.HKEY_CURRENT_USER,namespace) as marker:winreg.SetValueEx(marker,'SL3TestOwner',0,winreg.REG_SZ,identity)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,namespace,0,access) as root:
            for name in ('SOFTWARE\\Classes\\CLSID','SOFTWARE\\ASIO'):
                with winreg.CreateKeyEx(root,name,0,access):pass
            scenario('before-registration','absent')
            for item in records:
                with r['create_new'](root,item['key']) as key:
                    for name,value in item['strings'].items():winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
            for item in records:require(r['snapshot'](root,item['key'])['values']==r['model'](item)['values'],'Actual registration values must match installer generator')
            scenario('private-registry-alias-not-activation-proof','registry-probe')
            scenario('registration-free-com-reopen','manifest')
            with winreg.OpenKey(root,records[1]['key'],0,access) as key:winreg.SetValueEx(key,'',0,winreg.REG_SZ,str(production_dir/'sl3_asio.dll'))
            scenario('exact-production-com-idle-enumeration','production-enumeration',production_dir/'sl3_asio.dll')
            with winreg.OpenKey(root,records[1]['key'],0,access) as key:winreg.SetValueEx(key,'',0,winreg.REG_SZ,records[1]['strings'][''])
            for item in (records[1],records[0],records[2]):winreg.DeleteKeyEx(root,item['key'],winreg.KEY_WOW64_64KEY,0)
            scenario('after-registration-removal','absent')
    finally:cleanup(namespace)
    require(live()==before,'Live class/ASIO registrations must remain unchanged')
    try:winreg.OpenKey(winreg.HKEY_CURRENT_USER,namespace,0,access)
    except FileNotFoundError:pass
    else:raise ValueError('Private registry namespace remains')
    require(all(sha(ROOT/p)==v for p,v in source_pins.items()) and all(sha(ROOT/p)==v for p,v in build['inputs'].items()),'Diagnostic sources changed')
    require(all(sha(production_dir/name)==hashlib.sha256(raw).hexdigest() for name,raw in production_payload.items()),'Exact production package copy changed')
    report={'schema':'sl3.com-registration-activation-tests.v1','passed':True,'outcomes':outcomes,'sourceSha256':source_pins,'buildSha256':sha(build_path),'hostSha256':sha(host),'simulatedReferenceSha256':sha(reference),'fixtureDllSha256':sha(dll),'activationManifestSha256':sha(dll_dir/'fixture.manifest'),'registrationRecordsFromInstallerGenerator':True,'processLocalHkcrOverride':True,'privateNamespaceRemoved':True,'liveRegistrationsUnchanged':True,'productionInstallationPerformed':False,'seratoLaunched':False,'nativeDeviceAccess':False,'simulatedProviderConfiguredThroughTestExport':True,'installedRegistryActivationValidated':False,'registrationFreeComActivationValidated':True}
    report.update({'productionBundleManifestSha256':production_expected,'productionDllSha256':sha(production_dir/'sl3_asio.dll'),'productionAsioInitCalled':False,'productionEnumerationPassed':True})
    output=folder/'result.json';output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'passed':True,'scenarios':len(outcomes),'report':str(output)},indent=2))


if __name__=='__main__':main()
