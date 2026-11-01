"""Bind actual passive ETL replay checks and the limited cached-status finding."""
import importlib.util
import json
from pathlib import Path

import capstone
import pefile

ROOT=Path(__file__).resolve().parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


symbols=module('observer_hub_symbols',ROOT/'scripts/export-usbhub3-state-symbols.py')
require,sha=symbols.require,symbols.sha


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    folder=ROOT/'artifacts/build/usb-state-observer';builds={}
    expected={'scripts/native/usb-state-observer/main.cpp','scripts/native/usb-state-observer/CMakeLists.txt',
              'scripts/build-usb-state-observer.ps1','scripts/test-usb-state-observer.py','scripts/export-reopen-usb-timeline.py'}
    for config in ('Release','Debug'):
        path=folder/f'observer-build-{config}.json';build=read(path);exe=folder/config/'sl3_usb_state_observer.exe'
        require(set(build['inputs'])==expected and all(sha(ROOT/name)==value.lower() for name,value in build['inputs'].items()),'Observer source inputs changed')
        require(build['nativeDeviceOperation'] is False and build['livePositiveValidated'] is False and build['readinessAdmission'] is False,'Unsupported observer acceptance claim')
        require(sha(exe)==build['executableSha256'].lower(),'Observer binary changed')
        test_path=Path(build['testRecord']);require(sha(test_path)==build['testRecordSha256'].lower(),'Actual replay test evidence changed')
        result=read(test_path)
        require(result['executableSha256']==sha(exe) and result['testScriptSha256']==sha(ROOT/'scripts/test-usb-state-observer.py') and
                result['all585StateRowsMatchXmlIncluding100nsTimestamps'] is True and result['noOverwriteVerified'] is True and
                result['livePositiveValidated'] is False and result['readinessAdmission'] is False,'Replay verification scope differs')
        require(result['summary']['successful'] is True and result['summary']['eventsSeen']==14368 and
                result['summary']['stateRecords']==585 and result['summary']['sourceLossCountersComplete'] is True,'Actual completed ETL read differs')
        require(result['producer']['tokenQueried'] is True and result['producer']['elevated'] is False and
                result['producer']['elevationType']==3,'Actual saved-file replay was not observed with a normal token')
        require(sha(Path(result['outputDirectory'])/'replay.ndjson')==result['replaySha256'],'Saved native observation output changed')
        require({x['case'] for x in result['negativeCases']}=={'missing-file','invalid-session','duration-zero','duration-long','missing-session','malformed-etl'} and
                all(x['exitCode']==1 for x in result['negativeCases']),'Actual negative case inventory differs')
        builds[config]={'manifestSha256':sha(path),'executableSha256':sha(exe),'testRecordSha256':sha(test_path),
                        'replaySha256':result['replaySha256'],'summary':result['summary'],'producer':result['producer'],'negativeCases':result['negativeCases']}
    evidence={'scope':'Actual normal-token saved-ETL replay in Release/Debug; live positive subscription and readiness admission unverified',
              'builds':builds,'sourceInputs':build['inputs'],'independentOfProductionAsioBuild':True,
              'livePositiveValidated':False,'readinessAdmission':False,
              'limits':['Native rows exactly match the bound XML, including 100 ns times, but do not prove physical identity or loaded-image semantics.',
                        'Only owned consumer handles are closed; this tool cannot attest or stop source-session cleanup.',
                        'The live source must separately enable real-time delivery and grant consumer access.',
                        'Live header loss snapshots are incomplete; the full source ETL/loss validator remains authoritative.',
                        'A missing session may create a failed diagnostic output after OpenTrace succeeds; it never establishes a valid observation.',
                        'The live timeout requests consumer closure; already queued buffers can drain afterward. A supervising process still owns its deadline.']}
    (ROOT/'docs/evidence/usb-state-observer-build.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    data=symbols.inspect(symbols.REFERENCE/'USBHUB3.SYS',symbols.REFERENCE/'usbhub3.pdb',symbol_masks=('HUB*',),
                         layout_names=('_PORT_CONTEXT','_DEVICE_CONTEXT'),enum_names=('_USB_CONNECTION_STATUS',))
    data['exporterSha256']=sha(ROOT/'scripts/export-usbhub3-state-symbols.py')
    query_path=ROOT/'analysis/usbhub3-query-symbols.json';query_path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    port=next(x for x in data['layouts'] if x['name']=='_PORT_CONTEXT')
    status=next(x for x in port['members'] if x['name']=='ConnectionStatus')
    require(status['offset']==0x590 and status['typeIndex']==data['enums']['_USB_CONNECTION_STATUS']['typeIndex'],'Port cached-status layout differs')
    require(any(x=={'name':'DeviceConnected','value':1} for x in data['enums']['_USB_CONNECTION_STATUS']['members']),'Connected value differs')
    pe=pefile.PE(str(symbols.REFERENCE/'USBHUB3.SYS'));engine=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);functions=[]
    checks={'HUBFDO_IoctlGetNodeConnectionInfo':{0xe568:'mov ecx, dword ptr [rcx + 0x590]',0xe56e:'mov dword ptr [rax + 0x1f], ecx'},
            'HUBPDO_CreatePdo':{0x800f2:'mov rax, qword ptr [rdi + 8]',0x800f6:'mov dword ptr [rax + 0x590], 1'},
            'HUBDSM_Stopped':{0x8a30:'mov eax, 0x3e8',0x8a35:'ret '}}
    for name,instructions in checks.items():
        rows=[x for x in data['symbols'] if x['name']==name];require(len(rows)==1,'Missing unique status-query symbol')
        bounds=[e.struct for e in pe.DIRECTORY_ENTRY_EXCEPTION if e.struct.BeginAddress==rows[0]['rva']]
        require(len(bounds)==1,'Function boundary missing');start,end=bounds[0].BeginAddress,bounds[0].EndAddress
        raw=pe.get_data(start,end-start);decoded=[{'rva':i.address,'text':i.mnemonic+' '+i.op_str} for i in engine.disasm(raw,start)]
        text={x['rva']:x['text'] for x in decoded};require(all(text.get(rva)==value for rva,value in instructions.items()),'Cached-status dataflow differs')
        functions.append({'name':name,'startRva':start,'endRva':end,'instructions':decoded})
    disassembly=ROOT/'analysis/usbhub3-connection-disassembly.json';disassembly.write_text(json.dumps(functions,indent=2)+'\n',encoding='utf-8')
    result={'scope':'Inspected-image cached connection-status query path; not a ready-to-redirect predicate or a physical query result',
            'imageSha256':data['imageSha256'],'pdbSha256':data['pdbSha256'],'querySymbolsSha256':sha(query_path),
            'disassemblySha256':sha(disassembly),'symbolInspectorSha256':sha(ROOT/'scripts/export-usbhub3-state-symbols.py'),
            'exporterSha256':sha(Path(__file__)),'portConnectionStatusOffset':0x590,'copiedOutputOffset':0x1f,
            'cachedStatusEnum':'_USB_CONNECTION_STATUS','deviceConnectedValue':1,'sourceSetsConnectedDuringPdoCreation':True,
            'queryPathCopiesCachedStatus':True,'genericConnectedAcceptedAsReadiness':False,
            'limits':['The identified getter path copies a cached port field, not the DSM state.',
                      'The creation path assigns DeviceConnected; the small Stopped entry itself has no field update.',
                      'This is not an exhaustive write/call-graph analysis, nor a proof that the cached value is identical in every runtime state.',
                      'No hub IOCTL was sent and normal-token hub query permissions were not tested.',
                      'The current image/PDB identity does not bind the driver loaded in an earlier trace.',
                      'This does not rule out every supported normal-user observation API or establish a need for a privileged broker.']}
    (ROOT/'docs/evidence/usbhub3-connection-status.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Verified passive Release/Debug replay and cached-status counterexample; no live readiness or physical device acceptance')


if __name__=='__main__':main()
