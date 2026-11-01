"""Assess the preserved attended components; never upgrade the failed wrapper."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT/'tests/results/local/user-controls-attended-20261031-120514'
CAPSULE = ROOT/'artifacts/build/checkpoints/attended-controls-20261031-120514'


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    base = load('component_base', ROOT/'scripts/validate-controls-host-probe.py')
    user = load('component_tokens', ROOT/'scripts/validate-controls-user-probe.py')
    state = load('component_states', ROOT/'scripts/validate-usb-state-capture.py')
    require = base.require
    record = read(CONTEXT/'run.json')
    require(record['completed'] is False and record['probeExitCode'] == 0, 'Original outcome changed')
    require(sha(CONTEXT/'run.json') == sha(CAPSULE/'physical-records/run.json'), 'Original failed record changed')
    for name, expected in record['runnerInputs'].items():
        require(sha(CAPSULE/'scripts'/name) == expected.lower(), 'Attended runtime archive changed: '+name)
    require(sha(CAPSULE/'artifacts/build/native/native-build-Release.json') == record['buildManifestSha256'].lower(),
            'Attended build archive changed')
    for binary, expected in [('sl3_usbdk.exe', record['workerSha256']), ('sl3_host_probe.exe', record['probeSha256'])]:
        require(sha(CAPSULE/'artifacts/build/native/Release'/binary) == expected.lower(), 'Attended native image changed')
    probe = base.probe(CONTEXT/'probe', record['workerSha256'])
    user.tokens(record, probe['nativeJournal']['workerPid'])
    require(probe['probeRecordSha256'] == record['probeRecordSha256'].lower(), 'Native record binding differs')
    before, after = read(CONTEXT/'before-state.json'), read(CONTEXT/'after-state.json')
    for label in ('before', 'after'):
        require(sha(CONTEXT/(label+'-state.json')) == record[label+'StateSha256'].lower(), 'State binding differs')
    require(before['secureBoot'] is after['secureBoot'] is True and
            base.physical.state_contract(before) == base.physical.state_contract(after), 'Selected recovery differs')
    capture = read(CONTEXT/'trace/capture.json')
    require(sha(CONTEXT/'trace/capture.json') == record['traceRecordSha256'].lower(), 'Capture record changed')
    require(sha(CONTEXT/'trace'/capture['files'][0]['name']) == record['etlSha256'].lower(), 'Source ETL changed')
    require(0 < (CONTEXT/'events.xml').stat().st_size <= 512*1024*1024 and
            sha(CONTEXT/'events.xml') == record['traceStats']['xmlSha256'], 'Source XML changed or exceeds bound')
    require(sha(CONTEXT/'trace/state-observer.ndjson') == capture['stateObserver']['outputSha256'].lower(), 'Live rows changed')
    _, _, values = state.observations(CONTEXT/'trace/state-observer.ndjson', capture['session'], 60,
                                     capture['stateObserver']['process']['pid'])
    ns = '{http://schemas.microsoft.com/win/2004/08/events/event}'
    expected, header, count = [], None, 0
    for _, event in ET.iterparse(CONTEXT/'events.xml', events=['end']):
        if event.tag != ns+'Event':
            continue
        count += 1
        require(count <= 2_000_000, 'XML exceeds bounded event count')
        system = event.find(ns+'System')
        data = {d.get('Name'): (d.text or '').strip() for d in event.findall(ns+'EventData/'+ns+'Data')}
        if header is None:
            header = data
        if system.find(ns+'Provider').get('Guid', '').lower() == '{ac52ad17-cc01-4f85-8df5-4dce4333c99b}':
            event_id = int(system.findtext(ns+'EventID'))
            if event_id in (110,111):
                expected.append((event_id, int(system.findtext(ns+'Task')), int(system.find(ns+'Execution').get('ProcessID')),
                                 state.filetime(system.find(ns+'TimeCreated').get('SystemTime')),
                                 *[int(data[k],0) for k in ('fid_UsbDevice','fid_Context','fid_StartIndex','fid_State','fid_Event','fid_Depth')]))
        event.clear()
    require(count == record['traceStats']['eventCount'] and header['EventsLost'] == header['BuffersLost'] == '0'
            and header['SessionNameString'] == capture['session'], 'Header/count binding differs')
    size, written, maximum = (int(header[k]) for k in ('BufferSize','BuffersWritten','MaxFileSize'))
    require(int(header['LogFileMode'],0)&2 and written*size > maximum*1024*1024, 'Expected circular overwrite evidence')
    live, source = Counter(values), Counter(expected)
    require(not source-live and len(values) == 514 and len(expected) == 21 and sum((live-source).values()) == 493,
            'Retained state-row agreement differs')
    result = {'scope': 'Independent preserved component assessment; original wrapper failed and remains inadmissible',
              'originalRunSha256': sha(CONTEXT/'run.json'), 'endToEndPassed': False,
              'normalTokenControlComponentPassed': True, 'rateHz': probe['rateHz'], 'rawControls': probe['rawControls'],
              'workerSha256': record['workerSha256'].lower(), 'normalParentProbeWorkerTokensVerified': True,
              'selectedRecoveryMatches': True, 'secureBootBeforeAfter': True,
              'traceEventsRetained': count, 'reportedEventsLost': 0, 'reportedBuffersLost': 0,
              'circularOverwrite': {'bufferBytes':size, 'buffersWritten':written, 'totalBufferBytesWritten':size*written,
                                    'maximumFileBytes':maximum*1024*1024},
              'stateRows': {'live':514, 'retainedInFile':21, 'retainedRowsMatchExactly':True, 'missingFromFile':493},
              'fullWindowVerified':False, 'automaticPrerequisiteAdmission':False,
              'audioTested':False, 'currentSeratoIntegrationVerified':False,
              'sources': {str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in
                          (Path(__file__), ROOT/'scripts/validate-controls-host-probe.py',
                           ROOT/'scripts/validate-controls-user-probe.py', ROOT/'scripts/validate-usb-state-capture.py')}}
    (ROOT/'docs/evidence/attended-controls-components-20261031.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Verified current-worker normal-token control component and independently explained circular overwrite; wrapper remains failed')


if __name__ == '__main__':
    main()
