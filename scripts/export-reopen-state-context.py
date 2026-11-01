"""Correlate a saved failed redirect with version-qualified USBHUB3 state names."""
from datetime import datetime
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


symbols=module('reopen_hub_symbols',ROOT/'scripts/export-usbhub3-state-symbols.py')
timeline=module('reopen_hub_timeline',ROOT/'scripts/export-reopen-usb-timeline.py')
require,sha,read=timeline.require,timeline.digest,timeline.read


def main():
    # Revalidate the original run, observed journal prefixes, ETL/XML and event count.
    timeline.main()
    old_path=ROOT/'docs/evidence/reopen-usb-timeline-20261030.json';old=read(old_path)
    reference=symbols.REFERENCE;data=symbols.inspect(reference/'USBHUB3.SYS',reference/'usbhub3.pdb')
    data['exporterSha256']=sha(ROOT/'scripts/export-usbhub3-state-symbols.py')
    symbol_path=ROOT/'analysis/usbhub3-state-symbols.json'
    symbol_path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    acquisition=read(reference/'acquisition.json');host_path=ROOT/'analysis/usbhub3-installed-image.json';host=read(host_path)
    require(acquisition['imageSha256']==host['sha256'].lower()==data['imageSha256'] and host['signatureStatus']=='Valid',
            'Observed installed image differs from copied image')
    expected_url=f"https://msdl.microsoft.com/download/symbols/usbhub3.pdb/{data['rsds']['guid']}{data['rsds']['age']:X}/usbhub3.pdb"
    require(acquisition['pdbUrl']==expected_url and acquisition['pdbSha256']==data['pdbSha256'],'Symbol acquisition differs')
    source=read(reference/'microsoft-pdb-validation.json')
    require(source['commit']=='1bdc5900390b6edec02e7b6a1b6e7bdef6e76df1' and source['sha256']==
            sha(reference/'microsoft-pdb-validation.cpp')=='a6f274f9b47abd875f2dbd2716c273bec7846be3d41e87c14fa815710896c898',
            'PDB-validation source differs')
    negative_path=ROOT/'analysis/usbhub3-symbol-negatives.json';negative=read(negative_path)
    require(negative['sourceSha256']==sha(ROOT/'scripts/export-usbhub3-state-symbols.py') and
            {x['case'] for x in negative['cases']}=={'wrong-guid','wrong-age','wrong-image-hash','bad-pdb'} and
            len(negative['cases'])==4 and all(x['exitCode']==1 and x['outputCreated'] is False for x in negative['cases']),
            'Actual negative CLI evidence differs')
    folder=ROOT/'tests/results/local/inspect-reopen-staged-20261030-02'
    rows,count=timeline.parse(folder/'events.xml');require(count==old['traceStats']['eventCount'],'Saved trace count differs')
    children=set(old['childObjects']);target=[r for r in rows if r['eventId']==110 and r['data'].get('fid_UsbDevice') in children]
    dsm=[r for r in target if timeline.number(r['data']['fid_StartIndex'])==4000]
    states={x['value']:x['name'] for x in data['enums']['_DSM_STATE_ETW']['members']}
    events={x['value']:x['name'] for x in data['enums']['_DSM_EVENT']['members']}
    decoded=[]
    for row in dsm:
        state,event=timeline.number(row['data']['fid_State']),timeline.number(row['data']['fid_Event'])
        require(state in states and event in events,'Unknown saved DSM state/event under current mapping')
        decoded.append({**row,'stateNameForInspectedImage':states[state],'eventNameForInspectedImage':events[event]})
    unhandled=[r for r in old['timeline'] if r['eventId']==111 and r['time']>=old['secondCycleObservedUtc']]
    require(len(unhandled)==1,'Expected one failed-cycle unhandled event');unhandled=unhandled[0];fields=unhandled['data']
    require(timeline.number(fields['fid_StartIndex'])==4000 and timeline.number(fields['fid_State'])==0x1080 and
            timeline.number(fields['fid_Event'])==0xfab,'Saved unhandled event differs')
    final=[r for r in decoded if r['data']['fid_UsbDevice']==fields['fid_UsbDevice'] and r['data']['fid_Context']==fields['fid_Context']]
    after=[r for r in final if r['time']>unhandled['time']]
    expected=['DsmStateEtwStoppedEnumerated','DsmStateEtwCheckIfDeviceCanBeDisabledOnDriverNotFound',
              'DsmStateEtwDisablingDeviceInControllerOnStartTimeout','DsmStateEtwDisablingPortOnStartTimeout','DsmStateEtwStopped']
    require([r['stateNameForInspectedImage'] for r in after]==expected,'Post-request start-timeout sequence differs')
    previous=[r for r in final if r['time']<unhandled['time'] and r['stateNameForInspectedImage']==expected[0] and timeline.number(r['data']['fid_Depth'])==0]
    require(previous,'Missing preceding top-level stopped-enumerated transition')
    elapsed=(datetime.fromisoformat(after[1]['time'])-datetime.fromisoformat(previous[-1]['time'])).total_seconds()
    require(9.99<=elapsed<=10.01 and after[1]['eventNameForInspectedImage']=='DsmEventTimerFired','Observed timeout interval differs')
    entries=data['imageSemantics']['stateEntries']
    require(entries[1]['topLevelClientCyclePresent'] is True and any(t['eventName']=='DsmEventClientRequestCycle' and
            t['targetName']=='DsmStateRequestPortCycle' for t in entries[1]['transitions']),'Stopped cycle route differs')
    decoded_path=ROOT/'analysis/reopen-dsm-decoded.json'
    decoded_path.write_text(json.dumps({'scope':'Saved numeric DSM events labelled using inspected current-image enums; historical image identity is not captured',
         'symbolsSha256':sha(symbol_path),'xmlSha256':old['xmlSha256'],'events':decoded},indent=2)+'\n',encoding='utf-8')
    result={'scope':'Offline version-qualified interpretation of the saved failed reopen; candidate startup mechanism, no repaired or new hardware result',
            'timelineSha256':sha(old_path),'symbolsSha256':sha(symbol_path),'decodedDsmSha256':sha(decoded_path),
            'symbolExporterSha256':sha(ROOT/'scripts/export-usbhub3-state-symbols.py'),'contextExporterSha256':sha(Path(__file__)),
            'installedImageObservationSha256':sha(host_path),'installedImageVersion':host['fileVersion'],
            'negativeCliChecksSha256':sha(negative_path),
            'imageSha256':data['imageSha256'],'pdbSha256':data['pdbSha256'],'rsds':data['rsds'],'pdbIdentity':data['pdbIdentity'],
            'pdbUrl':expected_url,'pdbValidationSource':source,'dbghelpSha256':data['dbghelpSha256'],
            'historicalLoadedImageIdentityCaptured':False,'inspectedImagePdbMatchVerified':True,
            'stateFieldIsEntryEtwName':data['imageSemantics']['stateFieldIsEntryEtwName'],
            'eventDescriptor':{'rva':data['imageSemantics']['eventDescriptorRva'],'eventId':111,'task':13},
            'selectedStates':[{k:e[k] for k in ('name','internalValue','etwValue','etwName','entryRva','topLevelClientCyclePresent')} for e in entries],
            'unhandledEvent':{**unhandled,'stateNameForInspectedImage':states[0x1080],'eventNameForInspectedImage':events[0xfab]},
            'targetStateEvents':len(target),'decodedDsmEvents':len(decoded),'otherStateNamespaces':len(target)-len(decoded),
            'lastTopLevelStoppedEnumeratedBeforeCycle':previous[-1],'postCycleTransitions':after,
            'secondsToObservedStartTimeout':elapsed,'restingDeviceProblemBeforeRun':read(folder/'before-state.json')['devices'][0]['device']['Problem'],
            'limits':['The old capture did not bind the loaded USBHUB3 image. Current-image labels are conditional when applied to it.',
                      'ETW state values differ from internal state values; direct internal-enum lookup would mislabel this event.',
                      'Six other target-child state events use another namespace and are not labelled as DSM events.',
                      'The inspected stopped-enumerated top-level table lacks a cycle transition; this is not an exhaustive proof of every substate path.',
                      'The decoded sequence is consistent with incomplete original-driver startup; code 39 alone does not prove the entire cause.',
                      'A ten-second observed timeout is not a universal delay policy or a verified recovery barrier.',
                      'The exact outstanding UsbDk wait, supported normal-token state observation and repeated-open repair still require attended evidence.',
                      'No USB operation, kernel debugging, driver/security modification, ASIO deployment or current Serato connection occurred.']}
    (ROOT/'docs/evidence/reopen-state-context-20261030.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(f'Verified {len(decoded)} saved DSM labels, ETW/internal namespace distinction and observed {elapsed:.6f}s start-timeout sequence; historical image binding remains unproven')


if __name__=='__main__':main()
